import asyncio
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.btop_dashboard import BtopDashboard

async def test():
    print("Initializing dashboard...")
    dash = BtopDashboard()
    print("Dashboard created successfully")
    
    # Test adding logs
    dash.add_log("Test log 1: Dashboard initialized")
    dash.add_log("Test log 2: Checking colors")
    dash.add_alert("Test alert: System check", "info")
    
    print("Starting dashboard for 3 seconds...")
    # Start dashboard (but don't run forever)
    dash_task = asyncio.create_task(dash.run())
    
    # Let it run for 3 seconds
    await asyncio.sleep(3)
    
    # Stop it
    dash.running = False
    await dash_task
    print("\nDashboard test passed!")

if __name__ == "__main__":
    try:
        asyncio.run(test())
    except KeyboardInterrupt:
        pass
