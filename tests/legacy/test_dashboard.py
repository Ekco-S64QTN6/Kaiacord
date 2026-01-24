import sys
import os
import curses
import time
import threading
from collections import deque

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.dashboard_final import DashboardUI
from utils.unified_logging import UnifiedLogger
from utils.stats_tracker import StatsTracker

def test_dashboard():
    # Mock logger and stats
    logger = UnifiedLogger()
    stats = StatsTracker()
    
    # Populate some dummy data
    for i in range(20):
        logger.log(f"Test log message {i}", "INFO")
        stats.increment_messages()
        stats.increment_users()
        
    print("Starting dashboard test... Press 'Q' to exit.")
    time.sleep(1)
    
    try:
        curses.wrapper(lambda stdscr: DashboardUI(stdscr, logger, stats).main_loop())
    except Exception as e:
        print(f"Dashboard crashed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_dashboard()
