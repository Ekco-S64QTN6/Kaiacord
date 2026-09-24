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
