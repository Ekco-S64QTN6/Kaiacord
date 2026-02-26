#!/usr/bin/env python3
"""
Terminal management utilities for htop-like behavior.
Prevents scrolling, hides cursor, and manages alternate screen buffers.
"""

import os
import sys
import signal
import termios
import tty
import fcntl
import struct

class TerminalManager:
    """Manages terminal settings for htop-like dashboard behavior"""
    
    def __init__(self):
        self.original_settings = None
        self.original_flags = None
        self.fd = sys.stdin.fileno()
        self.is_tty = sys.stdout.isatty()
        
    def enable_alternate_screen(self):
        """Switch to alternate screen buffer (like htop)"""
        if self.is_tty:
            sys.stdout.write('\033[?1049h')  # Enter alternate screen
            sys.stdout.flush()
    
    def disable_alternate_screen(self):
        """Switch back to main screen buffer"""
        if self.is_tty:
            sys.stdout.write('\033[?1049l')  # Exit alternate screen
            sys.stdout.flush()
    
    def hide_cursor(self):
        """Hide the terminal cursor"""
        if self.is_tty:
            sys.stdout.write('\033[?25l')
            sys.stdout.flush()
    
    def show_cursor(self):
        """Show the terminal cursor"""
        if self.is_tty:
            sys.stdout.write('\033[?25h')
            sys.stdout.flush()
    
    def disable_mouse(self):
        """Disable mouse reporting"""
        if self.is_tty:
            sys.stdout.write('\033[?1000l\033[?1002l\033[?1003l')
            sys.stdout.flush()
    
    def enable_mouse(self):
        """Enable mouse reporting"""
        if self.is_tty:
            sys.stdout.write('\033[?1000h\033[?1002h\033[?1003h')
            sys.stdout.flush()
    
    def clear_screen(self):
        """Clear screen and move to home position"""
        if self.is_tty:
            sys.stdout.write('\033[2J\033[H')
            sys.stdout.flush()
    
    def get_terminal_size(self):
        """Get current terminal dimensions"""
        try:
            # Try ioctl first
            import fcntl, termios, struct
            h, w, hp, wp = struct.unpack('HHHH',
                fcntl.ioctl(self.fd, termios.TIOCGWINSZ,
                struct.pack('HHHH', 0, 0, 0, 0)))
            return w, h
        except Exception:
            # Fallback to environment variables
            try:
                w = int(os.environ.get('COLUMNS', 80))
                h = int(os.environ.get('LINES', 24))
                return w, h
            except Exception:
                return 80, 24
    
    def set_terminal_raw(self):
        """Set terminal to raw mode (non-canonical)"""
        if self.is_tty:
            self.original_settings = termios.tcgetattr(self.fd)
            tty.setraw(self.fd)
    
    def restore_terminal(self):
        """Restore original terminal settings"""
        if self.is_tty and self.original_settings:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.original_settings)
    
    def setup_signal_handlers(self):
        """Setup signal handlers for clean exit"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle termination signals"""
        self.cleanup()
        sys.exit(0)
    
    def enter_dashboard_mode(self):
        """Enter full dashboard mode (like htop)"""
        if not self.is_tty:
            return False
        
        try:
            # Save current state
            self.enable_alternate_screen()
            self.hide_cursor()
            self.disable_mouse()
            self.clear_screen()
            self.set_terminal_raw()
            self.setup_signal_handlers()
            return True
        except Exception as e:
            print(f"Failed to enter dashboard mode: {e}")
            return False
    
    def exit_dashboard_mode(self):
        """Exit dashboard mode and restore terminal"""
        if not self.is_tty:
            return
        
        try:
            self.show_cursor()
            self.enable_mouse()
            self.disable_alternate_screen()
            self.restore_terminal()
        except Exception as e:
            # Try to at least show cursor
            sys.stdout.write('\033[?25h\033[0m')
            sys.stdout.flush()
    
    def cleanup(self):
        """Cleanup terminal settings"""
        self.exit_dashboard_mode()
