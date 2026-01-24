#!/usr/bin/env python3
"""
Test script for BtopDashboard functionality
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.btop_dashboard import BtopDashboard, KaiaMonitor

async def test_dashboard():
    """Test the dashboard in isolation"""
    print("🧪 Testing BtopDashboard...")
    
    try:
        # Create dashboard instance
        dashboard = BtopDashboard(update_interval=1.0)
        print("✅ Dashboard instantiated")
        
        # Test adding logs
        dashboard.add_log("Test log message")
        dashboard.add_alert("Test alert", "info")
        print("✅ Logs and alerts added")
        
        # Test metrics update
        dashboard.update_metrics({
            'ollama_status': '🟢 TEST',
            'active_model': 'test-model',
            'uptime': '0s',
            'cpu_percent': 10.5,
            'gpu_percent': 25.0,
            'gpu_memory': '2048/8192 MB',
            'ram_usage': '512/4096 MB'
        })
        print("✅ Metrics updated")
        
        # Test layout calculation
        dashboard.layout.get_terminal_size()
        boxes = dashboard.layout.calculate_boxes()
        print(f"✅ Layout calculated: {len(boxes)} boxes")
        
        print("\n🎉 Dashboard test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Dashboard test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    print("🚀 Starting dashboard debug...")
    
    # Test 1: Dashboard instantiation
    success1 = await test_dashboard()
    
    if success1:
        print("\n✅ Dashboard basic functionality works!")
        print("\n📋 Next steps:")
        print("1. Try running Kaiacord.py with the fixes applied")
        print("2. Check if dashboard renders in terminal")
        print("3. Monitor for event loop errors")
    else:
        print("\n❌ Dashboard has issues that need fixing")
    
    return success1

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
