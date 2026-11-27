"""Ownership helpers for delayed GPU model startup recovery."""

import asyncio
from typing import Any


def schedule_prewarm_recovery_reload(
    awaitable,
    *,
    model_name: str,
    registry: Any = None,
) -> asyncio.Task:
    """Create and register a delayed model reload before yielding to shutdown.

    The registry also cancels tasks registered after its shutdown gate closes.
    Keep task creation and registration in the same event-loop turn so shutdown
    cannot observe an empty registry between those two operations.
    """
    if registry is None:
        from utils.infrastructure.monitoring.async_task_registry import task_registry
        registry = task_registry

    loop = asyncio.get_running_loop()
    task_name = f"prewarm_recovery_{model_name}"
    task = loop.create_task(awaitable, name=task_name)
    registry.register(task_name, task)
    return task
