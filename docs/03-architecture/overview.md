# Kaia Architecture Documentation

## Overview

Kaia is a self-hosted Discord AI bot with local inference and RAG-based memory. This document describes the technical architecture after the latest refactors (Phases 1-14).

## System Architecture

```mermaid
graph TB
    Discord[Discord API] --> Kaiacord[Kaiacord.py]
    Kaiacord --> Ctx[AppContext]
    Ctx --> DM[DashboardManager]
    Ctx --> MP[MessageProcessor]
    
    subgraph CL ["Core Logic"]
        RAG[kaia_rag.py]
        Intel[kaia_intelligence.py]
        Dream[kaia_dream.py]
    end
    
    subgraph INF ["Infrastructure"]
        Logging["logging/"]
        System["system/ config, state, context"]
        Monitoring["monitoring/"]
    end
    
    Ctx --> CL
    Ctx --> INF
    DM --> Logging
    DM --> Monitoring
    
    INF --> Logs[(logs/kaiacord.log)]
    CL --> Memory[(memory/)]
    CL --> KB[(knowledge_base/)]
```

## Directory Structure

```
Kaiacord/
├── Kaiacord.py              # Minimal Orchestrator (~170 lines)
├── utils/                   # Deeply modularized components
│   ├── core/                # Core AI logic (RAG, Intelligence, Dream, MessageProcessor)
│   ├── infrastructure/      # System foundations (AppContext, DashboardManager, Config)
│   ├── social/              # Twitter/X, Bluesky & Social Responder
│   ├── commands/            # Specialized command handlers
│   └── news/                # News retrieval & management
├── config/                  # Configuration & Bot Persona
├── knowledge_base/          # RAG text storage (News, Interaction Logs)
├── memory/                  # Persistent data (bot_state.json, semantic_cache.json, rag_storage/)
├── tools/                   # Utility & Maintenance Scripts
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
- ✅ Phased boot sequence (RAG -> News -> Model Warmup with 5-min timeout).
- ✅ GPU semaphore guard for single-access GPU operations.
- ✅ Curses-based real-time dashboard.
- ✅ Ordered shutdown (cancel tasks → unload model → persist RAG → close clients → kill runners).

---

### 3. Message Pipeline (`utils/core/message_processor.py`)

**Responsibility**: Decomposes the complex `on_message` logic into a modular pipeline.

**Pipeline Stages**:
1. **Entry Checks**: Rate limiting, blacklist/whitelist, boot guard.
2. **Intelligence**: Classification, Hallucination detection, Semantic Cache check.
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

Kaia is optimized for 12GB VRAM GPUs (like the RTX 3060). Classification and embeddings run on CPU (`num_gpu: 0`), leaving the full GPU budget for the chat model and its 20K-token KV cache.

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

- [GEMINI Report](../reports/GEMINI_Report.md)
- [Claude Report](../reports/Claude_Report.md)
