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
| `context_enricher.py` | Automated content enrichment (URL fetching, attachment scraping) |
| `kaia_dream.py` | Dream Engine for nightly associative memory processing |
| `hallucination_detector.py` | Canonical detector for AI structural leaks and fabrications |
| `message_processor.py` | Modular on_message pipeline with timeout guards and self-healing |
| `knowledge_boundary.py` | Entity extraction, fuzzy matching, and hallucination prevention boundary |
| `semantic_cache.py` | Enhanced semantic cache with pollution protection |
| `response_filter.py` | Hallucination detection, boilerplate filtering, and response cleaning |

## Infrastructure (`utils/infrastructure/`)

| Module | Purpose |
|--------|---------|
| `system/app_context.py` | **AppContext**: Central container for system singletons and dependencies |
| `system/dashboard_manager.py` | **Lifecycle Manager**: Run modes, startup, and cleanup |
| `logging/unified_logging.py` | Centralized logging with color-coded output |
| `system/yaml_config.py` | Hierarchical configuration management (env → kaia.yaml → default_config.yaml) |
| `system/bot_state.py` | Persistent state and interaction tracking |
| `system/rate_limiter.py` | Per-user interaction rate limiting |
| `system/shutdown_manager.py` | Ordered shutdown orchestration (model unload → RAG persist → cleanup) |
| `monitoring/stats_tracker.py` | Statistics collection and dashboard data |

## GPU & System (`utils/infrastructure/gpu/`)

| Module | Purpose |
|--------|---------|
| `gpu_manager.py` | Semaphore-based GPU concurrency guard (replaces legacy model-swapping manager) |
| `gpu_memory_manager.py` | GPU guard wrapper with ContextVar re-entrancy detection |

## Specialized Handlers

| Folder | Purpose |
|--------|---------|
| `utils/commands/` | Extracted logic for `!news`, `!dreams`, `!vram`, etc. |
| `utils/news/` | News retrieval, parsing, and ingestion logic |
| `utils/social/` | Bluesky, X/Twitter, Social Responder with circuit breakers |
