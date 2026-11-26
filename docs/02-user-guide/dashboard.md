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
- **Active Beliefs**: Current belief count loaded from `beliefs.json` (100-cap).
- **Memory Anchors**: Count of active episodic memory anchors (100-cap).
- **Relationships**: Count of active user relationship affinity logs in `memory/relationships/`.
- **Forum Drafts**: Cumulative forum response drafts created and queued for review.
- **Approved / Rejected**: Number of drafts approved or rejected via Discord buttons.

---

## 📊 Span Panels & Live Logging

### RAG Health Panel
Located below the three vertical columns on the right: the last retrieval's confidence and node
count, a running coherence average, the index size, the log file's size, the number of indexed
files and the dream count.

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
| **C** | Clear the live log and the alerts |
| **S** | Save the bot's stats (`stats_tracker.save_stats`) |
| **H** | Show this list; any key closes it |

Every frame is drawn from a fresh snapshot, so there is no refresh key.

---

## 🛠️ Technical Implementation

### Curses Interface: `utils/infrastructure/monitoring/btop_dashboard_v2.py`
Runs inside curses' alternate screen buffer to preserve shell history. Updates are managed thread-safely via curses' window locks.

### Metric Poller: `utils/infrastructure/monitoring/stats_poller.py`
Runs a background loop fetching system diagnostics. Specifically, a 30-second throttled Custom File Stats task parses:
- `memory/beliefs.json`
- `memory/anchors.json`
- `memory/relationships/` directory
- `memory/stats.json` (persisted forum stats)

### Stats Tracker: `utils/infrastructure/monitoring/stats_tracker.py`
Provides thread-safe atomic helpers (`StatsTracker.increment_forum_drafts()`, etc.) to count forum actions.

## The DJ booth

Separate from the terminal dashboard: while `!music records` plays, a browser window shows both
decks and the mixer live, and both are playable: load a record on the free deck from the crate,
drag to cue it, hear it in the window's PHONES, ▶ to start it synced, and mix with the faders. See
[commands](commands.md#music) and `music.dj_dashboard`.

The booth's lock, meters and timeline report technical synchronization and the mixer's actual
state; they do **not** grade whether a transition is musically good. The deck surface now has
memory/hot cues, counted beat loops and momentary **SLIP** roll pads, plus a separate **AUDIO FX**
row for the real master echo.
The header **FX** pill still controls visual booth effects only; it is not an audio effect.

To perform a slip roll, press and hold one of the **SLIP** pads (1, 2, 4 or 8) on the
on-air deck. The repeated, counted phrase plays while the underlying record keeps advancing;
release the pad to blend straight back to the live playhead. The selected PFL deck follows the
same roll. The roll arms for the next counted bar, so it is not an instantaneous scratch or a
persistent loop. Its hold is capped at 12 seconds as a safeguard if the browser loses the release
event. Slip rolls are manual performance controls, not yet a technique Kaia schedules herself.

To use the master echo, choose a TIME subdivision (½, 1, 2 or 4 beats), set FB (feedback, capped
at 0.65) and WET (effect level, capped at 0.50), then click **ECHO OFF** to turn it on. The delay
locks to the current on-air playback tempo when enabled. While active, you can adjust feedback
and wet level; the beat subdivision stays locked until the effect has fully released. Clicking
**ECHO ON** closes the input gate and lets a finite tail decay. The button reports **ECHO TAIL**
during that release. **KAIA MIX** cancels the tail immediately and hands the mixer back to Kaia.
The effect is on the program/master path: the headphone MASTER leg hears it, while the
independent PFL CUE leg remains dry.

To set a persistent pitch ride, move the **TEMPO** slider on the on-air deck between −8% and
+8%. It changes tempo and pitch together, ramps over eight rendered frames, and updates the
reported BPM and remaining-time clock. The selected PFL decoder follows the same rate whether
PHONES was selected before or after the ride began. Return the slider to 0.0% to restore the
synced/base rate. The pitch fader is distinct from the platter's temporary jog bend and is
available only while the on-air deck is playing without a transition, loop, slip roll, jog hold
or pause owning it.

To give the on-air record a temporary jog nudge, rotate the on-air deck's platter clockwise
to speed it up or counterclockwise to slow it down. A half-turn from the starting point reaches
the ±8% limit; returning toward the starting point moves the rate back toward the current pitch-fader setting. Release
the platter to ramp back to that persistent setting over eight rendered frames. The nudge
changes playback speed and pitch together and resumes from the source position reached during
the gesture. The selected PFL cue follows the same rate. The free deck's platter remains a cue
scrubber, not a live pitch control.

The nudge is available only on an on-air playing deck while no transition, loop, slip roll or
pause owns it. It is momentary, not a permanent pitch slider or an autonomous Kaia skill. A
10-second whole-hold safety cap forces a return to normal speed, including when the platter
crosses its centre without being released; the browser also releases the gesture on pointer
cancellation, window blur and page hide. If the booth later shows **JOG RELEASE** (for example,
after a reload lost the original pointer state), tap the platter once to acknowledge the engine's
completed safety return and re-arm jog control.

This is one human-operated echo effect, not a full effects bank or an autonomous Kaia skill.
Further performance effects and physical headphone/device acceptance remain open in [#403](https://github.com/Ekco-S64QTN6/Kaiacord/issues/403).
The browser gesture coverage is separate from Kaia's musical decision-making in
[#402](https://github.com/Ekco-S64QTN6/Kaiacord/issues/402); technical tests still do not
prove that a transition sounds good.
