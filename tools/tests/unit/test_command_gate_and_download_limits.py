"""Commands answer to the shutdown guard and the rate limit; a download keeps no credentials (GitHub #366)."""
import asyncio
import importlib.util
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import utils.core.message_processor as mp
from utils.commands import download_handler as dl
from utils.core.message_processor import MessageProcessor
from utils.core.sanitizer import redact_url


def _processor(shutting_down=False, allowed=True):
    p = MessageProcessor.__new__(MessageProcessor)
    p.ctx = MagicMock()
    p.bot = MagicMock()
    p.config = MagicMock(ignored_users=[], blacklisted_channels=[], whitelisted_channels=[])
    p.bot_state = MagicMock(boot_complete=True)
    p.rate_limiter = MagicMock()
    p.rate_limiter.is_allowed.return_value = allowed
    p.shutdown_manager = SimpleNamespace(shutting_down=shutting_down)
    p._run_intelligence_pipeline = AsyncMock()
    return p


def _message(content):
    msg = MagicMock()
    msg.platform, msg.content = "discord", content
    msg.author.bot, msg.author.id, msg.author.name = False, 42, "tester"
    msg.channel.send = AsyncMock()
    return msg


@pytest.mark.parametrize("shutting_down, allowed, runs", [
    (False, True, True),
    (True, True, False),          # shutting down: no handler starts
    (False, False, False),        # over the rate limit: no handler starts
])
def test_a_command_is_dispatched_only_past_the_shutdown_guard_and_rate_limit(monkeypatch, shutting_down, allowed, runs):
    dispatched = AsyncMock(return_value=True)
    monkeypatch.setattr(mp, "dispatch_command", dispatched)
    p = _processor(shutting_down, allowed)
    asyncio.run(p._process_internal(_message("!download https://example.com/a.pdf")))
    assert dispatched.called is runs
    assert not p._run_intelligence_pipeline.called          # a refused command is never answered as chat


def test_ordinary_talk_does_not_spend_the_rate_limit_at_the_command_gate(monkeypatch):
    monkeypatch.setattr(mp, "dispatch_command", AsyncMock(return_value=False))
    p = _processor()
    p.bot.user.display_name, p.bot.user.id = "Kaia", 999
    msg = _message("nothing addressed to anyone")
    msg.mentions, msg.role_mentions = [], []
    asyncio.run(p._process_internal(msg))
    assert not p.rate_limiter.is_allowed.called


@pytest.mark.parametrize("url, kept, gone", [
    ("https://user:hunter2@files.example.com/a/report.pdf", "https://files.example.com/a/report.pdf", "hunter2"),
    ("https://s3.example.com/b/doc.pdf?X-Amz-Signature=abc123&X-Amz-Credential=AKIA&versionId=7",
     "versionId=7", "abc123"),
    ("https://api.example.com/export?access_token=tok_live&format=md", "format=md", "tok_live"),
    ("https://x.blob.example.net/c/d.txt?sv=2024&sig=s3cr3t&se=2026", "/c/d.txt", "s3cr3t"),
    ("https://example.com/page?utm_source=news&id=44#section", "utm_source=news&id=44", "#section"),
    ("https://example.com/doc?api_key=k123&apikey=k456&q=moon", "q=moon", "k123"),
])
def test_a_url_is_written_down_without_its_credentials(url, kept, gone):
    out = redact_url(url)
    assert kept in out and gone not in out and "k456" not in out


def _run_download(monkeypatch, url, convert):
    monkeypatch.setattr(dl, "is_safe_url", lambda u: True)
    monkeypatch.setattr(dl, "_download_and_convert", convert)
    msg = _message(f"!download {url}")
    msg.channel.typing = MagicMock(return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False)))
    msg.author.display_name = "tester"
    return msg


def test_one_person_runs_one_download_at_a_time(monkeypatch):
    started, release = [], asyncio.Event()

    async def slow(url, name, uid):
        started.append(url)
        await release.wait()
        raise dl.DownloadError("stopped by the test")

    async def scenario():
        first = _run_download(monkeypatch, "https://example.com/1", slow)
        second = _run_download(monkeypatch, "https://example.com/2", slow)
        task = asyncio.create_task(dl.handle_download_command(None, first, None))
        await asyncio.sleep(0.05)
        await dl.handle_download_command(None, second, None)          # refused while the first runs
        release.set()
        await task
        return second

    second = asyncio.run(scenario())
    assert started == ["https://example.com/1"]
    assert "one download at a time" in second.channel.send.call_args.kwargs["embed"].description
    assert dl._downloading == set()                                   # released on failure too


def test_the_handler_stages_and_logs_the_redacted_url():
    src = open("utils/commands/download_handler.py", encoding="utf-8").read()
    assert "'source_url': redact_url(url)" in src and "'source_url': url" not in src
    assert "Staged {redact_url(url)}" in src


def test_a_sidecar_staged_with_a_credential_is_filed_without_it(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("process_ingress_under_test", "tools/maintenance/process_ingress.py")
    ingress = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ingress)
    monkeypatch.setattr(ingress, "KB", tmp_path)
    monkeypatch.setattr(ingress, "derive_topic_and_title", lambda body, title, **k: ("Reference", title, "", []))
    staged = tmp_path / "_ingress"
    staged.mkdir()
    md = staged / "notes.md"
    md.write_text("# Notes\n\n" + "The moon keeps one face toward us. " * 30, encoding="utf-8")
    md.with_suffix(".meta.json").write_text(json.dumps({
        "title": "Notes", "document_type": "Article", "folder": "documents",
        "source_url": "https://alice:pw@files.example.com/notes.txt?token=SECRETTOKEN&page=2",
    }), encoding="utf-8")
    ok, msg = ingress.process_one(md)
    assert ok, msg
    [filed] = list((tmp_path / "documents").glob("*.md"))
    text = filed.read_text(encoding="utf-8")
    assert "https://files.example.com/notes.txt?page=2" in text
    assert "SECRETTOKEN" not in text and "alice" not in text and "pw@" not in text


@pytest.mark.parametrize("handler", ["utils/commands/youtube_handler.py", "utils/commands/download_handler.py"])
def test_a_staged_document_never_exists_without_its_sidecar(handler):
    """The hourly processor files whatever document it finds: the sidecar is written first, off the loop."""
    src = open(handler, encoding="utf-8").read()
    writes = [line.strip() for line in src.splitlines() if "write_atomic" in line and "import" not in line]
    assert len(writes) == 2 and ".meta.json" in writes[0] and ".meta.json" not in writes[1]
    assert all(w.startswith("await asyncio.to_thread(write_atomic") for w in writes)
