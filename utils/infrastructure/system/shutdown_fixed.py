"""
Clean Shutdown Handler for Kaiacord
====================================

Proper shutdown that:
1. Cancels all async tasks
2. Releases GPU memory
3. Drains event loop
4. Exits cleanly

Does NOT call sys.exit() prematurely - lets the main loop handle exit.
"""

import sys
import asyncio
import signal
import threading
import warnings
from typing import Optional, Any
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error, log_warning

# Suppress harmless multiprocessing semaphore cleanup warnings at shutdown.
# LlamaIndex's tokenizer subprocesses create POSIX semaphores that outlive the
# resource_tracker, producing ~16 "leaked semaphore" warnings on every exit.
warnings.filterwarnings("ignore", message="resource_tracker:.*semaphore", category=UserWarning)


#: Registry names of the voice/radio teardown steps.
_PRELUDE_TASK_PREFIX = "shutdown_component_"


async def _bounded_shutdown_component(awaitable, label: str, deadline: float, registry=None) -> bool:
    """Run a teardown operation without allowing it to overrun the shared deadline.

    Use asyncio.wait rather than wait_for: wait_for awaits cancellation completion,
    so a coroutine that suppresses CancelledError can exceed the shutdown budget.
    A timed-out operation remains registered while callers preserve its resources.
    """
    if registry is None:
        from utils.infrastructure.monitoring.async_task_registry import task_registry
        registry = task_registry

    task = asyncio.create_task(awaitable, name=f"shutdown:{label}")
    registry.register(f"{_PRELUDE_TASK_PREFIX}{label}", task)
    timeout = max(0.0, deadline - asyncio.get_running_loop().time())
    try:
        _done, pending = await asyncio.wait({task}, timeout=timeout)
    except asyncio.CancelledError:
        task.cancel()
        raise

    if pending:
        task.cancel()
        log_error(
            f"  ❌ Shutdown step '{label}' exceeded the shared voice/radio "
            f"cleanup deadline ({timeout:.1f}s); cancelled, continuing shutdown."
        )
        return False

    try:
        task.result()
    except asyncio.CancelledError:
        log_error(f"  ❌ Shutdown step '{label}' was cancelled before completion.")
        return False
    except Exception as exc:
        log_error(f"  ❌ Shutdown step '{label}' failed: {exc}.")
        return False
    return True


def _shutdown_prelude_timeout() -> float:
    """One shared budget for voice/radio teardown before task cancellation."""
    try:
        from utils.infrastructure.system.yaml_config import config
        return max(0.0, float(config.shutdown_task_cancel_timeout))
    except Exception:
        return 5.0

class CleanShutdown:
    """Proper shutdown handler that doesn't break async loops"""
    
    def __init__(self):
        self.shutting_down = False
        self.original_sigint = signal.getsignal(signal.SIGINT)
        self.original_sigterm = signal.getsignal(signal.SIGTERM)
        self.stats_poller = None
        self.bot_task = None
        self.stop_event = None
        self._shutdown_complete = threading.Event()
        self._setup_complete = False
        self.rag = None
        
    def register_stats_poller(self, poller):
        """Register stats poller for cleanup"""
        self.stats_poller = poller

    def register_rag(self, rag_instance):
        """Register RAG instance for persistence on shutdown"""
        self.rag = rag_instance
    
    def register_stop_event(self, event):
        """Register stop event for dashboard/main loop"""
        self.stop_event = event
    
    def shutdown_handler(self, signum, frame):
        """
        Handle shutdown signals gracefully.
        
        IMPORTANT: This does NOT call sys.exit() - it just signals
        that shutdown should begin and lets the main loop handle cleanup.
        """
        if self.shutting_down:
            # Already shutting down - ignore additional signals
            return
        
        self.shutting_down = True
        log_warning("Received shutdown signal")
        
        # Stop stats poller if registered
        if self.stats_poller:
            try:
                self.stats_poller.stop()
                log_info("  ✅ Stopped stats poller")
            except Exception as e:
                log_error(f"  ❌ Error stopping stats poller: {e}")
        
        # Cancel bot task if registered
        if self.bot_task:
            try:
                self.bot_task.cancel()
                log_info("  ✅ Cancelled bot task")
            except Exception as e:
                log_error(f"  ❌ Error cancelling bot task: {e}")
        
        # Trigger stop event if registered
        if self.stop_event:
            try:
                self.stop_event.set()
                log_info("  ✅ Triggered stop event")
            except Exception as e:
                log_error(f"  ❌ Error triggering stop event: {e}")
        
        # Restore terminal is now handled by the dashboard or main loop
        # self.restore_terminal()
        
        # NOTE: We do NOT call sys.exit() here!
        # The main loop should detect shutting_down flag and exit cleanly.
    
    async def async_shutdown(self, app_ctx: Optional[Any] = None):
        """
        Async cleanup that properly cancels and awaits all tasks.
        
        Call this from an event loop before exiting.
        """
        log_info("  🔄 Running async shutdown...")

        # 0. Stop voice/radio operations before cancelling the background registry.
        # Graceful Discord disconnects should complete where possible, but all four
        # share one configured budget: the dashboard force-exits about 18 s after
        # it asks the bot to stop. A step that overruns is cancelled and shutdown
        # carries on — none of these touch the RAG index, Ollama or the GPU, so
        # giving up on them must not cost the index save and the model unload
        # below. The scanner's forked watcher dies with the process (PDEATHSIG).
        prelude_deadline = asyncio.get_running_loop().time() + _shutdown_prelude_timeout()

        try:
            from utils.audio.strudel_session import active_sessions, stop_all
            sessions = active_sessions()
            if sessions:
                log_info(f"  🔄 Leaving {len(sessions)} voice channel(s)...")
                if await _bounded_shutdown_component(stop_all(), "music", prelude_deadline):
                    log_info("  ✅ Voice channels released")
        except ImportError:
            pass                      # audio engine not installed
        except Exception as e:
            log_error(f"  ❌ Could not stop music: {e}; continuing shutdown.")

        try:
            from utils.audio.records import stop_all as records_stop_all
            await _bounded_shutdown_component(records_stop_all(), "records", prelude_deadline)
        except Exception as e:
            log_error(f"  ❌ Could not stop records: {e}; continuing shutdown.")

        try:
            from utils.radio.live import active as radio_active, stop_all as radio_stop_all
            if radio_active():
                if await _bounded_shutdown_component(radio_stop_all(), "radio-live", prelude_deadline):
                    log_info("  ✅ Live radio stopped")
        except Exception as e:
            log_error(f"  ❌ Could not stop live radio: {e}; continuing shutdown.")

        try:
            from utils.radio import scanner
            await _bounded_shutdown_component(scanner.shutdown(), "radio-scanner", prelude_deadline)
        except Exception as e:
            log_error(f"  ❌ Could not stop the radio scanner: {e}; continuing shutdown.")

        # 1. Cancel all registered tasks via registry (STOP EVERYTHING FIRST).
        # A task may suppress CancelledError and outlive the configured deadline.
        # Never persist/close the resources it may still be using in that case.
        tasks_stopped = True
        try:
            from utils.infrastructure.monitoring.async_task_registry import task_registry
            from utils.infrastructure.system.yaml_config import config

            timeout = config.shutdown_task_cancel_timeout
            cancelled = await task_registry.cancel_all(timeout=timeout)
            # A voice/radio step that overran is voice-only: it holds nothing the
            # teardown below closes, so it does not hold the teardown back.
            remaining = task_registry.get_pending_count() - sum(
                1 for name, task in task_registry.get_all_tasks().items()
                if not task.done() and name.startswith(_PRELUDE_TASK_PREFIX)
            )
            if remaining:
                tasks_stopped = False
                log_error(
                    f"  ❌ {remaining} async task(s) remain active after the {timeout:.1f}s "
                    "shutdown deadline. Their ownership is retained; skipping resource teardown."
                )
            else:
                log_info(f"  ✅ Cancelled {cancelled} async tasks")
        except ImportError:
            log_warning("  ⚠️  Task registry not available")
        except Exception as e:
            tasks_stopped = False
            log_error(f"  ❌ Error cancelling tasks; skipping resource teardown: {e}")

        if not tasks_stopped:
            # The dashboard's bounded join ends in force_exit(). Keep Ollama,
            # RAG storage/executor, AppContext and GPU resources alive until then
            # rather than racing a task that is still cleaning up.
            return

        # BotState has a private single-worker writer outside the task registry.
        # Capture one final snapshot after application tasks stop, then drain
        # its queue before the dashboard can force-exit the process.
        try:
            state = getattr(app_ctx, "bot_state", None) if app_ctx is not None else None
            if state is None:
                from utils.infrastructure.system.bot_state import bot_state as state
            save = getattr(state, "save", None)
            close = getattr(state, "close", None)
            if callable(save) and callable(close):
                def _save_and_close_bot_state():
                    save()
                    close()

                await asyncio.wait_for(asyncio.to_thread(_save_and_close_bot_state), timeout=5.0)
                log_info("  ✅ BotState snapshot writer drained")
            else:
                log_warning("  ⚠️ BotState writer has no close() method; final snapshot may not be drained")
        except asyncio.TimeoutError:
            log_error("  ❌ BotState writer did not drain within 5s; its final snapshot may be incomplete")
        except Exception as exc:
            log_error(f"  ❌ Could not drain BotState writer: {exc}")

        # 2. Force Ollama Model Unload (Crucial for VRAM release - DO THIS BEFORE RAG I/O)
        try:
            from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
            
            # Use provided client or create temporary one
            client = app_ctx.ollama_client if app_ctx else None
            
            log_info("  🔄 Releasing all Ollama VRAM models...")
            await OllamaGPUManager.unload_all_models(client)
            log_info("  ✅ Ollama VRAM released")
        except Exception as e:
            log_warning(f"  ⚠️  Failed to release Ollama VRAM: {e}")

        # 2b. No final RAG refresh here. It would run after the GPU models are
        # unloaded and the tasks cancelled, so every embedding fails and shutdown
        # blocks. The hourly maintenance task handles indexing, and persisting
        # the existing indices in step 3 is what data safety needs.

        # 3. Persist RAG Index (Critical Data Safety)
        if self.rag:
            try:
                log_info("  💾 Persisting RAG indices...")
                # Only what changed since the last save: every change is saved
                # when it is made, and rewriting all indices (~170 MB) here took
                # long enough to be cut short by a second signal.
                try:
                    saved = await asyncio.wait_for(
                        asyncio.to_thread(lambda: self.rag.persist(shutdown=True)),
                        timeout=15.0
                    )
                    if saved is None:
                        log_info("  ✅ RAG indices already on disk (nothing changed since the last save)")
                    elif saved:
                        log_success("  ✅ RAG indices saved")
                    else:
                        log_warning("  ⚠️ RAG indices NOT fully saved (see the error above)")
                except asyncio.TimeoutError:
                    log_warning("  ⚠️ RAG persistence taking too long, continuing...")
            except Exception as e:
                log_error(f"  ❌ Error persisting RAG: {e}")

        # 4a. Close Forum Client
        try:
            from utils.social.kaia_forum import close_forum_client
            # Use shorter timeout for forum close
            await asyncio.wait_for(close_forum_client(), timeout=3.0)
            log_info("  ✅ Forum client closed")
        except Exception as e:
            log_warning(f"  ⚠️  Failed to close forum client: {e}")

        # 4b. Shut down RAG thread pool
        try:
            from utils.core.rag_executor import shutdown_rag_executor
            shutdown_rag_executor()
            log_info("  ✅ RAG thread pool closed")
        except Exception as e:
            log_warning(f"  ⚠️  Failed to close RAG thread pool: {e}")

        # 4. Close AppContext (and its Ollama client)
        if app_ctx:
            try:
                # Use a protected close call
                if hasattr(app_ctx, 'close') and callable(app_ctx.close):
                    await asyncio.wait_for(app_ctx.close(), timeout=3.0)
                    log_info("  ✅ AppContext resources closed")
                else:
                    # Fallback to direct client close if close() missing
                    if hasattr(app_ctx, 'ollama_client') and hasattr(app_ctx.ollama_client, 'close'):
                         await asyncio.wait_for(app_ctx.ollama_client.close(), timeout=2.0)
                         log_info("  ✅ Ollama client closed directly")
            except Exception as e:
                log_error(f"  ❌ Error closing AppContext: {e}")

        # 5. Force GPU cleanup (Internal Torch/CUDA buffers)
        try:
            from utils.infrastructure.gpu.clear_gpu_memory import force_clear_gpu
            log_info("  🔄 Releasing GPU memory...")
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(force_clear_gpu),
                    timeout=5.0
                )
                log_info("  ✅ GPU memory released")
            except asyncio.TimeoutError:
                log_warning("  ⚠️ GPU memory release taking too long, continuing...")
        except ImportError:
            pass
        except Exception as e:
            log_error(f"  ❌ Error GPU cleanup: {e}")
        
        # 6. Stop Watchdog
        try:
            from utils.infrastructure.monitoring.watchdog import watchdog
            watchdog.stop()
            log_info("  ✅ LoopWatchdog stopped")
        except Exception: pass

        # 7. EMERGENCY: Kill orphaned Ollama runners (VRAM retrieval)
        try:
            from utils.infrastructure.system.yaml_config import config
            from utils.infrastructure.gpu.clear_gpu_memory import kill_orphaned_runners
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(
                        kill_orphaned_runners,
                        preserve_model=config.chat_model,
                        preserve_ctx=config.max_context_tokens
                    ),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                pass
        except Exception: pass

        self._shutdown_complete.set()
        log_info("  ✅ Async shutdown complete")
    
    def force_exit(self, exit_code: int = 0):
        """Emergency force exit if shutdown hangs"""
        log_warning(f"Forcing exit with code {exit_code}")
        self.restore_terminal()
        # Use os._exit to bypass all cleanup and force immediate termination
        import os
        os._exit(exit_code)
    
    def restore_terminal(self):
        """Restore terminal to normal state"""
        try:
            # Reset terminal
            sys.stdout.write("\033[0m\033[2J\033[H\033[?25h")
            sys.stdout.flush()
        except Exception:
            pass
    
    def setup(self):
        """Setup signal handlers (idempotent - safe to call multiple times)"""
        if self._setup_complete:
            return  # Already set up
        signal.signal(signal.SIGINT, self.shutdown_handler)
        signal.signal(signal.SIGTERM, self.shutdown_handler)
        self._setup_complete = True
    
    def cleanup(self):
        """
        Manual cleanup if needed.
        
        This is for synchronous contexts. For async contexts,
        use async_shutdown() instead.
        """
        if not self.shutting_down:
            self.shutdown_handler(None, None)
    
# Global instance
shutdown_manager = CleanShutdown()
