# Utils Reference

Core utility modules used by Kaiacord.

## Core Modules (`utils/core/`)

| Module | Purpose |
|--------|---------|
| `kaia_rag.py` | Retrieval-Augmented Generation system and vector indexing |
| `kaia_intelligence.py` | Intelligence Layer: Context optimization, personalization, and Query Classifier |
| `kaia_dream.py` | Dream Engine for nightly associative memory processing |
| `message_processor.py` | Modular on_message pipeline stage management |
| `semantic_cache.py` | Enhanced semantic cache with pollution protection |
| `response_filter.py` | Hallucination detection and response cleaning |

## Infrastructure (`utils/infrastructure/`)

| Module | Purpose |
|--------|---------|
| `system/app_context.py` | **AppContext**: Central container for system singletons and dependencies |
| `system/dashboard_manager.py` | **Lifecycle Manager**: Run modes, startup, and cleanup |
| `logging/unified_logging.py` | Centralized logging with color-coded output |
| `system/yaml_config.py` | Hierarchical configuration management |
| `system/bot_state.py` | Persistent state and interaction tracking |
| `system/rate_limiter.py` | Per-user interaction rate limiting |
| `monitoring/stats_tracker.py` | Statistics collection and dashboard data |

## Specialized Handlers

| Folder | Purpose |
|--------|---------|
| `utils/commands/` | Extracted logic for `!news`, `!dreams`, `!vram`, etc. |
| `utils/news/` | News retrieval, parsing, and ingestion logic |
| `utils/social/` | Bluesky, X/Twitter, and Social Responder logic |

## GPU & System

| Module | Purpose |
|--------|---------|
| `gpu/gpu_manager.py` | Smart GPU management for Ollama models |
| `system/shutdown_fixed.py` | Graceful shutdown orchestration |
