# Maintenance Tools Documentation

This directory contains scripts for maintaining, debugging, and fixing the Kaiacord system.

## Core Tools (tools/)

### `proper_fix.py`
**Purpose**: Primary tool for surgically fixing boilerplate and hallucination issues.  
**Usage**: `python tools/proper_fix.py`  
**Actions**:
- Removes hardcoded fallback responses from code
- Cleans specific fictional stories from logs
- Ensures RAG has Smart Fiction Filter installed
- Updates persona rules

### `nuclear_reset.py`
**Purpose**: Last resort for heavily contaminated systems.  
**Usage**: `python tools/nuclear_reset.py`  
**Actions**:
- Wipes `storage/` directory (vector index)
- Purges all `user_logs`
- Clears `semantic_cache.json`
- Re-indexes only core persona and clean files

> [!WARNING]
> This will delete all user memories. Use `proper_fix.py` first.

### `find_contamination.py`
**Purpose**: Scans logs for potential hallucinations.  
**Usage**: `python tools/find_contamination.py`

### `update_kaia_news.py`
**Purpose**: Fetches and summarizes daily tech news.  
**Usage**: `python tools/update_kaia_news.py`

### `generate_user_profiles.py`
**Purpose**: Generates/regenerates user profile summaries from interaction logs.  
**Usage**: `python tools/generate_user_profiles.py`

### `log_cleaner.py`
**Purpose**: Cleans up old or corrupted log files.  
**Usage**: `python tools/log_cleaner.py`

### `scan_knowledge_base.py`
**Purpose**: Scans knowledge base for issues or corrupted files.  
**Usage**: `python tools/scan_knowledge_base.py`

### `refresh_news.py`
**Purpose**: Quick refresh of news content.  
**Usage**: `python tools/refresh_news.py`

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

