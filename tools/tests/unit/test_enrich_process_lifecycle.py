"""The !enrich timeout cleanup must never wait indefinitely."""

import asyncio

from utils.commands.enrich_handler import _terminate_and_reap


class StubbornProcess:
    def __init__(self):
        self.returncode = None
        self.terminated = False
        self.killed = False
        self.wait_calls = 0
        self._never = asyncio.Event()

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        self.wait_calls += 1
        if not self.killed:
            await self._never.wait()
        return self.returncode


def test_terminate_escalates_to_kill_with_bounded_waits():
    async def scenario():
        process = StubbornProcess()
        await asyncio.wait_for(_terminate_and_reap(process, grace=0.01), timeout=0.5)
        assert process.terminated
        assert process.killed
        assert process.returncode == -9
        assert process.wait_calls == 2

    asyncio.run(scenario())


def test_already_exited_process_needs_no_signals():
    async def scenario():
        process = StubbornProcess()
        process.returncode = 0
        await _terminate_and_reap(process, grace=0.01)
        assert not process.terminated
        assert not process.killed
        assert process.wait_calls == 0

    asyncio.run(scenario())
