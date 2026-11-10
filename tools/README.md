# Tools

Standalone scripts for maintaining Kaia's corpus and index, diagnosing her,
and fetching what the optional subsystems need. None of them run inside the
bot; the nightly and weekly passes she runs herself call a few of these as
subprocesses. Most are also reachable from `bash scripts/kaia-tools.sh`.

Run everything with the project interpreter from the repo root:

```bash
venv/bin/python3 tools/<folder>/<script>.py --help
```

**Anything that writes across the corpus is a dry run by default** and needs
`--apply`. Tools that load the model send the shared runner options
(`gpu_manager.chat_options`) and `keep_alive=-1`, so they do not reload the
bot's model; they still queue behind her in Ollama, so run long batches when
nobody is talking to her.

## maintenance/

**Corpus health**

| Script | What it does |
|:--|:--|
| `audit_knowledge_base.py` | Read-only check for every fault class that has occurred; names the fix for each. `--check` exits non-zero. |
| `repair_frontmatter.py` | Repairs frontmatter that does not parse: stacked blocks, flow sequences holding block entries, a fence fused to the body. |
| `enrich_metadata.py` | Backfills `summary` and `keywords` with the model. Runs nightly. |
| `enrich_kb_metadata.py` | Normalises frontmatter on forum posts and user logs, no model. |
| `retitle_documents.py` | Gives badly named documents a real topic and title. |
| `repair_kb_book_structure.py` | Repairs structure in already-converted books. |
| `triage_dreams.py` | Quarantines anything in `kaia_dreams/` that is not a reflection. |
| `consolidate_dreams.py` | Merges nightly reflections into one document per subject. |
| `compare_book_chunking.py` | Read-only: scores book retrieval at several chunk sizes on questions with known answers, before any rebuild. |
| `tidy_troubleshooting.py` | Regenerates frontmatter on the generated troubleshooting guides. |

**User logs and profiles**

| Script | What it does |
|:--|:--|
| `compact_user_logs.py` | Deterministic cleanup of transcripts: link dumps, scrape debris, fragments. |
| `rollup_user_logs.py` | Rolls closed months of daily transcripts into one archive each. |
| `build_user_folder_index.py` | Writes a README into each user folder. |
| `clean_hallucinations.py` | Reports contaminated phrasing; with `--apply` touches only Kaia's lines. |
| `generate_user_profiles.py` | Rebuilds each user's `user_profile.md` from their logs. |
| `compact_forum_profiles.py` | Folds a forum user's scattered logs into one profile. `--repair-identity --apply` puts the identity keys back on compacted profiles (Kaia's own, linked accounts) with no model call. |
| `refresh_forum_profiles.py` | Deep-scrapes forum users the periodic scraper missed (`--linked`, `--user`, `--stubs`); lists them unless `--apply`. |
| `prune_relationship_events.py` | Drops stored relationship events the current detector would not record. |
| `clean_kaia_turns.py` | Runs today's reply filters over Kaia's own past turns in `user_logs/`, channel memory and board posts (never a person's turns); dry run unless `--apply`, refuses while the bot runs. Reindex after. |

**Ingestion and news**

| Script | What it does |
|:--|:--|
| `ebook_to_kb_md.py` | EPUB / PDF / TXT / HTML to knowledge-base Markdown. |
| `youtube_to_kb_md.py` | A YouTube transcript to Markdown with timestamp anchors. |
| `transcript_names.py` | Corrects names speech recognition misheard in a transcript. |
| `process_ingress.py` | Files what `!download` and `!youtube` staged in `_ingress/`. Runs hourly. |
| `update_kaia_news.py` | Writes the daily brief through Gemini with search grounding. |
| `ingest_manual_news.py` | Files a brief written by hand into `news/daily/`. |
| `scrape_tech_news.py` | Writes the daily tech digest. |
| `backfill_forum_corpus.py` | Pre-fills the Project 1999 Off-Topic corpus. |

**Index, system and assets**

| Script | What it does |
|:--|:--|
| `reindex_rag.py` | `--trigger` asks the running bot to refresh; `--clear` rebuilds from scratch (bot stopped). |
| `health_check.py` | That it runs in the project venv, packages (including `davey`), the GPU from `nvidia-smi`, Ollama models, token, config, permissions. |
| `fetch_music_assets.py` | Fetches Strudel and the samples `!music` needs. Run once after cloning. |
| `fetch_art_flock.py` | `!art` setup: `--build-flam3` builds flam3 into `~/.local/bin`, `--count N` fetches Electric Sheep genomes into `memory/art/flock/`, `--gate` preview-checks them. Run once after cloning. |
| `fetch_radio_assets.py` | Fetches kiwiclient for `!radio`. Run once. |
| `audition_tracks.py` | Plays each `!music` track and measures every part; `--calibrate` writes `levels.json`. |
| `records_graph.py` | Measures which records lock with which and walks hour-long sets through them (`memory/records/graph.json`, extended, never rebuilt). The bot runs it niced when a set starts with unmeasured records. |
| `beat_ticks.py` | Caches Essentia beat positions for each record, for the mixer's grids. |
| `band_notebook.py` | The local scanner's ledger as a notebook, one entry per frequency; `--write` updates the git-ignored `docs/reports/reference/local_band_notebook.md`, keeping its "My notes". Runs after every watch. |
| `ledger_repair.py` | Brings the scanner ledger up to how catches are judged now (`--clips`, …); dry run unless `--apply`. |
| `rx_preview.py` | KAIA//RX on a simulated RTL-SDR: the real scanner and dashboard, no dongle and no bot. |
| `fetch_street_names.py` | Builds the scanner's street list from OpenStreetMap into `memory/radio/streets.json`. |
| `uvk5.py` | Read-only Quansheng UV-K5 over its programming cable: find the port, firmware, EEPROM backup. Never transmits. |
| `check_md_anchors.py` | Validates in-page Markdown anchors against GitHub's slug rules. |
| `kaia_admin.py` | KAIA // OPS, the read-only admin dashboard on 127.0.0.1:47433, in its own process (`--detach`, `--no-window`). |
| `mem_report.py` | Reads `memory/diagnostics/mem_probe.jsonl`: RSS, what the heap trim gave back, and with `diagnostics.memory_trace` the lines Python's growth came from. |

## diagnostics/

| Script | What it does |
|:--|:--|
| `ask_index.py` | Asks the RAG index a question the way a chat turn does and prints what comes back. Reads a copy of the index. |
| `check_indexing_health.py` | Manifest against the files on disk, judged by the indexer's own exclusion rules. |
| `jspace_probe.py` | Replays prompts through Ollama persona'd, bare and fine-tuned. Bot stopped. |
| `list_gemini_models.py` | Lists the Gemini models this API key can call. |

## development/

| Script | What it does |
|:--|:--|
| `generate_self_model.py` | Kaia's first-person self-model from her recent conversations with everyone she talks to, and her dreams' text. |
| `build_spine_layouts.py` | Regenerates `utils/ttrpg/spine_layouts.json`, the 77 Spine of the World floors. Random per run. |
| `art_gallery.py` | A fixed, versioned gallery of `!art` renders (prompt, seed and palette per case) as a labelled contact sheet; `--against DIR` puts each case before and after a change. `--fast` for quick checks. Issue #48, step 1. |

## social/

| Script | What it does |
|:--|:--|
| `scrape_p99_wiki.py` | Crawls the Project 1999 wiki into `wiki/`. |
| `scrape_technical_discussion.py` | Scrapes the technical forum, resumably; a thread whose post count has not changed is skipped. |
| `synthesize_technical_knowledge.py` | Turns the technical forum and wiki into troubleshooting guides. The dry run makes no model call; `--apply` writes, and retries threads that errored. |
| `scrape_music_thread.py` | The "What Are You Listening To?" thread to a Google Sheet. |
| `export_x_cookies.py` | Writes `memory/x_cookies.json` for twikit from a browser session, a profile file, or two pasted cookies. |
| `smoke_test_x.py` | Logs into X and reads the account back. |

## simulation/

| Script | What it does |
|:--|:--|
| `game_audit.py` | Simulates hunts per class and reports win rate, deaths and rewards. |
| `progression_sim.py` | Plays characters from level 1 to 15 through the real combat engine, loot tables and prices; days per level, deaths, retreats and gil by source. Run before and after a balance change. |

## tests/

The test suite. See [`tests/README.md`](tests/README.md).
