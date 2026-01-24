import curses
import sys
import traceback

def safe_curses_wrapper(func, *args, **kwargs):
    """Safe wrapper that handles all curses errors"""
    try:
        # Initialize curses safely
        stdscr = curses.initscr()
        stdscr.clear()
        
        # Run the function
        result = func(stdscr, *args, **kwargs)
        
        # Clean up
        curses.nocbreak()
        stdscr.keypad(False)
        curses.echo()
        curses.endwin()
        
        return result
        
    except Exception as e:
        # If anything goes wrong, try to restore terminal
        try:
            curses.nocbreak()
            curses.echo()
            curses.endwin()
        except:
            pass
        
        # Print error
        sys.stdout.write("\033[0m\033[2J\033[H\033[?25h")
        sys.stdout.write(f"\n❌ Dashboard crashed: {e}\n")
        sys.stdout.write(traceback.format_exc())
        sys.stdout.flush()
        
        return None
