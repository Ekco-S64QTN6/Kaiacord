import threading
import time
import psutil
import os
import json
import traceback
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
            except Exception as e:
                # Log instead of silently swallowing
                try:
                    from utils.infrastructure.logging.kaia_logger import log_debug
                    log_debug(f"Stats polling error: {e}")
                except Exception:
                    pass
            time.sleep(self.update_interval)
                
    def _init_nvml(self):
        """Initialize NVML once."""
        try:
            import pynvml
            pynvml.nvmlInit()
            self.nvml_initialized = True
        except Exception:
            self.nvml_initialized = False

    def _update_all_stats(self):
        """Update all statistics"""
        new_stats = {}
        
        # 1. System Metrics (psutil is usually fast)
        try:
            new_stats['cpu_percent'] = psutil.cpu_percent(interval=None) # Non-blocking
            new_stats['memory_mb'] = psutil.Process().memory_info().rss / 1024 / 1024
            new_stats['uptime_minutes'] = (time.time() - self.start_time) / 60
        except Exception as e:
            try:
                from utils.infrastructure.logging.kaia_logger import log_debug
                log_debug(f"psutil stats error: {e}")
            except Exception:
                pass
        
        # 2. GPU utilization (Using pynvml for efficiency)
        if not hasattr(self, 'nvml_initialized'):
            self._init_nvml()

        if self.nvml_initialized:
            try:
                import pynvml
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                
                new_stats['gpu_util'] = float(util.gpu)
                new_stats['gpu_memory'] = f"{int(mem.used / 1024 / 1024)}/{int(mem.total / 1024 / 1024)} MB"
            except Exception:
                # Fallback or transient error
                new_stats['gpu_util'] = 0.0
                new_stats['gpu_memory'] = "N/A"
        else:
             new_stats['gpu_util'] = 0.0
             new_stats['gpu_memory'] = "N/A"
        
        # 3. Ollama Status (Using library if possible, falling back to lightweight check)
        try:
            import ollama
            # Fast check without spawning subprocess
            models = ollama.list()
            if models:
                new_stats['ollama_status'] = "🟢 ONLINE"
                
                # Heuristic for active model via VRAM usage since ollama.ps() might not be available in all versions
                # or might be slow. 
                # If pynvml says > 2GB used, likely a model is loaded.
                mem_used = 0
                if 'gpu_memory' in new_stats and '/' in new_stats['gpu_memory']:
                    try:
                        mem_used = int(new_stats['gpu_memory'].split('/')[0])
                    except (ValueError, IndexError):
                        pass

                if mem_used < 2048:
                    new_stats['active_model'] = "unloaded (idle)"
                elif mem_used < 6144:
                    new_stats['active_model'] = "warming"
                else:
                    # If we really want the name, we can try ps(), but let's be careful about timeout
                    # preventing the hang we saw before.
                    # For now, just say "Active" if VRAM is high to save overhead.
                     new_stats['active_model'] = "Active (VRAM high)"
            else:
                 new_stats['ollama_status'] = "🔴 OFFLINE"
                 new_stats['active_model'] = "None"

        except Exception:
             # Fallback to offline if connection fails
             new_stats['ollama_status'] = "🔴 OFFLINE"
             new_stats['active_model'] = "None"
            
        # 4. Apply Updates Under Lock (MINIMAL DURATION)
        with self.lock:
            # Merge new stats into main dict
            self.stats.update(new_stats)
            
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
