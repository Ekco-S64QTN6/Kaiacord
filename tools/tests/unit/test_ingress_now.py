"""!download and !youtube file their document at once."""
import asyncio
import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock

import discord


def _reply():
    reply = MagicMock()
    reply.embeds = [discord.Embed(title="📥  x")]
    reply.edit = AsyncMock()
    return reply


def test_the_reply_says_where_the_document_was_filed(monkeypatch, tmp_path):
    from utils.core import ingress

    async def fake_run(staged=None):
        return subprocess.CompletedProcess([], 0, "filed as documents/AI - A Title.md (812 words)\n", "")
    monkeypatch.setattr(ingress, "run", fake_run)
    reply = _reply()
    asyncio.run(ingress.file_now(tmp_path / "a.md", reply))
    footer = reply.edit.call_args.kwargs["embed"].footer.text
    assert footer.startswith("filed as documents/AI - A Title.md") and "five minutes" in footer


def test_a_failed_filing_is_left_for_the_hourly_pass(monkeypatch, tmp_path):
    from utils.core import ingress

    async def fake_run(staged=None):
        return subprocess.CompletedProcess([], 1, "", "FAIL a.md: too short after cleaning (12 words)")
    monkeypatch.setattr(ingress, "run", fake_run)
    reply = _reply()
    asyncio.run(ingress.file_now(tmp_path / "a.md", reply))
    assert "hourly" in reply.edit.call_args.kwargs["embed"].footer.text


def test_a_file_already_filed_by_the_hourly_pass_is_not_run_again(tmp_path):
    from utils.core import ingress
    result = asyncio.run(ingress.run(tmp_path / "gone.md"))
    assert result.returncode == 0 and result.stdout == "already filed"


def test_process_ingress_files_only_from_the_staging_folder(tmp_path):
    outside = tmp_path / "x.md"
    outside.write_text("hello", encoding="utf-8")
    r = subprocess.run([sys.executable, "tools/maintenance/process_ingress.py", "--file", str(outside)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and "Not a staged document" in r.stderr
    assert outside.read_text(encoding="utf-8") == "hello"


def test_a_video_already_filed_is_not_fetched_again(tmp_path, monkeypatch):
    from utils.commands import youtube_handler as yt
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "Transcript - The CUDA Moat is Gone.md").write_text(
        "Source: https://www.youtube.com/watch?v=abcdefghijk\n", encoding="utf-8")
    monkeypatch.setattr(yt, "TRANSCRIPTS", tmp_path / "t")
    monkeypatch.setattr(yt, "INGRESS", tmp_path / "missing")
    assert yt._already_have("abcdefghijk") == "The CUDA Moat is Gone"
    assert yt._already_have("zzzzzzzzzzz") is None
