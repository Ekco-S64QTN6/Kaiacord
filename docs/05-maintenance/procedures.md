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

### `clean_hallucinations.py` & `cleanup_kb.py`
**Purpose**: Scans and cleanses transcripts and knowledge documents of hallucinated artifacts, biological backstories, and bot-speak.  
**Usage**: `venv/bin/python3 tools/maintenance/cleanup_kb.py`

### `generate_user_profiles.py`
**Purpose**: Synthesizes user interaction logs into structured profiles in `knowledge_base/user_profiles/`.  
**Usage**: `venv/bin/python3 tools/maintenance/generate_user_profiles.py`

### `update_kaia_news.py`
**Purpose**: Fetches grounded daily tech news briefs via Gemini API and creates summaries.  
**Usage**: `venv/bin/python3 tools/maintenance/update_kaia_news.py`

### `ingest_manual_news.py`
**Purpose**: Manually ingests an external news brief into the RAG system.  
**Usage**: `venv/bin/python3 tools/maintenance/ingest_manual_news.py path/to/brief.md`

---

## Diagnostics & Probes (`tools/diagnostics/`)

### `check_indexing_health.py`
**Purpose**: Checks RAG index integrity, BM25 hydration, and document counts.  
**Usage**: `venv/bin/python3 tools/diagnostics/check_indexing_health.py`

### `diagnose_rag.py`
**Purpose**: Diagnostic tool to test RRF scoring and query retrieval for specific prompts.  
**Usage**: `venv/bin/python3 tools/diagnostics/diagnose_rag.py`

### `scan_knowledge_base.py`
**Purpose**: Scans knowledge base for corrupted markdown, formatting anomalies, or encoding issues.  
**Usage**: `venv/bin/python3 tools/diagnostics/scan_knowledge_base.py`

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

