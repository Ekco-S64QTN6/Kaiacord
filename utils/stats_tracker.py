import threading
import time
import json
import os
from datetime import datetime
from collections import defaultdict, deque

class StatsTracker:
    def __init__(self):
        self.lock = threading.RLock()
        self.stats = {
            'users': 0,
            'active_users': set(),
            'messages': 0,
            'queries': 0,
            'response_times': deque(maxlen=100),
            'avg_response_time': 0.0,
            'last_response_time': 0.0,
            'queue_size': 0,
            'active_channels': 0,
            'uptime_start': time.time(),
            'interactions_by_user': defaultdict(int),
            'interactions_by_hour': defaultdict(int),
            'last_update': time.time()
        }
        
        self.load_stats()
        
    def load_stats(self):
        """Load saved stats from disk"""
        try:
            stats_file = "./data/stats.json"
            if os.path.exists(stats_file):
                with open(stats_file, 'r') as f:
                    saved_stats = json.load(f)
                    self.stats['users'] = saved_stats.get('total_users', 0)
                    self.stats['messages'] = saved_stats.get('total_messages', 0)
        except:
            pass
    
    def save_stats(self):
        """Save stats to disk"""
        try:
            os.makedirs("./data", exist_ok=True)
            stats_file = "./data/stats.json"
            
            with self.lock:
                save_data = {
                    'total_users': self.stats['users'],
                    'total_messages': self.stats['messages'],
                    'last_saved': datetime.now().isoformat()
                }
            
            with open(stats_file, 'w') as f:
                json.dump(save_data, f, indent=2)
        except Exception as e:
            # Print error so it gets picked up by UnifiedLogger
            print(f"❌ Error saving stats: {e}")
            import traceback
            traceback.print_exc()
    
    def increment_users(self, user_id=None):
        """Increment user count"""
        with self.lock:
            self.stats['users'] += 1
            if user_id:
                self.stats['active_users'].add(user_id)
                self.stats['active_channels'] = len(self.stats['active_users'])
            self.stats['last_update'] = time.time()
        self.save_stats()
    
    def increment_messages(self, user_id=None):
        """Increment message count"""
        with self.lock:
            self.stats['messages'] += 1
            if user_id:
                self.stats['interactions_by_user'][user_id] += 1
                
                # Track by hour
                hour = datetime.now().strftime("%H:00")
                self.stats['interactions_by_hour'][hour] += 1
            self.stats['last_update'] = time.time()
        self.save_stats()
    
    def increment_queries(self):
        """Increment query count"""
        with self.lock:
            self.stats['queries'] += 1
            self.stats['last_update'] = time.time()
    
    def record_response_time(self, response_time):
        """Record a response time measurement"""
        with self.lock:
            self.stats['response_times'].append(response_time)
            self.stats['last_response_time'] = response_time
            
            # Calculate average
            if self.stats['response_times']:
                self.stats['avg_response_time'] = sum(self.stats['response_times']) / len(self.stats['response_times'])
            self.stats['last_update'] = time.time()
    
    def set_queue_size(self, size):
        """Update queue size"""
        with self.lock:
            self.stats['queue_size'] = size
            self.stats['last_update'] = time.time()

    def set_stat(self, key, value):
        """Set a specific statistic manually"""
        with self.lock:
            self.stats[key] = value
            self.stats['last_update'] = time.time()
    
    def get_stats(self):
        """Get current stats (thread-safe)"""
        with self.lock:
            stats_copy = self.stats.copy()
            
            # Calculate uptime
            stats_copy['uptime_minutes'] = (time.time() - stats_copy['uptime_start']) / 60
            stats_copy['uptime_hours'] = stats_copy['uptime_minutes'] / 60
            
            # Add active user count
            stats_copy['active_users_count'] = len(stats_copy['active_users'])
            
            # Calculate messages per minute
            uptime_minutes = max(1, stats_copy['uptime_minutes'])
            stats_copy['messages_per_minute'] = stats_copy['messages'] / uptime_minutes
            
            return stats_copy
    
    def get_top_users(self, limit=5):
        """Get top users by interaction count"""
        with self.lock:
            sorted_users = sorted(
                self.stats['interactions_by_user'].items(),
                key=lambda x: x[1],
                reverse=True
            )
            return sorted_users[:limit]
    
    def reset_stats(self):
        """Reset all stats (except totals)"""
        with self.lock:
            self.stats['active_users'].clear()
            self.stats['response_times'].clear()
            self.stats['interactions_by_hour'].clear()
            self.stats['avg_response_time'] = 0.0
            self.stats['last_response_time'] = 0.0
            self.stats['queue_size'] = 0
            self.stats['active_channels'] = 0
            self.stats['last_update'] = time.time()

# Global stats tracker
stats_tracker = StatsTracker()
