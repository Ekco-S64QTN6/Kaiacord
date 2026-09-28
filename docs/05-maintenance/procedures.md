# Maintenance Tools Documentation

This directory documents scripts for maintaining, diagnosing, and repairing the Kaiacord system.

## Maintenance Tools (`tools/maintenance/`)

### `health_check.py`
**Purpose**: System validation: that it runs in the project venv with its packages (including `davey`), the GPU from `nvidia-smi`, Ollama and the models, the Discord token, config and directory permissions.  
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
**Purpose**: Reports contaminated phrasing in the transcripts. With `--apply` it removes Kaia's matching lines only; a turn's first line keeps its `[time] Kaia:` prefix, so what follows is not reattributed to the previous speaker. User lines are never modified.  
**Usage**: `venv/bin/python3 tools/maintenance/clean_hallucinations.py [--apply]`

### `audit_knowledge_base.py`
**Purpose**: Read-only check of the corpus for every fault class that has occurred, naming the fix for each.  
**Usage**: `venv/bin/python3 tools/maintenance/audit_knowledge_base.py [--check]`

### `generate_user_profiles.py`
**Purpose**: Synthesizes each user's interaction logs into `knowledge_base/user_logs/<Name>_<id>/user_profile.md`.  
**Usage**: `venv/bin/python3 tools/maintenance/generate_user_profiles.py`

### Corpus repair tools
Everything that writes across the corpus is a **dry run unless `--apply`**: `repair_frontmatter.py`,
`retitle_documents.py`, `enrich_kb_metadata.py`, `refresh_forum_profiles.py`,
`compact_forum_profiles.py` (`--repair-identity --apply` restores the identity keys on forum
profiles without a model call — run it whenever `test_identity_and_profiles` fails),
`synthesize_technical_knowledge.py` (its dry run makes no model call). Run
`audit_knowledge_base.py` afterwards. `tools/README.md` lists every script.

### `band_notebook.py`
**Purpose**: The local scanner's ledger as a notebook, one entry per frequency. The watch
regenerates it after every night into the git-ignored `docs/reports/reference/local_band_notebook.md`;
the "My notes" section is kept as written.  
**Usage**: `venv/bin/python3 tools/maintenance/band_notebook.py [--write]`

### `update_kaia_news.py`
**Purpose**: Fetches grounded daily tech news briefs via Gemini API and creates summaries.  
**Usage**: `venv/bin/python3 tools/maintenance/update_kaia_news.py`

### `ingest_manual_news.py`
**Purpose**: Files a brief written by hand. Put it in `knowledge_base/news/daily/` first.  
**Usage**: `venv/bin/python3 tools/maintenance/ingest_manual_news.py`

---

## Diagnostics & Probes (`tools/diagnostics/`)

### `check_indexing_health.py`
**Purpose**: Compares the manifest with the files on disk, using the indexer's own exclusion rules, so an excluded file is not reported as missing.  
**Usage**: `venv/bin/python3 tools/diagnostics/check_indexing_health.py`

### `ask_index.py`
**Purpose**: Asks the RAG index a question the way a chat turn does and prints each hit with its score, label and source. Works on a copy of the index, so it is safe while the bot runs.  
**Usage**: `venv/bin/python3 tools/diagnostics/ask_index.py "who wrote Neuromancer?"`

### `jspace_probe.py`
**Purpose**: Jacobian space behavioral probe harness to verify persona boundaries, apology suppression, and RAG grounding.  
**Usage**: `./scripts/run_jspace_probe.sh full`

---

## Starting and stopping

`bash scripts/kaia-tools.sh` → stop / restart. Stop waits up to 90 s for the bot to exit, and
restart refuses to start a second bot if the first is still running — two bots on one token
answer every message twice. Both match only a Python process running `Kaiacord.py`, never the
terminal it was started in.

## Operational Notes

### Terminal UI Notes
| Status | Condition |
| :--- | :--- |
| the chat model's name | Ollama's `/api/ps` shows it loaded |
| `unloaded (idle)` | `/api/ps` inconclusive and GPU VRAM < 2 GB |
| `warming` | `/api/ps` inconclusive and GPU VRAM 2–6 GB |
| `Active (VRAM high)` | `/api/ps` inconclusive and GPU VRAM > 6 GB |
| `0 (idle)` | No active users in the last 15 minutes |

