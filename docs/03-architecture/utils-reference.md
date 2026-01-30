# Utils Reference

Core utility modules used by Kaiacord.

## Core Modules

| Module | Purpose |
|--------|---------|
| `kaia_rag.py` | Retrieval-Augmented Generation system, vector indexing, and hallucination detection |
| `kaia_image.py` | Image generation with FLUX.1-schnell |
| `kaia_vision.py` | Image analysis with llama3.2-vision |
| `kaia_news.py` | Unified News Manager (Consolidated) - news scanning, parsing, and retrieval |
| `kaia_intelligence.py` | Intelligence Layer: Semantic cache, context optimization, personalization, and Query Classifier (Consolidated) |

## Infrastructure

| Module | Purpose |
|--------|---------|
| `unified_logging.py` | Centralized logging with color-coded output |
| `kaia_logger.py` | Logging helper functions |
| `btop_dashboard.py` | Btop-style terminal dashboard |
| `terminal_manager.py` | Terminal control utilities |
| `stats_tracker.py` | Statistics collection |
| `stats_poller.py` | Statistics polling |

## Response Processing

| Module | Purpose |
|--------|---------|
| `boilerplate_detector.py` | Removes repetitive endings from responses |
| `performance_optimizer.py` | Response optimization |
| `knowledge_boundary.py` | Knowledge boundary enforcement |

## GPU & System

| Module | Purpose |
|--------|---------|
| `gpu_manager.py` | GPU management for Ollama |
| `clear_gpu_memory.py` | GPU memory cleanup |
| `shutdown_fixed.py` | Graceful shutdown handling |
