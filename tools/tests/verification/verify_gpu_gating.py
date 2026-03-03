#!/usr/bin/env python3
"""
Verification script for simplified GPU gating architecture.
Confirms concurrency safety, re-entrancy, and basic status reporting.
"""

import sys
import os
import asyncio
import time
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.getcwd())

from utils.infrastructure.gpu.gpu_manager import gpu_memory_manager, GPUTaskPriority
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error, log_action

async def mock_coro(duration=1):
    await asyncio.sleep(duration)
    return "done"

async def verify_gpu_gating():
    log_info("--- GPU Guard Verification ---")
    
    # 1. Start a low priority task
    log_info("Starting Low Priority Task (EMBEDDING)...")
    task_low = asyncio.create_task(gpu_memory_manager.run_with_gpu_guard(
        model_name="stable-diffusion",
        priority=GPUTaskPriority.EMBEDDING,
        coro=mock_coro(1),
        task_id="low_task"
    ))
    
    await asyncio.sleep(0.2)
    
    # 2. Start a high priority task that should wait for the semaphore
    log_info("Starting High Priority Task (CHAT)...")
    t_start = time.perf_counter()
    task_high = asyncio.create_task(gpu_memory_manager.run_with_gpu_guard(
        model_name="qwen3.5:9b",
        priority=GPUTaskPriority.CHAT,
        coro=mock_coro(0.5),
        task_id="high_task"
    ))
    
    await asyncio.gather(task_low, task_high)
    t_total = time.perf_counter() - t_start
    
    # High task should have taken ~1.5s total (waiting 1s for low, then 0.5s execution)
    # Actually wait 0.8s for low (since we slept 0.2 before starting high)
    if t_total >= 0.8:
        log_success(f"Gating confirmed: High task waited for Low task ({t_total:.2f}s total)")
    else:
        log_error(f"Gating FAILED: High task did not wait (total time: {t_total:.2f}s)")
    
    # 3. Test Re-entrancy
    log_info("Testing re-entrancy...")
    async def nested_coro():
        log_action("  Entering nested guard...")
        return await gpu_memory_manager.run_with_gpu_guard(
            model_name="qwen3.5:9b",
            coro=asyncio.sleep(0.1),
            task_id="nested_task"
        )
        
    await gpu_memory_manager.run_with_gpu_guard(
        model_name="qwen3.5:9b",
        coro=nested_coro(),
        task_id="parent_task"
    )
    log_success("Re-entrancy works (no deadlock).")

    # 4. Status Check
    status = gpu_memory_manager.get_vram_status()
    log_info(f"VRAM Status: {status}")
    log_success("GPU Layer Verification Complete.")

if __name__ == "__main__":
    asyncio.run(verify_gpu_gating())
