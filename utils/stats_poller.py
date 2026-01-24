import threading
import time
import psutil
import os
import json
from collections import deque

class RealTimeStatsPoller:
    def __init__(self, update_interval=1.5):
        self.update_interval = update_interval
        self.running = False
        self.thread = None
        self.stats = {
            'users': 0,
            'messages': 0,
            'avg_response_time': 0.0,
            'queue_size': 0,
            'active_channels': 0,
            'uptime_minutes': 0,
            'cpu_percent': 0.0,
            'memory_mb': 0.0,
            'gpu_util': 0.0,
            'gpu_memory': "0/0 MB",
            'last_update': time.time(),
            'ollama_status': "🔴 OFFLINE",
            'active_model': "None",
            'rag_documents': 0,
            'rag_size': "0 MB"
        }
        
        self.response_times = deque(maxlen=100)
        self.start_time = time.time()
        self.lock = threading.Lock()
        
    def start(self):
        """Start the polling thread"""
        self.running = True
        self.thread = threading.Thread(target=self._polling_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        """Stop the polling thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            
    def _polling_loop(self):
        """Main polling loop - runs in background thread"""
        while self.running:
            try:
                self._update_all_stats()
                time.sleep(self.update_interval)
            except Exception as e:
                # Silently fail or log to debug if needed, but avoid spamming main logs
                time.sleep(1)
                
    def _update_all_stats(self):
        """Update all statistics"""
        with self.lock:
            # Get system metrics
            try:
                self.stats['cpu_percent'] = psutil.cpu_percent(interval=0.1)
                self.stats['memory_mb'] = psutil.Process().memory_info().rss / 1024 / 1024
                self.stats['uptime_minutes'] = (time.time() - self.start_time) / 60
            except:
                pass
            
            # GPU utilization (if available)
            try:
                import subprocess
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', 
                     '--format=csv,noheader,nounits'],
                    capture_output=True, text=True, timeout=1
                )
                if result.returncode == 0:
                    util, mem_used, mem_total = result.stdout.strip().split(', ')
                    self.stats['gpu_util'] = float(util.strip())
                    self.stats['gpu_memory'] = f"{int(mem_used.strip())}/{int(mem_total.strip())} MB"
            except:
                self.stats['gpu_util'] = 0.0
                self.stats['gpu_memory'] = "N/A"
            
            # Calculate average response time
            if self.response_times:
                self.stats['avg_response_time'] = sum(self.response_times) / len(self.response_times)
                
            self.stats['last_update'] = time.time()
            
    def record_response_time(self, response_time_seconds):
        """Record a new response time measurement"""
        with self.lock:
            self.response_times.append(response_time_seconds)
        
    def get_stats(self):
        """Get current statistics (thread-safe)"""
        with self.lock:
            return self.stats.copy()
        
    def increment_messages(self):
        """Increment message count"""
        with self.lock:
            self.stats['messages'] += 1
        
    def increment_users(self):
        """Increment user count"""
        with self.lock:
            self.stats['users'] += 1
            
    def set_stat(self, key, value):
        """Set a specific statistic manually"""
        with self.lock:
            self.stats[key] = value

# Global stats poller instance
stats_poller = RealTimeStatsPoller(update_interval=1.5)
