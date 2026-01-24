import curses
import time
import sys
import signal

class MinimalDashboard:
    """Simple, foolproof dashboard that always works"""
    
    def __init__(self, stdscr, logger, stats_tracker):
        self.stdscr = stdscr
        self.logger = logger
        self.stats_tracker = stats_tracker
        self.running = True
        
        # Basic curses setup that NEVER fails
        self.stdscr.nodelay(1)
        self.stdscr.timeout(100)
        curses.curs_set(0)  # Hide cursor
        
        # Use default terminal colors (no background colors)
        try:
            curses.start_color()
            curses.use_default_colors()
            
            # Define ONLY text colors (no background colors)
            curses.init_pair(1, curses.COLOR_WHITE, -1)   # White text
            curses.init_pair(2, curses.COLOR_GREEN, -1)   # Green text
            curses.init_pair(3, curses.COLOR_YELLOW, -1)  # Yellow text
            curses.init_pair(4, curses.COLOR_RED, -1)     # Red text
            curses.init_pair(5, curses.COLOR_CYAN, -1)    # Cyan text
            curses.init_pair(6, curses.COLOR_MAGENTA, -1) # Magenta text
        except:
            pass  # If colors fail, just use defaults
    
    def draw_screen(self):
        """Draw the entire screen - keep it SIMPLE"""
        try:
            height, width = self.stdscr.getmaxyx()
            
            # Clear screen
            self.stdscr.clear()
            
            # Title - top line
            title = "KAIA v2.0 DASHBOARD"
            self.stdscr.addstr(0, (width - len(title)) // 2, title, curses.A_BOLD)
            
            # Separator
            self.stdscr.addstr(1, 0, "═" * width)
            
            # Stats line
            stats = self.stats_tracker.get_stats()
            stats_line = f"👥 Users: {stats.get('active_users_count', 0):3d} | "
            stats_line += f"💬 Messages: {stats.get('messages', 0):6d} | "
            stats_line += f"⚡ Response: {stats.get('avg_response_time', 0.0):5.2f}s"
            
            self.stdscr.addstr(2, 0, stats_line[:width])
            
            # System info line
            import psutil
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory()
            
            sys_line = f"CPU: {cpu:5.1f}% | RAM: {mem.percent:5.1f}% | "
            sys_line += f"↻ {stats.get('messages_per_minute', 0.0):5.1f}/min"
            self.stdscr.addstr(3, 0, sys_line[:width])
            
            # Separator
            self.stdscr.addstr(4, 0, "─" * width)
            
            # Logs section title
            self.stdscr.addstr(5, 0, "SYSTEM LOGS:", curses.A_BOLD)
            
            # Get and display logs
            logs_start = 6
            max_logs = height - logs_start - 3
            logs = self.logger.get_recent_logs(max_logs)
            
            for i, log in enumerate(logs):
                y = logs_start + i
                if y >= height - 3:
                    break
                
                # Format log line
                timestamp = log.get('timestamp', '')
                message = log.get('message', '')[:80]  # Limit length
                
                # Color coding
                log_type = log.get('type', 'INFO')
                color = 1  # Default white
                
                if log_type == 'SUCCESS':
                    color = 2  # Green
                elif log_type == 'ERROR':
                    color = 4  # Red
                elif log_type == 'WARNING':
                    color = 3  # Yellow
                elif log_type == 'ACTION':
                    color = 6  # Magenta
                elif log_type == 'INFO':
                    color = 5  # Cyan
                
                try:
                    self.stdscr.addstr(y, 0, f"{timestamp} {message}"[:width], curses.color_pair(color))
                except:
                    pass  # Skip if line doesn't fit
            
            # Bottom menu - SIMPLE, NO BACKGROUND COLORS
            menu_y = height - 2
            menu_text = "[Q]uit  [C]lear  [R]efresh  [S]ave"
            
            # Center menu
            menu_x = max(0, (width - len(menu_text)) // 2)
            
            # Draw menu with white text
            self.stdscr.addstr(menu_y, menu_x, menu_text, curses.A_BOLD)
            
            # Highlight first letters
            highlights = {'Q': menu_text.find('[Q]'), 
                         'C': menu_text.find('[C]'),
                         'R': menu_text.find('[R]'),
                         'S': menu_text.find('[S]')}
            
            for key, pos in highlights.items():
                if pos != -1:
                    self.stdscr.chgat(menu_y, menu_x + pos + 1, 1, curses.A_REVERSE)
            
            # Status line
            timestamp = time.strftime("%H:%M:%S")
            status = f"Last update: {timestamp}"
            self.stdscr.addstr(height - 1, 0, status[:width])
            
            # Refresh screen
            self.stdscr.refresh()
            
        except curses.error as e:
            # If drawing fails, just continue
            pass
    
    def run(self):
        """Main loop"""
        last_update = 0
        
        try:
            while self.running:
                current_time = time.time()
                
                # Update every second
                if current_time - last_update >= 1.0:
                    self.draw_screen()
                    last_update = current_time
                
                # Handle input
                try:
                    key = self.stdscr.getch()
                    
                    if key == ord('q') or key == ord('Q'):
                        break
                    elif key == ord('c') or key == ord('C'):
                        self.logger.clear_logs()
                    elif key == ord('r') or key == ord('R'):
                        self.draw_screen()  # Force redraw
                    elif key == ord('s') or key == ord('S'):
                        self.stats_tracker.save_stats()
                        self.logger.log("State saved", "SUCCESS")
                        
                except:
                    pass
                
                # Small sleep
                time.sleep(0.05)
                
        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean shutdown - SAFE version"""
        try:
            curses.nocbreak()
            self.stdscr.keypad(0)
            curses.echo()
            curses.endwin()
        except:
            pass
        
        # Always reset terminal
        sys.stdout.write("\033[0m\033[2J\033[H\033[?25h")
        sys.stdout.flush()
