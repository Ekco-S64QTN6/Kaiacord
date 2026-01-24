import curses
import time
import sys
import threading
from datetime import datetime

class CleanDashboard:
    """Clean, professional dashboard that actually works"""
    
    def __init__(self, stdscr, logger, stats_tracker):
        self.stdscr = stdscr
        self.logger = logger
        self.stats_tracker = stats_tracker
        self.running = True
        
        # Basic setup
        curses.curs_set(0)  # Hide cursor
        self.stdscr.nodelay(True)
        self.stdscr.timeout(100)
        
        # Initialize colors - SIMPLE AND WORKING
        self.init_simple_colors()
        
    def init_simple_colors(self):
        """Initialize only basic colors that work everywhere"""
        curses.start_color()
        
        # ONLY use these 3 color pairs - guaranteed to work
        # Pair 1: White text (default)
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
        
        # Pair 2: Green text (for good status)
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
        
        # Pair 3: Red text (for errors/warnings)
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
        
    def draw_screen(self):
        """Draw the entire screen - KEEP IT SIMPLE"""
        try:
            height, width = self.stdscr.getmaxyx()
            self.stdscr.clear()
            
            # === TOP STATUS BAR ===
            # Simple line: [STATUS] Users: X | Messages: Y | CPU: Z%
            stats = self.stats_tracker.get_stats()
            
            status_line = f"KAIA v2.0 | 👥 {stats.get('active_users_count', 0):2d} | "
            status_line += f"💬 {stats.get('messages', 0):4d} | "
            status_line += f"⚡ {stats.get('avg_response_time', 0.0):.1f}s"
            
            # Center it
            start_x = max(0, (width - len(status_line)) // 2)
            self.stdscr.addstr(0, start_x, status_line, curses.A_BOLD)
            
            # Separator line
            self.stdscr.addstr(1, 0, "─" * width)
            
            # === LOGS AREA ===
            logs_start = 2
            logs_height = height - 6  # Leave room for bottom
            
            # Get logs
            logs = self.logger.get_recent_logs(logs_height)
            
            for i, log in enumerate(logs):
                y = logs_start + i
                if y >= height - 4:
                    break
                
                # Simple format: TIME TYPE: Message
                timestamp = log.get('timestamp', '')
                message = log.get('message', '')
                log_type = log.get('type', 'INFO')
                
                # Truncate if too long
                line = f"{timestamp} {log_type}: {message}"
                if len(line) > width:
                    line = line[:width-3] + "..."
                
                # Basic color coding
                if 'ERROR' in log_type:
                    self.stdscr.addstr(y, 0, line, curses.color_pair(3))
                elif 'SUCCESS' in log_type:
                    self.stdscr.addstr(y, 0, line, curses.color_pair(2))
                else:
                    self.stdscr.addstr(y, 0, line, curses.color_pair(1))
            
            # === BOTTOM MENU ===
            menu_y = height - 3
            
            # Separator
            self.stdscr.addstr(menu_y, 0, "─" * width)
            
            # Simple menu - NO BACKGROUND COLORS
            menu_text = "[Q]uit  [C]lear  [R]efresh  [S]ave"
            menu_x = max(0, (width - len(menu_text)) // 2)
            
            self.stdscr.addstr(menu_y + 1, menu_x, menu_text, curses.A_BOLD)
            
            # Highlight Q with reverse video
            q_pos = menu_text.find('Q')
            if q_pos != -1:
                self.stdscr.chgat(menu_y + 1, menu_x + q_pos, 1, curses.A_REVERSE)
            
            # Status line
            time_str = datetime.now().strftime("%H:%M:%S")
            status = f"Last update: {time_str}"
            self.stdscr.addstr(menu_y + 2, 0, status)
            
            self.stdscr.refresh()
            
        except curses.error:
            # If we can't draw, just continue
            pass
    
    def handle_input(self):
        """Handle keyboard input"""
        try:
            key = self.stdscr.getch()
            
            if key == ord('q') or key == ord('Q'):
                return False
            elif key == ord('c') or key == ord('C'):
                self.logger.clear_logs()
            elif key == ord('r') or key == ord('R'):
                self.draw_screen()  # Force redraw
            elif key == ord('s') or key == ord('S'):
                self.stats_tracker.save_stats()
                self.logger.log("State saved", "SUCCESS")
            
            return True
        except:
            return True
    
    def run(self):
        """Main dashboard loop - SIMPLE AND RELIABLE"""
        last_draw = 0
        
        try:
            while self.running:
                current_time = time.time()
                
                # Update every second
                if current_time - last_draw >= 1.0:
                    self.draw_screen()
                    last_draw = current_time
                
                # Handle input
                if not self.handle_input():
                    break
                
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
        
        # Clear screen
        try:
            sys.stdout.write("\033[0m\033[2J\033[H\033[?25h")
            sys.stdout.flush()
        except:
            pass
