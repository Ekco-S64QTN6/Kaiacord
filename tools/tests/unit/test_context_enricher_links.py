"""A pasted link is resolved only as far as the person who pasted it could read."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.core import context_enricher as ce
from utils.core.context_enricher import ContextEnricher

GUILD = 1013809281251938364


def _setup(can_read: bool, channel_guild: int = GUILD):
    guild = MagicMock()
    guild.id = channel_guild
    member = object()
    guild.get_member = MagicMock(return_value=member)
    channel = MagicMock()
    channel.name = "kaia-opolis"
    channel.guild = guild
    channel.permissions_for = MagicMock(
        return_value=SimpleNamespace(view_channel=can_read, read_message_history=can_read))
    linked = MagicMock()
    linked.author.display_name = "Kaia"
    linked.content = "a draft waiting for moderation"
    channel.fetch_message = AsyncMock(return_value=linked)
    bot = MagicMock()
    bot.get_channel = MagicMock(return_value=channel)
    msg = MagicMock()
    msg.content = f"look https://discord.com/channels/{GUILD}/1462239450691145924/1552540842374332448"
    msg.author = SimpleNamespace(id=42)
    return ContextEnricher(bot), msg, channel


def test_a_link_the_requester_can_read_is_resolved():
    enricher, msg, _ = _setup(can_read=True)
    out = asyncio.run(enricher.resolve_message_links(msg))
    assert "a draft waiting for moderation" in out


def test_a_link_into_a_channel_the_requester_cannot_see_is_not():
    """Kaia reads with her own access; a private channel must not leak through her."""
    enricher, msg, channel = _setup(can_read=False)
    assert asyncio.run(enricher.resolve_message_links(msg)) == ""
    channel.fetch_message.assert_not_called()


def test_a_link_whose_guild_does_not_match_the_channel_is_not_resolved():
    enricher, msg, channel = _setup(can_read=True, channel_guild=999)
    assert asyncio.run(enricher.resolve_message_links(msg)) == ""


def test_discord_message_links_are_not_scraped_as_external_web_pages():
    enricher = ContextEnricher(MagicMock())
    links = [
        "https://discord.com/channels/1/2/3",
        "https://discordapp.com/channels/1/2/3",
        "https://ptb.discord.com/channels/1/2/3",
        "https://canary.discordapp.com/channels/1/2/3",
    ]
    for link in links:
        assert enricher.msg_link_pattern.search(link)
        assert enricher.external_link_pattern.findall(link) == []

    assert enricher.external_link_pattern.findall("read https://example.com/article") == [
        "https://example.com/article"
    ]


def test_trailing_punctuation_is_not_part_of_the_url():
    enricher = ContextEnricher(MagicMock())
    seen = []

    async def _scrape(url):
        seen.append(url)
        return f"Source: {url}\nok"
    enricher._scrape_single_url = _scrape
    msg = MagicMock()
    msg.content = "read this (https://example.com/a). and https://example.com/b."
    asyncio.run(enricher.resolve_external_urls(msg))
    assert seen == ["https://example.com/a", "https://example.com/b"]


def test_a_huge_page_is_read_only_up_to_the_cap():
    from aiohttp import web

    body = "<html><body>" + ("word " * 1_500_000) + "</body></html>"   # ~7.5 MB

    async def run():
        app = web.Application()
        app.router.add_get("/", lambda r: web.Response(text=body, content_type="text/html"))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            with patch.object(ce, "is_safe_url", return_value=True), \
                 patch.object(type(ce.config), "url_max_content_length", 10**9, create=True):
                enricher = ContextEnricher(MagicMock())
                return await enricher._scrape_single_url(f"http://127.0.0.1:{port}/")
        finally:
            await runner.cleanup()

    with patch.object(ce, "MAX_PAGE_BYTES", 50_000):
        out = asyncio.run(run())
    assert out.startswith("Source:")
    # Without the cap all ~1.5M words arrive; with it, what fits in 50 KB.
    assert 5_000 < out.count("word") < 12_000


def test_the_connector_refuses_a_name_that_resolves_to_a_private_address():
    """is_safe_url checks at receipt; the client resolves again at connect.
    The connector checks what it actually connects to."""
    from utils.core.sanitizer import public_only_connector

    async def run():
        conn = public_only_connector()
        try:
            with pytest.raises(OSError):
                await conn._resolver.resolve("localhost", 80)
        finally:
            await conn.close()
    asyncio.run(run())


def test_a_page_sent_in_pieces_is_read_whole():
    """content.read(n) returns whatever has arrived, up to n — a page came
    back as its first network chunk. The reader must keep reading."""
    from aiohttp import web

    async def handler(request):
        resp = web.StreamResponse(headers={"Content-Type": "text/html"})
        await resp.prepare(request)
        for i in range(20):
            await resp.write(f"<p>part{i} ".encode() + b"x" * 500 + b"</p>")
            await asyncio.sleep(0.01)
        await resp.write_eof()
        return resp

    async def run():
        app = web.Application()
        app.router.add_get("/", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            with patch.object(ce, "is_safe_url", return_value=True), \
                 patch.object(type(ce.config), "url_max_content_length", 10**9, create=True):
                return await ContextEnricher(MagicMock())._scrape_single_url(f"http://127.0.0.1:{port}/")
        finally:
            await runner.cleanup()

    out = asyncio.run(run())
    assert "part0" in out and "part19" in out


def test_a_linked_page_carries_no_length_instruction():
    """A 'keep your response brutally concise' directive rode after every page.
    Once pages stopped being cut at 2,000 characters it reached the model, and
    replies to links fell to a sentence or two."""
    enricher = ContextEnricher(MagicMock())

    async def _scrape(url):
        return f"Source: {url}\n" + "words " * 50
    enricher._scrape_single_url = _scrape
    msg = MagicMock()
    msg.content = "what do you think https://example.com/article"
    msg.embeds, msg.mentions, msg.reference = [], [], None
    with patch.object(type(ce.config), "url_fetching_enabled", True, create=True):
        out = asyncio.run(enricher.enrich_content(msg))
    assert "[LINKED_WEB_CONTENT]" in out
    assert "concise" not in out.lower() and "CORE_DIRECTIVE" not in out


def _embed(title, description, fields=()):
    return SimpleNamespace(title=title, description=description,
                           fields=[SimpleNamespace(name=n, value=v) for n, v in fields])


def test_a_reply_to_one_of_her_embeds_quotes_what_the_embed_says():
    """Her commands answer in an embed with no message text; "can you read
    this output" quoted her as "Kaia:" and nothing else, and she described
    the !help page as a corrupted transmission."""
    bot = MagicMock()
    bot.user.id = 7
    target = MagicMock(spec=["author", "content", "embeds", "mentions"])
    target.author = SimpleNamespace(id=7, display_name="Kaia")
    target.content = ""
    target.mentions = []
    target.embeds = [_embed("Kaia — help", "Pick a section.",
                            [("Music", "`!music` plays a live set")])]
    msg = MagicMock()
    msg.reference = SimpleNamespace(message_id=1, resolved=None)
    msg.channel.fetch_message = AsyncMock(return_value=target)
    enricher = ContextEnricher(bot)
    with patch.object(ContextEnricher, "_bot_message_recipient", return_value=None):
        out = asyncio.run(enricher.resolve_replies(msg))
    assert out.startswith("Kaia: ")
    assert "Pick a section." in out and "`!music` plays a live set" in out


def test_a_linked_message_carries_its_embeds_too():
    enricher, msg, channel = _setup(can_read=True)
    linked = channel.fetch_message.return_value
    linked.content = ""
    linked.embeds = [_embed("Draft", "a reply waiting for moderation")]
    out = asyncio.run(enricher.resolve_message_links(msg))
    assert "a reply waiting for moderation" in out


def test_a_quoted_embed_is_capped():
    enricher = ContextEnricher(MagicMock())
    big = SimpleNamespace(embeds=[_embed("t", "x" * 20_000)])
    assert len(enricher._with_embeds("hi", big)) < ce.QUOTED_EMBED_CHARS + 10





def _small_pdf(text="verified text from the PDF link"):
    """Build a minimal one-page PDF with extractable Helvetica text."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode("ascii"))
        data.extend(body)
        data.extend(b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(data)


def test_chat_link_extractor_reads_a_real_pdf_response():
    from aiohttp import web
    import aiohttp

    pdf = _small_pdf("verified text from an ordinary chat PDF link")

    async def run():
        app = web.Application()
        app.router.add_get("/report", lambda _r: web.Response(body=pdf, content_type="application/pdf"))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            with patch.object(ce, "is_safe_url", return_value=True), \
                 patch.object(ce, "public_only_connector", return_value=aiohttp.TCPConnector()), \
                 patch.object(type(ce.config), "url_max_content_length", 10000, create=True):
                return await ContextEnricher(MagicMock())._scrape_single_url(
                    f"http://127.0.0.1:{port}/report"
                )
        finally:
            await runner.cleanup()

    out = asyncio.run(run())
    assert out.startswith("Source: http://")
    assert "verified text from an ordinary chat PDF link" in out


def test_malformed_or_encrypted_pdfs_fail_closed():
    from io import BytesIO
    from pypdf import PdfWriter

    assert ce._extract_pdf_text(b"%PDF-1.4\nnot a valid document") == ""

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret")
    output = BytesIO()
    writer.write(output)
    assert ce._extract_pdf_text(output.getvalue()) == ""


def test_pdf_extraction_caps_pages_and_text(monkeypatch):
    import utils.core.context_enricher as module

    monkeypatch.setattr(module, "MAX_PDF_TEXT_CHARS", 12)
    assert len(module._extract_pdf_text(_small_pdf("this text is deliberately longer than twelve"))) <= 76


def test_pdf_parser_timeout_fails_closed(monkeypatch):
    import subprocess

    captured = {}

    def timeout(*args, **kwargs):
        captured.update(kwargs)
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(ce.subprocess, "run", timeout)
    assert ce._extract_pdf_text(_small_pdf()) == ""
    assert captured["timeout"] == ce.MAX_PDF_PARSE_TIMEOUT_SECONDS


def test_pdf_parser_uses_a_resource_limited_disposable_process(monkeypatch):
    from types import SimpleNamespace
    import sys

    captured = {}

    def run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout=b"bounded worker output")

    monkeypatch.setattr(ce.subprocess, "run", run)
    assert ce._extract_pdf_text(_small_pdf()) == "bounded worker output"
    assert captured["command"][:2] == [sys.executable, "-I"]
    assert captured["timeout"] == ce.MAX_PDF_PARSE_TIMEOUT_SECONDS
    assert captured["stdout"] == ce.subprocess.PIPE
    assert captured["stderr"] == ce.subprocess.DEVNULL
    assert "resource.setrlimit(resource.RLIMIT_AS" in ce._PDF_WORKER_SCRIPT
    assert "resource.setrlimit(resource.RLIMIT_CPU" in ce._PDF_WORKER_SCRIPT


def test_oversized_pdf_response_is_rejected_before_parser(monkeypatch):
    from types import SimpleNamespace

    # The worker itself also rejects oversized input; this guards the helper
    # independently from any caller's read cap.
    called = []
    monkeypatch.setattr(ce.subprocess, "run", lambda *a, **k: called.append(True))
    assert ce._extract_pdf_text(b"%PDF-" + b"x" * ce.MAX_PAGE_BYTES) == ""
    assert not called
