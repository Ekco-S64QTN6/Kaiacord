"""
Test Logging Bridge
===================

Verify logging bridge works and breaks circular dependency.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logging_bridge import (
    LoggingBridge,
    NullLoggingBridge,
    LoggingBridgeRegistry,
    LogLevel,
    register_logging_bridge,
    unregister_logging_bridge,
    get_logging_registry
)

class TestLoggingBridge(LoggingBridge):
    """Test implementation of logging bridge"""
    def __init__(self):
        self.logs = []
        self.available = True
    
    def log(self, level, message, metadata=None):
        """Record log message"""
        self.logs.append({
            'level': level,
            'message': message,
            'metadata': metadata
        })
    
    def log_raw(self, message):
        """Record raw message"""
        self.logs.append({'raw': message})
    
    def is_available(self):
        """Check availability"""
        return self.available

def test_logging_bridge():
    """Test logging bridge"""
    print("Testing logging bridge...")
    
    # Test null bridge
    print("\n1. Testing null bridge:")
    null_bridge = NullLoggingBridge()
    null_bridge.log(LogLevel.INFO, "test")
    null_bridge.log_raw("test")
    assert not null_bridge.is_available()
    print("✅ Null bridge works (no-op)")
    
    # Test custom bridge
    print("\n2. Testing custom bridge:")
    bridge = TestLoggingBridge()
    bridge.log(LogLevel.SUCCESS, "Test message", {"key": "value"})
    bridge.log_raw("Raw message")
    
    assert len(bridge.logs) == 2
    assert bridge.logs[0]['level'] == LogLevel.SUCCESS
    assert bridge.logs[0]['message'] == "Test message"
    assert bridge.logs[0]['metadata'] == {"key": "value"}
    assert bridge.logs[1]['raw'] == "Raw message"
    print("✅ Custom bridge records logs correctly")
    
    # Test registry
    print("\n3. Testing registry:")
    registry = LoggingBridgeRegistry()
    bridge1 = TestLoggingBridge()
    bridge2 = TestLoggingBridge()
    
    registry.register(bridge1)
    registry.register(bridge2)
    
    registry.log(LogLevel.ERROR, "Error message")
    
    assert len(bridge1.logs) == 1
    assert len(bridge2.logs) == 1
    assert bridge1.logs[0]['message'] == "Error message"
    assert bridge2.logs[0]['message'] == "Error message"
    print("✅ Registry sends to all bridges")
    
    # Test unregister
    print("\n4. Testing unregister:")
    registry.unregister(bridge2)
    registry.log(LogLevel.WARNING, "Warning message")
    
    assert len(bridge1.logs) == 2
    assert len(bridge2.logs) == 1  # Shouldn't have received second message
    print("✅ Unregister works")
    
    # Test global registry
    print("\n5. Testing global registry:")
    global_registry = get_logging_registry()
    test_bridge = TestLoggingBridge()
    register_logging_bridge(test_bridge)
    
    global_registry.log(LogLevel.INFO, "Global test")
    assert len(test_bridge.logs) == 1
    
    unregister_logging_bridge(test_bridge)
    global_registry.log(LogLevel.INFO, "After unregister")
    assert len(test_bridge.logs) == 1  # Shouldn't receive second message
    print("✅ Global registry works")
    
    print("\n✅ Logging bridge module is working correctly!")
    return True

if __name__ == "__main__":
    success = test_logging_bridge()
    sys.exit(0 if success else 1)
