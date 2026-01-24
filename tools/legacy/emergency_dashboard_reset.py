#!/usr/bin/env python3
"""
COMPLETE DASHBOARD RESET AND FIX
"""
import sys
import os
import time
from datetime import datetime

def reset_terminal():
    """Force terminal back to normal state"""
    reset_commands = [
        '\033[0m',       # Reset all attributes
        '\033[?25h',     # Show cursor
        '\033[?1049l',   # Exit alternate screen
        '\033[H',        # Home cursor
        '\033[2J',       # Clear screen
        '\033[3J',       # Clear scrollback
        '\033[?7h',      # Enable line wrap
        '\033[?12l',     # Disable cursor blinking
        '\033[?1l',      # Reset cursor keys
    ]
    
    for cmd in reset_commands:
        sys.stdout.write(cmd)
        sys.stdout.flush()
        time.sleep(0.01)
    
    sys.stdout.write("\n" + "="*80 + "\n")
    sys.stdout.write("🔄 EMERGENCY TERMINAL RESET COMPLETE\n")
    sys.stdout.write("="*80 + "\n\n")

def disable_dashboard_temporarily():
    """Patch Kaiacord.py to disable dashboard temporarily"""
    filepath = "Kaiacord.py"
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Replace dashboard initialization with a simple logger
    replacements = [
        ("dashboard = BtopDashboard()", '''# DISABLED DASHBOARD - USING SIMPLE LOGGER
class SimpleLogger:
    def __init__(self):
        self.metrics = type('obj', (object,), {
            'ollama_status': '🟢 ONLINE',
            'active_model': 'gemma3:12b',
            'uptime': '0s',
            'cpu_percent': 0.0,
            'gpu_percent': 0.0,
            'gpu_memory': '0/0 MB',
            'ram_usage': '0/0 MB',
            'active_users': 0,
            'total_messages': 0,
            'response_time': 0.0,
            'rag_documents': 0,
            'rag_size': '0 MB',
            'cache_hit_rate': 0.0,
            'request_queue': 0
        })()
    
    def add_log(self, msg): print(f"[LOG] {msg}")
    def update_metrics(self, metrics): pass
    def add_alert(self, msg, level): print(f"[{level.upper()}] {msg}")
    def run(self): pass
    async def run(self): pass

dashboard = SimpleLogger()'''),
        
        ("asyncio.create_task(dashboard.run())", "# DISABLED: asyncio.create_task(dashboard.run())"),
        
        ("patcher = BtopLoggingPatcher(dashboard)\n    patcher.patch_print()", '''# DISABLED DASHBOARD LOGGING PATCHER
    print("⚠️  Dashboard disabled - using standard logging")''')
    ]
    
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            print(f"✅ Replaced: {old[:20]}...")
        else:
            print(f"⚠️ Could not find: {old[:20]}...")
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    print("✅ Temporarily disabled dashboard in Kaiacord.py")

def create_alternative_monitor():
    """Create a simple file-based monitor instead of dashboard"""
    monitor_dir = "system_logs"
    os.makedirs(monitor_dir, exist_ok=True)
    
    monitor_script = f'''#!/usr/bin/env python3
"""
Simple file-based monitor for Kaiacord
"""
import time
import json
import os
from datetime import datetime

class FileMonitor:
    def __init__(self, log_dir="{monitor_dir}"):
        self.log_dir = log_dir
        self.current_log = os.path.join(log_dir, f"kaiacord_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    
    def add_log(self, message):
        with open(self.current_log, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime("%H:%M:%S")
            f.write(f"[{{timestamp}}] {{message}}\\n")
        print(f"[{{timestamp}}] {{message}}")
    
    def update_metrics(self, metrics):
        # Save metrics to JSON file
        metrics_file = os.path.join(self.log_dir, "metrics.json")
        with open(metrics_file, 'w') as f:
            json.dump({{**metrics, 'updated_at': datetime.now().isoformat()}}, f, indent=2)

# Use this in Kaiacord.py instead of BtopDashboard
monitor = FileMonitor()
'''
    
    with open("simple_monitor.py", "w") as f:
        f.write(monitor_script)
    
    print("✅ Created simple file-based monitor")

if __name__ == "__main__":
    print("🚨 EMERGENCY DASHBOARD FIX")
    print("="*80)
    
    reset_terminal()
    
    print("\n📝 Step 1: Temporarily disabling dashboard...")
    disable_dashboard_temporarily()
    
    print("\n📝 Step 2: Creating alternative monitor...")
    create_alternative_monitor()
    
    print("\n" + "="*80)
    print("✅ EMERGENCY FIXES APPLIED!")
    print("\n📋 NEXT STEPS:")
    print("1. Restart Kaiacord:")
    print("   python Kaiacord.py")
    print("\n2. You should see clean, left-aligned logs without dashboard")
    print("\n3. Dashboard is temporarily disabled to fix terminal corruption")
    print("\n4. Later, we can fix the dashboard properly")
    print("="*80)
