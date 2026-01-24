#!/usr/bin/env python3
"""
Simple file-based monitor for Kaiacord
"""
import time
import json
import os
from datetime import datetime

class FileMonitor:
    def __init__(self, log_dir="system_logs"):
        self.log_dir = log_dir
        self.current_log = os.path.join(log_dir, f"kaiacord_20260124_110811.log")
    
    def add_log(self, message):
        with open(self.current_log, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime("%H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
        print(f"[{timestamp}] {message}")
    
    def update_metrics(self, metrics):
        # Save metrics to JSON file
        metrics_file = os.path.join(self.log_dir, "metrics.json")
        with open(metrics_file, 'w') as f:
            json.dump({**metrics, 'updated_at': datetime.now().isoformat()}, f, indent=2)

# Use this in Kaiacord.py instead of BtopDashboard
monitor = FileMonitor()
