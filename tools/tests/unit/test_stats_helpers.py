"""
Test Stats Helpers Module
==========================

Quick test to verify stats_helpers module works correctly.
"""

import sys
import os

# Add parent directory to path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.stats_helpers import (
    set_stats_poller,
    safe_start_stats_poller,
    safe_stop_stats_poller,
    is_stats_poller_available,
    safe_get_stats
)

def test_stats_helpers():
    """Test stats_helpers without actual stats_poller"""
    print("Testing stats_helpers module...")
    
    # Test before registration
    print("\n1. Testing before stats_poller registration:")
    assert not is_stats_poller_available(), "Should not be available yet"
    assert not safe_start_stats_poller(), "Should return False"
    assert not safe_stop_stats_poller(), "Should return False"
    assert safe_get_stats() == {}, "Should return empty dict"
    print("✅ All tests passed - helpers work safely without stats_poller")
    
    # Mock stats_poller
    class MockStatsPoller:
        def __init__(self):
            self.running = False
            self.stats = {"test": "data"}
        
        def start(self):
            self.running = True
            print("   Mock stats_poller started")
        
        def stop(self):
            self.running = False
            print("   Mock stats_poller stopped")
        
        def get_stats(self):
            return self.stats
    
    # Test with mock
    print("\n2. Testing with mock stats_poller:")
    mock_poller = MockStatsPoller()
    set_stats_poller(mock_poller)
    
    assert is_stats_poller_available(), "Should be available after registration"
    assert safe_start_stats_poller(), "Should return True"
    assert mock_poller.running, "Mock should be running"
    assert safe_stop_stats_poller(), "Should return True"
    assert not mock_poller.running, "Mock should be stopped"
    assert safe_get_stats() == {"test": "data"}, "Should return mock stats"
    print("✅ All tests passed - helpers work with stats_poller")
    
    print("\n✅ Stats helpers module is working correctly!")
    return True

if __name__ == "__main__":
    success = test_stats_helpers()
    sys.exit(0 if success else 1)
