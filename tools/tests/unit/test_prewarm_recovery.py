"""Tests for registry ownership of delayed Ollama startup recovery."""

import asyncio

import pytest

from utils.infrastructure.gpu.prewarm_recovery import schedule_prewarm_recovery_reload
from utils.infrastructure.monitoring.async_task_registry import AsyncTaskRegistry


@pytest.mark.asyncio
async def test_delayed_prewarm_recovery_reload_is_cancelled_by_shutdown():
    registry = AsyncTaskRegistry()
    reload_started = asyncio.Event()
    generate_called = asyncio.Event()

    async def delayed_reload():
        reload_started.set()
        await asyncio.sleep(30.0)
        generate_called.set()

    task = schedule_prewarm_recovery_reload(
        delayed_reload(),
        model_name="test-model",
        registry=registry,
    )
    await asyncio.wait_for(reload_started.wait(), timeout=1.0)

    assert registry.get_pending_count() == 1
    assert registry.get_all_tasks()["prewarm_recovery_test-model"] is task

    assert await registry.cancel_all(timeout=0.5) == 1
    assert task.cancelled()
    assert registry.get_pending_count() == 0
    assert not generate_called.is_set()


@pytest.mark.asyncio
async def test_prewarm_recovery_registered_after_shutdown_is_cancelled_immediately():
    registry = AsyncTaskRegistry()
    await registry.cancel_all(timeout=0.1)
    generate_called = asyncio.Event()

    async def delayed_reload():
        await asyncio.sleep(30.0)
        generate_called.set()

    task = schedule_prewarm_recovery_reload(
        delayed_reload(),
        model_name="test-model",
        registry=registry,
    )
    await asyncio.sleep(0)

    assert task.cancelled()
    assert registry.get_pending_count() == 0
    assert not generate_called.is_set()
