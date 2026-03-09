# Tools Directory

Maintenance, diagnostic, and recovery utilities for Kaiacord v2.0.

## Quick Reference

| Tool | Category | Purpose |
|:-----|:---------|:--------|
| `update_kaia_news.py` | Maintenance | Update daily news briefs |
| `health_check.py` | Maintenance | System health validation |
| `nuclear_reset.py` | Recovery | **Complete system purge** ⚠️ |
| `find_contamination.py` | Recovery | Find hallucinated content |
| `proper_fix.py` | Recovery | Surgical hallucination removal |
| `scan_knowledge_base.py` | Diagnostics | Scan knowledge base |
| `diag_rag_index.py` | Diagnostics | RAG index diagnostics |
| `diagnose_embeddings.py` | Diagnostics | Embedding pipeline diagnostics |
| `diagnose_rag.py` | Diagnostics | Full RAG system diagnostics |
| `generate_user_profiles.py` | Development | Generate user profiles |
| `cleanup_kb.py` | Utilities | Knowledge base cleanup |
| `sanitize_logs.py` | Utilities | Strip runtime tags from user logs |
| `kb_cleanse_user_logs.py` | Utilities | LLM-powered log content cleanup |
| `sync_sanitized_logs.py` | Utilities | Sync manual log edits to RAG |

## Structure

```
tools/
├── maintenance/     # Regular maintenance scripts
├── diagnostics/     # Debugging and diagnostics
├── recovery/        # Emergency recovery tools ⚠️
├── social/          # X/Bluesky auth & cookie tools
├── development/     # Development tools
├── tests/           # Test suite
│   ├── unit/        # Component unit tests
│   ├── integration/ # End-to-end flow tests
│   └── verification/# Logic verification & smoke tests
├── rebuild_rag_cpu.py # Full RAG rebuild (CPU)
├── rebuild_rag_gpu.py # Full RAG rebuild (GPU)
└── legacy/          # Historical tools (preserved)
```

---

## Core Utilities (`tools/`)

### cleanup_kb.py
**Knowledge base cleanup**
```bash
python tools/cleanup_kb.py
```
Clears Out-of-vocabulary and OCR artifacts.

### sanitize_logs.py / kb_cleanse_user_logs.py
**User log sanitization**
```bash
python tools/sanitize_logs.py
python tools/kb_cleanse_user_logs.py
```
Strips injection tags or uses Ollama to denoise and reformat user logs.

### diag_rag_index.py / diagnose_embeddings.py / diagnose_rag.py
**RAG Pipeline Diagnostics**
Detailed checks and counts for the Knowledge Base and Embeddings.

---

## Maintenance Tools (`tools/maintenance/`)

### update_kaia_news.py
**Update daily news briefs**

```bash
python tools/maintenance/update_kaia_news.py

# With specific category
python tools/maintenance/update_kaia_news.py --category technology
```

Generates daily news briefs for RAG system. Requires `GEMINI_API_KEY` in `.env`.

### health_check.py
**System health validation**

```bash
python tools/maintenance/health_check.py
```

Checks:
- Ollama server status
- Required models (gemma3:12b, gemma2:2b, nomic-embed-text)
- GPU availability and VRAM
- Knowledge base accessibility
- Configuration files

---

## Diagnostics Tools (`tools/diagnostics/`)

### scan_knowledge_base.py
**Scan knowledge base for issues**

```bash
python tools/diagnostics/scan_knowledge_base.py
```

Scans knowledge base for:
- Corrupted files
- Missing embeddings
- Indexing issues

### trigger_rag_refresh.py
**Force RAG re-indexing**

```bash
python tools/diagnostics/trigger_rag_refresh.py
```

Forces a complete re-index of the knowledge base.

---

## Recovery Tools (`tools/recovery/`) ⚠️

> **Warning**: These tools modify or delete data. Use with caution!

### nuclear_reset.py
**Complete system purge**

```bash
python tools/recovery/nuclear_reset.py

# Dry run (preview only)
python tools/recovery/nuclear_reset.py --dry-run
```

**What it does**:
- Purges ALL user profiles
- Clears semantic cache
- Removes interaction logs
- Resets hallucination data
- Cleans corrupted files

**When to use**: Persistent hallucinations, corrupted data, fresh start

### find_contamination.py
**Find hallucinated content**

```bash
python tools/recovery/find_contamination.py

# Scan specific directory
python tools/recovery/find_contamination.py --dir knowledge_base/user_logs
```

Scans for known hallucination patterns (Juanita, Deane, etc.)

### proper_fix.py
**Surgical hallucination removal**

```bash
python tools/recovery/proper_fix.py

# Preview changes
python tools/recovery/proper_fix.py --dry-run
```

Removes specific hallucination patterns without affecting real data.

### clean_hallucinated_logs.py
**Clean interaction logs**

```bash
python tools/recovery/clean_hallucinated_logs.py
```

Removes hallucinated content from user interaction logs.

### emergency_hallucination_cleanup.py
**Emergency cleanup**

```bash
python tools/recovery/emergency_hallucination_cleanup.py
```

Aggressive hallucination removal for severe contamination.

---

## Development Tools (`tools/development/`)

### generate_user_profiles.py
**Generate user profiles**

```bash
python tools/development/generate_user_profiles.py

# For specific user
python tools/development/generate_user_profiles.py --user 123456789
```

Generates detailed user profiles from interaction logs.

### profile_generator.py
**Profile generation utility**

```bash
python tools/development/profile_generator.py
```

Helper utility for user profile generation.

---

## Migration Tools (`tools/migration/`)

Tools for migrating between versions are in `tools/maintenance/migrate_config.py`.

---

## Legacy Tools (`tools/legacy/`)

Historical tools preserved for reference. Not actively maintained.

---

## Tests (`tools/tests/`)

All tests are consolidated under `tools/tests/` with the following layout:

```bash
# Run all tests
python -m pytest tools/tests/ -q

# Run by category
python -m pytest tools/tests/unit/ -q
python -m pytest tools/tests/integration/ -q

# Health check
python tools/maintenance/health_check.py
```

| Directory | Contents |
|:----------|:---------|
| `unit/` | Component tests (RAG, intelligence, filters, social, config) |
| `integration/` | Full flow tests (chat, core pipeline, RAG integration) |
| `verification/` | Logic verification, smoke tests, benchmarks |
| `archive/` | Historical tests (preserved for reference) |

---

## Usage Pattern

### Routine Maintenance
```bash
# Daily news update
python tools/maintenance/update_kaia_news.py

# Health check
python tools/maintenance/health_check.py
```

### Troubleshooting
```bash
# Check for hallucinations
python tools/recovery/find_contamination.py

# Scan knowledge base
python tools/diagnostics/scan_knowledge_base.py
```

### Recovery
```bash
# 1. Find issues
python tools/recovery/find_contamination.py

# 2. Targeted fix
python tools/recovery/proper_fix.py --dry-run  # Preview
python tools/recovery/proper_fix.py             # Execute

# 3. If still issues, nuclear option
python tools/recovery/nuclear_reset.py --dry-run  # Preview
python tools/recovery/nuclear_reset.py             # Execute
```

---

## Adding `--help` to Tools

All tools should support `--help`. Example:

```python
#!/usr/bin/env python3
"""
Tool description here.
"""
import argparse

def main():
    parser = argparse.ArgumentParser(description="Tool description")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes")
    args = parser.parse_args()
    
    # Tool logic here
    
if __name__ == "__main__":
    main()
```

---

## Safety Best Practices

1. **Always dry-run first**: Use `--dry-run` when available
2. **Backup before recovery**: Copy `storage/` and `knowledge_base/` before using recovery tools
3. **Read the code**: Understand what a tool does before running it
4. **Start small**: Try targeted fixes before nuclear options

---

## Tool Development Guidelines

When creating new tools:
- Add `--help` support
- Add `--dry-run` for destructive operations
- Use color-coded logging (from `utils/unified_logging.py`)
- Handle errors gracefully
- Document in this README
