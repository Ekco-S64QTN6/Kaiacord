# Scripts Directory

Maintenance, diagnostic, and data processing scripts for Kaiacord.

> **Note**: Test and verification scripts have been moved to [`tools/tests/`](../tools/tests/).

## Active Scripts

| Script | Purpose | Usage |
|:-------|:--------|:------|
| `cleanup_kb.py` | Knowledge base cleanup | `python scripts/cleanup_kb.py` |
| `sync_sanitized_logs.py` | Sync sanitized logs with RAG | `python scripts/sync_sanitized_logs.py` |
| `force_reindex.py` | Force complete RAG re-index | `python scripts/force_reindex.py` |
| `fix_snow_crash_ocr.py` | Repair OCR artifacts in books | `python scripts/fix_snow_crash_ocr.py` |
| `kb_processor.py` | Knowledge base document processing | `python scripts/kb_processor.py` |
| `sanitize_logs.py` | Strip internal tags from logs | `python scripts/sanitize_logs.py` |

## Diagnostic Scripts

| Script | Purpose |
|:-------|:--------|
| `diag_rag_index.py` | RAG index health report |
| `diagnose_embeddings.py` | Embedding pipeline diagnostics |
| `diagnose_rag.py` | Full RAG system diagnostics |
| `repro_rag_failure.py` | Reproduce RAG failures |
| `repro_bluesky_timeout.py` | Reproduce Bluesky timeout issues |

## Archive

Historical/deprecated scripts: [`scripts/archive/`](archive/)
