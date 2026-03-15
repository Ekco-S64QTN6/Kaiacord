import os
import time
import uuid
import asyncio
import threading
from typing import Optional, Dict, Any
from enum import Enum
from contextvars import ContextVar
from utils.infrastructure.logging.kaia_logger import log_debug, log_action, log_info, log_error, log_warning

# Global GPU Concurrency Guard
# [ARCHITECTURAL NOTE]: We deliberately use a simple asyncio.Semaphore(1) instead
# of complex VRAM reservation/tracking systems.
# Rationale:
# 1. Simplicity = Stability. Complex model swapping logic caused deadlocks.
# 2. Modern Hardware: On 12GB+ GPUs, our 8GB models + context fit comfortably.
# 3. Concurrency Control: The semaphore alone is sufficient to prevent parallel
#    heavy inference tasks from thrashing the KV cache or overrunning VRAM.
# DO NOT re-implement "reservation" logic unless adding multi-model vision swapping.
gpu_semaphore = asyncio.Semaphore(1)

# Track if the current task is already inside a GPU-guarded block
gpu_context_active = ContextVar('gpu_context_active', default=False)

class GPUTaskPriority(Enum):
    """Priority levels for GPU tasks (Simplified for stability)"""
    CRITICAL = 0
    CHAT = 1
    EMBEDDING = 2

async def run_with_gpu_guard(model_name: str, coro, task_id: str = None, priority: GPUTaskPriority = GPUTaskPriority.CHAT):
    """
    Consolidated GPU concurrency gating.
    Uses a semaphore to prevent parallel heavy model calls and supports re-entrancy.
    """
    if task_id is None:
        task_id = f"gpu_{uuid.uuid4().hex[:6]}"

    if gpu_context_active.get():
        return await coro

    token = gpu_context_active.set(True)
    try:
        async with gpu_semaphore:
            await ModelContextMonitor.set_model(model_name)
            t_start = time.perf_counter()
            log_debug(f"[{task_id}] Executing protected GPU coro: {model_name} (Priority: {priority.name})")
            result = await coro
            log_debug(f"[{task_id}] Finished in {time.perf_counter() - t_start:.2f}s")
            return result
    finally:
        gpu_context_active.reset(token)

class ModelContextMonitor:
    """Tracks the currently loaded model in Ollama to prevent rapid swapping."""
    _current_model: Optional[str] = None
    _last_swap_time: float = 0
    _lock = asyncio.Lock()

    @classmethod
    async def set_model(cls, model_name: str):
        # nomic-embed-text is lightweight and can co-exist with chat models.
        # We don't want to trigger a 'swap' event for it, as that leads to VRAM clearing.
        if model_name in ("nomic-embed-text", "nomic-embed-text-cpu"):
            return False
            
        async with cls._lock:
            if cls._current_model != model_name:
                log_debug(f"Model context swap: {cls._current_model} -> {model_name}")
                cls._current_model = model_name
                cls._last_swap_time = time.perf_counter()
                return True # Model changed
            return False # Model stayed the same

    @classmethod
    def get_current_model(cls) -> Optional[str]:
        return cls._current_model

class GPUMonitor:
    """Monitor GPU usage for the dashboard (uses pynvml for efficiency)"""
    
    _nvml_initialized = False
    _nvml_lock = threading.Lock()
    
    @classmethod
    def _ensure_nvml(cls):
        """Initialize NVML once (Thread-safe)."""
        if not cls._nvml_initialized:
            with cls._nvml_lock:
                if not cls._nvml_initialized:
                    try:
                        import pynvml
                        pynvml.nvmlInit()
                        cls._nvml_initialized = True
                    except Exception:
                        cls._nvml_initialized = False
        return cls._nvml_initialized
    
    @staticmethod
    def get_gpu_info():
        """Get current GPU utilization using pynvml."""
        try:
            if not GPUMonitor._ensure_nvml():
                return None
            import pynvml
            device_count = pynvml.nvmlDeviceGetCount()
            gpu_info = []
            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                mem_used_mb = int(mem.used / 1024 / 1024)
                mem_total_mb = int(mem.total / 1024 / 1024)
                gpu_info.append({
                    'utilization': int(util.gpu),
                    'memory_used': mem_used_mb,
                    'memory_total': mem_total_mb,
                    'memory_percent': (mem_used_mb / mem_total_mb) * 100 if mem_total_mb > 0 else 0
                })
            return gpu_info if gpu_info else None
        except Exception:
            return None
    
    @staticmethod
    def is_gpu_available():
        """Check if GPU is available via pynvml."""
        return GPUMonitor._ensure_nvml()

class OllamaGPUManager:
    """Manage Ollama GPU settings and model loading"""
    
    def __init__(self, model_name: str = None):
        if model_name is None:
            from utils.infrastructure.system.yaml_config import config
            model_name = config.chat_model
        self.model_name = model_name
        self.gpu_available = GPUMonitor.is_gpu_available()
        
    @staticmethod
    async def unload_model(ollama_client, model_name: str):
        """Unload a model from Ollama to free VRAM"""
        dedicated_client = None
        try:
            from utils.infrastructure.system.yaml_config import config
            timeout = getattr(config, 'llm_request_seconds', 60.0)
            log_info(f"🔄 Unloading model: {model_name} (timeout: {timeout}s)")
            
            if ollama_client is None:
                import ollama
                dedicated_client = ollama.AsyncClient(timeout=timeout)
                client_to_use = dedicated_client
            else:
                client_to_use = ollama_client
                
            await client_to_use.generate(model=model_name, keep_alive=0)
            return True
        except Exception as e:
            log_info(f"⚠️  Failed to unload model {model_name}: {e}")
            return False
        finally:
            if dedicated_client:
                # Some versions of AsyncClient might not have .close()
                if hasattr(dedicated_client, 'close') and callable(dedicated_client.close):
                    await dedicated_client.close()

    @staticmethod
    async def unload_all_models(ollama_client=None):
        """Unload ALL running models from Ollama to reclaim all VRAM."""
        try:
            dedicated_client = None
            if ollama_client is None:
                import ollama
                dedicated_client = ollama.AsyncClient(timeout=30.0)
                client_to_use = dedicated_client
            else:
                client_to_use = ollama_client
            
            # 1. Try to list running models using ps()
            running_models = []
            try:
                resp = await client_to_use.ps()
                if hasattr(resp, 'models'):
                    # Modern Ollama client ProcessResponse object
                    running_models = [m.model for m in resp.models]
                elif isinstance(resp, dict) and 'models' in resp:
                    running_models = [m['name'] for m in resp['models']]
                elif isinstance(resp, list):
                    running_models = [m.name if hasattr(m, 'name') else m.get('name') for m in resp]
            except Exception as e:
                log_info(f"⚠️  Could not list running models via ps(): {e}")
                # Fallback list
                from utils.infrastructure.system.yaml_config import config
                running_models = [
                    config.chat_model, 
                    config.get('models.classification_model', 'gemma2:2b'),
                    config.get('models.embedding', 'nomic-embed-text-cpu'),
                ]

            # Filter duplicates and empty values
            running_models = list(set([m for m in running_models if m]))

            if not running_models:
                log_info("✅ No models running in Ollama.")
                return True

            log_info(f"🔄 Unloading {len(running_models)} models from VRAM: {', '.join(running_models)}")
            import aiohttp
            async with aiohttp.ClientSession() as session:
                for model in running_models:
                    try:
                        # Direct HTTP POST guarantees the keep_alive=0 request is dispatched 
                        # instantly, bypassing any blocking Python client queues.
                        async with session.post(
                            "http://127.0.0.1:11434/api/generate",
                            json={"model": model, "keep_alive": 0},
                            timeout=aiohttp.ClientTimeout(total=5.0)
                        ) as resp:
                            if resp.status == 200:
                                log_info(f"  ✅ Unloaded {model}")
                            else:
                                log_info(f"  ⚠️  Unload API returned {resp.status} for {model}")
                    except asyncio.TimeoutError:
                        log_info(f"  ⚠️  Unload timed out for {model} (Ollama dropped early?)")
                    except Exception as e:
                        log_info(f"  ❌ Failed to unload {model}: {e}")
            
            return True
        except Exception as e:
            log_info(f"⚠️  Global VRAM release failed: {e}")
            return False
        finally:
            if 'dedicated_client' in locals() and dedicated_client:
                if hasattr(dedicated_client, 'close') and callable(dedicated_client.close):
                    await dedicated_client.close()

    async def ensure_gpu_loading(self, ollama_client, keep_alive: int = -1):
        """Ensure model loads on GPU with proper parameters"""
        if not self.gpu_available:
            log_info("⚠️  GPU not detected. Running on CPU.")
            return False
        
        try:
            from utils.infrastructure.system.yaml_config import config
            timeout = getattr(config, 'model_load_timeout', 300.0)
            # Force GPU load with specific settings
            options = self.get_gpu_options(for_chat=True)
            
            # Check if client is closed
            if hasattr(ollama_client, '_client') and ollama_client._client.is_closed:
                return False

            log_info(f"🔄 Testing GPU model load (Lightweight, keep_alive={keep_alive})...")
            await asyncio.wait_for(
                ollama_client.generate(model=self.model_name, prompt="", keep_alive=keep_alive, options=options),
                timeout=timeout
            )
            
            # Verify GPU usage
            gpu_info = GPUMonitor.get_gpu_info()
            if gpu_info and gpu_info[0]['utilization'] > 0:
                log_info(f"✅ GPU active: {gpu_info[0]['utilization']}% utilization")
                return True
            else:
                log_info("✅ GPU load confirmed via generate.")
                return True 
                
        except Exception as e:
            log_info(f"❌ GPU load test failed: {e}")
            return False

    async def load_only(self, ollama_client):
        """Trigger a model load without a full chat test"""
        if not self.gpu_available:
            return False
        try:
            from utils.infrastructure.system.yaml_config import config
            ctx_size = config.max_context_tokens
            timeout = getattr(config, 'model_load_timeout', 300.0)
            
            log_info(f"🔄 Triggering GPU load for {self.model_name} (num_ctx: {ctx_size})...")
            log_info(f"⏳ Waiting up to {timeout}s for Ollama to allocate VRAM...")
            
            # Use fixed config
            options = self.get_gpu_options(for_chat=True, num_ctx=ctx_size)
            
            # Start timer
            start_time = time.time()
            
            await asyncio.wait_for(
                ollama_client.generate(model=self.model_name, prompt="", keep_alive=-1, options=options),
                timeout=timeout
            )
            
            elapsed = time.time() - start_time
            log_info(f"✅ {self.model_name} pre-warmed and locked in VRAM ({elapsed:.1f}s)")
            return True
        except asyncio.TimeoutError:
            log_info(f"❌ GPU load TIMED OUT after {timeout}s for {self.model_name}")
            log_info(f"⚠️  This model with {ctx_size} context may be too large for your VRAM.")
            return False
        except Exception as e:
            if "out of memory" in str(e).lower() or "allocation failed" in str(e).lower():
                 log_info(f"❌ CRITICAL: Model load failed due to OOM!")
                 log_info(f"⚠️  Reducing context size might help.")
            log_info(f"❌ GPU load failed: {e}")
            return False
    
    def get_gpu_options(self, for_chat: bool = True, num_ctx: Optional[int] = None) -> Dict[str, Any]:
        """Get optimal GPU options based on context, ensuring consistency for VRAM lock."""
        from utils.infrastructure.system.yaml_config import config
        if num_ctx is None:
            num_ctx = config.max_context_tokens
            
        # [CONSISTENCY GUARD]: We include num_thread and main_gpu in ALL calls (even if default)
        # to prevent Ollama from seeing different options objects and triggering re-loads.
        base_options = {
            'num_gpu': 99,
            'num_thread': config.num_thread,
            'main_gpu': 0, # Explicit 0 to keep fingerprint same
        }
        log_debug(f"[GPUMgr] Generated options (for_chat={for_chat}): {base_options}")
        
        if for_chat:
            max_tokens = getattr(config, 'max_response_tokens', 2048)
            base_options.update({
                'num_ctx': num_ctx, 
                'num_predict': max_tokens,
                'temperature': getattr(config, 'generation_base_temperature', 0.8),
                'top_p': 0.9,
            })
        else:
            base_options.update({
                'num_ctx': num_ctx,
            })
        
        return base_options

class GPUMemoryManager:
    """
    Simplified GPU memory status and utility class.
    Consolidated from legacy redundant file.
    """
    def __init__(self):
        self._torch = None
        self._cuda_available = None

    def _lazy_import_torch(self):
        if self._torch is None:
            try:
                import torch
                self._torch = torch
                self._cuda_available = torch.cuda.is_available()
            except ImportError:
                self._torch = False
                self._cuda_available = False
        return self._torch
    
    def is_cuda_available(self) -> bool:
        self._lazy_import_torch()
        return self._cuda_available
    
    def get_vram_status(self) -> dict:
        torch = self._lazy_import_torch()
        if not torch or not self.is_cuda_available():
            return {'total': 0.0, 'allocated': 0.0, 'free': 0.0}
        try:
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            allocated = torch.cuda.memory_allocated() / 1024**3
            free = total - allocated
            return {'total': total, 'allocated': allocated, 'free': free}
        except Exception:
            return {'total': 0.0, 'allocated': 0.0, 'free': 0.0}

    async def run_with_gpu_guard(self, model_name: str, coro, task_id: str = None, priority: GPUTaskPriority = GPUTaskPriority.CHAT, vram_gb: float = 0.0):
        """Pass-through to the global guard function for backward compatibility."""
        return await run_with_gpu_guard(model_name, coro, task_id=task_id, priority=priority)

# Global instances for compatibility
gpu_memory_manager = GPUMemoryManager()