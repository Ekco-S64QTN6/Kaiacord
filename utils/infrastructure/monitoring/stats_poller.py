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
            'log_size_mb': 0.0,
            'indexed_files': 0,
            'dreams_count': 0,
            'beliefs_count': 0,
            'anchors_count': 0,
            'relationship_count': 0
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
            # pynvml unavailable — fall back to nvidia-smi subprocess
            try:
                import subprocess
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total',
                     '--format=csv,noheader,nounits'],
                    capture_output=True, text=True, timeout=2.0
                )
                if result.returncode == 0:
                    parts = result.stdout.strip().split(',')
                    if len(parts) >= 3:
                        new_stats['gpu_util'] = float(parts[0].strip())
                        mem_used = int(parts[1].strip())
                        mem_total = int(parts[2].strip())
                        new_stats['gpu_memory'] = f"{mem_used}/{mem_total} MB"
                    else:
                        new_stats['gpu_util'] = 0.0
                        new_stats['gpu_memory'] = "N/A"
                else:
                    new_stats['gpu_util'] = 0.0
                    new_stats['gpu_memory'] = "N/A"
            except Exception:
                new_stats['gpu_util'] = 0.0
                new_stats['gpu_memory'] = "N/A"
        
        # 3. Ollama Status
        try:
            import urllib.request
            import urllib.error
            import json
            from utils.infrastructure.system.yaml_config import config
            
            # Prefer api/ps to see what's actually running
            req_ps = urllib.request.Request("http://127.0.0.1:11434/api/ps")
            try:
                with urllib.request.urlopen(req_ps, timeout=5.0) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    running_models = data.get('models', [])
                    new_stats['ollama_status'] = "🟢 ONLINE"
                    
                    # Target models for filtering
                    target_models = [
                        config.chat_model,          # gemma4:12b
                        config.embedding_model,     # nomic-embed-text-cpu  
                        config.get('models.classification_model', 'gemma2:2b')
                    ]
                    
                    model_list = []
                    seen_names = set()
                    
                    # 1. Add running target models first
                    for m in running_models:
                        full_name = m.get('name', '')
                        base_name = full_name.split(':')[0]
                        if any(target in full_name or full_name in target for target in target_models):
                            size_gb = m.get('size', 0) / (1024**3)
                            # Indicate if it's in VRAM
                            vram = m.get('size_vram', 0)
                            vram_tag = " (VRAM)" if vram > 0 else " (RAM)"
                            model_list.append(f"{base_name} {size_gb:.1f}G{vram_tag}")
                            seen_names.add(base_name)
                    
                    # 2. If nothing is running, fall back to api/tags to show what's available
                    if not model_list:
                        req_tags = urllib.request.Request("http://127.0.0.1:11434/api/tags")
                        with urllib.request.urlopen(req_tags, timeout=1.0) as tag_resp:
                            tag_data = json.loads(tag_resp.read().decode('utf-8'))
                            all_models = tag_data.get('models', [])
                            for m in all_models:
                                name = m.get('name', '').split(':')[0]
                                if name in [t.split(':')[0] for t in target_models]:
                                    size_gb = m.get('size', 0) / (1024**3)
                                    model_list.append(f"{name} {size_gb:.1f}G (off)")
                    
                    new_stats['ollama_models'] = model_list

                    # Determine active model status
                    # PRIORITY 1: Check api/ps for the actual configured chat model
                    active_chat_name = None
                    for m in running_models:
                        if config.chat_model in m.get('name', ''):
                            active_chat_name = config.chat_model
                            break
                    
                    if active_chat_name:
                        new_stats['active_model'] = active_chat_name
                    else:
                        # PRIORITY 2: Fall back to VRAM heuristic if api/ps is inconclusive
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
                try:
                    from utils.infrastructure.logging.kaia_logger import log_debug
                    log_debug(f"Ollama check HTTPError: {e}")
                except Exception:
                    pass
                new_stats['ollama_status'] = f"🟡 ERR {e.code}"
                if e.code == 500:
                     new_stats['active_model'] = "Loading System RAM"
                     new_stats['ollama_models'] = ["N/A"]
                else:
                     new_stats['active_model'] = "Error"
                     new_stats['ollama_models'] = []
            except Exception as e:
                try:
                    from utils.infrastructure.logging.kaia_logger import log_debug
                    log_debug(f"Ollama check inner exception: {e}", exc_info=True)
                except Exception:
                    pass
                new_stats['ollama_status'] = "🔴 OFFLINE"
                new_stats['active_model'] = "None"
                new_stats['ollama_models'] = []
        except Exception as e:
            try:
                from utils.infrastructure.logging.kaia_logger import log_debug
                log_debug(f"Ollama check outer exception: {e}", exc_info=True)
            except Exception:
                pass
            new_stats['ollama_status'] = "🔴 OFFLINE"
            new_stats['active_model'] = "None"
            new_stats['ollama_models'] = []

        # 4. Custom Kaia File Stats (Throttled to every 30s)
        current_time = time.time()
        if current_time - getattr(self, 'last_file_stats_update', 0) > 30:
            # KB/RAG Size
            try:
                kb_path = "knowledge_base"
                rag_path = "memory/rag_storage"
                total_size = 0
                for path in [kb_path, rag_path]:
                    try:
                        if os.path.exists(path):
                            for dirpath, _, filenames in os.walk(path):
                                for f in filenames:
                                    fp = os.path.join(dirpath, f)
                                    try:
                                        if not os.path.islink(fp):
                                            total_size += os.path.getsize(fp)
                                    except (FileNotFoundError, OSError):
                                        pass
                    except Exception as e:
                        try:
                            from utils.infrastructure.logging.kaia_logger import log_debug
                            log_debug(f"KB walk error for {path}: {e}")
                        except Exception:
                            pass
                new_stats['kb_size_mb'] = total_size / (1024 * 1024)
                new_stats['rag_size'] = f"{new_stats['kb_size_mb']:.1f} MB"
            except Exception as e:
                new_stats['kb_size_mb'] = 0.0
                new_stats['rag_size'] = "0 MB"

            # Dreams Count
            try:
                dreams_kb_path = "knowledge_base/kaia_dreams"
                total_dreams = 0
                if os.path.exists(dreams_kb_path):
                    for subdir in ['books', 'interactions', 'injected', 'other']:
                        sub_path = os.path.join(dreams_kb_path, subdir)
                        if os.path.exists(sub_path):
                            try:
                                total_dreams += len([f for f in os.listdir(sub_path) if f.startswith('dream_') and f.endswith('.md')])
                            except (FileNotFoundError, OSError):
                                pass
                new_stats['dreams_count'] = total_dreams
            except Exception:
                new_stats['dreams_count'] = 0

            # Indexed Files — reads file_manifest.json (or legacy indexed_files.json)
            try:
                indexed_path = "memory/rag_storage/file_manifest.json"
                if not os.path.exists(indexed_path):
                    indexed_path = "memory/rag_storage/indexed_files.json"
                if os.path.exists(indexed_path):
                    with open(indexed_path, 'r', encoding='utf-8') as f:
                        indexed_data = json.load(f)
                        new_stats['indexed_files'] = len(indexed_data)
                else:
                    new_stats['indexed_files'] = 0
            except Exception:
                new_stats['indexed_files'] = 0

            # Count beliefs
            try:
                beliefs_path = "memory/beliefs.json"
                if os.path.exists(beliefs_path):
                    with open(beliefs_path, 'r', encoding='utf-8') as f:
                        beliefs_data = json.load(f)
                        new_stats['beliefs_count'] = len(beliefs_data)
                else:
                    new_stats['beliefs_count'] = 0
            except Exception:
                new_stats['beliefs_count'] = 0

            # Count anchors
            try:
                anchors_path = "memory/anchors.json"
                if os.path.exists(anchors_path):
                    with open(anchors_path, 'r', encoding='utf-8') as f:
                        anchors_data = json.load(f)
                        new_stats['anchors_count'] = len(anchors_data)
                else:
                    new_stats['anchors_count'] = 0
            except Exception:
                new_stats['anchors_count'] = 0

            # Count relationships
            try:
                rel_dir = "memory/relationships"
                if os.path.exists(rel_dir):
                    new_stats['relationship_count'] = len([f for f in os.listdir(rel_dir) if f.endswith('.json')])
                else:
                    new_stats['relationship_count'] = 0
            except Exception:
                new_stats['relationship_count'] = 0

            # Log File Size
            try:
                log_path = "logs/kaiacord.log"
                if os.path.exists(log_path):
                    new_stats['log_size_mb'] = os.path.getsize(log_path) / (1024 * 1024)
                else:
                    new_stats['log_size_mb'] = 0.0
            except Exception:
                new_stats['log_size_mb'] = 0.0

            # Set self.last_file_stats_update so it is throttled correctly
            self.last_file_stats_update = current_time
            
        # Always update uptime (calculated from poller start time)
        new_stats['uptime_minutes'] = (time.time() - self.start_time) / 60
            
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
