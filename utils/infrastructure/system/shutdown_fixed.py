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
from typing import Optional


class CleanShutdown:
    """Proper shutdown handler that doesn't break async loops"""
    
    def __init__(self):
        self.shutting_down = False
        self.original_sigint = signal.getsignal(signal.SIGINT)
        self.original_sigterm = signal.getsignal(signal.SIGTERM)
        self.stats_poller = None
        self.bot_task = None
        self._shutdown_complete = threading.Event()
        self._setup_complete = False
        
    def register_stats_poller(self, poller):
        """Register stats poller for cleanup"""
        self.stats_poller = poller
    
    def register_bot_task(self, task):
        """Register bot task for cleanup"""
        self.bot_task = task
    
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
        print(f"\n\033[93m⚠️  Received shutdown signal\033[0m")
        
        # Stop stats poller if registered
        if self.stats_poller:
            try:
                self.stats_poller.stop()
                print("  ✅ Stopped stats poller")
            except Exception as e:
                print(f"  ❌ Error stopping stats poller: {e}")
        
        # Cancel bot task if registered
        if self.bot_task:
            try:
                self.bot_task.cancel()
                print("  ✅ Cancelled bot task")
            except Exception as e:
                print(f"  ❌ Error cancelling bot task: {e}")
        
        # Restore terminal - but don't exit
        self.restore_terminal()
        
        # NOTE: We do NOT call sys.exit() here!
        # The main loop should detect shutting_down flag and exit cleanly.
    
    async def async_shutdown(self):
        """
        Async cleanup that properly cancels and awaits all tasks.
        
        Call this from an event loop before exiting.
        """
        print("  🔄 Running async shutdown...")
        
        # Cancel all registered tasks via registry
        try:
            from utils.infrastructure.monitoring.async_task_registry import task_registry
            cancelled = await task_registry.cancel_all(timeout=5.0)
            print(f"  ✅ Cancelled {cancelled} async tasks")
        except ImportError:
            print("  ⚠️  Task registry not available")
        except Exception as e:
            print(f"  ❌ Error cancelling tasks: {e}")
        
        # Force GPU cleanup
        try:
            from utils.infrastructure.gpu.clear_gpu_memory import force_clear_gpu
            if force_clear_gpu():
                print("  ✅ GPU memory released")
            else:
                print("  ⚠️  GPU cleanup incomplete")
        except ImportError:
            pass
        except Exception as e:
            print(f"  ❌ GPU cleanup error: {e}")
        
        self._shutdown_complete.set()
        print("  ✅ Async shutdown complete")
    
    def restore_terminal(self):
        """Restore terminal to normal state"""
        try:
            # Reset terminal
            sys.stdout.write("\033[0m\033[2J\033[H\033[?25h")
            sys.stdout.flush()
        except:
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
    
    def wait_for_shutdown(self, timeout: float = 10.0) -> bool:
        """
        Wait for shutdown to complete.
        
        Returns True if shutdown completed, False if timed out.
        """
        return self._shutdown_complete.wait(timeout=timeout)


# Global instance
shutdown_manager = CleanShutdown()
