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
async def test_a_stuck_voice_stop_does_not_cost_the_index_save_or_the_model_unload(monkeypatch, tmp_path):
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

    # Shutdown saves and closes the process's BotState. Left the global one, it
    # closed the singleton every later test in this process writes channel
    # memory to, at a moment set by the writer thread, not by test order.
    from utils.infrastructure.system import bot_state as bot_state_module
    monkeypatch.setattr(bot_state_module, "bot_state",
                        bot_state_module.BotState(state_file=str(tmp_path / "bot_state.json")))

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


@pytest.mark.asyncio
async def test_timed_out_rag_shutdown_save_retains_worker_and_skips_later_teardown(
    monkeypatch, tmp_path
):
    """A save past the global deadline stays owned and prevents resource teardown."""
    import sys
    import threading
    import types
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from utils.core import rag_executor
    from utils.infrastructure.monitoring import async_task_registry
    from utils.infrastructure.monitoring.async_task_registry import AsyncTaskRegistry
    from utils.infrastructure.system import shutdown_fixed

    registry = AsyncTaskRegistry()
    monkeypatch.setattr(async_task_registry, "task_registry", registry)
    monkeypatch.setattr(shutdown_fixed, "_shutdown_prelude_timeout", lambda: 1.0)
    monkeypatch.setattr(shutdown_fixed, "_shutdown_total_timeout_s", lambda: 0.35)
    monkeypatch.setattr(shutdown_fixed, "RAG_SAVE_TIMEOUT_S", 0.01)

    # The audio/radio prelude is idle and uses only local async stubs.
    strudel = types.ModuleType("utils.audio.strudel_session")
    strudel.active_sessions = lambda: []
    strudel.stop_all = AsyncMock()
    records = types.ModuleType("utils.audio.records")
    records.stop_all = AsyncMock()
    radio_live = types.ModuleType("utils.radio.live")
    radio_live.active = lambda: False
    radio_live.stop_all = AsyncMock()
    scanner = types.ModuleType("utils.radio.scanner")
    scanner.shutdown = AsyncMock()
    for name, module in (
        ("utils.audio.strudel_session", strudel),
        ("utils.audio.records", records),
        ("utils.radio.live", radio_live),
        ("utils.radio.scanner", scanner),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    import utils.audio
    import utils.radio
    monkeypatch.setattr(utils.audio, "strudel_session", strudel, raising=False)
    monkeypatch.setattr(utils.audio, "records", records, raising=False)
    monkeypatch.setattr(utils.radio, "live", radio_live, raising=False)
    monkeypatch.setattr(utils.radio, "scanner", scanner, raising=False)

    worker_started = threading.Event()
    release_worker = threading.Event()
    teardown = []

    class BlockingRag:
        def persist(self, *, shutdown=False):
            assert shutdown is True
            worker_started.set()
            if not release_worker.wait(timeout=3):
                raise TimeoutError("test did not release the shutdown RAG writer")
            return True

    class FakeBotState:
        def save(self):
            return None

        def close(self):
            return None

    class FakeWatchdog:
        def stop(self):
            teardown.append("watchdog")

    from utils.infrastructure.monitoring import watchdog as watchdog_module
    monkeypatch.setattr(watchdog_module.watchdog, "stop", FakeWatchdog().stop)

    from utils.infrastructure.gpu import gpu_manager, clear_gpu_memory
    from utils.social import kaia_forum

    async def unload_all_models(_client):
        return None

    async def close_forum_client():
        teardown.append("forum")

    async def close_app_context():
        teardown.append("app-context")

    monkeypatch.setattr(
        gpu_manager.OllamaGPUManager,
        "unload_all_models",
        staticmethod(unload_all_models),
    )
    monkeypatch.setattr(kaia_forum, "close_forum_client", close_forum_client)
    monkeypatch.setattr(rag_executor, "shutdown_rag_executor_async",
                        AsyncMock(side_effect=lambda: teardown.append("executor")))
    monkeypatch.setattr(clear_gpu_memory, "force_clear_gpu", lambda: teardown.append("gpu"))
    monkeypatch.setattr(clear_gpu_memory, "kill_orphaned_runners",
                        lambda **_kw: teardown.append("runners"))

    app_ctx = SimpleNamespace(
        bot_state=FakeBotState(),
        ollama_client=object(),
        close=AsyncMock(side_effect=close_app_context),
    )
    shutdown = shutdown_fixed.CleanShutdown()
    shutdown.register_rag(BlockingRag())
    force_exits = []
    monkeypatch.setattr(shutdown, "force_exit", lambda code: force_exits.append(code))
    owner = asyncio.create_task(shutdown.async_shutdown(app_ctx))
    try:
        assert await asyncio.to_thread(worker_started.wait, 1.0)

        # The event loop continues to run while the writer is beyond both the
        # normal save budget and the shortened test shutdown deadline.
        ticks = 0
        for _ in range(20):
            await asyncio.sleep(0.02)
            ticks += 1
        assert ticks == 20
        assert not owner.done(), "shutdown detached a still-running RAG writer"
        assert shutdown._rag_save_task is not None
        assert not shutdown._rag_save_task.done()
        assert shutdown._shutdown_complete.is_set() is False
        assert teardown == []
        app_ctx.close.assert_not_awaited()

        release_worker.set()
        await asyncio.wait_for(owner, timeout=1.0)

        assert shutdown._rag_save_task is None
        assert shutdown._shutdown_complete.is_set() is False
        assert teardown == [], "later resource teardown ran after the global shutdown deadline"
        assert force_exits == [1], "simple mode did not enforce its global shutdown deadline"
        app_ctx.close.assert_not_awaited()
    finally:
        release_worker.set()
        if not owner.done():
            owner.cancel()
            try:
                await asyncio.wait_for(owner, timeout=1.0)
            except asyncio.CancelledError:
                pass
        pending_save = shutdown._rag_save_task
        if pending_save is not None and not pending_save.done():
            await asyncio.wait_for(pending_save, timeout=1.0)
