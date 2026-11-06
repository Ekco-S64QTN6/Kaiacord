"""Timeout and cancellation must not leave background maintenance children behind."""

import ast
import asyncio
import inspect
import signal

import pytest

from utils.core import background_tasks as bg


class _FakeProcess:
    pid = 12345

    def __init__(self, *, exit_on_term=True, exit_on_kill=True):
        self.exit_on_term = exit_on_term
        self.exit_on_kill = exit_on_kill
        self.calls = 0
        self.returncode = None
        self.started = asyncio.Event()
        self.signal_event = asyncio.Event()
        self.done = asyncio.Event()
        self.wait_calls = 0
        self.received_signals = []

    def receive_signal(self, sig):
        self.received_signals.append(sig)
        self.signal_event.set()

    def terminate(self):
        self.receive_signal(signal.SIGTERM)

    def kill(self):
        self.receive_signal(signal.SIGKILL)

    async def communicate(self):
        self.calls += 1
        self.started.set()
        while True:
            await self.signal_event.wait()
            self.signal_event.clear()
            sig = self.received_signals[-1]
            if sig == signal.SIGTERM and self.exit_on_term:
                self.returncode = -signal.SIGTERM
                self.done.set()
                return b"term-reaped", b""
            if sig == signal.SIGKILL and self.exit_on_kill:
                self.returncode = -signal.SIGKILL
                self.done.set()
                return b"kill-reaped", b""

    async def wait(self):
        self.wait_calls += 1
        await self.done.wait()
        return self.returncode


def _manager():
    return bg.CoreTaskManager.__new__(bg.CoreTaskManager)


def _route_signals(monkeypatch, process):
    signals = []

    def killpg(pid, sig):
        signals.append((pid, sig))
        process.receive_signal(sig)

    monkeypatch.setattr(bg.os, "killpg", killpg)
    return signals


@pytest.mark.asyncio
async def test_timeout_terminates_then_kills_and_reaps_the_process_group(monkeypatch):
    manager = _manager()
    process = _FakeProcess(exit_on_term=False)
    signals = _route_signals(monkeypatch, process)

    out, err = await manager._communicate_or_kill(
        process,
        "test maintenance child",
        timeout=0.01,
        terminate_grace=0.01,
        kill_grace=0.1,
    )

    assert (out, err) == (b"kill-reaped", b"")
    assert signals == [
        (process.pid, signal.SIGTERM),
        (process.pid, signal.SIGKILL),
    ]
    assert process.returncode == -signal.SIGKILL
    assert process.calls == 1
    assert process.wait_calls == 1


@pytest.mark.asyncio
async def test_timeout_keeps_output_when_sigterm_is_enough(monkeypatch):
    manager = _manager()
    process = _FakeProcess(exit_on_term=True)
    signals = _route_signals(monkeypatch, process)

    out, err = await manager._communicate_or_kill(
        process,
        "gracefully stopped maintenance child",
        timeout=0.01,
        terminate_grace=0.1,
        kill_grace=0.1,
    )

    assert (out, err) == (b"term-reaped", b"")
    assert signals == [(process.pid, signal.SIGTERM)]
    assert process.returncode == -signal.SIGTERM
    assert process.wait_calls == 0


@pytest.mark.asyncio
async def test_slow_sigkill_exit_retains_the_reaper_until_the_child_exits(monkeypatch):
    manager = _manager()
    process = _FakeProcess(exit_on_term=False, exit_on_kill=False)
    signals = _route_signals(monkeypatch, process)

    out, err = await manager._communicate_or_kill(
        process,
        "slow-kill maintenance child",
        timeout=0.01,
        terminate_grace=0.01,
        kill_grace=0.01,
    )

    assert (out, err) == (b"", b"")
    assert signals == [
        (process.pid, signal.SIGTERM),
        (process.pid, signal.SIGKILL),
    ]
    pending = manager._subprocess_cleanup_tasks
    assert len(pending) == 1
    reaper = next(iter(pending))
    assert not reaper.done()

    # Simulate the kernel completing a delayed SIGKILL after the bounded wait.
    process.exit_on_kill = True
    process.signal_event.set()
    await asyncio.wait_for(reaper, timeout=1)

    assert process.returncode == -signal.SIGKILL
    assert not pending


@pytest.mark.asyncio
async def test_task_cancellation_stops_and_reaps_its_subprocess(monkeypatch):
    manager = _manager()
    process = _FakeProcess()
    signals = _route_signals(monkeypatch, process)

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
    assert process.calls == 1


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
