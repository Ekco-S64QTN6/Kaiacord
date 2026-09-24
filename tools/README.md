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
| `tidy_troubleshooting.py` | Regenerates frontmatter on the generated troubleshooting guides. |

**User logs and profiles**

| Script | What it does |
|:--|:--|
| `compact_user_logs.py` | Deterministic cleanup of transcripts: link dumps, scrape debris, fragments. |
| `rollup_user_logs.py` | Rolls closed months of daily transcripts into one archive each. |
| `build_user_folder_index.py` | Writes a README into each user folder. |
| `clean_hallucinations.py` | Reports contaminated phrasing; with `--apply` touches only Kaia's lines. |
| `generate_user_profiles.py` | Rebuilds each user's `user_profile.md` from their logs. |
| `compact_forum_profiles.py` | Folds a forum user's scattered logs into one profile. `--repair-identity` restores Kaia's own. |
| `refresh_forum_profiles.py` | Deep-scrapes forum users the periodic scraper missed. |
| `prune_relationship_events.py` | Drops stored relationship events the current detector would not record. |

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
| `health_check.py` | Python, GPU, Ollama models, token, config, permissions, dependencies. |
| `fetch_music_assets.py` | Fetches Strudel and the samples `!music` needs. Run once after cloning. |
| `fetch_radio_assets.py` | Fetches kiwiclient for `!radio`. Run once. |
| `audition_tracks.py` | Plays each `!music` track and measures every part; `--calibrate` writes `levels.json`. |
| `check_md_anchors.py` | Validates in-page Markdown anchors against GitHub's slug rules. |

## diagnostics/

| Script | What it does |
|:--|:--|
| `ask_index.py` | Asks the RAG index a question the way a chat turn does and prints what comes back. Reads a copy of the index. |
| `check_indexing_health.py` | Manifest against the files on disk. |
| `jspace_probe.py` | Replays prompts through Ollama persona'd, bare and fine-tuned. Bot stopped. |
| `list_gemini_models.py` | Lists the Gemini models this API key can call. |

## development/

| Script | What it does |
|:--|:--|
| `generate_self_model.py` | Kaia's first-person self-model from her recent logs and dreams. |
| `generate_spine_layouts.py` | Pre-computes the 77-floor Spine of the World layouts. |

## social/

| Script | What it does |
|:--|:--|
| `scrape_p99_wiki.py` | Crawls the Project 1999 wiki into `wiki/`. |
| `scrape_technical_discussion.py` | Scrapes the technical forum, resumably. |
| `synthesize_technical_knowledge.py` | Turns the technical forum and wiki into troubleshooting guides. |
| `scrape_music_thread.py` | The "What Are You Listening To?" thread to a Google Sheet. |
| `export_x_cookies.py` | Writes `memory/x_cookies.json` for twikit from a browser session, a profile file, or two pasted cookies. |
| `smoke_test_x.py` | Logs into X and reads the account back. |

## simulation/

| Script | What it does |
|:--|:--|
| `game_audit.py` | Simulates hunts per class and reports win rate, deaths and rewards. |

## tests/

The test suite. See [`tests/README.md`](tests/README.md).
