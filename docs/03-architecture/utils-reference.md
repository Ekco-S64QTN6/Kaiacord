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
| `message_processor.py` | Modular on_message pipeline with timeout guards and self-healing |
| `response_filter.py` | Hallucination detection, boilerplate filtering, and response cleaning |
| `sanitizer.py` | Output sanitization |

## Cognitive Pipeline (`utils/core/`)

| Module | Purpose |
|--------|---------|
| `kaia_dream.py` | Dream Engine for nightly associative memory processing |
| `kaia_mood.py` | Persistent emotional state vector (valence/arousal/social_energy) |
| `kaia_monologue.py` | Private thought stream from passive channel observation |
| `kaia_proactive.py` | Autonomous conversation initiation engine |
| `kaia_presence.py` | Mood-aware Discord status driven by emotional arc |
| `memory_anchors.py` | Dream-extracted thematic anchors for cross-session callbacks |
| `relationship_manager.py` | Per-user relationship event store and staging |
| `curiosity_scanner.py` | Unresolved mention detection |

## Infrastructure (`utils/infrastructure/`)

| Module | Purpose |
|--------|---------|
| `system/app_context.py` | **AppContext**: Central container for system singletons and dependencies |
| `system/bot_state.py` | Persistent state and interaction tracking |
| `system/yaml_config.py` | Hierarchical configuration management |
| `system/messaging.py` | Discord message utilities |
| `system/rate_limiter.py` | Per-user interaction rate limiting |
| `logging/kaia_logger.py` | Structured logging |
| `monitoring/btop_dashboard_v2.py` | Live curses monitoring dashboard |
| `monitoring/async_task_registry.py`| Background task lifecycle tracking |
| `monitoring/watchdog.py` | Event loop health monitor |

## GPU & System (`utils/infrastructure/gpu/`)

| Module | Purpose |
|--------|---------|
| `gpu_manager.py` | Ollama GPU options |
| `gpu_memory_manager.py` | GPU task queue with priority scheduling |

## Specialized Handlers (`utils/commands/`)

| Module | Purpose |
|--------|---------|
| `registry.py` | Central command dispatcher |
| `art_handler.py` | `!art` fractal flame generation |
| `fishing_handler.py` | Fishing commands |
| `rpg_handler.py` | RPG command router |
| `dream_handler.py` | `!dream` commands |
| `social_handler.py` | Bluesky/X social posting |
| `sysmon_handler.py` | `!sysmon` monitoring |

## TTRPG (`utils/ttrpg/`)

| Module | Purpose |
|--------|---------|
| `combat_engine.py` | Combat resolution (DEF soft-cap + global cap) |
| `spine_dungeon.py` | 77-floor mega-dungeon generation |
| `class_advancement.py`| 10 advanced classes and proc logic |
| `character_manager.py`| Per-user character sheet I/O (async, locked) |
| `monster_registry.py` | 335 monster stat blocks |
| `equipment_registry.py`| 447 items across 7 tiers |
