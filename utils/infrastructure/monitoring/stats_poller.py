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
        self.polling_in_progress = False
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
            if not self.polling_in_progress:
                try:
                    self._update_all_stats()
                except Exception as e:
                    # Silently fail
                    pass
            time.sleep(self.update_interval)
                
    def _update_all_stats(self):
        """Update all statistics (Non-blocking for the lock)"""
        self.polling_in_progress = True
        try:
            new_stats = {}
            
            # 1. System Metrics (psutil is usually fast)
            try:
                new_stats['cpu_percent'] = psutil.cpu_percent(interval=0.1)
                new_stats['memory_mb'] = psutil.Process().memory_info().rss / 1024 / 1024
                new_stats['uptime_minutes'] = (time.time() - self.start_time) / 60
            except:
                pass
            
            # 2. GPU utilization (Subprocess with 1s timeout)
            try:
                import subprocess
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', 
                     '--format=csv,noheader,nounits'],
                    capture_output=True, text=True, timeout=1.0 # STRENGTHENED TIMEOUT
                )
                if result.returncode == 0:
                    util, mem_used, mem_total = result.stdout.strip().split(', ')
                    new_stats['gpu_util'] = float(util.strip())
                    new_stats['gpu_memory'] = f"{int(mem_used.strip())}/{int(mem_total.strip())} MB"
                else:
                    new_stats['gpu_util'] = 0.0
                    new_stats['gpu_memory'] = "N/A"
            except:
                new_stats['gpu_util'] = 0.0
                new_stats['gpu_memory'] = "N/A"
            
            # 3. Ollama Status (DANGEROUS: CAN HANG)
            # We use subprocess instead of the library to ensure timeout control
            try:
                import subprocess
                # Check for running models
                # Use --format json for parsing if needed, but simple grep works for "alive"
                ps_result = subprocess.run(
                    ['ollama', 'ps'], 
                    capture_output=True, text=True, timeout=2.0
                )
                
                if ps_result.returncode == 0:
                    new_stats['ollama_status'] = "🟢 ONLINE"
                    # Simple heuristic for active model
                    lines = ps_result.stdout.strip().split('\n')
                    if len(lines) > 1: # Header + at least one model
                        model_name = lines[1].split()[0]
                        
                        # VRAM-based status correction
                        mem_used = 0
                        if 'gpu_memory' in new_stats and '/' in new_stats['gpu_memory']:
                            mem_used = int(new_stats['gpu_memory'].split('/')[0])
                        
                        if mem_used < 2048:
                            new_stats['active_model'] = "unloaded (idle)"
                        elif mem_used < 6144:
                            new_stats['active_model'] = "warming"
                        else:
                            new_stats['active_model'] = model_name
                    else:
                        new_stats['active_model'] = "unloaded (idle)"
                else:
                    new_stats['ollama_status'] = "🔴 OFFLINE"
                    new_stats['active_model'] = "None"
            except (subprocess.TimeoutExpired, Exception):
                new_stats['ollama_status'] = "🔴 TIMEOUT/OFFLINE"
                new_stats['active_model'] = "None"
                
            # 4. Apply Updates Under Lock (MINIMAL DURATION)
            with self.lock:
                # Merge new stats into main dict
                self.stats.update(new_stats)
                
                # Calculate average response time
                if self.response_times:
                    self.stats['avg_response_time'] = sum(self.response_times) / len(self.response_times)
                
                self.stats['last_update'] = time.time()
                
        finally:
            self.polling_in_progress = False
            
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
