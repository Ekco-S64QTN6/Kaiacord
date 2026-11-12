"""
Async Task Registry for Kaiacord
=================================

Central registry for tracking and managing long-lived async tasks.
Enables clean shutdown by cancelling all pending tasks and awaiting their completion.

Usage:
    from utils.infrastructure.monitoring.async_task_registry import task_registry
    
    # Register a task
    task = asyncio.create_task(some_coroutine())
    task_registry.register("task_name", task)
    
    # On shutdown
    await task_registry.cancel_all(timeout=5.0)
"""

import asyncio
import threading
import time
from typing import Dict
from utils.infrastructure.logging.unified_logging import logger


class AsyncTaskRegistry:
    """
    Thread-safe registry for tracking async tasks.
    
    Features:
    - Register tasks by name for tracking
    - Automatic cleanup of completed tasks
    - Mass cancellation with proper await
    - Timeout-based forced cleanup
    """
    
    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._lock = threading.Lock()
        self._shutdown_requested = False
        self._shutdown_draining = False
        
    @staticmethod
    def _cancel_task(task: asyncio.Task) -> None:
        """Request cancellation on the task's event loop, even from other threads."""
        try:
            loop = task.get_loop()
            if loop.is_closed():
                return
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
            if current_loop is loop:
                task.cancel()
            else:
                loop.call_soon_threadsafe(task.cancel)
        except (AttributeError, RuntimeError):
            # Defensive fallback for task-like objects used by tooling/tests.
            try:
                task.cancel()
            except Exception:
                pass

    def _track_locked(self, name: str, task: asyncio.Task) -> None:
        """Track a task and remove it when it finishes. Caller holds _lock."""
        if name in self._tasks:
            existing = self._tasks[name]
            if existing.done():
                del self._tasks[name]
            else:
                name = f"{name}_{id(task)}"

        self._tasks[name] = task

        def cleanup_callback(t, name=name):
            with self._lock:
                to_remove = [k for k, v in self._tasks.items() if v is t]
                for key in to_remove:
                    del self._tasks[key]
                # A timed-out parent may finish cleanup later and register a
                # detached child after cancel_all() has returned. Keep shutdown
                # draining active until the whole tracked descendant set exits.
                if (self._shutdown_requested and self._shutdown_draining
                        and not any(not pending.done() for pending in self._tasks.values())):
                    self._shutdown_draining = False
            if not t.cancelled():
                exc = t.exception()
                if exc is not None:
                    logger.log(
                        f"Background task '{name}' failed: {type(exc).__name__}: {exc}",
                        "ERROR",
                    )

        task.add_done_callback(cleanup_callback)

    def register(self, name: str, task: asyncio.Task) -> None:
        """Register a task, or cancel it when shutdown has started.

        Tasks spawned by a cancelling task are still tracked while cancel_all()
        is draining. Otherwise a detached child could suppress cancellation and
        outlive shutdown while the registry incorrectly reports zero pending work.
        """
        cancel = False
        with self._lock:
            if self._shutdown_requested:
                cancel = True
                if self._shutdown_draining:
                    self._track_locked(name, task)
            else:
                self._track_locked(name, task)

        if cancel:
            self._cancel_task(task)
    def get_pending_count(self) -> int:
        """Get count of pending (non-completed) tasks."""
        with self._lock:
            return sum(1 for t in self._tasks.values() if not t.done())
    
    def get_all_tasks(self) -> Dict[str, asyncio.Task]:
        """Get a copy of all tracked tasks."""
        with self._lock:
            return self._tasks.copy()
    
    async def cancel_all(self, timeout: float = 5.0) -> int:
        """Cancel and drain all registered tasks, including children registered
        by cancellation cleanup, within one shared timeout budget.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.0, float(timeout))
        with self._lock:
            self._shutdown_requested = True
            self._shutdown_draining = True
            self._tasks = {name: task for name, task in self._tasks.items() if not task.done()}
            tracked = self._tasks.copy()

        if not tracked:
            with self._lock:
                self._shutdown_draining = False
            logger.log("No async tasks to cancel", "INFO")
            return 0

        # Cancel the initial snapshot exactly once. Tasks registered from a
        # cancellation handler are cancelled by register() and picked up below.
        seen = set(tracked.values())
        cancelled_count = 0
        for task in seen:
            if not task.done():
                self._cancel_task(task)
                cancelled_count += 1

        task_names = list(tracked.keys())
        logger.log(
            f"Cancelling {len(seen)} async tasks: "
            f"{', '.join(task_names[:5])}{'...' if len(task_names) > 5 else ''}",
            "ACTION",
        )

        wait_error = None
        while True:
            with self._lock:
                live = {name: task for name, task in self._tasks.items() if not task.done()}
                current = set(live.values())
                # Late registrations were cancelled synchronously by register().
                late = current - seen
                cancelled_count += sum(1 for task in late if not task.done())
                seen.update(late)
                if not current:
                    self._shutdown_draining = False
                    break

            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                _done, pending = await asyncio.wait(current, timeout=remaining)
            except Exception as exc:
                wait_error = exc
                break
            if pending:
                # The deadline expired. Refresh below so late children remain
                # visible even when they were not in the wait set at its start.
                break
            # Every task in this snapshot finished. Loop again in case one of
            # their cleanup paths registered another task before completing.

        with self._lock:
            live = {name: task for name, task in self._tasks.items() if not task.done()}
            pending = set(live.values())
            late = pending - seen
            cancelled_count += sum(1 for task in late if not task.done())
            seen.update(late)
            self._tasks = {name: task for name, task in self._tasks.items() if not task.done()}
            # When the deadline expires, descendants may still be created by
            # cancellation cleanup. Keep tracking them until the last live task
            # finishes; force_clear() remains the explicit emergency escape.
            self._shutdown_draining = bool(pending)

        if wait_error is not None:
            logger.log(f"Error during task cancellation: {wait_error}", "ERROR")

        if pending:
            pending_names = [name for name, task in live.items() if task in pending]
            logger.log(
                f"Timed out waiting for tasks; {len(pending)} remain running "
                f"and stay tracked: {', '.join(pending_names[:5])}"
                f"{'...' if len(pending_names) > 5 else ''}",
                "WARNING",
            )
        else:
            logger.log(f"All {cancelled_count} tasks cancelled cleanly", "SUCCESS")

        return cancelled_count
    def force_clear(self) -> int:
        """
        Force clear all tasks without awaiting.
        Use only in emergency shutdown scenarios.
        
        Returns:
            Number of tasks that were force-cancelled
        """
        with self._lock:
            self._shutdown_requested = True
            self._shutdown_draining = False
            tasks = list(self._tasks.values())
            self._tasks.clear()

        count = 0
        for task in tasks:
            if not task.done():
                self._cancel_task(task)
                count += 1
            
        if count > 0:
            logger.log(f"Force-cancelled {count} tasks", "WARNING")
            
        return count
    
    def reset(self) -> None:
        """Reset the registry for a fresh start (e.g., after restart)."""
        with self._lock:
            self._tasks.clear()
            self._shutdown_requested = False
            self._shutdown_draining = False


# Global registry instance
task_registry = AsyncTaskRegistry()
