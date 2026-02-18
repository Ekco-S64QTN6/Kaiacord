import asyncio
import time
import os
from typing import Optional, Dict, Any
from contextvars import ContextVar
from utils.infrastructure.logging.kaia_logger import log_debug, log_action

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
_gpu_context_active = ContextVar('gpu_context_active', default=False)

async def run_with_gpu_guard(model_name: str, coro, task_id: str = None):
    """
    Ultra-simple GPU concurrency gating.
    Uses a semaphore to prevent parallel heavy model calls.
    """
    if _gpu_context_active.get():
        return await coro

    token = _gpu_context_active.set(True)
    try:
        async with gpu_semaphore:
            await ModelContextMonitor.set_model(model_name)
            return await coro
    finally:
        _gpu_context_active.reset(token)

class ModelContextMonitor:
    """Tracks the currently loaded model in Ollama to prevent rapid swapping."""
    _current_model: Optional[str] = None
    _last_swap_time: float = 0
    _lock = asyncio.Lock()

    @classmethod
    async def set_model(cls, model_name: str):
        # nomic-embed-text is lightweight and can co-exist with chat models.
        # We don't want to trigger a 'swap' event for it, as that leads to VRAM clearing.
        if model_name == "nomic-embed-text":
            return False
            
        async with cls._lock:
            if cls._current_model != model_name:
                cls._current_model = model_name
                cls._last_swap_time = time.time()
                return True # Model changed
            return False # Model stayed the same

    @classmethod
    def get_current_model(cls) -> Optional[str]:
        return cls._current_model

class GPUMonitor:
    """Monitor GPU usage for the dashboard (uses pynvml for efficiency)"""
    
    _nvml_initialized = False
    
    @classmethod
    def _ensure_nvml(cls):
        """Initialize NVML once (idempotent)."""
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
    
    def __init__(self, model_name: str = "gemma3:12b"):
        self.model_name = model_name
        self.gpu_available = GPUMonitor.is_gpu_available()
        
    @staticmethod
    async def unload_model(ollama_client, model_name: str):
        """Unload a model from Ollama to free VRAM"""
        dedicated_client = None
        try:
            from utils.infrastructure.system.yaml_config import config
            timeout = getattr(config, 'llm_request_seconds', 60.0)
            print(f"🔄 Unloading model: {model_name} (timeout: {timeout}s)")
            
            if ollama_client is None:
                import ollama
                dedicated_client = ollama.AsyncClient(timeout=timeout)
                client_to_use = dedicated_client
            else:
                client_to_use = ollama_client
                
            await client_to_use.generate(model=model_name, keep_alive=0)
            return True
        except Exception as e:
            print(f"⚠️  Failed to unload model {model_name}: {e}")
            return False
        finally:
            if dedicated_client:
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
                # Get running models
                resp = await client_to_use.ps()
                # resp is usually a dict with 'models' key or a list depending on version
                if isinstance(resp, dict) and 'models' in resp:
                    running_models = [m['name'] for m in resp['models']]
                elif isinstance(resp, list):
                    running_models = [m.name if hasattr(m, 'name') else m.get('name') for m in resp]
            except Exception as e:
                print(f"⚠️  Could not list running models via ps(): {e}")
                # Fallback: we might not know what's running, 
                # but we can try to unload known ones
                from utils.infrastructure.system.yaml_config import config
                running_models = [config.chat_model, "gemma2:2b", "nomic-embed-text"]

            if not running_models:
                print("✅ No models running in Ollama.")
                return True

            print(f"🔄 Unloading {len(running_models)} models from VRAM: {', '.join(running_models)}")
            for model in running_models:
                try:
                    # Setting keep_alive=0 unloads the model
                    await client_to_use.generate(model=model, keep_alive=0)
                    print(f"  ✅ Unloaded {model}")
                except Exception as e:
                    print(f"  ❌ Failed to unload {model}: {e}")
            
            return True
        except Exception as e:
            print(f"⚠️  Global VRAM release failed: {e}")
            return False
        finally:
            if 'dedicated_client' in locals() and dedicated_client:
                await dedicated_client.close()

    async def ensure_gpu_loading(self, ollama_client):
        """Ensure model loads on GPU with proper parameters"""
        if not self.gpu_available:
            print("⚠️  GPU not detected. Running on CPU.")
            return False
        
        try:
            from utils.infrastructure.system.yaml_config import config
            # Force GPU load with specific settings
            gpu_options = {
                'num_gpu': -1,  # Offload all layers (clamped by model depth)
                'num_thread': 4,
                'main_gpu': 0,
                'num_ctx': config.max_context_tokens,
                'num_batch': 512,
            }
            
            # Check if client is closed
            if hasattr(ollama_client, '_client') and ollama_client._client.is_closed:
                return False

            print("🔄 Testing GPU model load...")
            test_response = await ollama_client.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": "test"}],
                options=gpu_options,
                stream=False
            )
            
            # Verify GPU usage
            gpu_info = GPUMonitor.get_gpu_info()
            if gpu_info and gpu_info[0]['utilization'] > 0:
                print(f"✅ GPU active: {gpu_info[0]['utilization']}% utilization")
                return True
            else:
                print("⚠️  GPU may not be utilized fully")
                return True  # Still return True as call succeeded
                
        except Exception as e:
            print(f"❌ GPU load test failed: {e}")
            return False

    async def load_only(self, ollama_client):
        """Trigger a model load without a full chat test"""
        if not self.gpu_available:
            return False
        try:
            from utils.infrastructure.system.yaml_config import config
            ctx_size = config.max_context_tokens
            timeout = getattr(config, 'model_load_timeout', 180.0)
            
            print(f"🔄 Triggering GPU load for {self.model_name} (num_ctx: {ctx_size})...")
            print(f"⏳ Waiting up to {timeout}s for Ollama to allocate VRAM...")
            
            # Use fixed config
            options = self.get_gpu_options(for_chat=True, num_ctx=ctx_size)
            
            # Start timer
            start_time = time.time()
            
            await asyncio.wait_for(
                ollama_client.generate(model=self.model_name, prompt="", keep_alive=-1, options=options),
                timeout=timeout
            )
            
            elapsed = time.time() - start_time
            print(f"✅ {self.model_name} pre-warmed and locked in VRAM ({elapsed:.1f}s)")
            return True
        except asyncio.TimeoutError:
            print(f"❌ GPU load TIMED OUT after {timeout}s for {self.model_name}")
            print(f"⚠️  This model with {ctx_size} context may be too large for your VRAM.")
            return False
        except Exception as e:
            if "out of memory" in str(e).lower() or "allocation failed" in str(e).lower():
                 print(f"❌ CRITICAL: Model load failed due to OOM!")
                 print(f"⚠️  Reducing context size might help.")
            print(f"❌ GPU load failed: {e}")
            return False
    
    def get_gpu_options(self, for_chat: bool = True, num_ctx: Optional[int] = None) -> Dict[str, Any]:
        """Get optimal GPU options based on context"""
        from utils.infrastructure.system.yaml_config import config
        if num_ctx is None:
            num_ctx = config.max_context_tokens
        base_options = {
            'num_gpu': -1,  # -1 = all layers to GPU
            'num_thread': 4,
        }
        
        if self.gpu_available:
            base_options['main_gpu'] = 0
            base_options['num_gpu'] = -1
        
        if for_chat:
            from utils.infrastructure.system.yaml_config import config
            max_tokens = getattr(config, 'max_response_tokens', 2048)
            
            base_options.update({
                'num_ctx': num_ctx, # Unified context size from config
                'num_batch': 512,
                'num_predict': max_tokens,
                'temperature': 0.7,
                'repeat_penalty': 1.1,
                'top_k': 40,
                'top_p': 0.9,
            })
        else:
            # For vision/other tasks - pull from config default
            from utils.infrastructure.system.yaml_config import config
            base_options.update({
                'num_ctx': config.max_context_tokens,
                'num_batch': 256,
            })
        
        return base_options

class LoggingPatcher:
    """Simple logging patcher for gpu_manager compatibility"""
    def __init__(self, dashboard):
        self.dashboard = dashboard
    
    def patch_print(self):
        """
        Patch print function to capture output for the dashboard.
        
        WARNING: This mutates `__builtins__.print` globally. All print() calls
        across the entire process will be routed through the dashboard logger
        after this is called. This is intentional — gpu_manager and other modules
        use print() specifically so this patcher can capture their output.
        """
        original_print = __builtins__.print
        
        def new_print(*args, **kwargs):
            message = ' '.join(str(arg) for arg in args)
            self.dashboard.log_raw_output(message)
            original_print(*args, **kwargs)
        
        __builtins__.print = new_print