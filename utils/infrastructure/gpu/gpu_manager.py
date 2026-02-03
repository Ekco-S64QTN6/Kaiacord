# gpu_manager.py
import os
import asyncio
import subprocess
from typing import Optional, Dict, Any
import time

class GPUMonitor:
    """Monitor GPU usage for the dashboard"""
    
    @staticmethod
    def get_gpu_info():
        """Get current GPU utilization using nvidia-smi"""
        try:
            # For NVIDIA GPUs
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                gpu_info = []
                for line in lines:
                    if ',' in line:
                        util, mem_used, mem_total = line.split(', ')
                        gpu_info.append({
                            'utilization': int(util.strip()),
                            'memory_used': int(mem_used.strip()),
                            'memory_total': int(mem_total.strip()),
                            'memory_percent': (int(mem_used.strip()) / int(mem_total.strip())) * 100
                        })
                return gpu_info
        except Exception as e:
            # GPU not available or nvidia-smi not installed
            pass
        return None
    
    @staticmethod
    def is_gpu_available():
        """Check if GPU is available"""
        try:
            result = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=2)
            return result.returncode == 0
        except:
            return False

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
            print(f"🔄 Triggering GPU load for {self.model_name}...")
            # CRITICAL FIX: Use keep_alive=0 to allow proper model unloading
            # Previous value of 3600 (1 hour) kept models in VRAM, preventing vision model from loading
            # This caused 7+ minute timeouts when trying to swap models
            await asyncio.wait_for(
                ollama_client.generate(model=self.model_name, prompt="", keep_alive=0),
                timeout=60.0  # 60 second timeout for large model load
            )
            print(f"✅ {self.model_name} loaded successfully")
            return True
        except asyncio.TimeoutError:
            print(f"❌ GPU load TIMED OUT after 60s for {self.model_name}")
            return False
        except Exception as e:
            print(f"❌ GPU load failed: {e}")
            return False
    
    def get_gpu_options(self, for_chat: bool = True) -> Dict[str, Any]:
        """Get optimal GPU options based on context"""
        base_options = {
            'num_gpu': -1,  # -1 = all layers to GPU
            'num_thread': 4,
        }
        
        if self.gpu_available:
            base_options['main_gpu'] = 0
            base_options['num_gpu'] = -1
        
        if for_chat:
            base_options.update({
                'num_ctx': 8192, # Balanced for context and performance
                'num_batch': 512,
                'num_predict': -1,
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
        """Patch print function to capture output"""
        original_print = __builtins__.print
        
        def new_print(*args, **kwargs):
            message = ' '.join(str(arg) for arg in args)
            self.dashboard.log_raw_output(message)
            original_print(*args, **kwargs)
        
        __builtins__.print = new_print