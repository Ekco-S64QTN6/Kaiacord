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
| `kaia_intelligence.py` | Intelligence facade — coordinates classification and optimization |
| `intent_classifier.py` | Dual-mode intent detection (Fast-path Regex + LLM Deep Dive) |
| `context_optimizer.py` | Dynamic context window management and token budgeting |
| `hallucination_detector.py` | Canonical detector for AI structural leaks and fabrications |
| `message_processor.py` | Modular on_message pipeline with timeout guards and self-healing (~2310 lines) |
| `response_filter.py` | BotSpeakFilter, boilerplate filtering, and response cleaning |
| `safety_pipeline.py` | 11-layer post-generation safety pipeline and dogtag replay |
| `sanitizer.py` | Output sanitization and artifact cleanup |
| `timezone_helper.py` | 4-clock Newsroom Wall timezone engine (12-hour AM/PM format, IANA safety) |
| `background_tasks.py` | Afterthoughts, dawn tasks, presence loops, and forum scheduling |
| `kaia_art.py` | Fractal flame renderer (CPU-only, NumPy/SciPy) |
| `kaia_reactions.py` | Non-verbal emoji reaction system |

## Cognitive Pipeline (`utils/core/`)

| Module | Purpose |
|--------|---------|
| `kaia_dream.py` | Dream Engine for nightly associative memory processing |
| `kaia_mood.py` | Persistent emotional state vector (valence/arousal/energy) with 6h decay |
| `kaia_monologue.py` | Private thought stream from passive channel observation |
| `kaia_proactive.py` | Autonomous conversation initiation (7-source trigger engine) |
| `kaia_presence.py` | Mood-aware Discord status driven by emotional arc |
| `memory_anchors.py` | Dream-extracted thematic anchors (100-cap) for cross-session callbacks |
| `relationship_manager.py` | Per-user relationship event store and staging (100-event cap) |
| `curiosity_scanner.py` | Unresolved mention detection and follow-up generation |

## Infrastructure (`utils/infrastructure/`)

| Module | Purpose |
|--------|---------|
| `system/app_context.py` | **AppContext**: Central container for system singletons and dependencies |
| `system/bot_state.py` | Persistent state, beliefs (100-cap), and user dossiers |
| `system/yaml_config.py` | Hierarchical configuration management |
| `system/messaging.py` | Discord message utilities and chunking guard ($\le 1990$ chars) |
| `system/rate_limiter.py` | Per-user interaction rate limiting |
| `logging/kaia_logger.py` | Structured logging |
| `monitoring/btop_dashboard_v2.py` | Live curses monitoring dashboard |
| `monitoring/async_task_registry.py`| Background task lifecycle tracking |
| `monitoring/watchdog.py` | Event loop health monitor |
| `monitoring/stats_tracker.py` | Thread-safe forum and pipeline statistics counter |
| `monitoring/stats_poller.py` | Background poller for hardware and cognitive telemetry |

## GPU & System (`utils/infrastructure/gpu/`)

| Module | Purpose |
|--------|---------|
| `gpu_manager.py` | Ollama GPU options |
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
| `forum_handler.py` | `!forum` linking and scrapers |
| `audit_handler.py` | `!audit` and `!flag` moderation audit handlers |
| `snapshot_handler.py` | `!snapshot` state archiving |
| `selfmodel_handler.py` | `!selfmodel` regeneration |
| `enrich_handler.py` | `!enrich` contextual text enrichment |
| `reindex_handler.py` | `!reindex` background knowledge refresh |
| `sysmon_handler.py` | `!sysmon` monitoring |
| `explain_handler.py` | `!explain` RAG retrieval diagnostics |
| `download_handler.py` | `!download` URL ingestion |
| `system_handler.py` | `!cache` and system administration commands |

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
| `monster_registry.py` | 366 monster stat blocks (41 boss-tier) |
| `equipment_registry.py`| 453 items across 7 tiers |
| `fishing.py` & `fishing_engine.py` | 253 fish species, rods, bait, and fishing economy |
| `shop.py` | Merchant inventory and pricing (Hemlock, Pell's, Caravan) |
| `housing.py`, `farming.py`, `pets.py`, `alchemy.py` | Estate management, harvesting, companions, brewing |
| `calendar.py` | Seasons, dynamic weather, and 13 special calendar holidays |
| `quest_registry.py` | 12 progressive quests (L1–L15) |
| `npc_registry.py` & `loot_tables.py` | NPC dialogue definitions and tiered drop tables |
