import curses
import time
import threading
from datetime import datetime
from collections import deque
import psutil
from utils.terminal_manager import TerminalManager

class DashboardUI:
    def __init__(self, stdscr, logger, stats_tracker):
        self.stdscr = stdscr
        self.logger = logger
        self.stats_tracker = stats_tracker
        
        # UI dimensions
        self.status_height = 6
        self.menu_height = 2
        # logs_height is now dynamic

        
        # Update intervals
        self.stats_refresh = 1.0  # Update stats every 1 second
        self.logs_refresh = 0.5   # Update logs every 0.5 seconds
        self.last_stats_update = 0
        self.last_logs_update = 0
        
        # Terminal Manager for raw mode
        self.terminal = TerminalManager()
        
        # Color pairs
        self.init_colors()
        
        # Start update thread
        self.running = True
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
        
    def init_colors(self):
        """Initialize color pairs for high visibility"""
        curses.start_color()
        curses.use_default_colors()
        
        # Menu colors (neon cyan background, white text)
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_CYAN)
        
        # Status panel colors - NEON CYBERPUNK THEME
        # Use bold/bright variants for neon effect
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Stats text
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK) # CPU
        curses.init_pair(4, curses.COLOR_MAGENTA, curses.COLOR_BLACK) # Memory
        curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_BLACK)   # GPU
        curses.init_pair(6, curses.COLOR_RED, curses.COLOR_BLACK)    # High usage
        
        # Log colors - Neon variants
        curses.init_pair(10, curses.COLOR_WHITE, curses.COLOR_BLACK)   # INFO
        curses.init_pair(11, curses.COLOR_MAGENTA, curses.COLOR_BLACK) # ACTION
        curses.init_pair(12, curses.COLOR_GREEN, curses.COLOR_BLACK)   # SUCCESS
        curses.init_pair(13, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # WARNING
        curses.init_pair(14, curses.COLOR_RED, curses.COLOR_BLACK)     # ERROR
    
    def _update_loop(self):
        """Background thread that updates UI periodically"""
        while self.running:
            try:
                current_time = time.time()
                
                # Update stats panel
                if current_time - self.last_stats_update >= self.stats_refresh:
                    self.stdscr.erase() # Use erase instead of clear for better performance
                    
                    # Recalculate dimensions
                    height, width = self.stdscr.getmaxyx()
                    self.logs_height = max(5, height - self.status_height - self.menu_height)
                    
                    self.draw_status_panel()
                    self.draw_logs_panel()
                    self.draw_menu()
                    self.stdscr.refresh()
                    self.last_stats_update = current_time
                
                # Update logs more frequently
                if current_time - self.last_logs_update >= self.logs_refresh:
                    self.draw_logs_panel()
                    self.stdscr.refresh()
                    self.last_logs_update = current_time
                
                time.sleep(0.1)
            except:
                pass
    
    def draw_status_panel(self):
        """Draw the status panel with live stats"""
        height, width = self.stdscr.getmaxyx()
        
        # Clear status area
        for y in range(self.status_height):
            self.stdscr.addstr(y, 0, " " * width)
        
        # Get current stats
        stats = self.stats_tracker.get_stats()
        
        # Get system stats
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        
        # Draw border
        self.stdscr.hline(0, 0, curses.ACS_HLINE, width)
        self.stdscr.hline(self.status_height-1, 0, curses.ACS_HLINE, width)
        self.stdscr.addch(0, 0, curses.ACS_ULCORNER)
        self.stdscr.addch(0, width-1, curses.ACS_URCORNER)
        self.stdscr.addch(self.status_height-1, 0, curses.ACS_LLCORNER)
        self.stdscr.addch(self.status_height-1, width-1, curses.ACS_LRCORNER)
        
        # Title
        self.stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        self.stdscr.addstr(0, 2, " KAIA 2.0 - STATUS & METRICS ")
        self.stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
        
        # Column 1: Bot Stats (left side)
        col1_x = 2
        self.stdscr.attron(curses.color_pair(2))
        
        # Users and Messages (with icons)
        self.stdscr.addstr(1, col1_x, f"👥 {stats['active_users_count']:2d} users")
        self.stdscr.addstr(2, col1_x, f"💬 {stats['messages']:6d} msgs")
        self.stdscr.addstr(3, col1_x, f"⚡ {stats['avg_response_time']:5.2f}s avg")
        self.stdscr.addstr(4, col1_x, f"📊 {stats['queue_size']:2d} in queue")
        
        # Column 2: System Stats (middle)
        col2_x = width // 3
        self.stdscr.addstr(1, col2_x, "SYSTEM:")
        
        # CPU with colored bar
        cpu_color = curses.color_pair(6 if cpu_percent > 80 else 3)
        cpu_bar = self._draw_bar(cpu_percent, 15)
        self.stdscr.attron(cpu_color)
        self.stdscr.addstr(2, col2_x, f"CPU: {cpu_bar} {cpu_percent:5.1f}%")
        self.stdscr.attroff(cpu_color)
        
        # Memory
        mem_gb = memory.used / 1024 / 1024 / 1024
        mem_percent = memory.percent
        mem_color = curses.color_pair(6 if mem_percent > 80 else 4)
        mem_bar = self._draw_bar(mem_percent, 15)
        self.stdscr.attron(mem_color)
        self.stdscr.addstr(3, col2_x, f"RAM: {mem_bar} {mem_gb:5.1f}GB")
        self.stdscr.attroff(mem_color)
        
        # Column 3: Performance (right side)
        col3_x = 2 * width // 3
        self.stdscr.addstr(1, col3_x, "PERFORMANCE:")
        self.stdscr.addstr(2, col3_x, f"↻ {stats['messages_per_minute']:5.1f} msg/min")
        self.stdscr.addstr(3, col3_x, f"⏱️  {stats['uptime_hours']:5.1f} hrs up")
        
        # Last update timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        try:
            self.stdscr.addstr(self.status_height-1, width - 10, f"🔄 {timestamp}")
        except curses.error:
            pass # Ignore error if window is too small
        
        self.stdscr.attroff(curses.color_pair(2))
    
    def _draw_bar(self, percent, width):
        """Draw a text progress bar"""
        filled = int((percent / 100) * width)
        bar = "█" * filled + "░" * (width - filled)
        return bar
    
    def draw_logs_panel(self):
        """Draw the logs panel"""
        height, width = self.stdscr.getmaxyx()
        logs_y = self.status_height
        
        # Calculate dynamic height
        available_height = height - self.status_height - self.menu_height
        if available_height < 1:
            return
            
        # Clear logs area
        for y in range(logs_y, logs_y + available_height):
            try:
                self.stdscr.addstr(y, 0, " " * (width - 1))
            except curses.error:
                pass
        
        # Get recent logs
        logs = self.logger.get_recent_logs(available_height)
        
        # Display logs
        for i, log in enumerate(logs):
            y = logs_y + i
            if y >= logs_y + available_height:
                break
            
            # Choose color based on log type
            color_map = {
                'INFO': 10,
                'ACTION': 11,
                'SUCCESS': 12,
                'WARNING': 13,
                'ERROR': 14
            }
            color_pair = color_map.get(log['type'], 10)
            
            # Format log line (single timestamp!)
            log_line = f"{log['timestamp']} {log['type']}: {log['message']}"
            
            # Truncate if too long
            if len(log_line) > width - 1:
                log_line = log_line[:width - 4] + "..."
            
            # Draw with color
            try:
                self.stdscr.attron(curses.color_pair(color_pair))
                self.stdscr.addstr(y, 0, log_line)
                self.stdscr.attroff(curses.color_pair(color_pair))
            except curses.error:
                pass
    
    def draw_menu(self):
        """Draw the bottom menu with high visibility"""
        height, width = self.stdscr.getmaxyx()
        menu_y = height - self.menu_height
        
        # Clear menu area with bright background
        self.stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
        for y in range(menu_y, height):
            try:
                self.stdscr.addstr(y, 0, " " * (width - 1))
            except curses.error:
                pass
        
        # Menu text (centered)
        menu_items = ["[Q]uit", "[C]lear logs", "[R]efresh", "[L]og filter", "[S]ave", "[1-6]Views"]
        menu_text = "  ".join(menu_items)
        
        start_x = max(0, (width - len(menu_text)) // 2)
        try:
            self.stdscr.addstr(menu_y, start_x, menu_text)
        except curses.error:
            pass
        
        # Status line below menu
        stats = self.stats_tracker.get_stats()
        status_text = f"Auto-refresh | Users: {stats['active_users_count']} | Messages: {stats['messages']}"
        status_x = max(0, (width - len(status_text)) // 2)
        try:
            self.stdscr.addstr(menu_y + 1, status_x, status_text)
        except curses.error:
            pass
        
        # Highlight hotkeys
        hotkeys = ['Q', 'C', 'R', 'L', 'S']
        for key in hotkeys:
            pos = menu_text.find(f"[{key}]")
            if pos != -1:
                try:
                    self.stdscr.attron(curses.color_pair(6) | curses.A_BOLD)
                    self.stdscr.addch(menu_y, start_x + pos + 1, key)
                    self.stdscr.attroff(curses.color_pair(6) | curses.A_BOLD)
                except curses.error:
                    pass
        
        self.stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
    
    def main_loop(self):
        """Main dashboard loop"""
        self.stdscr.nodelay(True)
        
        # Enter dashboard mode
        self.terminal.enter_dashboard_mode()
        self.logger.set_dashboard_mode(True)
        
        try:
            while self.running:
                # Handle keyboard input
                try:
                    key = self.stdscr.getch()
                    if key != -1:
                        if key == ord('q') or key == ord('Q'):
                            break
                        elif key == ord('c') or key == ord('C'):
                            self.logger.clear_logs()
                        elif key == ord('r') or key == ord('R'):
                            # Force full refresh
                            self.stdscr.clear()
                            self.draw_status_panel()
                            self.draw_logs_panel()
                            self.draw_menu()
                            self.stdscr.refresh()
                except:
                    pass
                
                time.sleep(0.05)
        finally:
            self.running = False
            # Exit dashboard mode
            self.logger.set_dashboard_mode(False)
            self.terminal.exit_dashboard_mode()
            
            # Force terminal reset to clear any artifacts
            try:
                curses.endwin()
                # Print reset code to clear any lingering modes
                print("\033[0m\033[?25h", end='', flush=True)
            except:
                pass
