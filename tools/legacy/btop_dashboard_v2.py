import curses
import time
import sys
import psutil
from datetime import datetime
import threading
from collections import deque

class BtopDashboard:
    """Btop-inspired dashboard with 3 quadrants and colored boxes"""
    
    def __init__(self, stdscr, logger, stats_tracker):
        self.stdscr = stdscr
        self.logger = logger
        self.stats_tracker = stats_tracker
        self.running = True
        
        # Setup curses
        curses.curs_set(0)
        self.stdscr.nodelay(True)
        self.stdscr.timeout(100)
        
        # Initialize btop colors
        self.init_btop_colors()
        
        # Performance history
        self.cpu_history = deque(maxlen=20)
        self.ram_history = deque(maxlen=20)
        
        # Start update thread - REMOVED due to curses thread-safety issues
        # self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        # self.update_thread.start()
    
    def init_btop_colors(self):
        """Initialize btop-style colors"""
        curses.start_color()
        curses.use_default_colors()
        
        # Btop color palette
        # Pair 1: Cyan text (for boxes and headers)
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        
        # Pair 2: Pink/Magenta text (for highlights and alerts)
        curses.init_pair(2, curses.COLOR_MAGENTA, -1)
        
        # Pair 3: Green text (for good stats)
        curses.init_pair(3, curses.COLOR_GREEN, -1)
        
        # Pair 4: Yellow text (for warnings)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        
        # Pair 5: Red text (for errors/critical)
        curses.init_pair(5, curses.COLOR_RED, -1)
        
        # Pair 6: White text (default)
        curses.init_pair(6, curses.COLOR_WHITE, -1)
        
        # Pair 7: Blue text (for info)
        curses.init_pair(7, curses.COLOR_BLUE, -1)
    
    def draw_box(self, y, x, height, width, title=None, color_pair=1):
        """Draw a box with optional title"""
        try:
            # Top border with title
            if title:
                title_str = f" {title} "
                left_len = (width - len(title_str)) // 2
                right_len = width - len(title_str) - left_len - 2
                top_line = "─" * left_len + title_str + "─" * right_len
                self.stdscr.addstr(y, x, "┌" + top_line + "┐", curses.color_pair(color_pair))
            else:
                self.stdscr.addstr(y, x, "┌" + "─" * (width - 2) + "┐", curses.color_pair(color_pair))
            
            # Sides
            for i in range(1, height - 1):
                self.stdscr.addstr(y + i, x, "│", curses.color_pair(color_pair))
                self.stdscr.addstr(y + i, x + width - 1, "│", curses.color_pair(color_pair))
            
            # Bottom border
            self.stdscr.addstr(y + height - 1, x, "└" + "─" * (width - 2) + "┘", curses.color_pair(color_pair))
            
            return y + 1, x + 1  # Return inner coordinates
        except curses.error:
            return y + 1, x + 1
    
    def draw_stats_quadrant(self, y, x, height, width):
        """Draw system stats in upper left quadrant"""
        try:
            # Draw cyan box
            inner_y, inner_x = self.draw_box(y, x, height, width, "SYSTEM STATS", 1)
            
            # Get system stats
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            network = psutil.net_io_counters()
            
            # Add to history for graphs
            self.cpu_history.append(cpu_percent)
            self.ram_history.append(memory.percent)
            
            # Bot stats
            stats = self.stats_tracker.get_stats()
            
            # Line 1: CPU
            cpu_bar = self._draw_btop_bar(cpu_percent, 20)
            cpu_color = 3 if cpu_percent < 50 else (4 if cpu_percent < 80 else 5)
            self.stdscr.addstr(inner_y, inner_x, "CPU:", curses.color_pair(1))
            self.stdscr.addstr(f" {cpu_bar} {cpu_percent:5.1f}%", curses.color_pair(cpu_color))
            
            # Line 2: Memory
            mem_bar = self._draw_btop_bar(memory.percent, 20)
            mem_color = 3 if memory.percent < 50 else (4 if memory.percent < 80 else 5)
            self.stdscr.addstr(inner_y + 1, inner_x, "RAM:", curses.color_pair(1))
            self.stdscr.addstr(f" {mem_bar} {memory.percent:5.1f}%", curses.color_pair(mem_color))
            
            # Line 3: Disk
            disk_bar = self._draw_btop_bar(disk.percent, 20)
            disk_color = 3 if disk.percent < 50 else (4 if disk.percent < 80 else 5)
            self.stdscr.addstr(inner_y + 2, inner_x, "DSK:", curses.color_pair(1))
            self.stdscr.addstr(f" {disk_bar} {disk.percent:5.1f}%", curses.color_pair(disk_color))
            
            # Line 4: Network
            self.stdscr.addstr(inner_y + 3, inner_x, "NET:", curses.color_pair(1))
            self.stdscr.addstr(f" ↑{network.bytes_sent // 1024:5d}K ↓{network.bytes_recv // 1024:5d}K", curses.color_pair(6))
            
            # Line 5: Bot stats - Users
            self.stdscr.addstr(inner_y + 4, inner_x, "USERS:", curses.color_pair(1))
            self.stdscr.addstr(f" {stats.get('active_users_count', 0):3d} active", curses.color_pair(3))
            
            # Line 6: Bot stats - Messages
            self.stdscr.addstr(inner_y + 5, inner_x, "MSGS:", curses.color_pair(1))
            self.stdscr.addstr(f" {stats.get('messages', 0):6d} total", curses.color_pair(3))
            
            # Line 7: Bot stats - Response time
            self.stdscr.addstr(inner_y + 6, inner_x, "RTIME:", curses.color_pair(1))
            resp_time = stats.get('avg_response_time', 0.0)
            resp_color = 3 if resp_time < 1.0 else (4 if resp_time < 3.0 else 5)
            self.stdscr.addstr(f" {resp_time:5.2f}s", curses.color_pair(resp_color))
            
            # Line 8: Uptime
            uptime_mins = stats.get('uptime_minutes', 0)
            self.stdscr.addstr(inner_y + 7, inner_x, "UPTIME:", curses.color_pair(1))
            self.stdscr.addstr(f" {uptime_mins:.0f}m", curses.color_pair(6))
        except curses.error:
            pass
    
    def draw_alerts_quadrant(self, y, x, height, width):
        """Draw alerts in upper right quadrant"""
        try:
            # Draw pink box
            inner_y, inner_x = self.draw_box(y, x, height, width, "ALERTS", 2)
            
            # Get recent logs with ERROR or WARNING status
            logs = self.logger.get_recent_logs(20)
            alerts = []
            
            for log in logs:
                log_type = log.get('type', '')
                if log_type in ['ERROR', 'WARNING', 'CRITICAL']:
                    alerts.append(log)
            
            # Display up to 8 alerts
            max_alerts = height - 2
            alerts_to_show = alerts[:max_alerts]
            
            if not alerts_to_show:
                self.stdscr.addstr(inner_y, inner_x, "✅ No active alerts", curses.color_pair(3))
                return
            
            for i, alert in enumerate(alerts_to_show):
                y_pos = inner_y + i
                if y_pos >= inner_y + max_alerts:
                    break
                
                timestamp = alert.get('timestamp', '')[-5:]  # Just HH:MM
                message = alert.get('message', '')
                log_type = alert.get('type', '')
                
                # Color code
                if 'ERROR' in log_type:
                    color = 5  # Red
                    symbol = "⛔"
                elif 'WARNING' in log_type:
                    color = 4  # Yellow
                    symbol = "⚠️ "
                else:
                    color = 7  # Blue
                    symbol = "ℹ️ "
                
                # Format alert line
                alert_line = f"{symbol} {timestamp} {message}"
                if len(alert_line) > width - 4:
                    alert_line = alert_line[:width - 7] + "..."
                
                self.stdscr.addstr(y_pos, inner_x, alert_line, curses.color_pair(color))
            
            # Show count if more alerts exist
            if len(alerts) > max_alerts:
                remaining = len(alerts) - max_alerts
                self.stdscr.addstr(inner_y + max_alerts - 1, inner_x, 
                                 f"... {remaining} more alerts", curses.color_pair(4))
        except curses.error:
            pass
    
    def draw_logs_quadrant(self, y, x, height, width):
        """Draw logs in bottom quadrant"""
        try:
            # Draw cyan box (full width)
            inner_y, inner_x = self.draw_box(y, x, height, width, "SYSTEM LOGS", 1)
            
            # Get logs
            logs = self.logger.get_recent_logs(height - 2)
            
            # Display logs
            for i, log in enumerate(logs):
                y_pos = inner_y + i
                if y_pos >= y + height - 1:
                    break
                
                timestamp = log.get('timestamp', '')
                message = log.get('message', '')
                log_type = log.get('type', 'INFO')
                
                # Color mapping
                color_map = {
                    'INFO': 6,      # White
                    'SUCCESS': 3,   # Green
                    'ACTION': 1,    # Cyan
                    'WARNING': 4,   # Yellow
                    'ERROR': 5,     # Red
                    'CRITICAL': 5,  # Red
                }
                
                color = color_map.get(log_type, 6)
                
                # Format log line
                log_line = f"{timestamp} {log_type}: {message}"
                if len(log_line) > width - 2:
                    log_line = log_line[:width - 5] + "..."
                
                self.stdscr.addstr(y_pos, inner_x, log_line, curses.color_pair(color))
        except curses.error:
            pass
    
    def draw_menu(self, y, x, width):
        """Draw the bottom menu"""
        try:
            # Pink background for menu bar
            self.stdscr.attron(curses.color_pair(2) | curses.A_BOLD)
            self.stdscr.addstr(y, x, " " * width)
            self.stdscr.attroff(curses.color_pair(2) | curses.A_BOLD)
            
            # Menu text (centered)
            menu_items = ["[Q]uit", "[C]lear logs", "[R]efresh", "[S]ave", "[L]og filter", "[H]elp"]
            menu_text = "  ".join(menu_items)
            
            start_x = max(x, x + (width - len(menu_text)) // 2)
            
            # Draw menu text with cyan on pink
            self.stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
            self.stdscr.addstr(y, start_x, menu_text)
            
            # Highlight hotkeys with reverse video
            hotkeys = ['Q', 'C', 'R', 'S', 'L', 'H']
            for key in hotkeys:
                pos = menu_text.find(f"[{key}]")
                if pos != -1:
                    self.stdscr.chgat(y, start_x + pos + 1, 1, curses.A_REVERSE)
            
            self.stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
            
            # Status line below menu
            status_y = y + 1
            stats = self.stats_tracker.get_stats()
            timestamp = datetime.now().strftime("%H:%M:%S")
            status_text = f"🔄 Auto-refresh | CPU: {psutil.cpu_percent():.1f}% | RAM: {psutil.virtual_memory().percent:.1f}% | {timestamp}"
            
            self.stdscr.addstr(status_y, x, status_text[:width], curses.color_pair(6))
        except curses.error:
            pass
    
    def _draw_btop_bar(self, percent, width):
        """Draw btop-style gradient bar"""
        filled = int((percent / 100) * width)
        
        # Gradient: █▓▒░
        bar = ""
        for i in range(width):
            if i < filled:
                # Gradient based on position
                if i < filled * 0.3:
                    bar += "█"
                elif i < filled * 0.6:
                    bar += "▓"
                elif i < filled * 0.9:
                    bar += "▒"
                else:
                    bar += "░"
            else:
                bar += " "
        
        return bar
    
    def draw_full(self):
        """Draw the complete btop dashboard"""
        try:
            height, width = self.stdscr.getmaxyx()
            self.stdscr.clear()
            
            # Calculate layout
            top_height = height // 3 + 2  # Upper quadrants
            bottom_height = height - top_height - 3  # Logs (minus menu)
            menu_y = height - 2
            
            # Upper left quadrant (stats) - 60% width
            stats_width = int(width * 0.6)
            self.draw_stats_quadrant(0, 0, top_height, stats_width)
            
            # Upper right quadrant (alerts) - 40% width
            alerts_width = width - stats_width
            self.draw_alerts_quadrant(0, stats_width, top_height, alerts_width)
            
            # Bottom quadrant (logs) - full width
            self.draw_logs_quadrant(top_height, 0, bottom_height, width)
            
            # Bottom menu
            self.draw_menu(menu_y, 0, width)
            
            # Refresh
            self.stdscr.refresh()
            
        except curses.error:
            pass  # Ignore drawing errors if screen is too small
    
    def handle_input(self):
        """Handle keyboard input"""
        try:
            key = self.stdscr.getch()
            
            if key == curses.ERR:
                return True
                
            if key == ord('q') or key == ord('Q'):
                return False
            elif key == ord('c') or key == ord('C'):
                self.logger.clear_logs()
            elif key == ord('r') or key == ord('R'):
                self.draw_full()  # Force redraw
            elif key == ord('s') or key == ord('S'):
                self.stats_tracker.save_stats()
                self.logger.log("State saved", "SUCCESS")
            elif key == ord('l') or key == ord('L'):
                # Toggle log filter
                self.logger.log("Log filter toggled", "INFO")
            elif key == ord('h') or key == ord('H'):
                self.show_help()
            
            return True
        except:
            return True
    
    def show_help(self):
        """Show help overlay"""
        height, width = self.stdscr.getmaxyx()
        
        # Create help box
        help_height = 10
        help_width = 40
        help_y = (height - help_height) // 2
        help_x = (width - help_width) // 2
        
        # Draw help box
        self.stdscr.attron(curses.color_pair(2))
        for y in range(help_y, help_y + help_height):
            self.stdscr.addstr(y, help_x, " " * help_width)
        
        # Draw border
        self.stdscr.addstr(help_y, help_x, "┌" + "─" * (help_width - 2) + "┐")
        for i in range(1, help_height - 1):
            self.stdscr.addstr(help_y + i, help_x, "│")
            self.stdscr.addstr(help_y + i, help_x + help_width - 1, "│")
        self.stdscr.addstr(help_y + help_height - 1, help_x, "└" + "─" * (help_width - 2) + "┘")
        
        # Title
        self.stdscr.addstr(help_y, help_x + (help_width - 6) // 2, " HELP ", curses.A_BOLD)
        
        # Help text
        help_lines = [
            "Q - Quit dashboard",
            "C - Clear logs",
            "R - Refresh display",
            "S - Save state",
            "L - Toggle log filter",
            "H - Show this help",
            "",
            "Press any key to close"
        ]
        
        for i, line in enumerate(help_lines):
            if i < help_height - 2:
                self.stdscr.addstr(help_y + 1 + i, help_x + 2, line, curses.color_pair(1))
        
        self.stdscr.attroff(curses.color_pair(2))
        self.stdscr.refresh()
        
        # Wait for keypress
        self.stdscr.getch()
    
    def run(self):
        """Main dashboard loop"""
        try:
            last_update = 0
            while self.running:
                # Handle input (non-blocking)
                if not self.handle_input():
                    break
                
                # Update screen every 1 second
                current_time = time.time()
                if current_time - last_update > 1.0:
                    self.draw_full()
                    last_update = current_time
                
                # Sleep briefly to prevent CPU hogging
                time.sleep(0.05)
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean shutdown"""
        self.running = False
        
        # Reset terminal
        try:
            curses.nocbreak()
            curses.echo()
            curses.endwin()
        except:
            pass
        
        # Clear screen
        try:
            sys.stdout.write("\033[0m\033[2J\033[H\033[?25h")
            sys.stdout.flush()
        except:
            pass
