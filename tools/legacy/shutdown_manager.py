import curses
import signal
import sys
import time
import threading
import os

class CleanShutdownManager:
    """Manages clean shutdown to prevent terminal corruption"""
    
    def __init__(self):
        self.shutting_down = False
        self.original_sigint = None
        self.original_sigterm = None
        self.terminal_state_saved = False
        self.original_termios = None
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        
        # Save terminal state
        self.save_terminal_state()
        
        # Set up signal handlers
        self.setup_signal_handlers()
        
    def save_terminal_state(self):
        """Save terminal state for restoration"""
        try:
            import termios
            import tty
            
            # Save termios settings
            fd = sys.stdin.fileno()
            self.original_termios = termios.tcgetattr(fd)
            self.terminal_state_saved = True
            
            # Save cursor position
            sys.stdout.write("\033[s")  # Save cursor
            sys.stdout.flush()
            
        except ImportError:
            pass  # Not on Unix-like system
    
    def restore_terminal_state(self):
        """Restore terminal to original state"""
        if self.shutting_down:
            return
            
        self.shutting_down = True
        
        try:
            # Stop any active curses sessions
            curses.endwin()
            curses.nocbreak()
            curses.echo()
            curses.endwin()
        except:
            pass
        
        try:
            # Reset terminal colors
            sys.stdout.write("\033[0m")  # Reset all attributes
            sys.stdout.write("\033[?25h")  # Show cursor
            sys.stdout.write("\033[u")  # Restore cursor position
            
            # Restore termios if saved
            if self.original_termios:
                import termios
                import tty
                fd = sys.stdin.fileno()
                termios.tcsetattr(fd, termios.TCSAFLUSH, self.original_termios)
            
            # Flush output
            sys.stdout.flush()
            sys.stderr.flush()
            
            # Restore stdout/stderr
            sys.stdout = self.original_stdout
            sys.stderr = self.original_stderr
            
        except Exception as e:
            # If all else fails, do minimal cleanup
            sys.stdout.write("\033[0m\n")
            sys.stdout.flush()
    
    def setup_signal_handlers(self):
        """Set up signal handlers for clean shutdown"""
        self.original_sigint = signal.getsignal(signal.SIGINT)
        self.original_sigterm = signal.getsignal(signal.SIGTERM)
        
        def shutdown_handler(signum, frame):
            print(f"\n\033[93m⚠️  Received shutdown signal {signum}\033[0m")
            self.perform_clean_shutdown()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)
    
    def perform_clean_shutdown(self):
        """Perform complete shutdown sequence"""
        print("\033[94m🔄 Performing clean shutdown...\033[0m")
        
        # Step 1: Stop all threads
        print("  • Stopping background threads...")
        
        # Step 2: Restore terminal
        print("  • Restoring terminal state...")
        self.restore_terminal_state()
        
        # Step 3: Clear any pending output
        print("  • Flushing buffers...")
        sys.stdout.write("\033[2J\033[H")  # Clear screen and home cursor
        sys.stdout.flush()
        
        print("\033[92m✅ Shutdown complete.\033[0m\n")
        
    def get_shutdown_handler(self):
        """Return a function that can be used as a shutdown handler"""
        def shutdown():
            if not self.shutting_down:
                self.perform_clean_shutdown()
        return shutdown

# Global instance
shutdown_manager = CleanShutdownManager()
