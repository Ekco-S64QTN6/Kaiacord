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
        
    def register_stats_poller(self, poller):
        """Register stats poller for cleanup"""
        self.stats_poller = poller
    
    def register_bot_task(self, task):
        """Register bot task for cleanup"""
        self.bot_task = task
    
    def shutdown_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        if self.shutting_down:
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
        
        # Restore terminal
        self.restore_terminal()
        
        # Exit cleanly
        sys.exit(0)
    
    def restore_terminal(self):
        """Restore terminal to normal state"""
        try:
            # Reset terminal
            sys.stdout.write("\033[0m\033[2J\033[H\033[?25h")
            sys.stdout.flush()
        except:
            pass
    
    def setup(self):
        """Setup signal handlers"""
        signal.signal(signal.SIGINT, self.shutdown_handler)
        signal.signal(signal.SIGTERM, self.shutdown_handler)
    
    def cleanup(self):
        """Manual cleanup if needed"""
        if not self.shutting_down:
            self.shutdown_handler(None, None)

# Global instance
shutdown_manager = CleanShutdown()
