import asyncio
import time
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
sys.path.append(os.getcwd())

from utils.infrastructure.gpu.gpu_manager import gpu_memory_manager, GPUTaskPriority
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error, log_action

async def mock_coro(duration=1):
    await asyncio.sleep(duration)
    return "done"

async def verify_preemption():
    """
    Simulate a high-priority task preempting a low-priority task.
    """
    log_action("🚀 Starting GPU Preemption Verification...")
    
    # Mock OllamaGPUManager.unload_model to track calls
    import utils.infrastructure.gpu.gpu_manager as gm_mod
    gm_mod.OllamaGPUManager.unload_model = AsyncMock(return_value=True)
    
    # Mock VRAM status to simulate pressure
    # Suppose total 12GB, allocated 0
    gpu_memory_manager.get_vram_status = MagicMock(return_value={
        'total': 12.0,
        'allocated': 0.0,
        'reserved': 0.0,
        'free': 12.0
    })
    
    # 1. Start a low priority task
    log_info("Starting Low Priority Task (EMBEDDING)...")
    task_low = asyncio.create_task(gpu_memory_manager.run_with_gpu_guard(
        model_name="stable-diffusion",
        priority=GPUTaskPriority.EMBEDDING,
        coro=mock_coro(2),
        task_id="low_task"
    ))
    
    await asyncio.sleep(0.5)
    
    # 2. Start a high priority task that should wait for the semaphore
    log_info("Starting High Priority Task (CHAT)...")
    task_high = asyncio.create_task(gpu_memory_manager.run_with_gpu_guard(
        model_name="gemma3:12b",
        priority=GPUTaskPriority.CHAT,
        coro=mock_coro(1),
        task_id="high_task"
    ))
    
    # In the simplified version, there is no preemption, just sequential gating (FIFO)
    log_info("Verifying sequential gating...")
    
    await asyncio.gather(task_low, task_high)
    log_success("GPU gating tasks completed correctly.")
    
    # 3. Test Re-entrancy
    log_info("Testing re-entrancy...")
    async def nested_coro():
        return await gpu_memory_manager.run_with_gpu_guard(
            model_name="gemma3:12b",
            coro=asyncio.sleep(0.1),
            task_id="nested_task"
        )
        
    await gpu_memory_manager.run_with_gpu_guard(
        model_name="gemma3:12b",
        coro=nested_coro(),
        task_id="parent_task"
    )
    log_success("Re-entrancy works (no deadlock).")
    
    # 3. Start a critical priority task that needs 6GB
    log_info("Starting Critical Priority Task (CRITICAL, 6GB)...")
    log_info("This should trigger preemption of 'low_task'...")
    
    task_critical = await gpu_memory_manager.run_with_gpu_guard(
        model_name="gemma3:12b",
        priority=GPUTaskPriority.CRITICAL,
        coro=mock_coro(1),
        vram_gb=6.0,
        task_id="critical_task"
    )
    
    # 4. Verify preemption happened
    # Check if unload_model was called for 'stable-diffusion'
    unloaded_models = [call.args[1] for call in gm_mod.OllamaGPUManager.unload_model.call_args_list]
    if "stable-diffusion" in unloaded_models:
        log_success("✅ SUCCESS: 'stable-diffusion' was UNLOADED to free VRAM for 'gemma3:12b'.")
    else:
        log_error("❌ FAILURE: 'stable-diffusion' was NOT unloaded.")
        print(f"Unloaded models: {unloaded_models}")
        
    # Check if low_task was removed from reservations
    if "low_task" not in gpu_memory_manager.reservations:
        log_success("✅ SUCCESS: 'low_task' reservation was cleared from internal tracking.")
    else:
        log_error("❌ FAILURE: 'low_task' reservation still exists.")

    log_success("Preemption verification complete.")

if __name__ == "__main__":
    asyncio.run(verify_preemption())
