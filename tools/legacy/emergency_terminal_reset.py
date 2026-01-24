#!/usr/bin/env python3
"""
Emergency terminal reset for Kaiacord dashboard issues
"""
import sys
import os
import time

def reset_terminal():
    """Reset terminal to normal state"""
    print("\n" + "="*80)
    print("🔄 EMERGENCY TERMINAL RESET")
    print("="*80)
    
    # Reset ANSI escape sequences
    reset_commands = [
        '\033[0m',      # Reset all attributes
        '\033[?25h',    # Show cursor
        '\033[?1049l',  # Exit alternate screen buffer
        '\033[H',       # Move cursor to home
        '\033[2J',      # Clear screen
        '\033[3J',      # Clear scrollback
    ]
    
    for cmd in reset_commands:
        sys.stdout.write(cmd)
        sys.stdout.flush()
        time.sleep(0.05)
    
    # Clear any colorama settings
    try:
        from colorama import init, Style
        init(autoreset=True)
        sys.stdout.write(Style.RESET_ALL)
        sys.stdout.flush()
    except ImportError:
        pass
    
    print("\n✅ Terminal has been reset to normal state")
    print("   You should now see normal, left-aligned text.")
    print("="*80 + "\n")

if __name__ == "__main__":
    reset_terminal()
