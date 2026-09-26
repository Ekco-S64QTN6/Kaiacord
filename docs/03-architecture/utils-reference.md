# Utils Reference

Core utility modules used by Kaiacord.

## Core Modules (`utils/core/`)

| Module | Purpose |
|--------|---------|
| `kaia_rag.py` | RAG facade — delegates to query, indexer, persistence, and retriever modules |
| `kaia_rag_query.py` | Hybrid BM25+vector retrieval, dynamic scoring, and identity resolution |
| `kaia_rag_indexer.py` | Document ingestion, BM25 indexing, and parallel background updates |
| `kaia_rag_persistence.py` | RAG state persistence (JSON manifest + BM25 pickle) and pre-warming |
| `kaia_rag_retriever.py` | Shared RAG utilities and thread-safe lock decorators |
| `kaia_intelligence.py` | Intelligence facade — coordinates intent matching, budgeting and enrichment |
| `intent_classifier.py` | Intent detection by regex. No model — the `gemma2:2b` second pass was removed in Sept 2026 because its verdict was never read |
| `context_optimizer.py` | Dynamic context window management and token budgeting |
| `hallucination_detector.py` | Canonical detector for AI structural leaks and fabrications |
| `message_processor.py` | Modular on_message pipeline with timeout guards and self-healing (~2310 lines) |
| `response_filter.py` | BotSpeakFilter, boilerplate filtering, and response cleaning |
| `safety_pipeline.py` | Post-generation safety pipeline and dogtag replay. Steps are numbered in the source; the count in this table was wrong twice, so it is not asserted here. |
| `sanitizer.py` | Output sanitization and artifact cleanup |
| `frontmatter.py` | The one writer for YAML frontmatter blocks. Every corpus writer that built one with an f-string eventually produced invalid YAML. |
| `timezone_helper.py` | 4-clock Newsroom Wall timezone engine (12-hour AM/PM format, IANA safety) |
| `background_tasks.py` | Afterthoughts, dawn tasks, presence loops, and forum scheduling |
| `kaia_art.py` | Fractal flame renderer (CPU-only, NumPy/SciPy) |
| `kaia_reactions.py` | Non-verbal emoji reactions — 85 emoji across 11 mood-biased pools, graded so the heaviest is not as likely as the mildest |

## Cognitive Pipeline (`utils/core/`)

| Module | Purpose |
|--------|---------|
| `kaia_dream.py` | Dream Engine for nightly associative memory processing |
| `kaia_mood.py` | Persistent emotional state vector (valence/arousal/energy) with 6h decay |
| `kaia_desires.py` | Needs vector (social/intellectual/creative/rest) driving whether she initiates |
| `kaia_monologue.py` | Private thought stream from passive channel observation |
| `kaia_proactive.py` | Autonomous conversation initiation (10-source trigger engine, gated by `kaia_desires`; `private_thought` opens with someone a dream or thought was about) |
| `unprompted.py` | The one gate, label picker and sender for everything she says unasked (daily cap, gap, quiet hours, Bluesky cross-post) |
| `kaia_presence.py` | Mood-aware Discord status driven by emotional arc |
| `memory_anchors.py` | Dream-extracted thematic anchors (100-cap) for cross-session callbacks; recalled ones kept as they age, faded ones offered as fragments |
| `beliefs_store.py` | The single reader/writer of `memory/beliefs.json` (dream engine and chat share one lock) |
| `relationship_manager.py` | Per-user relationship event store and staging (100-event cap) |
| `curiosity_scanner.py` | Unresolved mention detection and follow-up generation |
| `open_threads.py` | Ideas she has wondered about on several days (not about people), fed back to the monologue and to turns that touch them |
| `conversation_arc.py` | Where a conversation is: a fresh start, well along, or an explicit goodbye |
| `kaia_tastes.py` | Her real favourites — most-reflected books, sets played, pieces made — for turns that ask |
| `kaia_notes.py` | Writes `knowledge_base/kaia_notes/<name>.md` when a reply says she is keeping a note |
| `sky_facts.py` | Live space-weather, launch, asteroid, quake and ISS readings for turns that ask about them |
| `architecture_claims.py` | Notices a user stating how she works, and adds a soft note |
| `dm_log.py` | Direct messages logged to `memory/dm_logs/`, never to the shared user logs |

## Infrastructure (`utils/infrastructure/`)

| Module | Purpose |
|--------|---------|
| `system/app_context.py` | **AppContext**: Central container for system singletons and dependencies |
| `system/bot_state.py` | Persistent state, beliefs (100-cap), and user dossiers |
| `system/yaml_config.py` | Hierarchical configuration management |
| `system/messaging.py` | Discord message utilities and chunking guard ($\le 1990$ chars) |
| `system/rate_limiter.py` | Per-user interaction rate limiting |
| `logging/kaia_logger.py` | Structured logging |
| `monitoring/retrieval_trace.py` | In-memory ring buffer of recent RAG retrievals, so `!explain N` can look past the single cached one |
| `monitoring/btop_dashboard_v2.py` | Live curses monitoring dashboard |
| `monitoring/async_task_registry.py`| Background task lifecycle tracking. Register fire-and-forget tasks here: asyncio holds tasks weakly, so a bare `create_task` can be collected mid-run |
| `monitoring/watchdog.py` | Event loop health monitor |
| `monitoring/stats_tracker.py` | Thread-safe forum and pipeline statistics counter |
| `monitoring/stats_poller.py` | Background poller for hardware and cognitive telemetry |

## GPU & System (`utils/infrastructure/gpu/`)

| Module | Purpose |
|--------|---------|
| `gpu_manager.py` | Ollama GPU options. `chat_options(**overrides)` is how every chat-model call builds its options — the runner options must match or Ollama reloads the model |
| `gpu_memory_manager.py` | GPU task queue with priority scheduling (Semaphore Guard) |

## Specialized Handlers (`utils/commands/`)

| Module | Purpose |
|--------|---------|
| `registry.py` | Central command dispatcher |
| `scores_handler.py` | `!scores` / `!stats` gamified analytics & affinity leaderboards |
| `art_handler.py` | `!art` fractal flame generation |
| `fishing_handler.py` | Fishing commands & interactive fishing UI |
| `rpg_handler.py` | RPG command router |
| `help_handler.py` | `!help` command handler |
| `news_handler.py` | `!news` category brief dispatch |
| `dream_handler.py` | `!dream` commands |
| `memory_handler.py` | `!memory` commands |
| `social_handler.py` | `!quip` and Bluesky/X social posting |
| `forum_handler.py` | `!forum` linking, scrapers, and `!forum reply` (drafts through `forum_drafting`) |
| `audit_handler.py` | `!audit` and `!flag` moderation audit handlers |
| `snapshot_handler.py` | `!snapshot` state archiving |
| `selfmodel_handler.py` | `!selfmodel` regeneration |
| `enrich_handler.py` | `!enrich` contextual text enrichment |
| `reindex_handler.py` | `!reindex` background knowledge refresh |
| `sysmon_handler.py` | `!sysmon` monitoring |
| `explain_handler.py` | `!explain` RAG retrieval diagnostics |
| `download_handler.py` | `!download` — stages URLs into `knowledge_base/_ingress/` |
| `youtube_handler.py` | `!youtube` — stages video transcripts into `knowledge_base/_ingress/` |
| `music_handler.py` | `!music` — start, stop, genre switches and DJ requests |
| `radio_handler.py` | `!skyking`, `!numbers`, `!radio`, `!buzzer`, `!tacamo`, `!beacons`, `!overnight` |
| `sky_handler.py` | `!iss`, `!nasa`, `!earth`, `!spaceweather`, `!rocks`, `!launch`, `!quake`, `!sky` |
| `nightshift.py` | `!nightshift`, and the small print on each radio/sky box naming its siblings |
| `profile_handler.py` | Answers "what do you know about <user>" from their profile document |
| `embed_style.py` | The embed box every `!` command answers in (`box`, `add_field`, `notice`, `clean`) |

## Music (`utils/audio/`)

No model and no VRAM: Strudel runs in a headed browser and is captured into voice.

| Module | Purpose |
|--------|---------|
| `strudel_patterns.py` | The arranged track for each genre |
| `tracks.py` | Plays a track; `check()` enforces the rules that keep every bar audible |
| `performance.py` | A lane — one `$:` line of the program — and the edits made to it |
| `dj.py` | Kaia as DJ: genre from mood and hour, tempo from arousal, requests as lane edits |
| `strudel_engine.py` | Local server, Chromium via Playwright, PipeWire sink, ffmpeg capture |
| `strudel_session.py` | A voice-channel session driving the engine |
| `strudel_source.py` | The Discord audio source fed by the capture |
| `levels.json` | Measured per-part gains, written by `audition_tracks.py --calibrate` |

## Radio (`utils/radio/`)

Guest on volunteer services: polled every `radio.poll_hours`, history in `memory/radio/`.

| Module | Purpose |
|--------|---------|
| `fetch.py` | The one HTTP path: identifying User-Agent, public-only connector, caches |
| `eam_watch.py`, `priyom.py` | eam.watch's EAM log; Priyom's number-station schedule |
| `kiwi.py` | KiwiSDR directory, receiver choice, recording, S-meter and live streams |
| `watch.py` | Scheduled listening: HFGCS windows and followed stations, cross-checked against eam.watch |
| `transcribe.py`, `phonetic.py` | CPU faster-whisper, and phonetic readbacks merged with `?` where they disagree |
| `live.py` | `!radio`/`!buzzer`/`!scanner` live in a voice channel, clip playback, and `free_voice` so features hand the connection over |
| `beacons.py` | The NCDXF beacon chain, judged from the S-meter |
| `adsb.py` | E-6B/E-4B sightings on adsb.lol |
| `overnight.py` | The morning write-up: facts gathered in Python, one model call, invented numbers rejected |
| `log.py` | `memory/radio/log.json` and the clips |
| `scanner.py` | The local RTL-SDR: nightly schedule, nets, classification (voice/data/carrier), listen-along |
| `waterfall.py` | The hopping waterfall watch and NBFM demodulator, run in a forked child with its output on /dev/null |
| `ledger.py` | `memory/radio/local_ledger.sqlite3`: channels with an hour-of-day histogram, and every catch |
| `dongle.py`, `rtl.py` | librtlsdr through ctypes; the device lock, `rtl_fm` streams and audio measurement |

## Sky (`utils/sky/`)

| Module | Purpose |
|--------|---------|
| `feeds.py` | NASA, NOAA SWPC, JPL, USGS, Launch Library 2, DSN Now |
| `passes.py` | ISS passes, moon and planets from `sky.location`, computed locally with Skyfield |

## Social & Forum Layer (`utils/social/`)

| Module | Purpose |
|--------|---------|
| `kaia_bluesky.py` | Bluesky API client (AT Protocol) |
| `kaia_twitter.py` | X/Twitter API client (Twikit lazy-loaded) |
| `kaia_forum.py` | Project 1999 VBulletin 3.x forum client, crawler & moderation UI |
| `forum_tasks.py` | Periodic scraping and auto-posting background tasks |
| `kaia_social_responder.py` | Multi-platform social mention listener & responder |
| `social_response_generator.py` | Social response generation prompts and filters |
| `kaia_identities.py` | Discord ID ↔ Forum UID identity bridge |

## TTRPG (`utils/ttrpg/`)

| Module | Purpose |
|--------|---------|
| `combat_engine.py` | Combat resolution (DEF soft-cap + global cap) |
| `spine_dungeon.py` | 77-floor Spine of the World mega-dungeon generation |
| `class_advancement.py`| 10 advanced classes, stat scaling, and proc logic |
| `character_manager.py`| Per-user character sheet I/O (async, locked) |
| `monster_registry.py` | Monster stat blocks (369 / 44 boss-tier at time of writing — verify with `exec()` + `len(MONSTERS)`) |
| `equipment_registry.py`| 395 pieces of gear across 7 tiers, plus 58 consumables |
| `fishing.py` & `fishing_engine.py` | 248 fish species, rods, bait, and fishing economy |
| `shop.py` | Merchant inventory and pricing (Hemlock, the caravan); a merchant sells only its stock |
| `enhancement.py` & `town_projects.py` | Endgame gil sinks: gear rework +1..+5, and pooled gil for the town walls |
| `housing.py`, `farming.py`, `pets.py`, `alchemy.py` | Estate management, harvesting, companions, brewing |
| `calendar.py` | Seasons, dynamic weather, and 13 special calendar holidays |
| `quest_registry.py` | 12 progressive quests (L1–L15) |
| `npc_registry.py` & `loot_tables.py` | NPC dialogue definitions and tiered drop tables |
