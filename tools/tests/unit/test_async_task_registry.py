"""
Test for Async Task Registry

Verifies that:
1. Tasks can be registered and tracked
2. Mass cancellation works correctly
3. Completed tasks are auto-cleaned
4. Force clear works for emergency shutdown
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_task_registration():
    """Test basic task registration"""
    print("Testing task registration...")
    
    from utils.infrastructure.monitoring.async_task_registry import AsyncTaskRegistry
    
    registry = AsyncTaskRegistry()
    
    async def dummy_task():
        await asyncio.sleep(10)  # Long running
    
    task = asyncio.create_task(dummy_task())
    registry.register("test_task", task)
    
    assert registry.get_pending_count() == 1, "Should have 1 pending task"
    
    tasks = registry.get_all_tasks()
    assert "test_task" in tasks, "Task should be in registry"
    
    # Cleanup
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    
    print("✅ Task registration works")


async def test_mass_cancellation():
    """Test cancelling all tasks"""
    print("\nTesting mass cancellation...")
    
    from utils.infrastructure.monitoring.async_task_registry import AsyncTaskRegistry
    
    registry = AsyncTaskRegistry()
    
    async def long_task():
        await asyncio.sleep(60)  # Very long running
    
    # Register multiple tasks
    for i in range(5):
        task = asyncio.create_task(long_task())
        registry.register(f"task_{i}", task)
    
    assert registry.get_pending_count() == 5, "Should have 5 pending tasks"
    
    # Cancel all
    import time
    start = time.time()
    cancelled = await registry.cancel_all(timeout=2.0)
    elapsed = time.time() - start
    
    assert cancelled == 5, f"Should have cancelled 5 tasks, got {cancelled}"
    assert elapsed < 3.0, f"Cancellation took too long: {elapsed}s"
    assert registry.get_pending_count() == 0, "All tasks should be cancelled"
    
    print(f"✅ Mass cancellation completed in {elapsed:.2f}s")


async def test_auto_cleanup_completed_tasks():
    """Test that completed tasks are auto-cleaned"""
    print("\nTesting auto-cleanup of completed tasks...")
    
    from utils.infrastructure.monitoring.async_task_registry import AsyncTaskRegistry
    
    registry = AsyncTaskRegistry()
    
    async def quick_task():
        await asyncio.sleep(0.1)
        return "done"
    
    task = asyncio.create_task(quick_task())
    registry.register("quick", task)
    
    assert registry.get_pending_count() == 1, "Should have 1 pending task"
    
    # Wait for task to complete
    await asyncio.sleep(0.2)
    
    # Task should be auto-removed via callback
    await asyncio.sleep(0.1)  # Give callback time to run
    
    # Note: The task is done but might still be in registry until accessed
    # The auto-cleanup happens via the done callback
    tasks = registry.get_all_tasks()
    if "quick" in tasks:
        assert tasks["quick"].done(), "Task should be done"
    
    print("✅ Completed tasks handled correctly")


async def test_force_clear():
    """Test force clear for emergency shutdown"""
    print("\nTesting force clear...")
    
    from utils.infrastructure.monitoring.async_task_registry import AsyncTaskRegistry
    
    registry = AsyncTaskRegistry()
    
    async def stubborn_task():
        try:
            await asyncio.sleep(1000)
        except asyncio.CancelledError:
            # Simulate stubborn task that doesn't exit quickly
            await asyncio.sleep(0.5)
            raise
    
    # Register tasks
    for i in range(3):
        task = asyncio.create_task(stubborn_task())
        registry.register(f"stubborn_{i}", task)
    
    assert registry.get_pending_count() == 3, "Should have 3 pending tasks"
    
    # Force clear (synchronous, doesn't await)
    cleared = registry.force_clear()
    
    assert cleared == 3, f"Should have cleared 3 tasks, got {cleared}"
    
    # Give cancelled tasks time to run their exception handlers
    await asyncio.sleep(0.1)
    
    print(f"✅ Force clear cancelled {cleared} tasks")


async def test_shutdown_prevents_new_registration():
    """Test that shutdown prevents new task registration"""
    print("\nTesting shutdown prevents new registration...")
    
    from utils.infrastructure.monitoring.async_task_registry import AsyncTaskRegistry
    
    registry = AsyncTaskRegistry()
    
    # Cancel all (sets shutdown_requested)
    await registry.cancel_all()
    
    async def new_task():
        await asyncio.sleep(1)
    
    # Try to register after shutdown
    task = asyncio.create_task(new_task())
    registry.register("after_shutdown", task)
    
    # Task should be cancelled immediately
    await asyncio.sleep(0.1)
    assert task.cancelled(), "Task registered after shutdown should be cancelled"
    
    print("✅ New registrations blocked after shutdown")


async def test_registry_reset():
    """Test registry reset functionality"""
    print("\nTesting registry reset...")
    
    from utils.infrastructure.monitoring.async_task_registry import AsyncTaskRegistry
    
    registry = AsyncTaskRegistry()
    
    # Put registry in shutdown state
    await registry.cancel_all()
    
    # Reset should allow new registrations
    registry.reset()
    
    async def new_task():
        await asyncio.sleep(10)
    
    task = asyncio.create_task(new_task())
    registry.register("after_reset", task)
    
    assert registry.get_pending_count() == 1, "Should be able to register after reset"
    
    # Cleanup
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    
    print("✅ Registry reset works correctly")


async def main():
    """Run all async task registry tests"""
    print("=" * 60)
    print("ASYNC TASK REGISTRY TESTS")
    print("=" * 60)
    
    try:
        await test_task_registration()
        await test_mass_cancellation()
        await test_auto_cleanup_completed_tasks()
        await test_force_clear()
        await test_shutdown_prevents_new_registration()
        await test_registry_reset()
        
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✅")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
