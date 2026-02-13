# gpu_manager.py
import os
import asyncio
from typing import Optional, Dict, Any
import time

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
        try:
            print(f"🔄 Unloading model: {model_name}")
            await ollama_client.generate(model=model_name, keep_alive=0)
            return True
        except Exception as e:
            print(f"⚠️  Failed to unload model {model_name}: {e}")
            return False

    async def ensure_gpu_loading(self, ollama_client):
        """Ensure model loads on GPU with proper parameters"""
        if not self.gpu_available:
            print("⚠️  GPU not detected. Running on CPU.")
            return False
        
        try:
            # Force GPU load with specific settings
            gpu_options = {
                'num_gpu': -1,  # Offload all layers (clamped by model depth)
                'num_thread': 4,
                'main_gpu': 0,
                'num_ctx': 4096,
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
            ctx_size = getattr(config, 'max_context_tokens', 28000)
            timeout = getattr(config, 'model_load_timeout', 180.0)
            
            print(f"🔄 Triggering GPU load for {self.model_name} (num_ctx: {ctx_size})...")
            print(f"⏳ Waiting up to {timeout}s for Ollama to allocate VRAM...")
            
            # Use same options as chat to avoid reload
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
            print(f"❌ GPU load failed: {e}")
            return False
    
    def get_gpu_options(self, for_chat: bool = True, num_ctx: int = 28000) -> Dict[str, Any]:
        """Get optimal GPU options based on context"""
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
                'num_ctx': num_ctx, # Dynamic context sizing
                'num_batch': 512,
                'num_predict': max_tokens,
                'temperature': 0.7,
                'repeat_penalty': 1.1,
                'top_k': 40,
                'top_p': 0.9,
            })
        else:
            # For vision/other tasks
            base_options.update({
                'num_ctx': 4096,
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