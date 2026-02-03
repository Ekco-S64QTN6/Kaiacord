# Maintenance Tools Documentation

This directory contains scripts for maintaining, debugging, and fixing the Kaiacord system.

## Recovery Tools (tools/recovery/)

### `proper_fix.py`
**Purpose**: Primary tool for surgically fixing boilerplate and hallucination issues.  
**Usage**: `python tools/recovery/proper_fix.py`

### `nuclear_reset.py`
**Purpose**: Last resort for heavily contaminated systems.  
**Usage**: `python tools/recovery/nuclear_reset.py`

### `find_contamination.py`
**Purpose**: Scans logs for potential hallucinations.  
**Usage**: `python tools/recovery/find_contamination.py`

---

## Maintenance & Diagnostics

### `update_kaia_news.py`
**Purpose**: Fetches and summarizes daily tech news.  
**Usage**: `python tools/maintenance/update_kaia_news.py`

### `generate_user_profiles.py`
**Purpose**: Generates/regenerates user profile summaries from interaction logs.  
**Usage**: `python tools/development/generate_user_profiles.py`

### `scan_knowledge_base.py`
**Purpose**: Scans knowledge base for issues or corrupted files.  
**Usage**: `python tools/diagnostics/scan_knowledge_base.py`

### `refresh_news.py`
**Purpose**: Quick refresh of news content.  
**Usage**: `python tools/maintenance/refresh_news.py`

### `health_check.py`
**Purpose**: Comprehensive system validation.
**Usage**: `python tools/maintenance/health_check.py`

---

## Archived Tools (tools/legacy/)
One-time fix scripts and deprecated tools are stored in `tools/legacy/`. These are kept for reference but should not be used in normal operation.

---

## Operational Notes

### Log Deduplication
The `unified_logging.py` system implements a 60-second deduplication window for `DEBUG`-level maintenance messages (containing "refresh", "watcher", or "maintenance"). This prevents log spam during idle periods.

### Idle Log Behavior
During idle:
- **RAG refresh**: Logs "No new documents to index." at `DEBUG` level.
- **Memory audit**: Logs only if RSS changes by ≥50MB or cache size changes. Otherwise, logs at `DEBUG`.
- **Cold state persistence**: Only logs if the state hash changes.

### Terminal UI Notes
| Status | Condition |
| :--- | :--- |
| `unloaded (idle)` | GPU VRAM < 2GB |
| `warming` | GPU VRAM 2-6GB |
| `loaded (active)` | GPU VRAM > 6GB |
| `0 (idle)` | No active users in the last 15 minutes |

