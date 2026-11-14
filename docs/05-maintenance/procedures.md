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

### `scanner_hardware_check.py`
**Purpose**: Runs the scanner's own code on the real RTL-SDR and antenna, with NOAA Weather Radio as the only reference (seven fixed channels, a continuous public broadcast). The scanner's tests use synthetic IQ; this is the check that the dongle, tuner, antenna and the device hand-over behave. Receive only.  
**Usage**: `venv/bin/python3 tools/diagnostics/scanner_hardware_check.py --transcribe` outside `radio.local.hours` and nets, or after `!scanner off`. It refuses while the dongle is busy. About three minutes; it writes a `report.json` and one weather clip to a temporary folder (`--out`), never to `memory/`.

What it measures, in order:

1. The dongle and tuner (`rtl_test -t`; the serial is not recorded).
2. The seven weather channels: each one's level over the noise, and the carrier's offset from nominal. The offset of the channels received gives the crystal error in ppm, the value `radio.local.ppm` takes.
3. The watcher's tuned mode on the strongest channel: how much of the time it kept as audio (gaps), clipping, squelch, whether the broadcast reads as voice, and with `--transcribe` the transcript.
4. The `rtl_fm` stream a live listen plays: started, read, stopped and reaped.
5. The watcher hopping as it does at night: passes, seconds a pass, catches (counted, no frequencies), and that the weather carrier is not held over and over.
6. After every step, that the dongle can be opened again: the step released it.

Squelch and voice are judged only when the station quiets the channel by 10 dB or more: the watcher follows voice only under a full-quieting carrier, so a weak station reports "not judged" for those two.

Measured on 14 Nov 2026 (RTL2838 / R820T, gain 40, `ppm` 0): one station received, 162.550 at 9 dB over noise, crystal error +1.6 ppm (no correction needed); tuned audio kept 96% of 60 s with no clipping; 118 words of forecast transcribed correctly in 17 s on the CPU; 13 passes of 44 slices in 60 s (4.6 s a pass) at 22% of one core; the weather carrier was never held while hopping; the dongle was released after each of the five steps. The station quiets the channel 7.9 dB, so squelch and voice were not judged.

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

