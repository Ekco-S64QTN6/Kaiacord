import curses
import time
import threading
from datetime import datetime
import psutil

class CyberpunkDashboard:
    """Dashboard with neon cyberpunk theme and clean shutdown"""
    
    def __init__(self, stdscr, logger, stats_tracker):
        self.stdscr = stdscr
        self.logger = logger
        self.stats_tracker = stats_tracker
        
        # UI dimensions
        self.status_height = 6
        self.logs_height = 12
        self.menu_height = 2
        
        # Control flags
        self.running = True
        self.need_redraw = True
        
        # Update intervals
        self.last_stats_update = 0
        self.stats_refresh = 1.0
        
        # Initialize cyberpunk colors
        self.init_cyberpunk_colors()
        
        # Start update thread
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
        
        # Set up keypad
        stdscr.keypad(True)
        stdscr.nodelay(True)
        
    def init_cyberpunk_colors(self):
        """Initialize neon cyberpunk color palette"""
        curses.start_color()
        curses.use_default_colors()
        
        # Try to define custom colors if terminal supports it
        try:
            # Cyberpunk neon colors (RGB)
            # These work in terminals with 256-color or true-color support
            
            # Neon cyan - #00ffff
            curses.init_color(100, 0, 1000, 1000)
            
            # Neon magenta - #ff00ff  
            curses.init_color(101, 1000, 0, 1000)
            
            # Neon green - #00ff00
            curses.init_color(102, 0, 1000, 0)
            
            # Neon yellow - #ffff00
            curses.init_color(103, 1000, 1000, 0)
            
            # Dark cyberpunk blue - #0a0a2a
            curses.init_color(104, 40, 40, 160)
            
            # Bright white - #ffffff
            curses.init_color(105, 1000, 1000, 1000)
            
            # Create color pairs
            # Pair 1: Menu background (neon cyan on dark blue)
            curses.init_pair(1, 100, 104)  # Neon cyan on dark blue
            
            # Pair 2: Menu text (white on neon cyan)
            curses.init_pair(2, 105, 100)  # White on neon cyan
            
            # Pair 3: Highlight (neon magenta on dark blue)
            curses.init_pair(3, 101, 104)  # Neon magenta on dark blue
            
            # Pair 4: Stats text (neon green on black)
            curses.init_pair(4, 102, curses.COLOR_BLACK)
            
            # Pair 5: CPU meter (neon cyan on black)
            curses.init_pair(5, 100, curses.COLOR_BLACK)
            
            # Pair 6: Memory meter (neon magenta on black)
            curses.init_pair(6, 101, curses.COLOR_BLACK)
            
            # Pair 7: High usage warning (neon yellow on black)
            curses.init_pair(7, 103, curses.COLOR_BLACK)
            
            # Pair 8: Log info (white on black)
            curses.init_pair(8, 105, curses.COLOR_BLACK)
            
            # Pair 9: Log success (neon green on black)
            curses.init_pair(9, 102, curses.COLOR_BLACK)
            
            # Pair 10: Log action (neon cyan on black)
            curses.init_pair(10, 100, curses.COLOR_BLACK)
            
            # Pair 11: Log warning (neon yellow on black)
            curses.init_pair(11, 103, curses.COLOR_BLACK)
            
            # Pair 12: Log error (neon magenta on black)
            curses.init_pair(12, 101, curses.COLOR_BLACK)
            
            self.colors_available = True
            
        except curses.error:
            # Fall back to standard colors with bold for visibility
            # print("⚠️ Terminal doesn't support custom colors, using bright fallback")
            
            # Standard bright colors for fallback
            curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLUE)
            curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_CYAN)
            curses.init_pair(3, curses.COLOR_MAGENTA, curses.COLOR_BLUE)
            curses.init_pair(4, curses.COLOR_GREEN, curses.COLOR_BLACK)
            curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_BLACK)
            curses.init_pair(6, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
            curses.init_pair(7, curses.COLOR_YELLOW, curses.COLOR_BLACK)
            curses.init_pair(8, curses.COLOR_WHITE, curses.COLOR_BLACK)
            curses.init_pair(9, curses.COLOR_GREEN, curses.COLOR_BLACK)
            curses.init_pair(10, curses.COLOR_CYAN, curses.COLOR_BLACK)
            curses.init_pair(11, curses.COLOR_YELLOW, curses.COLOR_BLACK)
            curses.init_pair(12, curses.COLOR_RED, curses.COLOR_BLACK)
            
            self.colors_available = False
        
        # Always use bold for cyberpunk feel
        self.menu_bg_attr = curses.color_pair(1) | curses.A_BOLD
        self.menu_text_attr = curses.color_pair(2) | curses.A_BOLD
        self.menu_highlight_attr = curses.color_pair(3) | curses.A_BOLD | curses.A_REVERSE
    
    def _update_loop(self):
        """Background thread for updates"""
        while self.running:
            try:
                current_time = time.time()
                
                # Update stats periodically
                if current_time - self.last_stats_update >= self.stats_refresh:
                    self.need_redraw = True
                    self.last_stats_update = current_time
                
                if self.need_redraw:
                    self.stdscr.erase() # Use erase for better performance
                    
                    # Recalculate dimensions dynamically
                    height, width = self.stdscr.getmaxyx()
                    self.logs_height = max(5, height - self.status_height - self.menu_height)
                    
                    self.draw_status_panel()
                    self.draw_logs_panel()
                    self.draw_cyberpunk_menu()
                    self.stdscr.refresh()
                    self.need_redraw = False
                
                time.sleep(0.05)
                
            except Exception as e:
                if self.running:  # Only log if not shutting down
                    # self.logger.log(f"Dashboard update error: {e}", "ERROR")
                    pass
                time.sleep(0.1)
    
    def draw_cyberpunk_menu(self):
        """Draw neon cyberpunk menu at bottom"""
        height, width = self.stdscr.getmaxyx()
        menu_y = height - self.menu_height
        
        # Clear menu area with cyberpunk background
        self.stdscr.attron(self.menu_bg_attr)
        for y in range(menu_y, height):
            try:
                self.stdscr.addstr(y, 0, " " * (width - 1))
            except curses.error:
                pass
        
        # Menu options with cyberpunk styling
        menu_lines = [
            "[Q]uit  [C]lear  [R]efresh  [L]ogs  [S]ave  [1-6]Views",
            "┌───────────────────┤ KAIA v2.0 │───────────────────┐"
        ]
        
        # Center each line
        for i, line in enumerate(menu_lines):
            start_x = max(0, (width - len(line)) // 2)
            y_pos = menu_y + i
            
            # Draw with cyberpunk text color
            self.stdscr.attron(self.menu_text_attr)
            try:
                self.stdscr.addstr(y_pos, start_x, line)
            except curses.error:
                pass
            
            # Highlight hotkeys with cyberpunk highlight
            hotkeys = ['Q', 'C', 'R', 'L', 'S']
            for key in hotkeys:
                idx = line.find(f"[{key}]")
                if idx != -1:
                    self.stdscr.attron(self.menu_highlight_attr)
                    try:
                        self.stdscr.addch(y_pos, start_x + idx + 1, key)
                    except curses.error:
                        pass
                    self.stdscr.attroff(self.menu_highlight_attr)
            
            self.stdscr.attroff(self.menu_text_attr)
        
        self.stdscr.attroff(self.menu_bg_attr)
    
    def draw_status_panel(self):
        """Draw status panel with cyberpunk styling"""
        height, width = self.stdscr.getmaxyx()
        
        # Get stats
        stats = self.stats_tracker.get_stats()
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        
        # Cyberpunk status bar
        status_bar = "┌─[ STATUS ]"
        status_bar += "─" * (width - len(status_bar) - 1) + "┐"
        
        self.stdscr.attron(curses.color_pair(4) | curses.A_BOLD)
        try:
            self.stdscr.addstr(0, 0, status_bar)
        except curses.error:
            pass
        
        # Stats line 1
        stats_line1 = f"│ 👥 {stats['active_users_count']:2d} users "
        stats_line1 += f"│ 💬 {stats['messages']:6d} msgs "
        stats_line1 += f"│ ⚡ {stats['avg_response_time']:5.2f}s "
        
        # Add padding to fill width
        remaining = width - len(stats_line1) - 1
        if remaining > 0:
            stats_line1 += " " * remaining + "│"
        
        try:
            self.stdscr.addstr(1, 0, stats_line1)
        except curses.error:
            pass
        
        # Stats line 2 with cyberpunk meters
        cpu_color = curses.color_pair(7 if cpu_percent > 80 else 5)
        mem_color = curses.color_pair(7 if memory.percent > 80 else 6)
        
        cpu_bar = self._draw_cyber_bar(cpu_percent, 15)
        mem_bar = self._draw_cyber_bar(memory.percent, 15)
        
        stats_line2 = f"│ CPU:"
        self.stdscr.attron(cpu_color)
        stats_line2 += f" {cpu_bar} {cpu_percent:5.1f}%"
        self.stdscr.attroff(cpu_color)
        
        stats_line2 += " │ RAM:"
        self.stdscr.attron(mem_color)
        stats_line2 += f" {mem_bar} {memory.percent:5.1f}%"
        self.stdscr.attroff(mem_color)
        
        stats_line2 += f" │ ↻ {stats['messages_per_minute']:5.1f}/min │"
        
        # Add timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        time_str = f" {timestamp} "
        stats_line2 = stats_line2[:-1] + time_str + "│"
        
        try:
            self.stdscr.addstr(2, 0, stats_line2)
        except curses.error:
            pass
        
        # Bottom border
        bottom_border = "└" + "─" * (width - 2) + "┘"
        try:
            self.stdscr.addstr(3, 0, bottom_border)
        except curses.error:
            pass
        
        self.stdscr.attroff(curses.color_pair(4) | curses.A_BOLD)
    
    def _draw_cyber_bar(self, percent, width):
        """Draw cyberpunk-style progress bar"""
        filled = int((percent / 100) * width)
        
        # Cyberpunk characters: █▓▒░ (solid to light)
        if filled == width:
            bar = "█" * width
        elif filled > 0:
            bar = "█" * (filled - 1) + "▓" + "░" * (width - filled)
        else:
            bar = "░" * width
        
        return bar
    
    def draw_logs_panel(self):
        """Draw logs panel"""
        height, width = self.stdscr.getmaxyx()
        logs_y = 4  # After status panel
        
        # Calculate dynamic height
        available_height = height - self.status_height - self.menu_height
        if available_height < 1:
            return

        # Get recent logs
        logs = self.logger.get_recent_logs(available_height)
        
        # Clear logs area
        for y in range(logs_y, logs_y + available_height):
            try:
                self.stdscr.addstr(y, 0, " " * (width - 1))
            except curses.error:
                pass
        
        # Display logs with cyberpunk colors
        for i, log in enumerate(logs):
            y = logs_y + i
            if y >= logs_y + available_height:
                break
            
            # Map log types to cyberpunk colors
            color_map = {
                'INFO': 8,      # White
                'ACTION': 10,   # Neon cyan
                'SUCCESS': 9,   # Neon green
                'WARNING': 11,  # Neon yellow
                'ERROR': 12     # Neon magenta
            }
            
            color_pair = color_map.get(log['type'], 8)
            
            # Format log line (single timestamp)
            log_line = f"{log['timestamp']} {log['type']}: {log['message']}"
            
            # Truncate
            if len(log_line) > width - 2:
                log_line = log_line[:width - 5] + "..."
            
            # Draw with cyberpunk color
            try:
                self.stdscr.attron(curses.color_pair(color_pair))
                self.stdscr.addstr(y, 0, log_line)
                self.stdscr.attroff(curses.color_pair(color_pair))
            except curses.error:
                pass
    
    def handle_input(self):
        """Handle keyboard input"""
        try:
            key = self.stdscr.getch()
            
            if key == ord('q') or key == ord('Q'):
                return False  # Signal to quit
            
            elif key == ord('c') or key == ord('C'):
                self.logger.clear_logs()
                self.need_redraw = True
                
            elif key == ord('r') or key == ord('R'):
                self.need_redraw = True
                
            elif key == ord('l') or key == ord('L'):
                # Toggle log filter
                self.need_redraw = True
                
            elif key == ord('s') or key == ord('S'):
                # Save state
                self.stats_tracker.save_stats()
                self.logger.log("State saved", "SUCCESS")
                self.need_redraw = True
            
            return True  # Continue running
            
        except curses.error:
            return True
    
    def run(self):
        """Main dashboard loop"""
        try:
            while self.running:
                # Handle input
                should_continue = self.handle_input()
                if not should_continue:
                    break
                
                # Small sleep to prevent CPU hogging
                time.sleep(0.05)
                
        except KeyboardInterrupt:
            pass  # Allow clean shutdown
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources"""
        self.running = False
        
        if self.update_thread.is_alive():
            self.update_thread.join(timeout=1.0)
        
        # Clean up curses
        try:
            curses.nocbreak()
            self.stdscr.keypad(False)
            curses.echo()
            curses.endwin()
        except:
            pass
        
        # Clear terminal
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
