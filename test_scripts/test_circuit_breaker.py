import sys
import os
import time
from unittest.mock import MagicMock

# Add parent directory to path to import kaia_rag
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaia_rag import CircuitBreaker, CircuitOpenError

def test_circuit_breaker():
    print("\n--- Testing CircuitBreaker ---")
    
    # Create a circuit breaker that opens after 2 failures and resets after 2 seconds
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=2)
    
    @breaker
    def failing_function():
        print("Executing failing_function...")
        raise ValueError("Simulated failure")
        
    @breaker
    def success_function():
        print("Executing success_function...")
        return "Success"

    # 1. First failure
    print("\n1. Triggering first failure...")
    try:
        failing_function()
    except ValueError:
        print("Caught expected ValueError")
        
    assert breaker.failures == 1
    assert breaker.is_open() is False
    
    # 2. Second failure (should open the circuit)
    print("\n2. Triggering second failure...")
    try:
        failing_function()
    except ValueError:
        print("Caught expected ValueError")
        
    assert breaker.failures == 2
    assert breaker.is_open() is True
    print("✓ Circuit is now OPEN.")
    
    # 3. Call while open (should raise CircuitOpenError immediately)
    print("\n3. Calling while open...")
    try:
        failing_function()
        assert False, "Should have raised CircuitOpenError"
    except CircuitOpenError:
        print("✓ Caught expected CircuitOpenError")
        
    # 4. Wait for reset timeout
    print("\n4. Waiting for reset timeout (2s)...")
    time.sleep(2.1)
    assert breaker.is_open() is False
    print("✓ Circuit is now CLOSED (reset).")
    
    # 5. Successful call should reset failures
    print("\n5. Calling success_function...")
    result = success_function()
    assert result == "Success"
    assert breaker.failures == 0
    print("✓ Failures reset after success.")

if __name__ == "__main__":
    try:
        test_circuit_breaker()
        print("\n✨ CircuitBreaker tests passed!")
    except Exception as e:
        print(f"\n❌ Tests failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
