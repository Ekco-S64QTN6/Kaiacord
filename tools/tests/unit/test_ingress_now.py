"""!download and !youtube file their document at once."""
import asyncio

import pytest
import importlib.util
import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock

import discord


def _load_ingress_processor():
    spec = importlib.util.spec_from_file_location(
        "process_ingress_under_test", "tools/maintenance/process_ingress.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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



def test_ingress_processor_lock_is_shared_across_independent_file_descriptors(tmp_path, monkeypatch):
    import fcntl
    import threading

    processor = _load_ingress_processor()
    lock_path = tmp_path / "ingress_process.lock"
    monkeypatch.setattr(processor, "_process_lock_path", lambda: lock_path)
    entered = threading.Event()
    finished = threading.Event()

    def contender():
        with processor._processing_lock():
            entered.set()
        finished.set()

    with open(lock_path, "a+", encoding="utf-8") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
        worker = threading.Thread(target=contender, daemon=True)
        worker.start()
        assert not entered.wait(timeout=0.1), "second ingress pass entered while the first held the OS lock"
        fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
        assert entered.wait(timeout=2.0), "second ingress pass did not enter after lock release"
        assert finished.wait(timeout=2.0)
        worker.join(timeout=2.0)


def test_cli_main_holds_the_lock_around_the_entire_processor_run():
    import inspect

    processor = _load_ingress_processor()
    source = inspect.getsource(processor.main)
    assert "with _processing_lock()" in source
    assert "return _main_locked()" in source


def test_a_filing_that_runs_too_long_is_ended_with_its_group_and_reaped(monkeypatch):
    import os
    import subprocess as sp
    from utils.core import ingress
    started = {}
    real = asyncio.create_subprocess_exec

    async def fake_exec(*cmd, **kwargs):
        assert kwargs.get("start_new_session") is True          # a session of its own
        proc = await real(sys.executable, "-c", "import time; time.sleep(60)", **kwargs)
        started["proc"] = proc
        return proc

    monkeypatch.setattr(ingress.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(ingress, "TIMEOUT", 0.5)

    async def go():
        with pytest.raises(sp.TimeoutExpired):
            await ingress.run()
    asyncio.run(go())
    assert started["proc"].returncode is not None               # waited for, not left running
    with pytest.raises(ProcessLookupError):
        os.killpg(started["proc"].pid, 0)                        # and nothing of its group is left
