"""
btop-Style Curses Dashboard for Kaiacord
=========================================

A production-ready, thread-safe curses dashboard following strict architectural rules:
- curses runs ONLY in the main UI thread
- Snapshot-based rendering (no partial updates)
- Pane-based layout with proper resize handling
- Terminal safety with guaranteed cleanup

Author: Kaiacord Team
"""

import curses
import time
import sys
import os
import threading
import signal
from utils.infrastructure.system.shutdown_fixed import shutdown_manager
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Deque
from collections import deque
from datetime import datetime
import copy


# ==================== DATACLASSES ====================

@dataclass
class LogEntry:
    """Immutable log entry for snapshot"""
    timestamp: str
    log_type: str
    message: str
    source: str = "system"


@dataclass
class AlertEntry:
    """Immutable alert entry for snapshot"""
    timestamp: str
    level: str  # ERROR, WARNING, CRITICAL
    message: str
    symbol: str = "⚠️"


@dataclass
class DashboardState:
    """
    Immutable snapshot of dashboard state for rendering.
    Created once per frame from thread-safe sources.
    """
    # System metrics
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    gpu_util: float = 0.0
    gpu_memory: str = "N/A"
    disk_percent: float = 0.0
    net_sent_kbs: float = 0.0  # KB/s rate (not cumulative)
    net_recv_kbs: float = 0.0  # KB/s rate (not cumulative)
    
    # Bot metrics
    uptime_minutes: float = 0.0
    active_users: str = "0 (idle)"
    total_messages: int = 0
    avg_response_time: float = 0.0
    ollama_status: str = "🔴 OFFLINE"
    active_model: str = "None"
    ollama_models: Tuple[str, ...] = field(default_factory=tuple)
    rag_size: str = "0 MB"
    kb_size_mb: float = 0.0
    log_size_mb: float = 0.0
    indexed_files: int = 0
    dreams_count: int = 0
    queue_size: int = 0
    
    # Logs and alerts (tuples for immutability)
    log_entries: Tuple[LogEntry, ...] = field(default_factory=tuple)
    alerts: Tuple[AlertEntry, ...] = field(default_factory=tuple)
    
    # RAG Metrics
    rag_confidence: float = 0.0
    rag_nodes: int = 0
    coherence_ema: float = 0.85
    hallucination_count: int = 0
    rag_stale: bool = True  # True if last RAG query was >15 min ago
    
    # Cognition & Forums
    beliefs_count: int = 0
    anchors_count: int = 0
    relationship_count: int = 0
    forum_drafts: int = 0
    forum_approved: int = 0
    forum_rejected: int = 0
    
    # Timestamp
    snapshot_time: float = field(default_factory=time.time)


# ==================== PANE LAYOUT ====================

@dataclass
class Pane:
    """Represents a rectangular pane in the layout"""
    y: int
    x: int
    height: int
    width: int
    title: str = ""
    footer: str = ""
    color_pair: int = 1


class LayoutManager:
    """Manages pane-based layout with resize handling"""
    
    def __init__(self):
        self.height = 24
        self.width = 80
        self.panes: Dict[str, Pane] = {}
        
    def calculate_layout(self, height: int, width: int):
        """Calculate pane dimensions based on terminal size"""
        self.height = height
        self.width = width
        
        # Minimum dimensions
        if height < 20 or width < 60:
            return False
        
        # Title is now integrated into the panels
        header_height = 0
        
        # Footer (1 line: just a tiny gap at the bottom)
        footer_height = 1
        
        # Available height for content
        content_height = height - header_height - footer_height
        
        # Top section (stats + status): 45% of content, min 10 lines
        top_height = max(10, int(content_height * 0.45))
        
        # Alerts section: 15% of content, min 4 lines
        alerts_height = max(4, int(content_height * 0.15))
        
        # Logs section: remaining space
        logs_height = content_height - top_height - alerts_height
        
        # Width splits (Symmetric three-column split on top)
        left_width = int(width * 0.35)
        right_width = width - left_width
        middle_width = int(right_width * 0.5)
        far_right_width = right_width - middle_width
        
        # Define panes
        y = header_height
        
        # System stats (top left)
        self.panes['stats'] = Pane(
            y=y, x=0, 
            height=top_height, width=left_width,
            title="SYSTEM STATS", color_pair=1
        )
        
        # Bot status (top middle)
        status_height = top_height - 6
        self.panes['status'] = Pane(
            y=y, x=left_width,
            height=status_height, width=middle_width,
            title="BOT STATUS", color_pair=2
        )
        
        # Cognitive Pipeline (top far right)
        self.panes['cognition'] = Pane(
            y=y, x=left_width + middle_width,
            height=status_height, width=far_right_width,
            title="COGNITIVE PIPELINE", color_pair=6
        )
        
        # RAG Health (middle right)
        self.panes['rag_health'] = Pane(
            y=y + status_height, x=left_width,
            height=6, width=right_width,
            title="RAG HEALTH", color_pair=3
        )
        
        y += top_height
        
        # Alerts (full width)
        self.panes['alerts'] = Pane(
            y=y, x=0,
            height=alerts_height, width=width,
            title="ALERTS", color_pair=4
        )
        
        y += alerts_height
        
        # Menu text with cyberpunk separators
        menu_footer = "[Q]uit ╭─╮ [C]lear ╭─╮ [R]efresh ╭─╮ [S]ave ╭─╮ [H]elp"
        
        # Logs (full width)
        self.panes['logs'] = Pane(
            y=y, x=0,
            height=logs_height, width=width,
            title="LIVE LOGS", footer=menu_footer, color_pair=1
        )
        
        # Footer
        self.panes['footer'] = Pane(
            y=height - footer_height, x=0,
            height=footer_height, width=width,
            title="", color_pair=2
        )
        
        return True


# ==================== MAIN DASHBOARD CLASS ====================

class BtopDashboardV2:
    """
    Production-ready btop-style curses dashboard.
    
    Architecture Rules:
    1. curses runs ONLY in this class, ONLY in the main thread
    2. Background threads update thread-safe data sources
    3. UI loop takes snapshots and renders full frames
    4. Terminal is ALWAYS restored on exit
    """
    
    # Unicode box drawing characters
    BOX = {
        'tl': '╭', 'tr': '╮', 'bl': '╰', 'br': '╯',
        'h': '─', 'v': '│', 'ml': '├', 'mr': '┤',
        'tm': '┬', 'bm': '┴', 'mm': '┼'
    }
    
    # Progress bar characters
    BAR_CHARS = ['█', '▓', '▒', '░', ' ']
    
    def __init__(self, 
                 stats_poller=None, 
                 logger=None,
                 stats_tracker=None,
                 stop_event=None,
                 cleanup_complete_event=None,
                 shared_stats=None,
                 log_queue=None,
                 frame_interval: float = 0.1,  # ~10 FPS
                 update_interval: float = 1.0):  # Stats update interval
        """
        Initialize dashboard.
        """
        self.stats_poller = stats_poller
        self.logger = logger
        self.stats_tracker = stats_tracker
        self.stop_event = stop_event
        self.cleanup_complete_event = cleanup_complete_event
        self.shared_stats = shared_stats
        self.log_queue = log_queue
        self.frame_interval = frame_interval
        self.update_interval = update_interval
        
        self.running = False
        self.stdscr = None
        self.layout = LayoutManager()
        
        # Internal state
        self._lock = threading.Lock()
        self._last_update = 0
        self._cached_state: Optional[DashboardState] = None
        
        # For standalone mode (when external sources not provided)
        self._internal_logs: Deque[dict] = deque(maxlen=200)
        self._internal_alerts: Deque[dict] = deque(maxlen=50)
        
        # Network rate tracking (Bug 6 fix)
        self._prev_net_sent: int = 0
        self._prev_net_recv: int = 0
        self._prev_net_time: float = 0.0
        
        # Signal handling
        self._original_sigint = None
        self._original_sigterm = None
        
    def _init_colors(self):
        """Initialize btop-style color pairs"""
        curses.start_color()
        curses.use_default_colors()
        
        # Color pairs (foreground, background)
        # Pair 1: Cyan (borders, headers)
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        
        # Pair 2: Magenta/Pink (highlights, bot status)
        curses.init_pair(2, curses.COLOR_MAGENTA, -1)
        
        # Pair 3: Green (success, good stats)
        curses.init_pair(3, curses.COLOR_GREEN, -1)
        
        # Pair 4: Yellow (warnings)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        
        # Pair 5: Red (errors, critical)
        curses.init_pair(5, curses.COLOR_RED, -1)
        
        # Pair 6: White (normal text)
        curses.init_pair(6, curses.COLOR_WHITE, -1)
        
        # Pair 7: Blue (info)
        curses.init_pair(7, curses.COLOR_BLUE, -1)
        
    def _init_curses(self, stdscr):
        """Initialize curses settings"""
        self.stdscr = stdscr
        
        # Hide cursor
        curses.curs_set(0)
        
        # Non-blocking input
        stdscr.nodelay(True)
        stdscr.timeout(int(self.frame_interval * 1000))
        
        # Enable keypad
        stdscr.keypad(True)
        
        # Initialize colors
        self._init_colors()
        
        # REQUIREMENT: Suppress ALL stdout/stderr from noisy libraries
        import logging
        noisy_libs = ["torch", "diffusers", "transformers", "tokenizers", "httpx", "httpcore", "llama_index", "ollama", "asyncio"]
        for logger_name in noisy_libs:
            l = logging.getLogger(logger_name)
            l.setLevel(logging.ERROR)
            l.propagate = False
            
        # Enable dashboard mode in logger to suppress stdout
        if self.logger:
            self.logger.set_dashboard_mode(True)
            
        # Calculate initial layout
        height, width = stdscr.getmaxyx()
        self.layout.calculate_layout(height, width)
        
    def _restore_terminal(self):
        """Ensure terminal is fully restored"""
        try:
            # Curses cleanup
            curses.nocbreak()
            curses.echo()
            curses.endwin()
        except Exception:
            pass
            
        # ANSI escape sequences for full reset
        try:
            # \033[0m    - Reset all attributes
            # \033[?25h  - Show cursor
            # \033[?1049l - Exit alternate screen buffer
            # \033[H      - Move cursor to home (top-left)
            # \033[2J     - Clear entire screen
            sys.stdout.write('\033[0m\033[?25h\033[?1049l\033[H\033[2J')
            sys.stdout.flush()
        except Exception:
            pass
            
    def _get_system_metrics(self):
        """Fetch system metrics with a hard timeout to prevent dashboard hangs."""
        import psutil
        try:
            return {
                'cpu_percent': psutil.cpu_percent(interval=0),
                'memory': psutil.virtual_memory(),
                'disk': psutil.disk_usage('/'),
                'net': psutil.net_io_counters()
            }
        except Exception:
            return None

    def _take_snapshot(self) -> DashboardState:
        """
        Create an immutable snapshot of current state.
        This is the ONLY place where we read from shared data sources.
        """
        import psutil
        import concurrent.futures
        
        # Get system metrics with timeout (isolated in dashboard process)
        metrics = None
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._get_system_metrics)
            try:
                metrics = future.result(timeout=1.0)
            except concurrent.futures.TimeoutError:
                pass
        
        if metrics:
            cpu_percent = metrics['cpu_percent']
            memory = metrics['memory']
            disk = metrics['disk']
            net = metrics['net']
        else:
            cpu_percent = 0.0
            memory = type('obj', (object,), {'percent': 0, 'used': 0, 'total': 1})()
            disk = type('obj', (object,), {'percent': 0})()
            net = type('obj', (object,), {'bytes_sent': 0, 'bytes_recv': 0})()
        
        # Get stats from poller if available
        poller_stats = {}
        if self.stats_poller:
            try:
                poller_stats = self.stats_poller.get_stats()
            except Exception:
                pass
                
        # Get stats from tracker if available
        tracker_stats = {}
        if self.stats_tracker:
            try:
                tracker_stats = self.stats_tracker.get_stats()
            except Exception:
                pass
        
        # Get logs from logger if available
        log_entries = []
        alerts = []
        
        if self.log_queue:
            # Drain queue into internal buffer
            try:
                while not self.log_queue.empty():
                    log = self.log_queue.get_nowait()
                    self._internal_logs.append(log)
                    if log.get('type') in ['ERROR', 'WARNING', 'CRITICAL']:
                        symbol = '⛔' if log.get('type') == 'ERROR' else ('⚠️' if log.get('type') == 'WARNING' else '🔴')
                        self._internal_alerts.append({
                            'timestamp': log.get('timestamp', ''),
                            'level': log.get('type', 'WARNING'),
                            'message': log.get('message', ''),
                            'symbol': symbol
                        })
            except Exception:
                pass

        if self.logger:
            try:
                raw_logs = self.logger.get_recent_logs(50)
                for log in raw_logs:
                    if log.get('type') == 'DEBUG':
                        continue
                        
                    entry = LogEntry(
                        timestamp=log.get('timestamp', ''),
                        log_type=log.get('type', 'INFO'),
                        message=log.get('message', ''),
                        source=log.get('source', 'system')
                    )
                    log_entries.append(entry)
                    
                    # Also collect alerts
                    if log.get('type') in ['ERROR', 'WARNING', 'CRITICAL']:
                        symbol = '⛔' if log.get('type') == 'ERROR' else ('⚠️' if log.get('type') == 'WARNING' else '🔴')
                        alerts.append(AlertEntry(
                            timestamp=log.get('timestamp', ''),
                            level=log.get('type', 'WARNING'),
                            message=log.get('message', ''),
                            symbol=symbol
                        ))
            except Exception:
                pass
        else:
            # Use internal buffers
            with self._lock:
                for log in list(self._internal_logs)[-50:]:
                    log_entries.append(LogEntry(
                        timestamp=log.get('timestamp', ''),
                        log_type=log.get('type', 'INFO'),
                        message=log.get('message', ''),
                        source=log.get('source', 'system')
                    ))
                for alert in list(self._internal_alerts)[-10:]:
                    alerts.append(AlertEntry(
                        timestamp=alert.get('timestamp', ''),
                        level=alert.get('level', 'WARNING'),
                        message=alert.get('message', ''),
                        symbol=alert.get('symbol', '⚠️')
                    ))
        
        # Compute network rate (KB/s) from cumulative counters
        now = time.time()
        net_sent_kbs = 0.0
        net_recv_kbs = 0.0
        if self._prev_net_time > 0:
            elapsed = now - self._prev_net_time
            if elapsed > 0.1:
                net_sent_kbs = (net.bytes_sent - self._prev_net_sent) / 1024.0 / elapsed
                net_recv_kbs = (net.bytes_recv - self._prev_net_recv) / 1024.0 / elapsed
        self._prev_net_sent = net.bytes_sent
        self._prev_net_recv = net.bytes_recv
        self._prev_net_time = now

        # Helper: pick first non-None value from sources
        def _pick(key, *sources, default=None):
            for src in sources:
                if src is not None:
                    val = src.get(key)
                    if val is not None:
                        return val
            return default

        ss = self.shared_stats  # Shorthand

        # Build the immutable state
        return DashboardState(
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_used_mb=memory.used / 1024 / 1024,
            memory_total_mb=memory.total / 1024 / 1024,
            gpu_util=_pick('gpu_util', poller_stats, ss, default=0.0),
            gpu_memory=_pick('gpu_memory', poller_stats, ss, default='N/A'),
            disk_percent=disk.percent,
            net_sent_kbs=max(0.0, net_sent_kbs),
            net_recv_kbs=max(0.0, net_recv_kbs),
            uptime_minutes=_pick('uptime_minutes', poller_stats, tracker_stats, ss, default=0.0),
            active_users=_pick('active_users_display', tracker_stats, ss, default='0 (idle)'),
            total_messages=_pick('messages', tracker_stats, poller_stats, ss, default=0),
            avg_response_time=_pick('avg_response_time', tracker_stats, poller_stats, ss, default=0.0),
            ollama_status=_pick('ollama_status', ss, poller_stats, default='🔴 OFFLINE'),
            active_model=_pick('active_model', ss, poller_stats, default='None'),
            ollama_models=tuple(_pick('ollama_models', ss, poller_stats, default=[])),
            rag_size=_pick('rag_size', ss, poller_stats, default='0 MB'),
            kb_size_mb=_pick('kb_size_mb', ss, poller_stats, default=0.0),
            indexed_files=_pick('indexed_files', ss, poller_stats, default=0),
            dreams_count=_pick('dreams_count', ss, poller_stats, default=0),
            queue_size=_pick('queue_size', tracker_stats, ss, default=0),
            rag_confidence=_pick('rag_confidence', ss, default=0.0),
            rag_nodes=_pick('rag_nodes', ss, default=0),
            coherence_ema=_pick('coherence_ema', ss, default=0.85),
            hallucination_count=_pick('hallucination_count', ss, default=0),
            rag_stale=_pick('rag_stale', ss, default=True),
            beliefs_count=_pick('beliefs_count', ss, poller_stats, default=0),
            anchors_count=_pick('anchors_count', ss, poller_stats, default=0),
            relationship_count=_pick('relationship_count', ss, poller_stats, default=0),
            forum_drafts=_pick('forum_drafts', ss, tracker_stats, default=0),
            forum_approved=_pick('forum_approved', ss, tracker_stats, default=0),
            forum_rejected=_pick('forum_rejected', ss, tracker_stats, default=0),
            log_size_mb=_pick('log_size_mb', ss, poller_stats, default=0.0),
            log_entries=tuple(log_entries),
            alerts=tuple(alerts[-10:]),  # Limit alerts
            snapshot_time=time.time()
        )
        
    def _draw_box(self, pane: Pane):
        """Draw a box with title"""
        if not self.stdscr:
            return
            
        try:
            y, x = pane.y, pane.x
            h, w = pane.height, pane.width
            color = curses.color_pair(pane.color_pair)
            
            # Clamp to screen bounds
            max_y, max_x = self.stdscr.getmaxyx()
            if y >= max_y or x >= max_x:
                return
            w = min(w, max_x - x)
            h = min(h, max_y - y)
            
            if w < 3 or h < 3:
                return
            
            # Top border with title
            if pane.title:
                title_str = f" {pane.title} "
                available = max(0, w - 2)
                if len(title_str) + 2 <= available:
                    left_len = (available - len(title_str) - 2) // 2
                    right_len = available - len(title_str) - 2 - left_len
                    top_line = (self.BOX['h'] * left_len) + '╮' + title_str + '╭' + (self.BOX['h'] * right_len)
                else:
                    left_len = max(0, (available - len(title_str)) // 2)
                    right_len = max(0, available - len(title_str) - left_len)
                    top_line = self.BOX['h'] * left_len + title_str + self.BOX['h'] * right_len
            else:
                top_line = self.BOX['h'] * (w - 2)
                
            self.stdscr.addstr(y, x, self.BOX['tl'] + top_line[:w-2] + self.BOX['tr'], color)
            
            # Sides and background clearing
            for i in range(1, h - 1):
                if y + i < max_y:
                    # Clear the line inside the box to prevent stray characters
                    self.stdscr.addstr(y + i, x + 1, " " * (w - 2), color)
                    # Draw vertical borders
                    self.stdscr.addstr(y + i, x, self.BOX['v'], color)
                    if x + w - 1 < max_x:
                        self.stdscr.addstr(y + i, x + w - 1, self.BOX['v'], color)
            
            # Bottom border
            if y + h - 1 < max_y:
                if pane.footer:
                    footer_str = f" {pane.footer} "
                    available = max(0, w - 2)
                    if len(footer_str) + 2 <= available:
                        left_len = (available - len(footer_str) - 2) // 2
                        right_len = available - len(footer_str) - 2 - left_len
                        bottom_line = (self.BOX['h'] * left_len) + '╮' + footer_str + '╭' + (self.BOX['h'] * right_len)
                    else:
                        left_len = max(0, (available - len(footer_str)) // 2)
                        right_len = max(0, available - len(footer_str) - left_len)
                        bottom_line = self.BOX['h'] * left_len + footer_str + self.BOX['h'] * right_len
                    bottom = self.BOX['bl'] + bottom_line[:w-2] + self.BOX['br']
                else:
                    bottom = self.BOX['bl'] + self.BOX['h'] * (w - 2) + self.BOX['br']
                self.stdscr.addstr(y + h - 1, x, bottom[:w], color)
                
        except curses.error:
            pass
            
    def _draw_progress_bar(self, value: float, width: int) -> str:
        """Create a highly precise btop-style smooth progress bar"""
        value = max(0, min(100, value))
        blocks = [' ', '▏', '▎', '▍', '▌', '▋', '▊', '▉', '█']
        
        fill_amount = (value / 100.0) * width
        filled_chars = int(fill_amount)
        remainder = fill_amount - filled_chars
        
        bar = ""
        for i in range(width):
            if i < filled_chars:
                bar += '█'
            elif i == filled_chars:
                idx = int(remainder * 8)
                bar += blocks[idx]
            else:
                bar += ' '
                
        return bar
        
    def _get_color_for_value(self, value: float, thresholds: Tuple[float, float] = (50, 80)) -> int:
        """Get color pair based on value thresholds (low=green, high=red)"""
        if value < thresholds[0]:
            return 3  # Green
        elif value < thresholds[1]:
            return 4  # Yellow
        else:
            return 5  # Red

    def _get_color_inverted(self, value: float, thresholds: Tuple[float, float] = (60, 85)) -> int:
        """Get color pair with inverted logic (high=green, low=red) for confidence/coherence"""
        if value >= thresholds[1]:
            return 3  # Green (high is good)
        elif value >= thresholds[0]:
            return 4  # Yellow
        else:
            return 5  # Red (low is bad)
            
    def _safe_addstr(self, y: int, x: int, text: str, attr=None):
        """Safely add string, handling screen bounds"""
        if not self.stdscr:
            return
        try:
            max_y, max_x = self.stdscr.getmaxyx()
            if y >= max_y or x >= max_x:
                return
            # Truncate text to fit
            text = text[:max_x - x - 1]
            if attr:
                self.stdscr.addstr(y, x, text, attr)
            else:
                self.stdscr.addstr(y, x, text)
        except curses.error:
            pass
            
    def _draw_stats_pane(self, state: DashboardState):
        """Draw system stats pane"""
        pane = self.layout.panes.get('stats')
        if not pane:
            return
            
        self._draw_box(pane)
        
        inner_y = pane.y + 1
        inner_x = pane.x + 2
        inner_width = pane.width - 4
        bar_width = min(20, inner_width - 15)
        label_w = 4
        
        def draw_stat_row(y_offset, label, value_pct, val_str=None):
            bar = self._draw_progress_bar(value_pct, bar_width)
            color = self._get_color_for_value(value_pct)
            
            self._safe_addstr(inner_y + y_offset, inner_x, label.ljust(label_w), curses.color_pair(1) | curses.A_BOLD)
            self._safe_addstr(inner_y + y_offset, inner_x + label_w, "[", curses.color_pair(6))
            self._safe_addstr(inner_y + y_offset, inner_x + label_w + 1, bar, curses.color_pair(color))
            self._safe_addstr(inner_y + y_offset, inner_x + label_w + 1 + bar_width, "]", curses.color_pair(6))
            
            display_str = val_str if val_str else f"{value_pct:5.1f}%"
            self._safe_addstr(inner_y + y_offset, inner_x + label_w + 3 + bar_width, display_str, curses.color_pair(color) | curses.A_BOLD)

        draw_stat_row(0, "CPU", state.cpu_percent)
        draw_stat_row(1, "RAM", state.memory_percent)
        draw_stat_row(2, "GPU", state.gpu_util)
        draw_stat_row(3, "DSK", state.disk_percent)
        
        # Non-bar metrics: Network, VRAM, etc.
        self._safe_addstr(inner_y + 4, inner_x, "NET ".ljust(label_w), curses.color_pair(1) | curses.A_BOLD)
        net_str = f"▼ {state.net_recv_kbs:6.1f}K/s ▲ {state.net_sent_kbs:6.1f}K/s"
        self._safe_addstr(inner_y + 4, inner_x + label_w + 1, net_str, curses.color_pair(3))
        
        self._safe_addstr(inner_y + 5, inner_x, "VRAM".ljust(label_w), curses.color_pair(1) | curses.A_BOLD)
        self._safe_addstr(inner_y + 5, inner_x + label_w + 1, f"{state.gpu_memory}", curses.color_pair(2) | curses.A_BOLD)

        # Vertical Models List
        if state.ollama_models:
            self._safe_addstr(inner_y + 7, inner_x, "MODELS", curses.color_pair(1) | curses.A_BOLD | curses.A_UNDERLINE)
            for i, model in enumerate(state.ollama_models):
                if inner_y + 8 + i >= pane.y + pane.height - 1:
                    break
                # Truncate model name if too long
                display_model = f"• {model}"
                if len(display_model) > pane.width - 4:
                    display_model = display_model[:pane.width - 7] + "..."
                self._safe_addstr(inner_y + 8 + i, inner_x, display_model, curses.color_pair(6))
        
    def _draw_status_pane(self, state: DashboardState):
        """Draw bot status pane"""
        pane = self.layout.panes.get('status')
        if not pane:
            return
            
        self._draw_box(pane)
        
        inner_y = pane.y + 1
        inner_x = pane.x + 2
        
        def draw_status_row(y_offset, label, value, val_color_pair):
            self._safe_addstr(inner_y + y_offset, inner_x, label.ljust(8), curses.color_pair(1) | curses.A_BOLD)
            self._safe_addstr(inner_y + y_offset, inner_x + 8, str(value), curses.color_pair(val_color_pair) | curses.A_BOLD)

        # Base Stats
        draw_status_row(0, "Status:", state.ollama_status, 3 if "ONLINE" in state.ollama_status else 5)
        
        hours = int(state.uptime_minutes // 60)
        mins = int(state.uptime_minutes % 60)
        uptime_str = f"{hours}h {mins}m"
        draw_status_row(1, "Uptime:", uptime_str, 6)
        
        draw_status_row(2, "Users:", state.active_users, 3)
        draw_status_row(3, "Msgs:", f"{state.total_messages:,}", 3)
        
        resp_color = self._get_color_for_value(state.avg_response_time * 33, (50, 80))
        draw_status_row(4, "RTime:", f"{state.avg_response_time:.2f}s", resp_color)
        
        # Active Model
        draw_status_row(5, "Model:", state.active_model, 3)
        
    def _draw_cognition_pane(self, state: DashboardState):
        """Draw Kaia's cognitive pipeline and forum stats pane"""
        pane = self.layout.panes.get('cognition')
        if not pane:
            return
            
        self._draw_box(pane)
        
        inner_y = pane.y + 1
        inner_x = pane.x + 2
        col_width = pane.width - 4
        
        if col_width >= 22:
            # Symmetrical two-column layout
            col2_offset = max(13, col_width // 2 + 1)
            use_short = col_width < 28
            
            # Suffixes and labels configuration
            if use_short:
                b_val = f"{state.beliefs_count}/100"
                a_val = f"{state.anchors_count}/100"
                aff_val = f"{state.relationship_count}"
                d_val = f"{state.dreams_count}"
                dr_val = f"{state.forum_drafts}"
                ap_val = f"{state.forum_approved}"
                rj_val = f"{state.forum_rejected}"
                
                # short labels
                l_b, l_a, l_aff, l_d = "Beliefs", "Anchors", "Affinity", "Dreams"
                l_dr, l_ap, l_rj = "Drafts", "Apprvd", "Reject"
                val_offset = 8
            else:
                b_val = f"{state.beliefs_count}/100 act"
                a_val = f"{state.anchors_count}/100 act"
                aff_val = f"{state.relationship_count} users"
                d_val = f"{state.dreams_count} mems"
                dr_val = f"{state.forum_drafts} gen"
                ap_val = f"{state.forum_approved} post"
                rj_val = f"{state.forum_rejected} closed"
                
                # standard labels
                l_b, l_a, l_aff, l_d = "Beliefs:", "Anchors:", "Affinity:", "Dreams:"
                l_dr, l_ap, l_rj = "Drafts:", "Approved:", "Rejected:"
                val_offset = 10

            # Draw Column 1: Cognition (left side of pane)
            self._safe_addstr(inner_y, inner_x, l_b.ljust(val_offset), curses.color_pair(1) | curses.A_BOLD)
            self._safe_addstr(inner_y, inner_x + val_offset, b_val, curses.color_pair(3 if state.beliefs_count > 0 else 6) | curses.A_BOLD)
            
            self._safe_addstr(inner_y + 1, inner_x, l_a.ljust(val_offset), curses.color_pair(1) | curses.A_BOLD)
            self._safe_addstr(inner_y + 1, inner_x + val_offset, a_val, curses.color_pair(3 if state.anchors_count > 0 else 6) | curses.A_BOLD)
            
            self._safe_addstr(inner_y + 2, inner_x, l_aff.ljust(val_offset), curses.color_pair(1) | curses.A_BOLD)
            self._safe_addstr(inner_y + 2, inner_x + val_offset, aff_val, curses.color_pair(2) | curses.A_BOLD)
            
            self._safe_addstr(inner_y + 3, inner_x, l_d.ljust(val_offset), curses.color_pair(1) | curses.A_BOLD)
            self._safe_addstr(inner_y + 3, inner_x + val_offset, d_val, curses.color_pair(2) | curses.A_BOLD)

            # Draw Column 2: Forums (right side of pane)
            col2_x = inner_x + col2_offset
            self._safe_addstr(inner_y, col2_x, l_dr.ljust(val_offset), curses.color_pair(1) | curses.A_BOLD)
            self._safe_addstr(inner_y, col2_x + val_offset, dr_val, curses.color_pair(6) | curses.A_BOLD)
            
            self._safe_addstr(inner_y + 1, col2_x, l_ap.ljust(val_offset), curses.color_pair(1) | curses.A_BOLD)
            self._safe_addstr(inner_y + 1, col2_x + val_offset, ap_val, curses.color_pair(3) | curses.A_BOLD)
            
            self._safe_addstr(inner_y + 2, col2_x, l_rj.ljust(val_offset), curses.color_pair(1) | curses.A_BOLD)
            self._safe_addstr(inner_y + 2, col2_x + val_offset, rj_val, curses.color_pair(5 if state.forum_rejected > 0 else 6) | curses.A_BOLD)
        else:
            # Fall back to single column if the width is extremely small
            def draw_cognition_row(y_offset, label, value, val_color_pair):
                self._safe_addstr(inner_y + y_offset, inner_x, label.ljust(10), curses.color_pair(1) | curses.A_BOLD)
                self._safe_addstr(inner_y + y_offset, inner_x + 10, str(value), curses.color_pair(val_color_pair) | curses.A_BOLD)

            draw_cognition_row(0, "Beliefs:", f"{state.beliefs_count}/100", 3 if state.beliefs_count > 0 else 6)
            draw_cognition_row(1, "Anchors:", f"{state.anchors_count}/100", 3 if state.anchors_count > 0 else 6)
            draw_cognition_row(2, "Affinity:", f"{state.relationship_count}", 2)
            draw_cognition_row(3, "Dreams:", f"{state.dreams_count}", 2)
            draw_cognition_row(4, "Drafts:", f"{state.forum_drafts}", 6)
            draw_cognition_row(5, "Approved:", f"{state.forum_approved}", 3)
            draw_cognition_row(6, "Rejected:", f"{state.forum_rejected}", 5 if state.forum_rejected > 0 else 6)
        
    def _draw_rag_health_pane(self, state: DashboardState):
        """Draw RAG health pane"""
        pane = self.layout.panes.get('rag_health')
        if not pane:
            return
            
        self._draw_box(pane)
        
        inner_y = pane.y + 1
        inner_x = pane.x + 2
        inner_width = pane.width - 4
        
        # Staleness indicator
        stale_suffix = " (stale)" if state.rag_stale else ""
        stale_attr = curses.A_DIM if state.rag_stale else curses.A_BOLD

        # Confidence Bar (inverted colors: high=green, low=red)
        conf_pct = state.rag_confidence * 100
        max_bar_width = (inner_width // 2 - 17) if inner_width >= 45 else (inner_width - 15)
        bar_width = max(5, min(20, max_bar_width))
        bar = self._draw_progress_bar(conf_pct, bar_width)
        color = self._get_color_inverted(conf_pct, (60, 85))
        
        self._safe_addstr(inner_y, inner_x, "Confidence:".ljust(12), curses.color_pair(1) | curses.A_BOLD)
        self._safe_addstr(inner_y, inner_x + 12, "[", curses.color_pair(6))
        self._safe_addstr(inner_y, inner_x + 13, bar, curses.color_pair(color))
        self._safe_addstr(inner_y, inner_x + 13 + bar_width, "]", curses.color_pair(6))
        self._safe_addstr(inner_y, inner_x + 15 + bar_width, f"{state.rag_confidence:.2f}{stale_suffix}", curses.color_pair(color) | stale_attr)
        
        # Stats Row
        self._safe_addstr(inner_y + 1, inner_x, "Retrieved Nodes:".ljust(18), curses.color_pair(1) | curses.A_BOLD)
        self._safe_addstr(inner_y + 1, inner_x + 18, f"{state.rag_nodes}", curses.color_pair(2) | stale_attr)
        
        # Coherence EMA (inverted colors: high=green, low=red)
        self._safe_addstr(inner_y + 2, inner_x, "Coherence EMA:".ljust(18), curses.color_pair(1) | curses.A_BOLD)
        coh_color = self._get_color_inverted(state.coherence_ema * 100, (60, 85))
        self._safe_addstr(inner_y + 2, inner_x + 18, f"{state.coherence_ema:.3f}", curses.color_pair(coh_color) | curses.A_BOLD)
        
        # Hallucinations
        h_color = 3 if state.hallucination_count == 0 else (4 if state.hallucination_count < 3 else 5)
        self._safe_addstr(inner_y + 3, inner_x, "Hallucinations (24h):".ljust(22), curses.color_pair(1) | curses.A_BOLD)
        self._safe_addstr(inner_y + 3, inner_x + 22, f"{state.hallucination_count}", curses.color_pair(h_color) | curses.A_BOLD)

        # Draw Column 2: RAG Index/Log Stats
        if inner_width >= 45:
            col2_x = inner_x + max(28, inner_width // 2 + 1)
            
            # Row 0: Index Size
            self._safe_addstr(inner_y, col2_x, "Index Size:".ljust(15), curses.color_pair(1) | curses.A_BOLD)
            self._safe_addstr(inner_y, col2_x + 15, state.rag_size, curses.color_pair(3) | curses.A_BOLD)
            
            # Row 1: Log Size
            self._safe_addstr(inner_y + 1, col2_x, "Log File Size:".ljust(15), curses.color_pair(1) | curses.A_BOLD)
            self._safe_addstr(inner_y + 1, col2_x + 15, f"{state.log_size_mb:.1f} MB", curses.color_pair(3) | curses.A_BOLD)
            
            # Row 2: Indexed Files
            self._safe_addstr(inner_y + 2, col2_x, "Indexed Files:".ljust(15), curses.color_pair(1) | curses.A_BOLD)
            self._safe_addstr(inner_y + 2, col2_x + 15, f"{state.indexed_files}", curses.color_pair(2) | curses.A_BOLD)
            
            # Row 3: Dreams Count
            self._safe_addstr(inner_y + 3, col2_x, "Dreams Count:".ljust(15), curses.color_pair(1) | curses.A_BOLD)
            self._safe_addstr(inner_y + 3, col2_x + 15, f"{state.dreams_count}", curses.color_pair(2) | curses.A_BOLD)
        
    def _draw_alerts_pane(self, state: DashboardState):
        """Draw alerts pane"""
        pane = self.layout.panes.get('alerts')
        if not pane:
            return
            
        self._draw_box(pane)
        
        inner_y = pane.y + 1
        inner_x = pane.x + 2
        inner_width = pane.width - 4
        max_alerts = pane.height - 2
        
        if not state.alerts:
            self._safe_addstr(inner_y, inner_x, "✅ No active alerts", curses.color_pair(3))
            return
            
        for i, alert in enumerate(state.alerts[:max_alerts]):
            if i >= max_alerts:
                break
                
            color = 5 if alert.level == 'ERROR' else (4 if alert.level == 'WARNING' else 7)
            # Clear the line before writing new alert
            self._safe_addstr(inner_y + i, inner_x, " " * inner_width)
            alert_text = f"{alert.symbol} {alert.timestamp} {alert.message}"
            if len(alert_text) > inner_width:
                alert_text = alert_text[:inner_width - 3] + "..."
            self._safe_addstr(inner_y + i, inner_x, alert_text, curses.color_pair(color))
            
    def _draw_logs_pane(self, state: DashboardState):
        """Draw logs pane"""
        pane = self.layout.panes.get('logs')
        if not pane:
            return
            
        self._draw_box(pane)
        
        inner_y = pane.y + 1
        inner_x = pane.x + 2
        inner_width = pane.width - 4
        max_logs = pane.height - 2
        
        # Color mapping
        type_colors = {
            'INFO': 6,
            'SUCCESS': 3,
            'READY': 2,
            'ACTION': 1,
            'WARNING': 4,
            'ERROR': 5,
            'CRITICAL': 5
        }
        
        # Show most recent logs (reversed order - newest at bottom)
        logs_to_show = list(state.log_entries)[-max_logs:]
        
        for i, log in enumerate(logs_to_show):
            color_pair = type_colors.get(log.log_type, 6)
            attr = curses.color_pair(color_pair)
            
            # Special handling for READY - make it bold and fill line
            if log.log_type == 'READY':
                attr |= curses.A_BOLD
                log_text = f"{log.timestamp} {log.log_type}: {log.message}"
                # Pad to fill the pane width for maximum impact
                log_text = log_text.ljust(inner_width)
            else:
                log_text = f"{log.timestamp} {log.log_type}: {log.message}"
                
            if len(log_text) > inner_width:
                log_text = log_text[:inner_width - 3] + "..."
            self._safe_addstr(inner_y + i, inner_x, log_text, attr)
            
    def _draw_footer(self, state: DashboardState):
        """Footer is now empty as menu is in logs pane border"""
        pass

            
    def _draw_frame(self, state: DashboardState):
        """Draw complete frame from snapshot"""
        if not self.stdscr:
            return
            
        try:
            # Clear screen
            self.stdscr.erase()
            
            # Check for resize
            height, width = self.stdscr.getmaxyx()
            if height != self.layout.height or width != self.layout.width:
                if not self.layout.calculate_layout(height, width):
                    # Terminal too small
                    self._safe_addstr(height // 2, 2, "Terminal too small! Resize to at least 60x20", curses.color_pair(5))
                    return
            
            # Draw all panes
            self._draw_stats_pane(state)
            self._draw_status_pane(state)
            self._draw_cognition_pane(state)
            self._draw_rag_health_pane(state)
            self._draw_alerts_pane(state)
            self._draw_logs_pane(state)
            self._draw_footer(state)
            
        except curses.error:
            pass
            
    def _handle_input(self) -> bool:
        """Handle keyboard input. Returns False to exit."""
        if not self.stdscr:
            return True
            
        try:
            key = self.stdscr.getch()
            
            if key == curses.ERR:
                return True
                
            if key in (ord('q'), ord('Q')):
                if self.stop_event:
                    self.stop_event.set()
                return False
            elif key in (ord('c'), ord('C')):
                self._clear_logs()
            elif key in (ord('r'), ord('R')):
                self._cached_state = None  # Force refresh
            elif key in (ord('s'), ord('S')):
                self._save_state()
            elif key in (ord('h'), ord('H')):
                self._show_help()
                
            return True
            
        except Exception:
            return True
            
    def _clear_logs(self):
        """Clear logs"""
        if self.logger:
            try:
                self.logger.clear_logs()
            except Exception:
                pass
        with self._lock:
            self._internal_logs.clear()
            self._internal_alerts.clear()
            
    def _save_state(self):
        """Save current state"""
        if self.stats_tracker:
            try:
                self.stats_tracker.save_stats()
                self.add_log("State saved", "SUCCESS")
            except Exception as e:
                self.add_log(f"Failed to save state: {e}", "ERROR")
                
    def _show_help(self):
        """Show help overlay"""
        if not self.stdscr:
            return
            
        try:
            height, width = self.stdscr.getmaxyx()
            
            help_lines = [
                "══════════ HELP ══════════",
                "",
                "  Q - Quit dashboard",
                "  C - Clear logs",
                "  R - Force refresh",
                "  S - Save state",
                "  H - Show this help",
                "",
                "  Press any key to close",
                "══════════════════════════"
            ]
            
            # Center the help box
            help_height = len(help_lines) + 2
            help_width = max(len(line) for line in help_lines) + 4
            start_y = (height - help_height) // 2
            start_x = (width - help_width) // 2
            
            # Draw box
            for i in range(help_height):
                self._safe_addstr(start_y + i, start_x, " " * help_width, curses.color_pair(2) | curses.A_REVERSE)
                
            # Draw content
            for i, line in enumerate(help_lines):
                self._safe_addstr(start_y + 1 + i, start_x + 2, line, curses.color_pair(1) | curses.A_BOLD)
                
            self.stdscr.refresh()
            
            # Wait for keypress
            self.stdscr.nodelay(False)
            self.stdscr.getch()
            self.stdscr.nodelay(True)
            self.stdscr.timeout(int(self.frame_interval * 1000))
            
        except curses.error:
            pass
            
    def _main_loop(self, stdscr):
        """Main UI loop - runs in main thread only"""
        self._init_curses(stdscr)
        self.running = True
        
        while self.running and not shutdown_manager.shutting_down:
            # Check external stop event
            if self.stop_event and self.stop_event.is_set():
                break
                
            # Handle input
            if not self._handle_input():
                self.running = False
                if self.stop_event:
                    self.stop_event.set()
                break
                
            # Take snapshot and draw
            try:
                state = self._take_snapshot()
                self._draw_frame(state)
                stdscr.refresh()
            except Exception as e:
                # Log error to file via logging module
                import logging
                logging.getLogger("kaiacord").error(f"Dashboard draw error: {e}")
                
            # Sleep (mandatory to prevent 100% CPU usage)
            time.sleep(self.frame_interval)
            
    def run(self):
        """
        Run the dashboard.
        This MUST be called from the main thread.
        """
        # Signals are handled globally by shutdown_manager
        
        try:
            # Use curses.wrapper for safe initialization and cleanup
            curses.wrapper(self._main_loop)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            # Report error to stderr since dashboard failed
            import traceback
            sys.__stderr__.write(f"\n❌ Dashboard error: {e}\n")
            traceback.print_exc(file=sys.__stderr__)
            sys.__stderr__.flush()
        finally:
            self._restore_terminal()
            
    def stop(self):
        """Signal the dashboard to stop"""
        self.running = False
        
    # ==================== PUBLIC API ====================
    
    def add_log(self, message: str, log_type: str = "INFO"):
        """Add a log entry (thread-safe)"""
        if self.logger:
            try:
                self.logger.log(message, log_type)
            except Exception:
                pass
        else:
            with self._lock:
                self._internal_logs.append({
                    'timestamp': datetime.now().strftime("%H:%M:%S"),
                    'type': log_type,
                    'message': message,
                    'source': 'dashboard'
                })
                
    def add_alert(self, message: str, level: str = "WARNING"):
        """Add an alert (thread-safe)"""
        symbol = '⛔' if level == 'ERROR' else ('⚠️' if level == 'WARNING' else '🔴')
        
        if self.logger:
            try:
                self.logger.log(message, level)
            except Exception:
                pass
        else:
            with self._lock:
                self._internal_alerts.append({
                    'timestamp': datetime.now().strftime("%H:%M:%S"),
                    'level': level,
                    'message': message,
                    'symbol': symbol
                })

    def log_system_event(self, event_type: str, message: str):
        """Compatibility method for kaia_logger"""
        self.add_log(f"⚡ {event_type}: {message}", log_type=event_type)
        
        # Also add as alert if it's high priority
        if event_type in ["ERROR", "CRITICAL", "WARNING"]:
            self.add_alert(message, level=event_type)
        elif event_type == "READY":
             self.add_alert(message, level="INFO")

    def log_response(self, content: str, tokens_saved: int = 0, response_time: float = 0.0):
        """Compatibility method for kaia_logger"""
        msg = f"🤖 Response: {content[:100]}..."
        if response_time > 0:
            msg += f" ({response_time:.2f}s)"
        self.add_log(msg, log_type="INFO")


# ==================== STANDALONE RUNNER ====================

def run_standalone():
    """Run dashboard in standalone mode for testing"""
    print("Starting btop dashboard v2...")
    print("Press Q to quit")
    
    # Try to import optional dependencies
    stats_poller = None
    logger = None
    stats_tracker = None
    
    try:
        from utils.infrastructure.monitoring.stats_poller import stats_poller as sp
        stats_poller = sp
        stats_poller.start()
    except Exception:
        pass
        
    try:
        from utils.infrastructure.logging.unified_logging import logger as ul
        logger = ul
    except Exception:
        pass
        
    try:
        from utils.infrastructure.monitoring.stats_tracker import stats_tracker as st
        stats_tracker = st
    except Exception:
        pass
    
    dashboard = BtopDashboardV2(
        stats_poller=stats_poller,
        logger=logger,
        stats_tracker=stats_tracker
    )
    
    try:
        dashboard.run()
    finally:
        if stats_poller:
            try:
                stats_poller.stop()
            except Exception:
                pass
        print("\nDashboard exited cleanly.")


if __name__ == "__main__":
    run_standalone()
