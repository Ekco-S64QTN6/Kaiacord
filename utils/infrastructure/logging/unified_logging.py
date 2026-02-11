import os
import sys
import time
import threading
import logging
import logging.handlers
from datetime import datetime
from collections import OrderedDict, deque

class UnifiedLogger:
    """Single source of truth for all logging"""
    def __init__(self):
        self.lock = threading.RLock()
        self.console_buffer = []
        self.dashboard_buffer = deque(maxlen=200)
        self.message_history = OrderedDict()
        self.last_console_message = None
        self.last_message_time = 0
        self.duplicate_window = 0.05  # 50ms window
        self.dashboard_mode = False
        self.log_file = "logs/kaiacord.log"
        self._ensure_log_dir()
        self._file_handler = self._create_file_handler()
        self.debug_dedup = {}  # (message_hash): timestamp
        
        # Color codes for terminal
        self.colors = {
            'ACTION': '\033[95m',     # Magenta
            'SUCCESS': '\033[92m',    # Green
            'READY': '\033[95;1m',    # Bold Pink/Light Magenta
            'INFO': '\033[94m',       # Blue
            'WARNING': '\033[93m',    # Yellow
            'ERROR': '\033[91m',      # Red
            'RESET': '\033[0m',
            'BOLD': '\033[1m'
        }
        
    def _ensure_log_dir(self):
        """Ensure the logs directory exists"""
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

    def _create_file_handler(self):
        """Create a rotating file handler (10MB max, 5 backups)"""
        try:
            handler = logging.handlers.RotatingFileHandler(
                self.log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
            )
            handler.setFormatter(logging.Formatter('%(message)s'))
            return handler
        except Exception:
            return None

    def set_dashboard_mode(self, enabled: bool):
        """Enable/disable dashboard mode (suppresses stdout)"""
        self.dashboard_mode = enabled

    def _should_log(self, message, log_type):
        """Check if this message should be logged (deduplication)"""
        current_time = time.time()
        message_key = f"{log_type}:{hash(message)}"
        
        with self.lock:
            # Check if this is a duplicate within time window
            if message_key in self.message_history:
                last_time = self.message_history[message_key]
                if current_time - last_time < self.duplicate_window:
                    return False
            
            # Update history (keep only last 1000 entries)
            self.message_history[message_key] = current_time
            if len(self.message_history) > 1000:
                self.message_history.popitem(last=False)
            
            return True
    
    def _is_debug_duplicate(self, message, log_type):
        """Check if this is a repeating maintenance debug message"""
        if log_type != "DEBUG":
            return False
            
        msg_lower = message.lower()
        if not any(kw in msg_lower for kw in ["refresh", "watcher", "maintenance"]):
            return False
            
        current_time = time.time()
        msg_hash = hash(message)
        
        with self.lock:
            if msg_hash in self.debug_dedup:
                last_time = self.debug_dedup[msg_hash]
                if current_time - last_time < 60:
                    return True
            
            self.debug_dedup[msg_hash] = current_time
            # Cleanup old entries occasionally
            if len(self.debug_dedup) > 100:
                self.debug_dedup = {k: v for k, v in self.debug_dedup.items() if current_time - v < 60}
                
            return False
    
    def log(self, message, log_type="INFO", source=None):
        """Main logging method - all logs go through here"""
        # Safety check for late-stage shutdown
        try:
            if sys is None or not hasattr(sys, 'meta_path') or sys.meta_path is None:
                return
        except (NameError, AttributeError):
            return

        if not self._should_log(message, log_type):
            return
            
        # Suppression: Silence the PyNaCl warning (voice not supported)
        if "PyNaCl is not installed" in message:
            return
            
        if self._is_debug_duplicate(message, log_type):
            return
            
        # Default level suppression (unless in debug mode, which we don't have a simple flag for yet)
        if log_type == "DEBUG":
            # For now, only log DEBUG to file, not to buffers or console unless explicitly allowed
            # This prevents LlamaIndex and others from spamming the UI
            self._write_to_file({'timestamp': datetime.now().strftime("%H:%M:%S"), 'type': log_type, 'message': f"[HIDDEN] {message}"})
            return
        
        try:
            # Check if datetime is still available
            if 'datetime' not in globals() and 'datetime' not in sys.modules:
                return
            timestamp = datetime.now().strftime("%H:%M:%S")
        except (AttributeError, NameError, TypeError, ImportError):
            # Interpreter is likely finalizing
            return
        
        # Create clean log entry (single timestamp)
        log_entry = {
            'timestamp': timestamp,
            'type': log_type,
            'message': message,
            'source': source or 'system',
            'raw_time': time.time()
        }
        
        # Add to buffers
        with self.lock:
            self.dashboard_buffer.append(log_entry)
            self.console_buffer.append(log_entry)
        
        # Write to console (once, formatted)
        self._write_to_console(log_entry)
        
        # Write to file (with rotation)
        self._write_to_file(log_entry)
        
        return log_entry
    
    def _write_to_file(self, log_entry):
        """Write log entry to rotating file"""
        if self._file_handler:
            try:
                record = logging.LogRecord(
                    name='kaiacord', level=logging.INFO, pathname='', lineno=0,
                    msg=f"[{log_entry['timestamp']}] {log_entry['type']}: {log_entry['message']}",
                    args=None, exc_info=None
                )
                self._file_handler.emit(record)
            except Exception:
                pass
        else:
            # Fallback: direct write if handler creation failed
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(f"[{log_entry['timestamp']}] {log_entry['type']}: {log_entry['message']}\n")
            except Exception:
                pass
    
    def _write_to_console(self, log_entry):
        """Write formatted log to console"""
        if self.dashboard_mode:
            return

        color = self.colors.get(log_entry['type'], self.colors['INFO'])
        reset = self.colors['RESET']
        
        if log_entry['type'] == 'READY':
            # Highlight the ENTIRE line for readiness
            formatted = f"\r{color}[{log_entry['timestamp']}] {log_entry['type']}: {log_entry['message']}{reset}"
        else:
            # Format: [TIME] TYPE: Message (only prefix colored)
            formatted = f"\r{color}[{log_entry['timestamp']}] {log_entry['type']}:{reset} {log_entry['message']}"
        
        # Strip colors if NOT a TTY
        is_tty = hasattr(sys.__stdout__, 'isatty') and sys.__stdout__.isatty()
        if not is_tty:
            # Simple regex to strip ANSI codes
            import re
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            formatted = ansi_escape.sub('', formatted)

        # Skip if this is the same as last console message (rapid duplicates)
        if formatted != self.last_console_message:
            try:
                # Use sys.__stdout__ to bypass any monkey-patching
                # Check if it exists for safe interpreter finalization
                if sys and hasattr(sys, '__stdout__') and sys.__stdout__ is not None:
                    sys.__stdout__.write(formatted + "\r\n")
                    sys.__stdout__.flush()
                self.last_console_message = formatted
                self.last_message_time = time.time()
            except (AttributeError, TypeError, ImportError):
                # Interpreter is likely finalizing - stop logging to console
                pass


    
    def get_recent_logs(self, count=20, filter_type=None):
        """Get recent logs for dashboard display"""
        with self.lock:
            logs = list(self.dashboard_buffer)[-count:]
            
            if filter_type:
                logs = [log for log in logs if log['type'] == filter_type]
            
            return logs
    
    def clear_logs(self):
        """Clear log buffers"""
        with self.lock:
            self.dashboard_buffer.clear()
            self.console_buffer.clear()

# Global logger instance
logger = UnifiedLogger()

# Interception classes
class UnifiedStdout:
    def write(self, text):
        if text.strip():
            # Avoid logging color codes directly as text
            if not text.startswith('\x1B'):
                logger.log(text.strip(), "INFO")
    
    def flush(self):
        if sys and hasattr(sys, '__stdout__') and sys.__stdout__ is not None:
            sys.__stdout__.flush()

class UnifiedStderr:
    def write(self, text):
        if text.strip():
            # Capture as ERROR
            logger.log(text.strip(), "ERROR")
    
    def flush(self):
        if sys and hasattr(sys, '__stderr__') and sys.__stderr__ is not None:
            sys.__stderr__.flush()

# Replace ALL existing logging
def replace_all_logging():
    """Monkey-patch all logging to use unified system"""
    import builtins
    import logging
    
    # Store originals if not already stored
    if not hasattr(builtins, '_original_print'):
        builtins._original_print = builtins.print
    
    if not hasattr(sys, '_original_stdout'):
        sys._original_stdout = sys.stdout
    
    if not hasattr(sys, '_original_stderr'):
        sys._original_stderr = sys.stderr
    
    # Custom print function
    def unified_print(*args, **kwargs):
        if args:
            message = ' '.join(str(arg) for arg in args)
            
            if not message.strip():
                return
                
            # Detect log type from common prefixes
            log_type = "INFO"
            if message.startswith("✅") or "SUCCESS" in message:
                log_type = "SUCCESS"
                clean_msg = message.replace("✅", "").replace("SUCCESS", "").strip()
                if clean_msg.startswith(":"): clean_msg = clean_msg[1:].strip()
                message = clean_msg
            elif message.startswith("⚡") or "ACTION" in message:
                log_type = "ACTION"
                clean_msg = message.replace("⚡", "").replace("ACTION", "").strip()
                if clean_msg.startswith(":"): clean_msg = clean_msg[1:].strip()
                message = clean_msg
            elif message.startswith("⚠️") or "WARNING" in message:
                log_type = "WARNING"
                clean_msg = message.replace("⚠️", "").replace("WARNING", "").strip()
                if clean_msg.startswith(":"): clean_msg = clean_msg[1:].strip()
                message = clean_msg
            elif message.startswith("❌") or "ERROR" in message:
                log_type = "ERROR"
                clean_msg = message.replace("❌", "").replace("ERROR", "").strip()
                if clean_msg.startswith(":"): clean_msg = clean_msg[1:].strip()
                message = clean_msg
            
            # Remove any existing timestamps
            if "|" in message and len(message.split("|")) >= 2:
                # Check if it starts with timestamp pattern
                parts = message.split("|", 2)
                # HH:MM:SS pattern check
                t_parts = parts[0].strip().split(":")
                if len(t_parts) == 3 and all(p.isdigit() for p in t_parts):
                    if len(parts) > 1:
                        # Check if second part is also a timestamp (legacy redundancy)
                        t2_parts = parts[1].strip().split(":")
                        if len(t2_parts) == 3 and all(p.isdigit() for p in t2_parts):
                            message = parts[2].strip()
                        else:
                            message = "|".join(parts[1:]).strip()
            
            # Log through unified system
            logger.log(message, log_type)
    
    # Replace print
    builtins.print = unified_print
    
    # Intercept stdout and stderr
    sys.stdout = UnifiedStdout()
    sys.stderr = UnifiedStderr()
    
    # Configure Python logging
    class UnifiedLogHandler(logging.Handler):
        def emit(self, record):
            # Avoid infinite loops from our own logging
            if record.name == 'root' and "Unified logging system initialized" in record.getMessage():
                return
            logger.log(self.format(record), record.levelname)
    
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    unified_handler = UnifiedLogHandler()
    unified_handler.setFormatter(logging.Formatter('%(message)s'))
    root_logger.addHandler(unified_handler)
    root_logger.setLevel(logging.INFO)
    
    logger.log("Unified logging system initialized", "SUCCESS")

def log_ollama_interaction(prompt, response):
    """Log Ollama interactions to a separate file"""
    try:
        os.makedirs("logs", exist_ok=True)
        with open("logs/ollama_client.log", "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"--- {timestamp} ---\n")
            f.write(f"PROMPT: {str(prompt)[:500]}...\n")
            f.write(f"RESPONSE: {str(response)[:500]}...\n\n")
    except Exception:
        pass
