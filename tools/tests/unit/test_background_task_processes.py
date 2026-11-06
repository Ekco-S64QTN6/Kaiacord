"""Timeout and cancellation must not leave background maintenance children behind."""

import ast
import asyncio
import inspect
import signal

import pytest

from utils.core import background_tasks as bg


class _FakeProcess:
    pid = 12345

    def __init__(self, *, hangs_until_kill=False):
        self.calls = 0
        self.returncode = None
        self.started = asyncio.Event()
        self.hangs_until_kill = hangs_until_kill

    async def communicate(self):
        self.calls += 1
        self.started.set()
        if self.calls == 1 or (self.hangs_until_kill and self.calls == 2):
            await asyncio.Future()
        self.returncode = -signal.SIGKILL if self.calls == 3 else -signal.SIGTERM
        return b"reaped", b""


def _manager():
    manager = bg.CoreTaskManager.__new__(bg.CoreTaskManager)
    return manager


@pytest.mark.asyncio
async def test_timeout_terminates_then_kills_and_reaps_the_process_group(monkeypatch):
    manager = _manager()
    process = _FakeProcess(hangs_until_kill=True)
    signals = []
    monkeypatch.setattr(bg.os, "killpg", lambda pid, sig: signals.append((pid, sig)))

    out, err = await manager._communicate_or_kill(
        process,
        "test maintenance child",
        timeout=0.01,
        terminate_grace=0.01,
        kill_grace=0.1,
    )

    assert (out, err) == (b"reaped", b"")
    assert signals == [
        (process.pid, signal.SIGTERM),
        (process.pid, signal.SIGKILL),
    ]
    assert process.returncode == -signal.SIGKILL
    assert process.calls == 3


@pytest.mark.asyncio
async def test_task_cancellation_stops_and_reaps_its_subprocess(monkeypatch):
    manager = _manager()
    process = _FakeProcess()
    signals = []
    monkeypatch.setattr(bg.os, "killpg", lambda pid, sig: signals.append((pid, sig)))

    task = asyncio.create_task(
        manager._communicate_or_kill(
            process,
            "cancelled maintenance child",
            timeout=60,
            terminate_grace=0.1,
            kill_grace=0.1,
        )
    )
    await asyncio.wait_for(process.started.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert signals == [(process.pid, signal.SIGTERM)]
    assert process.returncode == -signal.SIGTERM
    assert process.calls == 2


def test_every_background_subprocess_uses_a_dedicated_session():
    source = inspect.getsource(bg.CoreTaskManager)
    tree = ast.parse(source)
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_subprocess_exec"
    ]

    assert len(calls) == 5
    assert all(
        any(
            kw.arg == "start_new_session"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is True
            for kw in call.keywords
        )
        for call in calls
    )


def test_scheduled_maintenance_runners_share_the_cancellable_cleanup_helper():
    methods = (
        bg.CoreTaskManager._make_metadata_enrichment_task,
        bg.CoreTaskManager._make_dream_curation_task,
        bg.CoreTaskManager._make_corpus_hygiene_task,
    )
    for method in methods:
        assert "self._communicate_or_kill(" in inspect.getsource(method)
