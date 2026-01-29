# 🖥️ Kaia Dashboard (Btop-Style)

## Overview
The new dashboard provides a real-time, high-performance terminal interface for monitoring Kaiacord. It is inspired by `btop` and `htop`, featuring a responsive layout, live metrics, and a cyberpunk aesthetic.

## ✨ Key Features

### 📊 Real-Time Metrics
- **System Stats**: CPU, GPU, VRAM, and RAM usage tracking.
- **Bot Performance**: Response times, active user count, and message queue depth.
- **RAG Status**: Document count, index size, and cache hit rates.
- **Uptime**: Accurate uptime tracking (fixed float/datetime issues).

### 🖥️ Terminal Management
- **Alternate Screen Buffer**: Runs in a separate screen buffer (like `htop`), preserving your shell history upon exit.
- **Input Handling**: Supports keyboard shortcuts for filtering and control.
- **Stable Rendering**: No flickering or scrolling artifacts.
- **Mouse Support**: Disabled to prevent accidental scrolling interference.

### 📝 Live Logging
- **Color-Coded Logs**: distinct colors for INFO, WARNING, ERROR, and SUCCESS.
- **Duplicate Filtering**: Automatically collapses repeated log messages to reduce noise.
- **Log Filters**: Quickly toggle between ALL, ERROR, WARNING, etc., using keyboard shortcuts.
- **Auto-Scroll**: Always shows the latest activity.

## ⌨️ Controls

| Key | Action |
| :--- | :--- |
| **Q** | Quit the dashboard (and bot) |
| **C** | Clear alerts |
| **R** | Force refresh |
| **L** | Cycle log filters |
| **S** | Save current logs to file |
| **1-6** | Quick filter selection |

## 🛠️ Technical Implementation

### Curses Dashboard (Primary): `utils/btop_dashboard_v2.py`
The production curses dashboard uses snapshot-based rendering and a pane-based layout. It runs in curses' alternate screen buffer.

### ANSI Dashboard (Legacy): `utils/btop_dashboard_legacy.py`
The legacy ANSI fallback is preserved for terminals that don't support curses.

### `utils/stats_poller.py` & `utils/stats_tracker.py`
Authoritative sources for GPU metrics and user activity:
- **Model Status**: Derived from VRAM thresholds (<2GB = idle, 2-6GB = warming, >6GB = loaded).
- **Active Users**: Counted via a 15-minute sliding window.

### `BtopLoggingPatcher` (Deprecated)
Log interception is now handled by `unified_logging.py` which provides built-in deduplication.

## 🐛 Recent Fixes
- **Scrolling Fix**: Implemented alternate screen buffer to prevent terminal history pollution.
- **Duplicate Logs**: Added a cooldown and counter for repeated log messages.
- **DateTime Error**: Switched to `time.time()` (float) for robust uptime calculation.
- **Shutdown Error**: Fixed `kaia_vision` import path to prevent `No module named` errors on exit.
