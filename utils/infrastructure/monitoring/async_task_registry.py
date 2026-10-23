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

    def register(self, name: str, task: asyncio.Task) -> None:
        """Register a task unless shutdown has already begun.

        The shutdown check and insertion share one lock with cancel_all()'s
        shutdown flag/snapshot. Otherwise a thread can pass the check, pause,
        and insert after cancel_all() already took its snapshot.
        """
        cancel = False
        with self._lock:
            if self._shutdown_requested:
                cancel = True
            else:
                # Clean up any existing task with this name if it's done.
                if name in self._tasks:
                    existing = self._tasks[name]
                    if existing.done():
                        del self._tasks[name]
                    else:
                        # Task with this name still running - append unique suffix.
                        name = f"{name}_{id(task)}"

                self._tasks[name] = task

                def cleanup_callback(t, name=name):
                    with self._lock:
                        to_remove = [k for k, v in self._tasks.items() if v is t]
                        for k in to_remove:
                            del self._tasks[k]
                    # A background task that died with an exception said nothing:
                    # nobody awaits these, so the error was never retrieved.
                    if not t.cancelled() and t.exception() is not None:
                        logger.log(f"Background task '{name}' failed: "
                                   f"{type(t.exception()).__name__}: {t.exception()}", "ERROR")

                task.add_done_callback(cleanup_callback)

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
        """
        Cancel all registered tasks and await their completion.
        
        Args:
            timeout: Maximum time to wait for tasks to complete
            
        Returns:
            Number of tasks that were cancelled
        """
        with self._lock:
            self._shutdown_requested = True
            tasks = list(self._tasks.values())
            task_names = list(self._tasks.keys())
        
        if not tasks:
            logger.log("No async tasks to cancel", "INFO")
            return 0
        
        logger.log(f"Cancelling {len(tasks)} async tasks: {', '.join(task_names[:5])}{'...' if len(task_names) > 5 else ''}", "ACTION")
        
        # Cancel all tasks
        cancelled_count = 0
        for task in tasks:
            if not task.done():
                task.cancel()
                cancelled_count += 1
        
        if cancelled_count == 0:
            logger.log("All tasks already completed", "INFO")
            return 0
        
        # Wait for all tasks with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
            logger.log(f"All {cancelled_count} tasks cancelled cleanly", "SUCCESS")
        except asyncio.TimeoutError:
            # Some tasks didn't complete in time
            still_pending = sum(1 for t in tasks if not t.done())
            logger.log(f"Timeout waiting for tasks - {still_pending} still pending", "WARNING")
        except Exception as e:
            logger.log(f"Error during task cancellation: {e}", "ERROR")
        
        # Clear registry
        with self._lock:
            self._tasks.clear()
        
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


# Global registry instance
task_registry = AsyncTaskRegistry()
