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
            'ollama_models': [],
            'rag_documents': 0,
            'rag_size': "0 MB",
            'kb_size_mb': 0.0,
            'indexed_files': 0,
            'dreams_count': 0
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
        
        # 3. Ollama Status
        try:
            import urllib.request
            import urllib.error
            import json
            req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
            try:
                with urllib.request.urlopen(req, timeout=1.0) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    models = data.get('models', [])
                    new_stats['ollama_status'] = "🟢 ONLINE"
                    
                    # Extract up to 3 models to display
                    model_list = []
                    for m in models[:3]:
                        name = m.get('name', 'unknown').split(':')[0]
                        size_gb = m.get('size', 0) / (1024**3)
                        model_list.append(f"{name} ({size_gb:.1f}G)")
                    
                    new_stats['ollama_models'] = model_list

                    # VRAM heuristic for active model
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
                         new_stats['active_model'] = "Active (VRAM high)"
            except urllib.error.HTTPError as e:
                new_stats['ollama_status'] = f"🟡 ERR {e.code}"
                if e.code == 500:
                     new_stats['active_model'] = "Loading System RAM"
                     new_stats['ollama_models'] = ["N/A"]
                else:
                     new_stats['active_model'] = "Error"
                     new_stats['ollama_models'] = []
            except Exception:
                 new_stats['ollama_status'] = "🔴 OFFLINE"
                 new_stats['active_model'] = "None"
                 new_stats['ollama_models'] = []
        except Exception:
             new_stats['ollama_status'] = "🔴 OFFLINE"
             new_stats['active_model'] = "None"
             new_stats['ollama_models'] = []

        # 4. Custom Kaia File Stats
        current_time = time.time()
        if current_time - getattr(self, 'last_file_stats_update', 0) > 30:
            try:
                # KB Size (knowledge_base + memory/rag_storage)
                kb_path = "knowledge_base"
                rag_path = "memory/rag_storage"
                total_size = 0
                for path in [kb_path, rag_path]:
                    if os.path.exists(path):
                        for dirpath, _, filenames in os.walk(path):
                            for f in filenames:
                                fp = os.path.join(dirpath, f)
                                if not os.path.islink(fp):
                                    total_size += os.path.getsize(fp)
                new_stats['kb_size_mb'] = total_size / (1024 * 1024)
                
                # Dreams Count
                dreams_path = "memory/dream_cache.json"
                if os.path.exists(dreams_path):
                    with open(dreams_path, 'r', encoding='utf-8') as f:
                        dreams_data = json.load(f)
                        new_stats['dreams_count'] = len(dreams_data)
                
                # Indexed Files
                indexed_path = "memory/rag_storage/indexed_files.json"
                if os.path.exists(indexed_path):
                    with open(indexed_path, 'r', encoding='utf-8') as f:
                        indexed_data = json.load(f)
                        new_stats['indexed_files'] = len(indexed_data)
                
                self.last_file_stats_update = current_time
            except Exception as e:
                try:
                    from utils.infrastructure.logging.kaia_logger import log_debug
                    log_debug(f"File stats error: {e}")
                except Exception:
                    pass
            

            
        # 4. Apply Updates Under Lock (MINIMAL DURATION)
        with self.lock:
            # Merge new stats into main dict
            new_stats['uptime_minutes'] = (time.time() - self.start_time) / 60
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
