import time
import sys
import threading
from collections import OrderedDict
from datetime import datetime

class ConsolidatedLogger:
    def __init__(self, max_retention=100):
        self.lock = threading.Lock()
        self.max_retention = max_retention
        self.message_buffer = OrderedDict()
        self.last_print_time = {}
        self.duplicate_window = 0.1  # 100ms window for duplicate detection
        self.dashboard_mode = False
        
    def set_dashboard_mode(self, enabled: bool):
        """Enable/disable dashboard mode (suppresses stdout)"""
        self.dashboard_mode = enabled
        
    def log(self, message, log_type="INFO", force_print=False):
        """Centralized logging with duplicate suppression"""
        current_time = time.time()
        # Create a key that ignores the timestamp part if it exists in the message
        # This helps deduplicate "12:00:00 Message" vs "Message"
        clean_msg = message
        if " | " in message and message[:8].replace(':', '').isdigit():
             clean_msg = message.split(" | ", 1)[1]
             
        message_key = f"{clean_msg}_{log_type}"
        
        with self.lock:
            # Check if this is a duplicate within the time window
            if message_key in self.last_print_time:
                time_diff = current_time - self.last_print_time[message_key]
                if time_diff < self.duplicate_window and not force_print:
                    return None  # Skip duplicate
            
            # Update tracking
            self.last_print_time[message_key] = current_time
            
            # Store in buffer (for UI display)
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_message = self._format_message(timestamp, clean_msg, log_type)
            
            # Store only if it's not already in buffer (exact match)
            if formatted_message not in self.message_buffer:
                self.message_buffer[formatted_message] = current_time
                
                # Keep buffer size manageable
                if len(self.message_buffer) > self.max_retention:
                    self.message_buffer.popitem(last=False)
            
            return formatted_message
    
    def _format_message(self, timestamp, message, log_type):
        """Single format for all log messages"""
        type_symbols = {
            "ACTION": "⚡",
            "SUCCESS": "✅", 
            "ERROR": "❌",
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "CRITICAL": "🚨",
            "DEBUG": "🐛"
        }
        symbol = type_symbols.get(log_type, "•")
        # If message already has the symbol, don't add it again
        if symbol in message:
            return f"{timestamp} | {message}"
        return f"{timestamp} | {symbol} {log_type}: {message}"
    
    def get_recent_logs(self, count=20):
        """Get recent logs for UI display"""
        with self.lock:
            return list(self.message_buffer.keys())[-count:]

# Global instance
global_logger = ConsolidatedLogger()

# Monkey-patch to replace existing loggers
def replace_all_logging():
    import builtins
    
    # Save original print if not already saved
    if not hasattr(builtins, '_original_print'):
        builtins._original_print = builtins.print

    # Create a single print function
    def unified_print(*args, **kwargs):
        # Construct message
        message = " ".join(str(arg) for arg in args)
        
        if not message.strip():
            return

        # Extract log type from message if present
        log_type = "INFO"
        
        # Detect log type from common patterns
        if "⚡" in message or "ACTION:" in message:
            log_type = "ACTION"
            message = message.replace("⚡", "").replace("ACTION:", "").strip()
        elif "✅" in message or "SUCCESS:" in message:
            log_type = "SUCCESS"
            message = message.replace("✅", "").replace("SUCCESS:", "").strip()
        elif "❌" in message or "ERROR:" in message:
            log_type = "ERROR"
            message = message.replace("❌", "").replace("ERROR:", "").strip()
        elif "⚠️" in message or "WARNING:" in message:
            log_type = "WARNING"
            message = message.replace("⚠️", "").replace("WARNING:", "").strip()
        elif "🚨" in message or "CRITICAL:" in message:
            log_type = "CRITICAL"
            message = message.replace("🚨", "").replace("CRITICAL:", "").strip()
        
        # Log through consolidated system
        formatted = global_logger.log(message, log_type)
        
        if formatted:
            # Only print to stdout if NOT in dashboard mode
            if not global_logger.dashboard_mode:
                builtins._original_print(formatted, **kwargs)
    
    # Replace print
    builtins.print = unified_print
    
    # Also capture sys.stdout.write
    # We need to be careful not to break terminal control codes
    original_stdout_write = sys.stdout.write
    
    def unified_write(text):
        if not text.strip():
            original_stdout_write(text)
            return
            
        # Check if it looks like a log message (not just control codes)
        if len(text.strip()) > 1 and not text.startswith('\033'):
             unified_print(text.strip())
        else:
             original_stdout_write(text)

    # Only replace stdout.write if we really want to capture EVERYTHING
    # For now, replacing print is usually enough for Python apps
    # sys.stdout.write = unified_write
