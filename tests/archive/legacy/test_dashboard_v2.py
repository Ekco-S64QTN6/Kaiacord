
import curses
import time
import sys
import os
import threading
from collections import deque

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.btop_dashboard_v2 import BtopDashboard

# Mock classes
class MockLogger:
    def get_recent_logs(self, limit=10):
        return [
            {'timestamp': '10:00:00', 'type': 'INFO', 'message': 'Test log message'},
            {'timestamp': '10:00:01', 'type': 'WARNING', 'message': 'Test warning'},
            {'timestamp': '10:00:02', 'type': 'ERROR', 'message': 'Test error'}
        ] * 5
    
    def log(self, message, type="INFO"):
        pass
        
    def clear_logs(self):
        pass

class MockStatsTracker:
    def get_stats(self):
        return {
            'active_users_count': 5,
            'messages': 1234,
            'avg_response_time': 1.5,
            'uptime_minutes': 120
        }
    
    def save_stats(self):
        pass

def test_dashboard(stdscr):
    logger = MockLogger()
    tracker = MockStatsTracker()
    
    dashboard = BtopDashboard(stdscr, logger, tracker)
    
    # Run for 3 seconds then exit
    start_time = time.time()
    while time.time() - start_time < 3:
        dashboard.draw_full()
        dashboard.handle_input()
        time.sleep(0.1)

if __name__ == "__main__":
    try:
        curses.wrapper(test_dashboard)
        print("✅ Dashboard test passed (ran for 3 seconds)")
    except Exception as e:
        print(f"❌ Dashboard test failed: {e}")
        import traceback
        traceback.print_exc()
