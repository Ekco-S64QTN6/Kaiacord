import os
import sys
import time
import asyncio
from utils.infrastructure.system.terminal_manager import TerminalManager
from utils.infrastructure.logging.unified_logging import logger
from utils.infrastructure.monitoring.stats_poller import stats_poller
from utils.infrastructure.monitoring.stats_tracker import stats_tracker
from datetime import datetime
from typing import List, Dict, Deque
from collections import deque
import threading
from dataclasses import dataclass, field
import json
import signal

# ==================== CYBERPUNK COLORS ====================
class CyberpunkColors:
    """Cyberpunk color palette matching Btop++ TTY theme"""
    
    # Text colors
    CYBER_CYAN = "\033[38;2;0;255;255m"
    CYBER_PINK = "\033[38;2;255;0;255m"
    CYBER_BLUE = "\033[38;2;0;150;255m"
    CYBER_PURPLE = "\033[38;2;180;0;255m"
    CYBER_GREEN = "\033[38;2;0;255;128m"
    CYBER_YELLOW = "\033[38;2;255;255;0m"
    CYBER_ORANGE = "\033[38;2;255;128;0m"
    CYBER_WHITE = "\033[38;2;240;240;240m"
    CYBER_GRAY = "\033[38;2;64;64;64m"
    CYBER_BLACK = "\033[38;2;12;12;12m"
    
    # Background colors
    BG_CYAN = "\033[48;2;0;40;40m"
    BG_PINK = "\033[48;2;40;0;40m"
    BG_BLUE = "\033[48;2;0;20;40m"
    BG_DARK = "\033[48;2;8;8;16m"
    BG_DARKER = "\033[48;2;4;4;8m"
    
    # Status colors
    SUCCESS = CYBER_GREEN
    WARNING = CYBER_YELLOW
    ERROR = CYBER_PINK
    CRITICAL = CYBER_ORANGE
    INFO = CYBER_CYAN
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    
    # Gradients
    @staticmethod
    def gradient(text: str, color1: str, color2: str) -> str:
        """Create gradient text effect"""
        result = ""
        length = len(text)
        r1, g1, b1 = 0, 255, 255  # CYBER_CYAN
        r2, g2, b2 = 255, 0, 255  # CYBER_PINK
        
        for i, char in enumerate(text):
            ratio = i / max(length - 1, 1)
            r = int(r1 + (r2 - r1) * ratio)
            g = int(g1 + (g2 - g1) * ratio)
            b = int(b1 + (b2 - b1) * ratio)
            result += f"\033[38;2;{r};{g};{b}m{char}"
        
        return result + CyberpunkColors.RESET

# ==================== DASHBOARD LAYOUT ====================
@dataclass
class DashboardLayout:
    """Responsive terminal layout manager"""
    
    # Box drawing characters
    BOX_CHARS = {
        'tl': '┌', 'tr': '┐', 'bl': '└', 'br': '┘',
        'h': '─', 'v': '│', 'ml': '├', 'mr': '┤',
        'tm': '┬', 'bm': '┴', 'mm': '┼'
    }
    
    def __init__(self):
        self.width = 80
        self.height = 24
        self.get_terminal_size()
        
    def get_terminal_size(self):
        """Get current terminal dimensions"""
        try:
            import shutil
            size = shutil.get_terminal_size()
            self.width = size.columns
            self.height = size.lines
        except Exception:
            pass
    
    def calculate_boxes(self):
        """Calculate box dimensions based on terminal size"""
        return {
            'status': {
                'x': 1, 'y': 2,
                'width': self.width // 2 - 2,
                'height': self.height // 2 - 3
            },
            'alerts': {
                'x': self.width // 2 + 1, 'y': 2,
                'width': self.width // 2 - 2,
                'height': self.height // 2 - 3
            },
            'logs': {
                'x': 1, 'y': self.height // 2 + 1,
                'width': self.width - 2,
                'height': self.height // 2 - 2
            }
        }

# ==================== METRICS STORAGE ====================
@dataclass
class DashboardMetrics:
    """Current dashboard metrics"""
    ollama_status: str = "🔴 OFFLINE"
    active_model: str = "None"
    uptime: str = "0s"
    cpu_percent: float = 0.0
    gpu_percent: float = 0.0
    gpu_memory: str = "0/0 MB"
    ram_usage: str = "0/0 MB"
    active_users: int = 0
    total_messages: int = 0
    response_time: float = 0.0
    rag_documents: int = 0
    rag_size: str = "0 MB"
    cache_hit_rate: float = 0.0
    request_queue: int = 0

# ==================== MAIN DASHBOARD CLASS ====================
class BtopDashboard:
    """Btop-style terminal dashboard for Kaiacord"""
    
    def __init__(self, update_interval: float = 1.0):
        self.metrics = DashboardMetrics()
        self.layout = DashboardLayout()
        self.update_interval = update_interval
        self.running = True
        # self.log_buffer = deque(maxlen=1000)  # REMOVED: Use global_logger buffer
        # self.filtered_logs = deque(maxlen=500)  # REMOVED
        self.alerts = deque(maxlen=50)
        self.log_filters = [
            "ALL", "ERROR", "WARNING", "INFO", "SUCCESS", "DEBUG"
        ]
        self.current_filter = 0  # Index into log_filters
        self.show_raw_logs = True  # Always show logs in bottom box
        self.last_rendered = {}  # For delta updates
        self.render_lock = threading.Lock()
        self.boxes = {}
        
        # Terminal management (like htop)
        self.terminal = TerminalManager()
        self.in_dashboard_mode = False
        
        # Start metrics collection
        self.start_time = time.time()
        self.active_sessions = {}
        # asyncio.create_task(self.update_metrics_loop()) # Moved to run()
        
    # ==================== RENDERING METHODS ====================
    
    def clear_screen(self):
        """Clear screen with cyberpunk style"""
        os.system('clear')
        sys.stdout.write(f"{CyberpunkColors.BG_DARK}")
        
    def draw_box(self, x: int, y: int, width: int, height: int, title: str, 
                 color: str = CyberpunkColors.CYBER_CYAN):
        """Draw a box with title"""
        chars = DashboardLayout.BOX_CHARS
        
        # Top border with title
        top_line = f"{color}{chars['tl']}{chars['h'] * (width-2)}{chars['tr']}"
        self.print_at(x, y, top_line)
        
        # Title (centered)
        if title:
            title_display = f" {title} "
            title_pos = x + (width - len(title_display)) // 2
            self.print_at(title_pos, y, f"{CyberpunkColors.BOLD}{CyberpunkColors.CYBER_PINK}{title_display}")
        
        # Sides
        for i in range(1, height-1):
            self.print_at(x, y+i, f"{color}{chars['v']}")
            self.print_at(x+width-1, y+i, f"{color}{chars['v']}")
        
        # Bottom border
        bottom_line = f"{color}{chars['bl']}{chars['h'] * (width-2)}{chars['br']}"
        self.print_at(x, y+height-1, bottom_line)
        
        return {'x': x+1, 'y': y+1, 'width': width-2, 'height': height-2}
    
    def print_at(self, x: int, y: int, text: str):
        """Print text at specific position - stable version"""
        # Clamp coordinates to terminal bounds
        width, height = self.terminal.get_terminal_size()
        x = max(1, min(x, width - 1))
        y = max(1, min(y, height - 1))
        
        # Move cursor and print
        sys.stdout.write(f"\033[{y};{x}H{text}")
        sys.stdout.flush()
    
    def render_dashboard(self):
        """Render the entire dashboard"""
        with self.render_lock:
            self.layout.get_terminal_size()
            self.boxes = self.layout.calculate_boxes()
            
            # Clear and set background
            if not self.in_dashboard_mode:
                 sys.stdout.write('\033[?1049h')  # Enter alternate buffer
                 self.in_dashboard_mode = True
                 sys.stdout.flush()
            
            self.clear_screen()
            
            # Header
            header = f"{CyberpunkColors.BOLD}{CyberpunkColors.gradient('KAIACORD DASHBOARD', CyberpunkColors.CYBER_CYAN, CyberpunkColors.CYBER_PINK)}"
            header_pos = (self.layout.width - len('KAIACORD DASHBOARD')) // 2
            self.print_at(header_pos, 1, header)
            
            # Draw boxes
            status_box = self.draw_box(**self.boxes['status'], 
                                     title="STATUS & METRICS",
                                     color=CyberpunkColors.CYBER_CYAN)
            
            alerts_box = self.draw_box(**self.boxes['alerts'],
                                     title="ALERTS & WARNINGS",
                                     color=CyberpunkColors.CYBER_PINK)
            
            logs_box = self.draw_box(**self.boxes['logs'],
                                   title="LIVE LOGS",
                                   color=CyberpunkColors.CYBER_BLUE)
            
            # Fill content
            self.render_status_box(status_box)
            self.render_alerts_box(alerts_box)
            self.render_logs_box(logs_box)
            
            # Footer with controls
            self.render_footer()
            
            # Move cursor out of the way
            sys.stdout.write(f"\033[{self.layout.height};0H")
            sys.stdout.flush()
    
    def render_status_box(self, box: Dict):
        """Render status and metrics in left box"""
        x, y, width, height = box['x'], box['y'], box['width'], box['height']
        
        lines = [
            f"{CyberpunkColors.CYBER_CYAN}┌─ MODEL & SYSTEM",
            f"{CyberpunkColors.CYBER_WHITE}  Status: {self.metrics.ollama_status}",
            f"  Model: {CyberpunkColors.CYBER_PINK}{self.metrics.active_model}",
            f"  Uptime: {self.metrics.uptime}",
            "",
            f"{CyberpunkColors.CYBER_CYAN}┌─ PERFORMANCE",
            f"{CyberpunkColors.CYBER_WHITE}  CPU: {self.get_progress_bar(self.metrics.cpu_percent, 20)} {self.metrics.cpu_percent:.1f}%",
            f"  GPU: {self.get_progress_bar(self.metrics.gpu_percent, 20)} {self.metrics.gpu_percent:.1f}%",
            f"  VRAM: {self.metrics.gpu_memory}",
            f"  RAM: {self.metrics.ram_usage}",
            "",
            f"{CyberpunkColors.CYBER_CYAN}┌─ BOT STATS",
            f"{CyberpunkColors.CYBER_WHITE}  Users: {self.metrics.active_users}",
            f"  Messages: {self.metrics.total_messages:,}",
            f"  Response: {self.metrics.response_time:.2f}s",
            f"  Queue: {self.metrics.request_queue}",
            "",
            f"{CyberpunkColors.CYBER_CYAN}┌─ RAG SYSTEM",
            f"{CyberpunkColors.CYBER_WHITE}  Documents: {self.metrics.rag_documents}",
            f"  Index: {self.metrics.rag_size}",
            f"  Cache: {self.get_progress_bar(self.metrics.cache_hit_rate*100, 20)} {self.metrics.cache_hit_rate:.1%}",
        ]
        
        for i, line in enumerate(lines[:height]):
            self.print_at(x, y + i, line)
    
    def render_alerts_box(self, box: Dict):
        """Render alerts and warnings in right box"""
        x, y, width, height = box['x'], box['y'], box['width'], box['height']
        
        if not self.alerts:
            self.print_at(x, y, f"{CyberpunkColors.DIM}No alerts")
            return
        
        # Show most recent alerts (fit in box)
        display_alerts = list(self.alerts)[-height+1:]
        
        for i, alert in enumerate(display_alerts):
            if i >= height - 1:
                break
                
            # Color code by level
            if alert['level'] == 'error':
                color = CyberpunkColors.ERROR
                icon = "⛔"
            elif alert['level'] == 'warning':
                color = CyberpunkColors.WARNING
                icon = "⚠️"
            elif alert['level'] == 'critical':
                color = CyberpunkColors.CRITICAL
                icon = "🚨"
            else:
                color = CyberpunkColors.INFO
                icon = "💡"
            
            time_str = alert['time'].strftime("%H:%M:%S")
            message = alert['message'][:width-15]
            
            line = f"{CyberpunkColors.DIM}{time_str} {color}{icon} {message}"
            self.print_at(x, y + i, line)
        
        # Show overflow indicator
        if len(self.alerts) > len(display_alerts):
            self.print_at(x, y + height - 2, 
                         f"{CyberpunkColors.DIM}... {len(self.alerts) - len(display_alerts)} more alerts")
    
    def render_logs_box(self, box: Dict):
        """Render live logs in bottom box - NO FLICKERING"""
        x, y, width, height = box['x'], box['y'], box['width'], box['height']
        
        # Get logs from unified logger
        recent_logs = logger.get_recent_logs(count=height*2)
        
        current_filter = self.log_filters[self.current_filter]
        if current_filter == "ALL":
            display_logs = recent_logs[-height+1:]
        else:
            display_logs = [log for log in recent_logs
                          if log['type'] == current_filter][-height+1:]
        
        # Apply color coding and wrapping
        colored_logs = []
        for log in display_logs:
            msg = f"{log['timestamp']} | {log['message']}"
            log_type = log['type']
            
            # Determine color
            if log_type in ["ERROR", "CRITICAL"]:
                color = CyberpunkColors.ERROR
            elif log_type == "WARNING":
                color = CyberpunkColors.WARNING
            elif log_type == "SUCCESS":
                color = CyberpunkColors.SUCCESS
            elif log_type == "INFO":
                color = CyberpunkColors.INFO
            elif log_type == "ACTION":
                color = CyberpunkColors.CYBER_PURPLE
            else:
                color = CyberpunkColors.CYBER_WHITE
            
            # Wrap lines
            wrapped_lines = []
            current_line = ""
            words = msg.split(' ')
            
            for word in words:
                if len(current_line) + len(word) + 1 <= width:
                    current_line += (word + " ")
                else:
                    wrapped_lines.append(f"{color}{current_line.strip()}")
                    current_line = f"  {word} " # Indent continuation lines
            
            if current_line:
                wrapped_lines.append(f"{color}{current_line.strip()}")
                
            colored_logs.extend(wrapped_lines)
        
        # Display logs (bottom-aligned)
        start_idx = max(0, len(colored_logs) - (height - 1))
        for i, log in enumerate(colored_logs[start_idx:], start=1):
            if i < height:
                self.print_at(x, y + i - 1, log)
        
        # Clear remaining lines
        for i in range(len(colored_logs) - start_idx + 1, height):
            self.print_at(x, y + i - 1, " " * width)
        
        # Filter indicator
        filter_indicator = f"[Filter: {self.log_filters[self.current_filter]}]"
        self.print_at(x + width - len(filter_indicator), y + height - 1, 
                     f"{CyberpunkColors.DIM}{filter_indicator}")
    
    def render_footer(self):
        """Render footer with controls"""
        y = self.layout.height
        
        controls = [
            f"{CyberpunkColors.BOLD}[Q]{CyberpunkColors.DIM}uit",
            f"{CyberpunkColors.BOLD}[C]{CyberpunkColors.DIM}lear alerts",
            f"{CyberpunkColors.BOLD}[R]{CyberpunkColors.DIM}efresh",
            f"{CyberpunkColors.BOLD}[L]{CyberpunkColors.DIM}og filter ({self.log_filters[self.current_filter]})",
            f"{CyberpunkColors.BOLD}[S]{CyberpunkColors.DIM}ave logs",
            f"{CyberpunkColors.BOLD}[1-6]{CyberpunkColors.DIM}Quick filter",
        ]
        
        footer_text = "  ".join(controls)
        self.print_at(1, y, f"{CyberpunkColors.CYBER_GRAY}{footer_text}")
    
    def get_progress_bar(self, value: float, width: int) -> str:
        """Create a cyberpunk progress bar"""
        fill = int((value / 100) * width)
        empty = width - fill
        
        if value < 30:
            color = CyberpunkColors.CYBER_GREEN
        elif value < 70:
            color = CyberpunkColors.CYBER_YELLOW
        else:
            color = CyberpunkColors.CYBER_PINK
        
        return f"{color}{'█' * fill}{CyberpunkColors.CYBER_GRAY}{'░' * empty}"
    
    # ==================== LOG MANAGEMENT ====================
    
    def add_log(self, message: str):
        """Add a log message (Wrapper for unified logger)"""
        logger.log(message, "INFO", source="dashboard")
        if self.show_raw_logs:
            # Schedule async refresh for immediate update
            asyncio.create_task(self.schedule_refresh())
    
    def clear_logs(self):
        """Clear all logs"""
        self.log_buffer.clear()
    
    def save_logs(self, filename: str = None):
        """Save current logs to file"""
        if filename is None:
            filename = f"kaiacord_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        with open(filename, 'w', encoding='utf-8') as f:
            for log in logger.get_recent_logs(1000):
                f.write(f"{log['timestamp']} [{log['type']}] {log['message']}\n")
        
        self.add_log(f"Logs saved to {filename}")
    
    # ==================== METRICS UPDATES ====================
    
    async def update_metrics_loop(self):
        """Background task to update metrics from poller"""
        while self.running:
            try:
                # Get stats from poller
                stats = stats_poller.get_stats()
                
                # Update dashboard metrics
                self.metrics.cpu_percent = stats.get('cpu_percent', 0.0)
                self.metrics.gpu_percent = stats.get('gpu_util', 0.0)
                self.metrics.ram_usage = f"{int(stats.get('memory_mb', 0))} MB"
                self.metrics.gpu_memory = stats.get('gpu_memory', "N/A")
                self.metrics.uptime = f"{int(stats.get('uptime_minutes', 0))}m"
                
                # Get stats from tracker
                tracker_stats = stats_tracker.get_stats()
                self.metrics.active_users = tracker_stats.get('users', 0)
                self.metrics.total_messages = tracker_stats.get('messages', 0)
                self.metrics.response_time = stats.get('avg_response_time', 0.0)
                self.metrics.request_queue = stats.get('queue_size', 0)
                self.metrics.rag_documents = stats.get('rag_documents', 0)
                self.metrics.rag_size = stats.get('rag_size', "0 MB")
                self.metrics.ollama_status = stats.get('ollama_status', "🔴 OFFLINE")
                self.metrics.active_model = stats.get('active_model', "None")
                
            except Exception as e:
                pass
            
            # Update frequently for smooth UI
            await asyncio.sleep(0.5)
    
    def format_uptime(self, seconds: float) -> str:
        """Format seconds into human readable uptime"""
        try:
            seconds = float(seconds)
            days, remainder = divmod(int(seconds), 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds_remaining = divmod(remainder, 60)
            
            if days > 0:
                return f"{days}d {hours}h"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m {int(seconds_remaining)}s"
        except (TypeError, ValueError):
            return "0s"

    def update_user_session(self, user_id: str, username: str, activity: str = "Active"):
        """Update or create a user session"""
        if user_id not in self.active_sessions:
            self.active_sessions[user_id] = {
                'user_id': user_id,
                'username': username,
                'last_active': time.time(),
                'activity': activity
            }
        else:
            self.active_sessions[user_id]['last_active'] = time.time()
            self.active_sessions[user_id]['activity'] = activity
    
    # ==================== KEYBOARD HANDLING ====================
    
    async def handle_input(self):
        """Handle keyboard input"""
        try:
            import select
            import tty
            import termios
            
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            
            try:
                tty.setraw(fd)
                
                while self.running:
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        key = sys.stdin.read(1)
                        await self.process_keypress(key)
                    
                    await asyncio.sleep(0.01)
                    
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                
        except Exception as e:
            # Fallback for Windows or systems without termios
            while self.running:
                await asyncio.sleep(0.1)
    
    async def process_keypress(self, key: str):
        """Process a single keypress"""
        key = key.lower()
        
        if key == 'q':
            self.running = False
            print(f"\n{CyberpunkColors.CYBER_PINK}Shutting down dashboard...")
        elif key == 'c':
            self.alerts.clear()
            self.add_log("Alerts cleared")
        elif key == 'r':
            self.add_log("Manual refresh triggered")
            self.render_dashboard()
        elif key == 'l':
            self.current_filter = (self.current_filter + 1) % len(self.log_filters)
            self.add_log(f"Log filter: {self.log_filters[self.current_filter]}")
            self.render_dashboard()
        elif key == 's':
            asyncio.create_task(self.save_logs_async())
        elif key in ['1', '2', '3', '4', '5', '6']:
            idx = int(key) - 1
            if idx < len(self.log_filters):
                self.current_filter = idx
                self.add_log(f"Quick filter: {self.log_filters[self.current_filter]}")
                self.render_dashboard()
    
    async def save_logs_async(self):
        """Save logs asynchronously"""
        filename = f"kaiacord_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.save_logs(filename)
        self.add_log(f"✅ Logs saved to {filename}")
    
    # ==================== PUBLIC API ====================
    
    def update_metrics(self, metrics: Dict):
        """Update dashboard metrics from bot"""
        for key, value in metrics.items():
            if hasattr(self.metrics, key):
                setattr(self.metrics, key, value)
    
    def add_alert(self, message: str, level: str = "info"):
        """Add an alert"""
        self.alerts.append({
            'time': datetime.now(),
            'message': message,
            'level': level
        })
    
    async def schedule_refresh(self):
        """Schedule a dashboard refresh on next tick"""
        # Cancel any pending refresh to avoid multiple refreshes
        if hasattr(self, '_refresh_task') and not self._refresh_task.done():
            self._refresh_task.cancel()
        
        # Schedule refresh on next event loop iteration
        self._refresh_task = asyncio.create_task(self.delayed_refresh())

    async def delayed_refresh(self):
        """Perform a delayed refresh to batch multiple log updates"""
        await asyncio.sleep(0.1)  # Small delay to batch rapid updates
        if self.running:
            self.render_dashboard()

    async def run(self):
        """Main dashboard loop"""
        # Enter dashboard mode (like htop)
        self.in_dashboard_mode = self.terminal.enter_dashboard_mode()
        if not self.in_dashboard_mode:
            print("Warning: Not in a TTY, dashboard may not display correctly")
        
        # Start metrics update loop
        metrics_task = asyncio.create_task(self.update_metrics_loop())
        
        # Start input handling
        input_task = asyncio.create_task(self.handle_input())
        
        # Initial render
        self.render_dashboard()
        
        # Main loop
        try:
            while self.running:
                # Only re-render if needed (logs auto-update)
                await asyncio.sleep(0.2)
                
        except KeyboardInterrupt:
            self.running = False
        finally:
            # Cancel tasks
            metrics_task.cancel()
            input_task.cancel()
            try:
                await metrics_task
                await input_task
            except asyncio.CancelledError:
                pass
            
            # Exit dashboard mode
            if self.in_dashboard_mode:
                self.terminal.exit_dashboard_mode()
                logger.set_dashboard_mode(False)
            
            # RESET TERMINAL STATE - CRITICAL FIX
            self.reset_terminal_completely()

    def reset_terminal_completely(self):
        """Completely reset terminal to normal state"""
        try:
            # Clear any pending escape sequences
            sys.stdout.write('\033[0m')  # Reset all attributes
            sys.stdout.write('\033[?25h')  # Show cursor
            sys.stdout.write('\033[?1049l')  # Exit alternate screen buffer if we entered it
            sys.stdout.write('\033[H')  # Move cursor to home
            sys.stdout.write('\033[2J')  # Clear entire screen
            sys.stdout.write('\033[3J')  # Clear scrollback buffer
            sys.stdout.flush()
            
            # Also reset colorama
            try:
                from colorama import Style
                sys.stdout.write(Style.RESET_ALL)
                sys.stdout.flush()
            except ImportError:
                pass
        except Exception as e:
            print(f"Warning: Failed to reset terminal: {e}")

class KaiaMonitor:
    def __init__(self, dashboard: BtopDashboard):
        self.dashboard = dashboard
    
    def log_message(self, user: str, content: str, user_id: str = None):
        """Log a Discord message to dashboard"""
        self.dashboard.add_log(f"💬 {user}: {content[:100]}...")
    
    def log_response(self, response: str, tokens_saved: int = 0, response_time: float = 0.0):
        """Log Kaia's response"""
        self.dashboard.add_log(f"🤖 Response: {response[:100]}... ({response_time:.2f}s)")
        self.dashboard.metrics.response_time = response_time
    
    def log_system_event(self, event_type: str, message: str):
        """Log system events"""
        self.dashboard.add_log(f"⚡ {event_type}: {message}")
        
        if "error" in event_type.lower() or "failed" in event_type.lower():
            self.dashboard.add_alert(message, "error")
        elif "warning" in event_type.lower():
            self.dashboard.add_alert(message, "warning")
        else:
            self.dashboard.add_alert(message, "info")
    
    def update_metrics(self, metrics: Dict):
        """Update dashboard metrics"""
        self.dashboard.update_metrics(metrics)
    
    def update_system_metrics(self):
        """Update system-level metrics for the dashboard"""
        try:
            import psutil
            process = psutil.Process()
            
            # CPU
            self.dashboard.metrics.cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # RAM
            ram = psutil.virtual_memory()
            self.dashboard.metrics.ram_usage = f"{ram.used//1024//1024}/{ram.total//1024//1024}MB"
            
            # Process memory
            rss_mb = process.memory_info().rss / 1024 / 1024
            # self.dashboard.metrics.ram_usage_detail = f"{rss_mb:.1f}MB RSS" # Not in metrics dataclass yet
            
        except Exception as e:
            self.dashboard.add_log(f"Metrics error: {e}")

class BtopLoggingPatcher:
    """Patch logging to capture all output for the dashboard"""
    def __init__(self, dashboard: BtopDashboard):
        self.dashboard = dashboard
        self.original_print = print
        self.last_message = None
        self.message_count = 0
        self.duplicate_buffer = set()
        self.log_cache = []
    
    def patch_print(self):
        """Patch print function to capture output without duplicates"""
        def new_print(*args, **kwargs):
            # Build message
            message = ' '.join(str(arg) for arg in args)
            
            # Skip empty messages
            if not message.strip():
                if not self.dashboard.in_dashboard_mode:
                    self.original_print(*args, **kwargs)
                return
            
            # Create fingerprint for deduplication
            line_fingerprint = hash(message.strip())
            
            # Skip if seen recently (deduplication)
            if line_fingerprint in self.duplicate_buffer:
                return
                
            self.duplicate_buffer.add(line_fingerprint)
            
            # Clean old fingerprints (keep last 100)
            if len(self.duplicate_buffer) > 100:
                # Convert to list, slice, convert back to set
                # This is a simple way to keep buffer size managed
                self.duplicate_buffer = set(list(self.duplicate_buffer)[-100:])
            
            # Clean the message
            import re
            
            # Remove timestamps like [12:31:21]
            message = re.sub(r'\[\d{2}:\d{2}:\d{2}\]', '', message)
            
            # Remove ANSI color codes
            clean_message = re.sub(r'\033\[[0-9;]*m', '', message)
            
            # Remove leading/trailing whitespace
            clean_message = clean_message.strip()
            
            # Skip if empty after cleaning
            if not clean_message:
                if not self.dashboard.in_dashboard_mode:
                    self.original_print(*args, **kwargs)
                return
            
            # Add to dashboard with current timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = f"{timestamp} | {clean_message}"
            self.dashboard.add_log(log_entry)
            
            # CRITICAL: Only print to original stdout if NOT in dashboard mode
            # This prevents logs from printing below the UI
            if not self.dashboard.in_dashboard_mode:
                self.original_print(*args, **kwargs)
        
        import builtins
        builtins.print = new_print
