import asyncio
import time
import sys
import os
import threading

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.infrastructure.logging.unified_logging import logger

async def latency_monitor(stop_event):
    """Measures event loop latency by checking delay of a periodic task."""
    latencies = []
    while not stop_event.is_set():
        start_time = time.perf_counter()
        await asyncio.sleep(0.1)
        end_time = time.perf_counter()
        latency = (end_time - start_time) - 0.1
        latencies.append(latency)
        if latency > 0.05: # Warn if delay > 50ms
             print(f"Loop Delay Detected: {latency*1000:.2f}ms")
    return latencies

async def heavy_logger(count):
    """Generates many logs to stress the logging system."""
    print(f"Starting heavy logging of {count} messages...")
    for i in range(count):
        logger.log(f"Stress test message {i}", "DEBUG")
        if i % 100 == 0:
            await asyncio.sleep(0) # Yield periodically
    print("Heavy logging finished.")

async def simulate_rag_retrieval():
    """Simulates a RAG retrieval that might have sync blockers."""
    # This specifically tests if our async functions block
    # We'll use the real classes but maybe mock the heavy parts if needed
    print("Simulating RAG retrieval blocks...")
    # In a real scenario, we'd call the actual retriever here
    # For this test, we just want to see if logging blocks us
    await asyncio.sleep(1.0)
    print("RAG simulation finished.")

async def run_test():
    stop_event = asyncio.Event()
    
    # Start monitor
    monitor_task = asyncio.create_task(latency_monitor(stop_event))
    
    # Run stress tests
    await heavy_logger(2000)
    await simulate_rag_retrieval()
    
    # Let it settle
    await asyncio.sleep(1.0)
    
    stop_event.set()
    latencies = await monitor_task
    
    max_latency = max(latencies) if latencies else 0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    
    print("\n--- Test Results ---")
    print(f"Average Loop Latency: {avg_latency*1000:.4f}ms")
    print(f"Maximum Loop Latency: {max_latency*1000:.4f}ms")
    
    if max_latency < 0.2: # 200ms threshold
        print("✅ SUCCESS: Loop remained responsive under load.")
    else:
        print("❌ FAILURE: High loop latency detected.")

if __name__ == "__main__":
    asyncio.run(run_test())
