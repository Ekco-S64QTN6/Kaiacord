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
from typing import Optional, Any
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error, log_warning


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
    
    def register_bot_task(self, task):
        """Register bot task for cleanup"""
        self.bot_task = task
    
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

        # 1. Cancel all registered tasks via registry (STOP EVERYTHING FIRST)
        try:
            from utils.infrastructure.monitoring.async_task_registry import task_registry
            from utils.infrastructure.system.yaml_config import config
            
            timeout = config.shutdown_task_cancel_timeout
            cancelled = await task_registry.cancel_all(timeout=timeout)
            log_info(f"  ✅ Cancelled {cancelled} async tasks")
        except ImportError:
            log_warning("  ⚠️  Task registry not available")
        except Exception as e:
            log_error(f"  ❌ Error cancelling tasks: {e}")

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

        # 2b. Final RAG Refresh Sweep (Self-Heal)
        if self.rag:
            try:
                from utils.core.rag_executor import run_rag
                log_info("  🔄 Performing final knowledge base sweep...")
                # Run sync or with very short timeout to avoid hang
                await asyncio.wait_for(run_rag(self.rag.refresh_knowledge_base), timeout=10.0)
                log_info("  ✅ Final sweep complete")
            except Exception:
                log_warning("  ⚠️ Final knowledge sweep skipped/timed out")

        # 3. Persist RAG Index (Critical Data Safety)
        if self.rag:
            try:
                log_info("  💾 Persisting RAG indices...")
                # Reduce timeout for persistence on shutdown
                persist_thread = threading.Thread(target=self.rag.persist, args=(True,))
                persist_thread.daemon = True
                persist_thread.start()
                persist_thread.join(timeout=15.0) # Reduced from 30s
                if persist_thread.is_alive():
                    log_warning("  ⚠️ RAG persistence taking too long, continuing...")
                else:
                    log_success("  ✅ RAG indices saved")
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
            # Use a raw thread to avoid the default executor
            cleanup_thread = threading.Thread(target=force_clear_gpu)
            cleanup_thread.daemon = True
            cleanup_thread.start()
            cleanup_thread.join(timeout=5.0) # Reduced from 10s
            log_info("  ✅ GPU memory released")
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
            from utils.infrastructure.gpu.clear_gpu_memory import kill_orphaned_runners
            from utils.infrastructure.system.yaml_config import config
            # Use a raw thread with shorter timeout
            kill_thread = threading.Thread(
                target=kill_orphaned_runners, 
                kwargs={"preserve_model": config.chat_model, "preserve_ctx": config.max_context_tokens}
            )
            kill_thread.daemon = True
            kill_thread.start()
            kill_thread.join(timeout=5.0) # Reduced from 10s
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
    
    def wait_for_shutdown(self, timeout: float = None) -> bool:
        """
        Wait for shutdown to complete.
        
        Returns True if shutdown completed, False if timed out.
        """
        if timeout is None:
             from utils.infrastructure.system.yaml_config import config
             timeout = config.shutdown_timeout
             
        return self._shutdown_complete.wait(timeout=timeout)


# Global instance
shutdown_manager = CleanShutdown()
