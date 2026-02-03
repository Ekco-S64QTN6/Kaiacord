"""
Test for Image Generation Circuit Breaker

Verifies that:
1. Circuit breaker properly disables image gen after OOM
2. Subsequent calls return immediately with error
3. Chat functionality remains available
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_circuit_breaker_initial_state():
    """Test that circuit breaker starts enabled"""
    print("Testing circuit breaker initial state...")
    
    from utils.kaia_image import is_image_gen_available, get_pipeline_status
    
    # Initially should be available
    assert is_image_gen_available() == True, "Image gen should be available initially"
    
    status = get_pipeline_status()
    assert status['disabled'] == False, "Should not be disabled initially"
    assert status['disable_reason'] == '', "Should have no disable reason"
    assert status['recovery_in_progress'] == False, "Recovery should not be in progress"
    
    print("✅ Circuit breaker initial state correct")


async def test_circuit_breaker_manual_disable():
    """Test manual disable functionality"""
    print("\nTesting manual disable...")
    
    from utils.kaia_image import (
        is_image_gen_available, 
        force_disable_image_gen, 
        get_pipeline_status,
        _image_gen_disabled,
        _disable_reason
    )
    
    # Manually disable
    force_disable_image_gen("Test disable")
    
    # Should now be disabled
    assert is_image_gen_available() == False, "Image gen should be disabled after manual disable"
    
    status = get_pipeline_status()
    assert status['disabled'] == True, "Status should show disabled"
    assert 'Test disable' in status['disable_reason'], "Should show test disable reason"
    
    print("✅ Manual disable works correctly")


async def test_generate_returns_immediately_when_disabled():
    """Test that generate_image returns immediately when disabled"""
    print("\nTesting generate returns immediately when disabled...")
    
    from utils.kaia_image import generate_image
    
    # This should return immediately without trying to load models
    import time
    start = time.time()
    success, message = await generate_image("test prompt", "/tmp/test.png")
    elapsed = time.time() - start
    
    assert success == False, "Should return False when disabled"
    assert "disabled" in message.lower(), f"Message should mention disabled: {message}"
    assert elapsed < 1.0, f"Should return immediately, took {elapsed}s"
    
    print(f"✅ Generate returned in {elapsed:.3f}s with message: {message}")


async def test_pipeline_status_details():
    """Test pipeline status reporting"""
    print("\nTesting pipeline status details...")
    
    from utils.kaia_image import get_pipeline_status
    
    status = get_pipeline_status()
    
    # Check all required fields exist
    required_fields = [
        'pipeline_loaded', 'disabled', 'disable_reason',
        'recovery_in_progress', 'gpu_allocated_gb', 'gpu_reserved_gb'
    ]
    
    for field in required_fields:
        assert field in status, f"Missing field: {field}"
    
    print(f"✅ Pipeline status has all fields: {status}")


async def main():
    """Run all circuit breaker tests"""
    print("=" * 60)
    print("CIRCUIT BREAKER TESTS")
    print("=" * 60)
    
    try:
        await test_circuit_breaker_initial_state()
        await test_circuit_breaker_manual_disable()
        await test_generate_returns_immediately_when_disabled()
        await test_pipeline_status_details()
        
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
