"""Cancellation and shutdown ownership for the shared synchronous RAG pool."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from utils.core import rag_executor as rag


@pytest.mark.parametrize(
    ("runner_name", "semaphore_name"),
    (
        ("run_rag", "indexing_semaphore"),
        ("run_rag_retrieval", "retrieval_semaphore"),
    ),
)
@pytest.mark.asyncio
async def test_cancelled_owner_retains_semaphore_until_worker_exits(
    runner_name, semaphore_name, monkeypatch
):
    """A cancelled caller must not free its in-flight slot while the thread runs."""
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rag-lifecycle-test")
    monkeypatch.setattr(rag, "rag_executor", pool)
    monkeypatch.setattr(rag, semaphore_name, asyncio.Semaphore(1))

    worker_started = threading.Event()
    release_worker = threading.Event()
    contender_started = threading.Event()
    runner = getattr(rag, runner_name)

    def blocked_worker():
        worker_started.set()
        if not release_worker.wait(timeout=3):
            raise TimeoutError("test did not release the RAG worker")
        return "finished"

    owner = asyncio.create_task(runner(blocked_worker))
    contender = None
    try:
        assert await asyncio.to_thread(worker_started.wait, 1.0)

        owner.cancel()
        await asyncio.sleep(0.05)
        assert not owner.done(), "cancellation detached the active executor worker"

        contender = asyncio.create_task(
            runner(lambda: contender_started.set() or "second")
        )
        await asyncio.sleep(0.05)
        assert not contender_started.is_set(), (
            "the semaphore was released before the first worker stopped"
        )
        assert not contender.done()

        release_worker.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(owner, timeout=1.0)
        assert await asyncio.wait_for(contender, timeout=1.0) == "second"
        assert contender_started.is_set()
    finally:
        release_worker.set()
        for task in (owner, contender):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=1.0)
                except asyncio.CancelledError:
                    pass
        await asyncio.to_thread(pool.shutdown, wait=True)


@pytest.mark.asyncio
async def test_cancelled_owner_remains_registered_until_executor_worker_drains(
    monkeypatch,
):
    """Shutdown's registry gate must still see an owner draining a real worker."""
    from utils.infrastructure.monitoring.async_task_registry import AsyncTaskRegistry

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag-registry-test")
    monkeypatch.setattr(rag, "rag_executor", pool)
    monkeypatch.setattr(rag, "indexing_semaphore", asyncio.Semaphore(1))
    worker_started = threading.Event()
    release_worker = threading.Event()
    registry = AsyncTaskRegistry()

    def blocked_worker():
        worker_started.set()
        if not release_worker.wait(timeout=3):
            raise TimeoutError("test did not release the registered RAG worker")
        return True

    owner = asyncio.create_task(rag.run_rag(blocked_worker))
    registry.register("rag-owner", owner)
    try:
        assert await asyncio.to_thread(worker_started.wait, 1.0)

        cancelled = await registry.cancel_all(timeout=0.05)
        assert cancelled == 1
        assert not owner.done()
        assert registry.get_pending_count() == 1
        assert any(task is owner for task in registry.get_all_tasks().values())

        release_worker.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(owner, timeout=1.0)
        await asyncio.sleep(0)
        assert registry.get_pending_count() == 0
        assert registry.get_all_tasks() == {}
    finally:
        release_worker.set()
        if not owner.done():
            owner.cancel()
            try:
                await asyncio.wait_for(owner, timeout=1.0)
            except asyncio.CancelledError:
                pass
        await asyncio.to_thread(pool.shutdown, wait=True)


@pytest.mark.asyncio
async def test_cancelled_worker_exception_is_retrieved_without_replacing_cancellation(
    monkeypatch,
):
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag-exception-test")
    monkeypatch.setattr(rag, "rag_executor", pool)
    monkeypatch.setattr(rag, "indexing_semaphore", asyncio.Semaphore(1))
    worker_started = threading.Event()
    release_worker = threading.Event()

    def failing_worker():
        worker_started.set()
        if not release_worker.wait(timeout=3):
            raise TimeoutError("test did not release the failing RAG worker")
        raise RuntimeError("worker failure after owner cancellation")

    owner = asyncio.create_task(rag.run_rag(failing_worker))
    try:
        assert await asyncio.to_thread(worker_started.wait, 1.0)
        owner.cancel()
        await asyncio.sleep(0.02)
        assert not owner.done()
        release_worker.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(owner, timeout=1.0)
        await asyncio.sleep(0.02)
    finally:
        release_worker.set()
        if not owner.done():
            owner.cancel()
            try:
                await asyncio.wait_for(owner, timeout=1.0)
            except asyncio.CancelledError:
                pass
        await asyncio.to_thread(pool.shutdown, wait=True)


@pytest.mark.asyncio
async def test_executor_shutdown_waits_off_loop_thread_and_keeps_loop_responsive(
    monkeypatch,
):
    shutdown_started = threading.Event()
    worker_started = threading.Event()
    release_worker = threading.Event()

    class ObservedExecutor(ThreadPoolExecutor):
        shutdown_thread = None

        def shutdown(self, wait=True, *, cancel_futures=False):
            self.shutdown_thread = threading.current_thread()
            shutdown_started.set()
            return super().shutdown(wait=wait, cancel_futures=cancel_futures)

    pool = ObservedExecutor(max_workers=1, thread_name_prefix="rag-shutdown-test")
    monkeypatch.setattr(rag, "rag_executor", pool)

    def blocked_worker():
        worker_started.set()
        if not release_worker.wait(timeout=3):
            raise TimeoutError("test did not release the shutdown worker")
        return "closed"

    loop = asyncio.get_running_loop()
    worker = loop.run_in_executor(pool, blocked_worker)
    closer = None
    try:
        assert await asyncio.to_thread(worker_started.wait, 1.0)
        closer = asyncio.create_task(rag.shutdown_rag_executor_async())
        assert await asyncio.to_thread(shutdown_started.wait, 1.0)
        assert not closer.done()
        assert pool.shutdown_thread is not threading.current_thread()

        # These loop turns would be impossible while shutdown(wait=True) ran here.
        ticks = 0
        for _ in range(4):
            await asyncio.sleep(0.01)
            ticks += 1
        assert ticks == 4

        release_worker.set()
        await asyncio.wait_for(closer, timeout=1.0)
        assert await asyncio.wait_for(worker, timeout=1.0) == "closed"
    finally:
        release_worker.set()
        if closer is not None and not closer.done():
            await asyncio.wait_for(closer, timeout=1.0)
        elif closer is None:
            await asyncio.to_thread(pool.shutdown, wait=True)


@pytest.mark.parametrize(
    ("async_name", "sync_name", "args"),
    (
        ("add_memory_async", "add_memory", (42, "tester", "remembered fact")),
        ("log_user_interaction_async", "log_user_interaction",
         (42, "tester", "hello", "hi")),
        ("persist_async", "persist", (True, True)),
    ),
)
@pytest.mark.asyncio
async def test_default_executor_rag_writers_remain_registered_until_worker_exits(
    async_name, sync_name, args, monkeypatch
):
    """Cancellation cannot orphan a default-executor RAG mutation."""
    from utils.core.kaia_rag_persistence import RAGPersistenceMixin
    from utils.infrastructure.monitoring.async_task_registry import AsyncTaskRegistry

    started = threading.Event()
    release = threading.Event()
    registry = AsyncTaskRegistry()
    harness = RAGPersistenceMixin.__new__(RAGPersistenceMixin)

    def blocked_writer(*_args, **_kwargs):
        started.set()
        if not release.wait(timeout=3):
            raise TimeoutError("test did not release the default-executor RAG writer")
        return True

    monkeypatch.setattr(harness, sync_name, blocked_writer, raising=False)
    async_writer = getattr(RAGPersistenceMixin, async_name)
    owner = asyncio.create_task(async_writer(harness, *args))
    registry.register("rag-default-writer", owner)
    try:
        assert await asyncio.to_thread(started.wait, 1.0)

        cancelled = await registry.cancel_all(timeout=0.05)
        assert cancelled == 1
        assert not owner.done(), "registry treated a running default-executor writer as drained"
        assert registry.get_pending_count() == 1
        assert any(task is owner for task in registry.get_all_tasks().values())

        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(owner, timeout=1.0)
        await asyncio.sleep(0)
        assert registry.get_pending_count() == 0
        assert registry.get_all_tasks() == {}
    finally:
        release.set()
        if not owner.done():
            owner.cancel()
            try:
                await asyncio.wait_for(owner, timeout=1.0)
            except asyncio.CancelledError:
                pass
