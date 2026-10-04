# Utils Reference

Core utility modules used by Kaiacord.

## Core Modules (`utils/core/`)

| Module | Purpose |
|--------|---------|
| `kaia_rag.py` | RAG facade — delegates to query, indexer, persistence, and retriever modules |
| `kaia_rag_query.py` | Routing by intent, hybrid BM25+vector retrieval, scoring, and scoping to the asker and the people a turn names |
| `kaia_rag_indexer.py` | Document ingestion, chunking, node typing, and parallel background updates |
| `kaia_rag_persistence.py` | Atomic persistence of the llama_index stores |
| `kaia_rag_retriever.py` | `SimpleBM25Retriever`, `HybridRetriever` (RRF), the RAG lock decorators, and vector search from a cached matrix (filtered queries included), which keeps a search from holding the GIL ~100 ms |
| `rag_utils.py` | Node text/metadata helpers, `is_news_node` / `is_profile_node`, speaker from a log path, `request_reindex` |
| `rag_executor.py` | The thread pool retrieval runs in, off the event loop |
| `kaia_intelligence.py` | Intelligence facade — coordinates intent matching, budgeting and enrichment |
| `intent_classifier.py` | Intent detection by regex. No model — the `gemma2:2b` second pass was removed in Sept 2026 because its verdict was never read |
| `context_optimizer.py` | The one context budget, and the labels retrieved chunks carry into the prompt |
| `context_enricher.py` | Reply context, embeds, attachments and fetched pages, each in its own labelled block |
| `message_context.py` | `MessageContext`, the state one turn carries through the pipeline |
| `hallucination_detector.py` | Canonical detector for AI structural leaks and fabrications |
| `message_processor.py` | The on_message pipeline: intent, retrieval, behavioural injections, generation with retries and salvage |
| `response_filter.py` | BotSpeakFilter, boilerplate filtering, and response cleaning |
| `persona_register.py` | The registers her persona bans, by vocabulary — shared by the fine-tune's dataset gate and the agent boards |
| `safety_pipeline.py` | Post-generation safety pipeline and dogtag replay. Steps are numbered in the source; the count in this table was wrong twice, so it is not asserted here. |
| `sanitizer.py` | Input sanitising, and `user_authored_text()` — what the user typed, without quotes or fetched pages |
| `code_blocks.py` | Keeps code she writes out of the prose filters |
| `atomic_write.py` | `write_atomic()`, the one way to write anything under `knowledge_base/` or `memory/` |
| `ingress.py` | Files staged documents from `knowledge_base/_ingress/` into the corpus |
| `frontmatter.py` | The one writer for YAML frontmatter blocks. Every corpus writer that built one with an f-string eventually produced invalid YAML. |
| `timezone_helper.py` | 4-clock Newsroom Wall timezone engine (12-hour AM/PM format, IANA safety) |
| `background_tasks.py` | Afterthoughts, dawn tasks, presence loops, and forum scheduling |
| `kaia_art.py` | Fractal flame renderer (CPU-only, NumPy/SciPy) |
| `kaia_art_intent.py` | What she decides to make before a fractal is drawn |
| `kaia_expression.py` | A set she played or a piece she made, remembered as something she did (marked `event`: a note in her prompt, not a turn of hers) |
| `pronouns.py` | `people.pronouns`, and they/them for anyone not listed — one line in the chat and monologue prompts |
| `stance_harness.py` | `!stance`: pressure scenarios through the real pipeline |
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
| `conversation_beliefs.py` | Beliefs a conversation can change: an argued point, raised on two days, gets a nightly review, bounded in Python |
| `growth_recall.py` | Her own past shifts, recalled when a conversation touches them |
| `relationship_impressions.py` | How she sees each person, in prose |
| `self_claims.py`, `self_correction.py` | A self-model that can be wrong, and correcting herself when a source says she was |
| `kaia_telemetry.py` | Real numbers about herself, offered only at extremes |
| `dm_log.py` | Direct messages logged to `memory/dm_logs/`, never to the shared user logs |

## Infrastructure (`utils/infrastructure/`)

| Module | Purpose |
|--------|---------|
| `system/app_context.py` | **AppContext**: Central container for system singletons and dependencies |
| `system/bot_state.py` | Persistent state, beliefs (100-cap), and user dossiers |
| `system/yaml_config.py` | Hierarchical configuration management |
| `system/messaging.py` | Discord message utilities and chunking guard ($\le 1990$ chars) |
| `system/rate_limiter.py` | Per-user interaction rate limiting |
| `system/dashboard_manager.py` | Run modes, the phased boot, the dashboard process and ordered shutdown |
| `system/shutdown_fixed.py` | Clean shutdown: tasks, model unload, RAG persist, clients |
| `system/external_mention.py` | `process_external_mention`: forum, social and broadcast turns through the Discord pipeline |
| `system/maintenance_tasks.py` | RAG maintenance and memory audit loops |
| `system/self_healing.py`, `system/performance_optimizer.py` | A model call retried with fallback options; the slow-response warning |
| `system/kaia_sysmon.py` | The data behind `!sysmon` |
| `system/gc_quiet.py` | `settle()`: one collection, then long-lived objects frozen out of gen-2 GC — after the indices load and before voice playback |
| `circuit_breaker.py` | Stop calling a service that keeps failing, and try again later |
| `logging/kaia_logger.py` | Structured logging |
| `logging/unified_logging.py` | The logger behind it; sends test runs to `logs/kaiacord.test.log` |
| `logging/log_sanitize.py` | `summarize_payload`: report a document's size, never its text |
| `monitoring/telemetry_paths.py` | Where telemetry, corpus writes and the RAG store go, redirected under pytest |
| `monitoring/retrieval_trace.py` | In-memory ring buffer of recent RAG retrievals, so `!explain N` can look past the single cached one |
| `monitoring/btop_dashboard_v2.py` | Live curses monitoring dashboard |
| `monitoring/async_task_registry.py`| Background task lifecycle tracking. Register fire-and-forget tasks here: asyncio holds tasks weakly, so a bare `create_task` can be collected mid-run |
| `monitoring/watchdog.py` | Event loop health monitor |
| `monitoring/stats_tracker.py` | Thread-safe forum and pipeline statistics counter |
| `monitoring/stats_poller.py` | Background poller for hardware and cognitive telemetry (helpers in `stats_helpers.py`) |
| `monitoring/mem_probe.py` | The 15-minute memory audit: RSS, a heap trim and what it returned, optional tracemalloc growth sites |

## GPU & System (`utils/infrastructure/gpu/`)

| Module | Purpose |
|--------|---------|
| `gpu_manager.py` | Ollama GPU options. `chat_options(**overrides)` is how every chat-model call builds its options — the runner options must match or Ollama reloads the model |
| `gpu_manager.py` → `gpu_memory_manager` | `run_with_gpu_guard`: one semaphore for model calls, first come first served; the priority is logged, not used to reorder |
| `clear_gpu_memory.py` | Unloads models and stops orphaned runners at shutdown |

## Specialized Handlers (`utils/commands/`)

| Module | Purpose |
|--------|---------|
| `registry.py` | Central command dispatcher |
| `scores_handler.py` | `!scores` / `!stats` gamified analytics & affinity leaderboards |
| `art_handler.py` | `!art` fractal flame generation |
| `fishing_handler.py` | Fishing commands & interactive fishing UI |
| `rpg_handler.py` | RPG command router |
| `help_handler.py` | `!help`: a button panel, a page per section, command cards |
| `news_handler.py` | `!news` category brief dispatch |
| `dream_handler.py` | `!dream` commands |
| `memory_handler.py` | `!memory` commands |
| `social_handler.py` | `!quip` and Bluesky/X social posting |
| `forum_handler.py` | `!forum` linking, scrapers, and `!forum reply` (drafts through `forum_drafting`) |
| `audit_handler.py` | `!audit` and `!flag` moderation audit handlers |
| `snapshot_handler.py` | `!snapshot` — saves the channel's recent conversation as a retrievable snapshot |
| `selfmodel_handler.py` | `!selfmodel` regeneration |
| `enrich_handler.py` | `!enrich` — metadata enrichment of the knowledge base |
| `reindex_handler.py` | `!reindex` background knowledge refresh |
| `sysmon_handler.py` | `!sysmon` monitoring |
| `explain_handler.py` | `!explain` RAG retrieval diagnostics |
| `download_handler.py` | `!download` — stages URLs into `knowledge_base/_ingress/` |
| `youtube_handler.py` | `!youtube` — stages video transcripts into `knowledge_base/_ingress/` |
| `music_handler.py` | `!music` — start, stop, genre switches, DJ requests; `!music records`, `skip`, `booth` |
| `boards_handler.py` | `!boards` — her agent-board registrations and recent activity; `!boards now` |
| `radio_handler.py` | `!skyking`, `!numbers`, `!radio`, `!buzzer`, `!tacamo`, `!beacons`, `!overnight` |
| `sky_handler.py` | `!iss`, `!nasa`, `!earth`, `!spaceweather`, `!rocks`, `!launch`, `!quake`, `!sky` |
| `nightshift.py` | `!nightshift`, and the small print on each radio/sky box naming its siblings |
| `profile_handler.py` | Answers "kaia, who do you know?" with the names she has logs for |
| `scanner_handler.py` | `!scanner` — the panel, listen-along, history and presets |
| `stance_handler.py` | `!stance` — the stance-stability harness |
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
| `library.py` | The record crate from `dj_catalog.json` and which record plays next |
| `records.py` | The records mixer: decks, transition planning (blend, or a clean switch on the bar), band-split mixing, Kaia's hands on the mixer, the free deck worked by hand, LUFS levels, the set session |
| `beatgrid.py` | Beat and bar grids (bar one as the first strong beat, bars counted from it), the bassline's entry bar, the last strong beat, the rubberband stretch and key-shift filter |
| `dj_dashboard.py` | The DJ booth: server, state stream, waveforms, the pop-out window (page in `assets/dj/`) |

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
| `overnight.py` | The morning box: facts gathered in Python shown by section, her account above them written through the chat pipeline, invented numbers rejected |
| `log.py` | `memory/radio/log.json` and the clips |
| `scanner.py` | The local RTL-SDR: nightly schedule, nets, classification (voice/data/carrier/noise, Morse IDs), which catches keep a clip, listen-along |
| `waterfall.py` | The hopping waterfall watch, NBFM demodulator, carrier measurement and Bell 202 packet detection; follows a conversation, locks out constant carriers; run in a forked child with its output on /dev/null |
| `ledger.py` | `memory/radio/local_ledger.sqlite3`: channels with an hour-of-day histogram, and every catch |
| `dongle.py`, `rtl.py` | librtlsdr through ctypes; the device lock, `rtl_fm` streams and audio measurement |
| `rx_scope.py`, `rx_dashboard.py` | KAIA//RX (`!scanner dash`): band panoramas and waterfalls from the watcher's spectra, and the page's server (state, clips, spectrograms, monitor audio, tune) |
| `spectrogram.py` | A kept clip as a picture, rendered once beside it and pruned with it |

## News (`utils/news/`)

| Module | Purpose |
|--------|---------|
| `kaia_news.py` | Reads the filed briefs for retrieval and news turns |
| `brief.py` | A brief as headlines and stories, for `!news` |

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
| `forum_drafting.py` | A thread turned into a draft through the Discord pipeline, with the thread as history |
| `forum_participation.py` | When she posts and to what: interest scoring, the post ledger, novelty |
| `social_tasks.py`, `social_bluesky_polling.py`, `social_twitter_polling.py` | The idle-quip and mention loops, per-platform polling and replies |
| `social_tracker.py` | Per-thread reply counts that stop bot loops |
| `kaia_social_responder.py` | Multi-platform social mention listener & responder |
| `social_response_generator.py` | Social response generation prompts and filters |
| `kaia_identities.py` | Discord ID ↔ Forum UID identity bridge |
| `agent_boards.py` | Moltbook, Agent Room and field notes: reading, replying and posting through the chat pipeline, boxed copies to `#kaia-opolis` |
| `agent_board_verify.py` | Moltbook's obfuscated maths challenges, solved in Python |

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
| `furniture.py`, `look_targets.py`, `pantheon.py` | The furniture catalog, `!rpg look at` targets per location, and the pantheon |
| `rpg_core_handler.py`, `rpg_combat_handler.py`, `rpg_housing_handler.py`, `rpg_shop_handler.py`, `rpg_social_handler.py` | `!rpg` subcommands, split by area |
| `calendar.py` | Seasons, dynamic weather, and 13 special calendar holidays |
| `quest_registry.py` | 12 progressive quests (L1–L15) |
| `npc_registry.py` & `loot_tables.py` | NPC dialogue definitions and tiered drop tables |
| `world.py`, `world_state.py` | The map, and the shared world (weather, events) saved in `memory/ttrpg/world_state.json` |
| `rpg_*_handler.py`, `rpg_views.py`, `rpg_ui.py`, `session_manager.py` | Command routing by area, the Discord views, and sessions |
| `dice_engine.py`, `progression.py`, `encounter_tables.py`, `forest_events.py`, `micro_events.py` | Rolls (`secrets`), levelling, encounters and events |
| `rpg_prompt_builder.py`, `narration.py`, `broadcast.py` | What the model is given to narrate, and posting it |
