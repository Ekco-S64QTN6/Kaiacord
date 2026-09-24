# Maintenance Tools Documentation

This directory documents scripts for maintaining, diagnosing, and repairing the Kaiacord system.

## Maintenance Tools (`tools/maintenance/`)

### `health_check.py`
**Purpose**: Comprehensive system validation (Ollama status, model availability, GPU detection, config validation).  
**Usage**: `venv/bin/python3 tools/maintenance/health_check.py`

### `reindex_rag.py`
**Purpose**: Manages knowledge base indexing. Supports live incremental indexing or full database wipe and rebuild.  
**Usage**:
```bash
# Trigger incremental re-index while bot is running
venv/bin/python3 tools/maintenance/reindex_rag.py --trigger

# Full vector database wipe and rebuild
venv/bin/python3 tools/maintenance/reindex_rag.py --clear
```

### `clean_hallucinations.py`
**Purpose**: Reports contaminated phrasing in the transcripts. With `--apply` it removes Kaia's matching lines only; user lines are never modified.  
**Usage**: `venv/bin/python3 tools/maintenance/clean_hallucinations.py [--apply]`

### `audit_knowledge_base.py`
**Purpose**: Read-only check of the corpus for every fault class that has occurred, naming the fix for each.  
**Usage**: `venv/bin/python3 tools/maintenance/audit_knowledge_base.py [--check]`

### `generate_user_profiles.py`
**Purpose**: Synthesizes each user's interaction logs into `knowledge_base/user_logs/<Name>_<id>/user_profile.md`.  
**Usage**: `venv/bin/python3 tools/maintenance/generate_user_profiles.py`

### `update_kaia_news.py`
**Purpose**: Fetches grounded daily tech news briefs via Gemini API and creates summaries.  
**Usage**: `venv/bin/python3 tools/maintenance/update_kaia_news.py`

### `ingest_manual_news.py`
**Purpose**: Files a brief written by hand. Put it in `knowledge_base/news/daily/` first.  
**Usage**: `venv/bin/python3 tools/maintenance/ingest_manual_news.py`

---

## Diagnostics & Probes (`tools/diagnostics/`)

### `check_indexing_health.py`
**Purpose**: Checks RAG index integrity, BM25 hydration, and document counts.  
**Usage**: `venv/bin/python3 tools/diagnostics/check_indexing_health.py`

### `ask_index.py`
**Purpose**: Asks the RAG index a question the way a chat turn does and prints each hit with its score, label and source. Works on a copy of the index, so it is safe while the bot runs.  
**Usage**: `venv/bin/python3 tools/diagnostics/ask_index.py "who wrote Neuromancer?"`

### `jspace_probe.py`
**Purpose**: Jacobian space behavioral probe harness to verify persona boundaries, apology suppression, and RAG grounding.  
**Usage**: `./scripts/run_jspace_probe.sh full`

---

## Operational Notes

### Terminal UI Notes
| Status | Condition |
| :--- | :--- |
| `unloaded (idle)` | GPU VRAM < 2GB |
| `warming` | GPU VRAM 2-6GB |
| `loaded (active)` | GPU VRAM > 6GB |
| `0 (idle)` | No active users in the last 15 minutes |

