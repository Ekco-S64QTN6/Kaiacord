"""Regression tests for bounded voice/radio shutdown before resource teardown."""

import asyncio

import pytest


@pytest.mark.asyncio
async def test_bounded_shutdown_component_returns_at_deadline_and_keeps_task_tracked():
    from utils.infrastructure.monitoring.async_task_registry import AsyncTaskRegistry
    from utils.infrastructure.system.shutdown_fixed import _bounded_shutdown_component

    registry = AsyncTaskRegistry()
    started = asyncio.Event()
    cancellation_seen = asyncio.Event()
    release = asyncio.Event()

    async def slow_stop():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancellation_seen.set()
            await release.wait()

    loop = asyncio.get_running_loop()
    deadline = loop.time() + 0.03
    result = await _bounded_shutdown_component(slow_stop(), "music-test", deadline, registry)

    assert result is False
    assert started.is_set()
    assert cancellation_seen.is_set()
    pending = registry.get_all_tasks()
    assert len(pending) == 1
    task = next(iter(pending.values()))
    assert not task.done()

    release.set()
    await asyncio.wait_for(task, timeout=1.0)
    await asyncio.sleep(0)
    assert registry.get_all_tasks() == {}


@pytest.mark.asyncio
async def test_async_shutdown_skips_resource_teardown_when_voice_stop_exceeds_budget(monkeypatch):
    from utils.audio import strudel_session
    from utils.infrastructure.monitoring.async_task_registry import task_registry
    from utils.infrastructure.system import shutdown_fixed

    task_registry.reset()
    monkeypatch.setattr(shutdown_fixed, "_shutdown_prelude_timeout", lambda: 0.03)
    monkeypatch.setattr(strudel_session, "active_sessions", lambda: [object()])

    started = asyncio.Event()
    cancellation_seen = asyncio.Event()
    release = asyncio.Event()

    async def slow_stop_all():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancellation_seen.set()
            await release.wait()

    monkeypatch.setattr(strudel_session, "stop_all", slow_stop_all)

    class FakeRag:
        persist_called = False

        def persist(self, **kwargs):
            self.persist_called = True
            return True

    rag = FakeRag()
    shutdown = shutdown_fixed.CleanShutdown()
    shutdown.register_rag(rag)

    await asyncio.wait_for(shutdown.async_shutdown(), timeout=0.5)

    assert started.is_set()
    assert cancellation_seen.is_set()
    assert rag.persist_called is False
    assert shutdown._shutdown_complete.is_set() is False
    pending = task_registry.get_all_tasks()
    assert "shutdown_component_music" in pending

    release.set()
    await asyncio.wait_for(pending["shutdown_component_music"], timeout=1.0)
    await asyncio.sleep(0)
    task_registry.reset()
