# Scripts Directory

Diagnostic, testing, and maintenance scripts for Kaiacord development and troubleshooting.

## 📋 Categories

### 🔧 Active Maintenance Scripts

| Script | Purpose | Usage |
|:-------|:--------|:------|
| `kb_cleanse_user_logs.py` | **Automated log sanitization** with LLM-powered metadata generation | Runs automatically every 4 hours via maintenance_tasks.py |
| `cleanup_kb.py` | Knowledge base cleanup and organization | `python scripts/cleanup_kb.py` |
| `sync_sanitized_logs.py` | Sync sanitized logs with RAG index | `python scripts/sync_sanitized_logs.py` |
| `force_reindex.py` | Force complete RAG re-indexing | `python scripts/force_reindex.py` |

### 🧪 Testing & Verification Scripts

| Script | Purpose | When to Use |
|:-------|:--------|:------------|
| `test_md_logging.py` | Test .md logging with YAML frontmatter | After logging changes |
| `test_quip_rag_fix.py` | Verify quip RAG integration | After RAG modifications |
| `test_skepticism.py` | Test skepticism and fact-checking | After persona changes |
| `test_summarization.py` | Test document summarization | After RAG strategy changes |
| `verify_filter_fix.py` | Verify response filter fixes | After filter modifications |
| `verify_social_fix.py` | Verify social media integration | After social responder changes |
| `verify_rag_cleanup.py` | Verify RAG cleanup operations | After KB maintenance |

### 🔍 Diagnostic Scripts

| Script | Purpose | Output |
|:-------|:--------|:-------|
| `diag_rag_index.py` | Diagnose RAG index health | Index stats and issues |
| `repro_rag_failure.py` | Reproduce RAG failures | Error reproduction |
| `repro_bluesky_timeout.py` | Reproduce Bluesky timeout issues | Timeout analysis |

### 🗑️ Log Cleanup Scripts (Legacy)

| Script | Status | Replaced By |
|:-------|:-------|:------------|
| `clean_logs_roleplay.py` | **Deprecated** | `kb_cleanse_user_logs.py` |
| `clean_logs_aggressive.py` | **Deprecated** | `kb_cleanse_user_logs.py` |
| `purge_broken_logs.py` | **Deprecated** | `kb_cleanse_user_logs.py` |

## 🚀 Quick Reference

### Common Tasks

**Force re-index knowledge base:**
```bash
python scripts/force_reindex.py
```

**Clean and enrich all logs:**
```bash
python scripts/kb_cleanse_user_logs.py
```

**Test new features:**
```bash
python scripts/test_<feature_name>.py
```

### After Major Changes

1. Run relevant test scripts
2. Check diagnostics with `diag_rag_index.py`
3. Force re-index if needed

## 📝 Script Development Guidelines

When creating new scripts:

1. **Add docstring** at the top explaining purpose
2. **Use proper imports** from utils/ modules
3. **Add to this README** in the appropriate category
4. **Include usage examples** in comments
5. **Use asyncio** for async operations (don't mix with sync)

## 🔄 Maintenance

**Deprecated scripts** should be moved to `scripts/archive/` once confirmed obsolete.

**Active scripts** should be kept up-to-date with the main codebase.
