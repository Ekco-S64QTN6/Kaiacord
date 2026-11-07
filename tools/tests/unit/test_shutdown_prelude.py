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
    await asyncio.wait_for(cancellation_seen.wait(), timeout=0.2)
    pending = registry.get_all_tasks()
    assert len(pending) == 1
    task = next(iter(pending.values()))
    assert not task.done()

    release.set()
    await asyncio.wait_for(task, timeout=1.0)
    await asyncio.sleep(0)
    assert registry.get_all_tasks() == {}


@pytest.mark.asyncio
async def test_a_stuck_voice_stop_does_not_cost_the_index_save_or_the_model_unload(monkeypatch):
    from utils.audio import strudel_session
    from utils.infrastructure.monitoring import async_task_registry
    from utils.infrastructure.monitoring.async_task_registry import AsyncTaskRegistry
    from utils.infrastructure.system import shutdown_fixed

    registry = AsyncTaskRegistry()
    monkeypatch.setattr(async_task_registry, "task_registry", registry)
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

    # Everything after the voice/radio steps is stubbed: this test must not
    # unload the live model, close real clients or kill this machine's runners.
    from utils.infrastructure.gpu import gpu_manager, clear_gpu_memory
    from utils.social import kaia_forum
    from utils.core import rag_executor
    teardown = []

    async def unload_all_models(_client):
        teardown.append("unload")

    async def close_forum_client():
        teardown.append("forum")

    monkeypatch.setattr(gpu_manager.OllamaGPUManager, "unload_all_models", staticmethod(unload_all_models))
    monkeypatch.setattr(kaia_forum, "close_forum_client", close_forum_client)
    monkeypatch.setattr(rag_executor, "shutdown_rag_executor", lambda: teardown.append("executor"))
    monkeypatch.setattr(clear_gpu_memory, "force_clear_gpu", lambda: teardown.append("gpu"))
    monkeypatch.setattr(clear_gpu_memory, "kill_orphaned_runners", lambda **_kw: teardown.append("runners"))

    rag = FakeRag()
    shutdown = shutdown_fixed.CleanShutdown()
    shutdown.register_rag(rag)

    await asyncio.wait_for(shutdown.async_shutdown(), timeout=0.5)

    assert started.is_set()
    await asyncio.wait_for(cancellation_seen.wait(), timeout=0.2)
    assert rag.persist_called is True
    assert teardown == ["unload", "forum", "executor", "gpu", "runners"]
    assert shutdown._shutdown_complete.is_set() is True
    # The registry's own cancel reaches the step that ignored the first one.
    release.set()
    await asyncio.sleep(0)
    assert registry.get_all_tasks() == {}
