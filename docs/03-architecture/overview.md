# Kaia Architecture Documentation

## Overview

Kaia is a self-hosted Discord AI bot with local inference and RAG-based memory. This document describes the technical architecture after Phase 53 refactors.

## System Architecture

```mermaid
graph TB
    Discord[Discord API] --> Kaiacord[Kaiacord.py]
    Kaiacord --> Ctx[AppContext]
    Ctx --> DM[DashboardManager]
    Ctx --> MP[MessageProcessor]
    
    subgraph CL ["Core Logic"]
        RAG["kaia_rag.py (facade)\n+ query / indexer / persistence"]
        Intel["kaia_intelligence.py (facade)\n+ classifier / optimizer"]
        Dream[kaia_dream.py]
        MP[message_processor.py]
        COG["Cognitive Pipeline\nmonologue · mood · proactive · anchors"]
    end

    subgraph SOC ["Social & Forum Layer"]
        Social["social_responder.py\n+ bluesky / x"]
        Forum["kaia_forum.py\n+ P99 crawler / moderation views"]
    end
    
    subgraph INF ["Infrastructure"]
        Logging["logging/"]
        System["system/ config, state, context"]
        Monitoring["monitoring/\n+ stats_poller / stats_tracker"]
    end
    
    Ctx --> CL
    Ctx --> INF
    Ctx --> SOC
    DM --> Logging
    DM --> Monitoring
    
    INF --> Logs[(logs/kaiacord.log)]
    CL --> Memory[(memory/ - bot_state.json, stats.json)]
    CL --> KB[(knowledge_base/)]
```

## Directory Structure

```
Kaiacord/
├── Kaiacord.py              # Minimal Orchestrator (~170 lines)
├── utils/                   # Deeply modularized components
│   ├── core/                # RAG, Intelligence, Dream, Cognitive Pipeline, MessageProcessor
│   ├── infrastructure/      # AppContext, DashboardManager, Config, Monitoring
│   ├── social/              # Twitter/X, Bluesky, Social Responder & Project 1999 Forum Client/Scraper
│   ├── commands/            # Specialized command handlers
│   └── news/                # News retrieval & management
├── config/                  # Configuration & Bot Persona
├── knowledge_base/          # RAG text storage (News, Interaction Logs)
├── memory/                  # Persistent data (bot_state.json, rag_storage/)
├── tools/                   # Utility & Maintenance Scripts
│   ├── maintenance/         # News, Indexing, Health checks
│   ├── diagnostics/         # RAG & Embedding verification
│   ├── recovery/            # Contamination & Hallucination fixes
│   └── tests/               # Pytest suite
├── docs/                    # Detailed technical documentation
└── logs/                    # Consolidated logging (kaiacord.log)
```

## Core Components

### 1. Bot Core (`Kaiacord.py`)

**Responsibility**: High-level orchestration, event routing, and bootstrapping the `AppContext`.

**Key Flow**:
1. Initializes `AppContext` with core singletons (config, bot, client).
2. Initializes `DashboardManager` and `MessageProcessor` by passing the context.
3. Routes events strictly to the processor, which accesses dependencies via the context.

---

### 1.1 Application Context (`utils/infrastructure/system/app_context.py`)

**Responsibility**: The "Single Source of Truth" for application dependencies.

**Features**:
- Holds shared instances (RAG, DreamEngine, OllamaClient, BotState).
- Replaces module-level globals to prevent circular imports.
- Provides an `asyncio.Event` for boot synchronization.

---

### 2. Dashboard & Lifecycle (`utils/infrastructure/system/dashboard_manager.py`)

**Responsibility**: Manages run modes (Curses/Simple), startup tasks, and clean shutdown.

**Features**:
- ✅ Phased boot sequence (Phase 1: Chat model GPU load -> Phase 2: Bot ready -> Phase 3: Background RAG/News).
- ✅ GPU semaphore guard for single-access GPU operations.
- ✅ Curses-based real-time dashboard.
- ✅ Ordered shutdown (cancel tasks → unload model → persist RAG → close clients → kill runners).

---

### 3. Message Pipeline (`utils/core/message_processor.py`)

**Responsibility**: Decomposes the complex `on_message` logic into a modular pipeline.

**Pipeline Stages**:
1. **Entry Checks**: Rate limiting, blacklist/whitelist, boot guard.
2. **Intelligence**: Classification, Hallucination detection.
3. **Retrieval**: Parallel RAG retrieval, News enhancement, Persona adaptation.
4. **Generation**: Self-healing prompt construction and multi-pass AI call.

---

### 4. Configuration System (`utils/infrastructure/system/yaml_config.py`)

**Responsibility**: Hierarchical configuration management.

---

### 5. State Management (`utils/infrastructure/system/bot_state.py`)

**Responsibility**: Bot state persistence and interaction tracking.

---

### 6. Logging System

**Responsibility**: Consolidated, color-coded, and hardened logging across all modules.

---

### 7. Cognitive Pipeline (28 Features)

**Responsibility**: Autonomous personality systems that create the illusion of inner life.

| Module | Purpose |
|:-------|:--------|
| `kaia_mood.py` | Persistent emotional state vector (valence/arousal/energy) with 6h decay |
| `kaia_monologue.py` | Private thought stream from passive channel observation |
| `kaia_proactive.py` | Autonomous conversation initiation (7-source trigger engine) |
| `memory_anchors.py` | Dream-extracted thematic anchors (100-cap) for cross-session callbacks |
| `kaia_presence.py` | Mood-aware Discord status driven by emotional arc + engagement |
| `bot_state.py` | Relationship stages (stranger→inner_circle), 100-cap beliefs, user dossiers |
| `timezone_helper.py` | 4-clock Newsroom Wall timezone engine (12-hour format, IANA DST/leap-year safety) |
| `curiosity_scanner.py` | Unresolved mention detection and follow-up generation |

**Design rule**: Every cognitive injection is wrapped in `try/except Exception: pass`. Cognitive failures never block message generation.

---

### 8. TTRPG System (Aethelgard)

**Responsibility**: A full persistent RPG with turn-based combat, 10 classes, and a 77-floor mega-dungeon.

**Features**:
- Deterministic game math handled entirely by Python; LLM handles narration only.
- Per-user async locks prevent race conditions during combat or item generation.
- Full registry system (369 monsters with 44 bosses, 453 equipment items across 7 tiers, 253 fish species) integrated with procedural dungeon generation.

### 9. Project 1999 Forum Client (`utils/social/kaia_forum.py`)

**Responsibility**: Scrapes and interacts with the Project 1999 vBulletin forums.

**Features**:
- Crawls threads in Forum 19 (Off-Topic) and Forum 40 (Technical Discussion) periodically.
- Forwards drafts to the Discord moderation queue `#kaia-opolis` with interactive view buttons.
- Caches forum user post profiles (4h/1h cooldowns) and delta-verifies post count changes before running heavy scraper operations.
- Enforces strict zero-hallucination support guidelines for Technical Discussion replies.

---

## Data Flow

### Message Processing Flow

```mermaid
sequenceDiagram
    participant User
    participant Discord
    participant Kaiacord
    participant MP[MessageProcessor]
    participant RAG
    participant Ollama

    User->>Discord: Send message
    Discord->>Kaiacord: on_message event
    Kaiacord->>MP: process(msg)
    MP->>RAG: Retrieve context
    RAG-->>MP: Context nodes
    MP->>Ollama: Generate response (Self-Healing)
    Ollama-->>MP: AI response
    MP->>Kaiacord: send_response
    Kaiacord->>Discord: await send
```

---

## GPU Memory Management Strategy

**Priority Levels**:
1. **CHAT** (P1): Main LLM (e.g., gemma3:12b) remains resident in VRAM for fast response.
2. **MAINTENANCE**: Periodic RAG re-indexing and nightly Dream cycles.

Kaia is optimized for 12GB VRAM GPUs (like the RTX 3060). Classification and embeddings run on CPU (`num_gpu: 0`), leaving the full GPU budget for the chat model and its 8K-token KV cache.

---

## Circuit Breakers & Self-Healing

### Social API Circuit Breakers
All social media API calls (Bluesky, X/Twitter) are wrapped in `CircuitBreaker` instances:
- Opens after 3 consecutive failures.
- Auto-resets after 5-minute timeout.
- Prevents cascade failures from taking down the main bot loop.

### Self-Healing Generation Loop
Kaia implements a 3-pass self-healing generation loop:
1. **Attempt 1**: Standard parameters.
2. **Attempt 2**: Temperature scaling on failure/hallucination.
3. **Attempt 3**: Fallback safety response if generation persists in failing.

---

## References

- [Master Report](../reports/master_report.md)
- [Unified Production Audit](../reports/audit_report.md)
