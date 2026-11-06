"""The async system monitor must kill and reap utility subprocesses."""

import asyncio
import signal

import pytest

from utils.infrastructure.system import kaia_sysmon


class _FakeProcess:
    pid = 24680

    def __init__(self, *, exit_on_kill=True):
        self.exit_on_kill = exit_on_kill
        self.started = asyncio.Event()
        self.output_ready = asyncio.Event()
        self.exit_ready = asyncio.Event()
        self.killed = False
        self.returncode = None
        self.wait_calls = 0

    async def communicate(self):
        self.started.set()
        await self.output_ready.wait()
        return b"system output", b""

    async def wait(self):
        self.wait_calls += 1
        await self.exit_ready.wait()
        self.returncode = -signal.SIGKILL
        return self.returncode

    def kill(self):
        self.killed = True
        if self.exit_on_kill:
            self.output_ready.set()
            self.exit_ready.set()


def _spawn(monkeypatch, process):
    calls = []

    async def create_subprocess_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return process

    monkeypatch.setattr(
        kaia_sysmon.asyncio, "create_subprocess_exec", create_subprocess_exec
    )
    return calls


@pytest.mark.asyncio
async def test_timeout_kills_utility_and_waits_for_child_reaping(monkeypatch):
    process = _FakeProcess()
    calls = _spawn(monkeypatch, process)

    result = await kaia_sysmon._run_cmd_async(["nvidia-smi"], timeout=0.01)

    assert result == ""
    assert calls
    assert process.killed
    assert process.wait_calls == 1
    assert process.returncode == -signal.SIGKILL


@pytest.mark.asyncio
async def test_cancellation_kills_and_reaps_utility_before_propagating(monkeypatch):
    process = _FakeProcess()
    _spawn(monkeypatch, process)

    task = asyncio.create_task(
        kaia_sysmon._run_cmd_async(["ss", "-tlnp"], timeout=60)
    )
    await asyncio.wait_for(process.started.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert process.killed
    assert process.wait_calls == 1
    assert process.returncode == -signal.SIGKILL


@pytest.mark.asyncio
async def test_slow_kill_reaping_task_is_retained_until_the_kernel_reports_exit():
    process = _FakeProcess(exit_on_kill=False)

    await kaia_sysmon._kill_and_reap(process, wait_timeout=0.01)

    assert process.killed
    assert process.wait_calls == 1
    pending = kaia_sysmon._PENDING_PROCESS_REAPERS
    assert len(pending) == 1
    reaper = next(iter(pending))
    assert not reaper.done()

    process.exit_ready.set()
    await asyncio.wait_for(reaper, timeout=1)

    assert process.returncode == -signal.SIGKILL
    assert not pending
