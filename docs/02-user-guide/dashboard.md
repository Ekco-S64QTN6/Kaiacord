# 🖥️ Kaia Dashboard (Btop-Style)

## Overview
The dashboard provides a real-time, high-performance terminal interface for monitoring Kaiacord. It is inspired by `btop` and `htop`, featuring a responsive layout, live metrics, and a cyberpunk aesthetic.

---

## ✨ Symmetrical Three-Column Layout

The top half of the interface is split symmetrically into three vertical columns to partition system health, bot statistics, and cognitive/forum pipelines cleanly:

### 1. SYSTEM STATS (Left Column, 35% Width)
Tracks hardware resource utilization:
- **CPU**: Total processor load percentage.
- **RAM**: Free and utilized system memory.
- **GPU**: NVIDIA graphic card utilization.
- **VRAM**: Free and utilized video memory (critical for Ollama Chat VRAM safety).

### 2. BOT STATUS (Middle Column, 32.5% Width)
Tracks high-level bot execution metadata:
- **Ollama Status**: Shows green online (`🟢 ONLINE`) or red offline indicator.
- **Active Model**: Displays the name of the loaded chat model (e.g., `gemma3:12b`).
- **Uptime**: Precise, float-based runtime tracking in minutes.
- **Messages**: Number of processed Discord messages since initialization.
- **Dreams**: Number of nightly dream summaries processed.
- **Files**: Total indexed document count across vector stores.

### 3. COGNITIVE PIPELINE & FORUMS (Right Column, 32.5% Width)
Tracks Kaia's internal cognitive layers and Project 1999 forum stats:
- **Active Beliefs**: Current belief count loaded from `beliefs.json` (50-cap).
- **Memory Anchors**: Count of active episodic memory anchors.
- **Relationships**: Count of active user relationship affinity logs in `memory/relationships/`.
- **Forum Drafts**: Cumulative forum response drafts created and queued for review.
- **Approved / Rejected**: Number of drafts approved or rejected via Discord buttons.

---

## 📊 Span Panels & Live Logging

### RAG Health Panel
Located below the three vertical columns on the right, displaying RAG vector database statuses, cache hit ratios, and search latency.

### 📝 Live Logging (Bottom Half)
- **High-Visibility Elevation**: While standard `DEBUG` logs are suppressed, elevated operations (inner monologues, dream summaries, belief shifts, scraper stages, proactive checks, and emotional arc updates) are logged as `INFO` or `WARNING` to stream directly to this panel.
- **Color Coding**: Distinct ANSI color profiles for log levels:
  - `INFO`: Cyan/White text.
  - `WARNING`: Yellow text (e.g. hallucination warnings).
  - `SUCCESS`: Green text.
  - `ERROR`: Red text.
- **De-duplication**: Automatically collapses sequential duplicate messages and displays a repeat count to conserve screen space.

---

## ⌨️ Controls

| Key | Action |
| :--- | :--- |
| **Q** | Quit the dashboard (and shut down the bot gracefully) |
| **C** | Clear warnings and alerts |
| **R** | Force GUI layout refresh |
| **L** | Cycle log view filters (ALL -> INFO -> WARNING -> ERROR) |
| **S** | Export current screen logs to file |
| **1-6** | Fast-jump log filter selections |

---

## 🛠️ Technical Implementation

### Curses Interface: `utils/infrastructure/monitoring/btop_dashboard_v2.py`
Runs inside curses' alternate screen buffer to preserve shell history. Updates are managed thread-safely via curses' window locks.

### Metric Poller: `utils/infrastructure/monitoring/stats_poller.py`
Runs a background loop fetching system diagnostics. Specifically, a 30-second throttled Custom File Stats task parses:
- `memory/beliefs.json`
- `memory/memory_anchors.json`
- `memory/relationships/` directory
- `memory/stats.json` (persisted forum stats)

### Stats Tracker: `utils/infrastructure/monitoring/stats_tracker.py`
Provides thread-safe atomic helpers (`StatsTracker.increment_forum_draft()`, etc.) to count forum actions.
