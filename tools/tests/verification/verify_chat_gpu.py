import asyncio
import sys
import os
import subprocess

# Add project root to path
sys.path.append(os.getcwd())

from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, GPUMonitor
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error
import ollama

async def verify_chat_gpu():
    model_name = "gemma3:12b"
    log_info(f"Verifying GPU offloading for chat model: {model_name}")
    
    manager = OllamaGPUManager(model_name)
    client = ollama.AsyncClient()
    
    try:
        # This calls ensure_gpu_loading which uses the options we modified
        log_info("Testing GPU model load (Immediate Unload requested)...")
        success = await manager.ensure_gpu_loading(client, keep_alive=0)
        
        if success:
            log_success(f"Confirmed: {model_name} is loading on GPU with num_gpu: -1")
            
            # Double check with nvidia-smi directly
            gpu_info = GPUMonitor.get_gpu_info()
            if gpu_info:
                log_info(f"Current GPU Utilization: {gpu_info[0]['utilization']}%")
                log_info(f"Memory Used: {gpu_info[0]['memory_used']}MB / {gpu_info[0]['memory_total']}MB")
            
            return True
        else:
            log_error(f"Failed: {model_name} did not load on GPU as expected.")
            return False
            
    except Exception as e:
        log_error(f"Error during verification: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(verify_chat_gpu())
    sys.exit(0 if success else 1)
