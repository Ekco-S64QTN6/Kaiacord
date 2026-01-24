import curses
import time
import sys
from datetime import datetime
import psutil

class ProfessionalDashboard:
    """Clean, professional dashboard with dark theme"""
    
    def __init__(self, stdscr, logger, stats_tracker):
        self.stdscr = stdscr
        self.logger = logger
        self.stats_tracker = stats_tracker
        
        # Setup curses properly
        self.setup_curses()
        
        # State
        self.running = True
        
    def setup_curses(self):
        """Setup curses with proper terminal handling"""
        curses.curs_set(0)  # Hide cursor
        self.stdscr.nodelay(1)  # Non-blocking input
        self.stdscr.timeout(100)  # 100ms timeout
        
        # Use terminal's default colors (dark theme)
        curses.use_default_colors()
        
        # Initialize color pairs for professional look
        self.init_colors()
        
    def init_colors(self):
        """Initialize professional color scheme"""
        curses.start_color()
        
        # Professional dark theme colors
        # Pair 1: White text on black (normal text)
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
        
        # Pair 2: Bright white text on black (headers)
        curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)
        
        # Pair 3: Cyan text on black (status)
        curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)
        
        # Pair 4: Green text on black (success/good)
        curses.init_pair(4, curses.COLOR_GREEN, curses.COLOR_BLACK)
        
        # Pair 5: Yellow text on black (warning)
        curses.init_pair(5, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        
        # Pair 6: Red text on black (error/critical)
        curses.init_pair(6, curses.COLOR_RED, curses.COLOR_BLACK)
        
        # Pair 7: Magenta text on black (highlight)
        curses.init_pair(7, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        
        # Pair 8: Blue text on black (info)
        curses.init_pair(8, curses.COLOR_BLUE, curses.COLOR_BLACK)
        
    def draw_border(self, y, x, width, title=None):
        """Draw a clean border box"""
        height = 3
        
        # Top border
        if title:
            title_str = f"[ {title} ]"
            left_len = (width - len(title_str)) // 2
            right_len = width - len(title_str) - left_len - 2
            top_line = "─" * left_len + title_str + "─" * right_len
            self.stdscr.addstr(y, x, "┌" + top_line + "┐")
        else:
            self.stdscr.addstr(y, x, "┌" + "─" * (width - 2) + "┐")
        
        # Middle (empty)
        for i in range(1, height - 1):
            self.stdscr.addstr(y + i, x, "│")
            self.stdscr.addstr(y + i, x + width - 1, "│")
            
        # Bottom border
        self.stdscr.addstr(y + height - 1, x, "└" + "─" * (width - 2) + "┘")
        
        return y + height
    
    def draw_status_box(self):
        """Draw the status box with clean layout"""
        height, width = self.stdscr.getmaxyx()
        
        # Clear top area
        for y in range(0, 5):
            self.stdscr.addstr(y, 0, " " * width)
        
        # Get stats
        stats = self.stats_tracker.get_stats()
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        
        # Draw status border with title
        self.stdscr.attron(curses.color_pair(2) | curses.A_BOLD)
        self.draw_border(0, 0, width, "KAIA v2.0 STATUS")
        self.stdscr.attroff(curses.color_pair(2) | curses.A_BOLD)
        
        # Row 1: User stats
        row1 = f"👥 Users: {stats.get('active_users_count', 0):3d} | "
        row1 += f"💬 Messages: {stats.get('messages', 0):6d} | "
        row1 += f"⚡ Response: {stats.get('avg_response_time', 0.0):5.2f}s"
        
        self.stdscr.attron(curses.color_pair(1))
        self.stdscr.addstr(1, 2, row1[:width-4])
        self.stdscr.attroff(curses.color_pair(1))
        
        # Row 2: System stats
        cpu_bar = self._draw_bar(cpu_percent, 15)
        mem_bar = self._draw_bar(memory.percent, 15)
        
        row2 = f"CPU: {cpu_bar} {cpu_percent:5.1f}% | "
        row2 += f"RAM: {mem_bar} {memory.percent:5.1f}% | "
        row2 += f"↻ {stats.get('messages_per_minute', 0.0):5.1f}/min"
        
        # Color CPU and RAM based on usage
        self.stdscr.attron(curses.color_pair(1))
        self.stdscr.addstr(2, 2, "CPU: ")
        
        if cpu_percent > 80:
            self.stdscr.attron(curses.color_pair(6))
        elif cpu_percent > 60:
            self.stdscr.attron(curses.color_pair(5))
        else:
            self.stdscr.attron(curses.color_pair(4))
        
        self.stdscr.addstr(f"{cpu_bar} {cpu_percent:5.1f}%")
        self.stdscr.attroff(curses.A_NORMAL)
        
        self.stdscr.attron(curses.color_pair(1))
        self.stdscr.addstr(" | RAM: ")
        
        if memory.percent > 80:
            self.stdscr.attron(curses.color_pair(6))
        elif memory.percent > 60:
            self.stdscr.attron(curses.color_pair(5))
        else:
            self.stdscr.attron(curses.color_pair(4))
        
        self.stdscr.addstr(f"{mem_bar} {memory.percent:5.1f}%")
        self.stdscr.attroff(curses.A_NORMAL)
        
        self.stdscr.attron(curses.color_pair(1))
        self.stdscr.addstr(f" | ↻ {stats.get('messages_per_minute', 0.0):5.1f}/min")
        self.stdscr.attroff(curses.color_pair(1))
        
        # Timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        time_str = f" [{timestamp}]"
        if len(time_str) <= width - 2:
            self.stdscr.attron(curses.color_pair(3))
            self.stdscr.addstr(2, width - len(time_str) - 2, time_str)
            self.stdscr.attroff(curses.color_pair(3))
        
        return 4  # Return next y position
    
    def _draw_bar(self, percent, width):
        """Draw a simple progress bar"""
        filled = int((percent / 100) * width)
        return "█" * filled + "░" * (width - filled)
    
    def draw_logs(self, start_y):
        """Draw the logs section"""
        height, width = self.stdscr.getmaxyx()
        logs_height = height - start_y - 3
        
        # Clear logs area
        for y in range(start_y, height - 3):
            self.stdscr.addstr(y, 0, " " * width)
        
        # Draw logs border
        self.stdscr.attron(curses.color_pair(2) | curses.A_BOLD)
        self.draw_border(start_y, 0, width, "SYSTEM LOGS")
        self.stdscr.attroff(curses.color_pair(2) | curses.A_BOLD)
        
        # Get logs
        logs = self.logger.get_recent_logs(logs_height - 2)
        
        # Display logs
        for i, log in enumerate(logs):
            y = start_y + 1 + i
            if y >= height - 4:
                break
            
            # Format log line
            timestamp = log.get('timestamp', '')
            message = log.get('message', '')
            
            # Choose color based on type
            log_type = log.get('type', 'INFO')
            if log_type == 'SUCCESS':
                color = curses.color_pair(4)
            elif log_type == 'ERROR':
                color = curses.color_pair(6)
            elif log_type == 'WARNING':
                color = curses.color_pair(5)
            elif log_type == 'ACTION':
                color = curses.color_pair(7)
            elif log_type == 'INFO':
                color = curses.color_pair(8)
            else:
                color = curses.color_pair(1)
            
            # Create log line
            log_line = f"{timestamp} {message}"
            if len(log_line) > width - 4:
                log_line = log_line[:width - 7] + "..."
            
            # Draw log
            self.stdscr.attron(color)
            self.stdscr.addstr(y, 2, log_line)
            self.stdscr.attroff(color)
    
    def draw_menu(self):
        """Draw a clean menu at the bottom"""
        height, width = self.stdscr.getmaxyx()
        menu_y = height - 2
        
        # Clear menu area with black background
        for y in range(menu_y, height):
            self.stdscr.addstr(y, 0, " " * width)
        
        # Menu options (centered)
        menu_items = ["[Q]uit", "[C]lear", "[R]efresh", "[L]ogs", "[S]ave"]
        menu_text = "  ".join(menu_items)
        
        # Center the menu
        start_x = max(0, (width - len(menu_text)) // 2)
        
        # Draw menu text with white on black
        self.stdscr.attron(curses.color_pair(1))
        self.stdscr.addstr(menu_y, start_x, menu_text)
        
        # Highlight hotkeys with cyan
        hotkeys = ['Q', 'C', 'R', 'L', 'S']
        for key in hotkeys:
            pos = menu_text.find(f"[{key}]")
            if pos != -1:
                self.stdscr.attron(curses.color_pair(3) | curses.A_BOLD)
                self.stdscr.addch(menu_y, start_x + pos + 1, key)
                self.stdscr.attroff(curses.color_pair(3) | curses.A_BOLD)
        
        self.stdscr.attroff(curses.color_pair(1))
        
        # Status line
        stats = self.stats_tracker.get_stats()
        uptime_mins = stats.get('uptime_minutes', 0)
        status_text = f"🔄 Auto-refresh | Uptime: {uptime_mins:.0f}m"
        
        status_x = max(0, (width - len(status_text)) // 2)
        self.stdscr.attron(curses.color_pair(3))
        self.stdscr.addstr(menu_y + 1, status_x, status_text)
        self.stdscr.attroff(curses.color_pair(3))
    
    def draw(self):
        """Draw the entire dashboard"""
        self.stdscr.clear()
        
        # Draw all components
        next_y = self.draw_status_box()
        self.draw_logs(next_y)
        self.draw_menu()
        
        self.stdscr.refresh()
    
    def handle_input(self):
        """Handle keyboard input"""
        try:
            key = self.stdscr.getch()
            
            if key == ord('q') or key == ord('Q'):
                return False
            elif key == ord('c') or key == ord('C'):
                self.logger.clear_logs()
            elif key == ord('r') or key == ord('R'):
                pass  # Redraw happens automatically
            elif key == ord('s') or key == ord('S'):
                self.stats_tracker.save_stats()
                self.logger.log("State saved", "SUCCESS")
            
            return True
        except curses.error:
            return True
    
    def run(self):
        """Main dashboard loop"""
        last_update = 0
        update_interval = 1.0  # Update every second
        
        try:
            while self.running:
                current_time = time.time()
                
                # Update periodically or on input
                if current_time - last_update >= update_interval:
                    self.draw()
                    last_update = current_time
                
                # Handle input
                if not self.handle_input():
                    break
                
                # Small sleep
                time.sleep(0.05)
                
        except KeyboardInterrupt:
            pass
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
        
        # Clear screen and show cursor
        sys.stdout.write("\033[2J\033[H\033[?25h")
        sys.stdout.flush()
