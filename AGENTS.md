# AGENTS.md

> Instructions for AI coding agents working on this repository.
> Last updated: May 14, 2026

## Project Overview

**Kaiacord** is a Discord bot built with `discord.py 2.6.4` and Python 3.14+. It features:

- **Kaia** — An AI persona powered by Ollama (local LLM, `gemma3:12b`) with RAG retrieval via LlamaIndex, featuring a 26-feature cognitive pipeline (presence, mood, afterthoughts, inner monologue, proactive initiation, relationship tracking, belief formation, dream reflections, memory anchors, conversational stance)
- **Aethelgard TTRPG** — A full turn-based RPG system (combat, 10 advanced classes, equipment, dungeons, housing, farming, pets, alchemy) with a 77-floor mega-dungeon
- **Fractal Art** — `!art` command generating fractal flames (Electric Sheep algorithm) with Kaia commentary
- **Fishing minigame** — Rod-based fishing economy
- **Social & Forum integrations** — Bluesky/X posting and Project 1999 Forum Scraper, Auto-posting, and Technical Support review system
- **Curses Monitoring** — Interactive, real-time cyber-dashboard split symmetrically with live log filtering

Tech stack: `discord.py`, `ollama`, `llama-index`, `fastapi`, `aiohttp`, `PyYAML`, `python-dotenv`, `numpy`, `scipy`, `Pillow`, `curses`.

## ⚠️ Critical: Runtime Constraints

**This is a live Discord bot. You CANNOT import or run project modules directly.**

The import chain touches Discord client initialization, async event loops, and bot token validation. Any attempt to `import` from `utils/` will **hang indefinitely** — no error, no timeout, just a frozen process.

### What works for validation:
```bash
# Syntax check (fast, no imports)
python3 -c "import ast; ast.parse(open('utils/ttrpg/monster_registry.py').read())"

# Data-only files can be exec'd in isolation (no cross-imports)
python3 -c "exec(open('utils/ttrpg/monster_registry.py').read()); print(len(MONSTERS))"

# ALWAYS wrap in timeout as a safety net — if you accidentally exec a file
# with cross-imports, this prevents an infinite hang
timeout 10 python3 -c "..."
```

### What does NOT work:
```bash
# ❌ HANGS FOREVER — do not attempt
python3 -c "from utils.ttrpg.combat_engine import ..."
python3 -c "from utils.core.message_processor import ..."
python3 -m pytest
python3 Kaiacord.py
```

### Data-only files (safe to `exec()` in isolation):
- `utils/ttrpg/monster_registry.py` — pure dicts, no imports
- `utils/ttrpg/equipment_registry.py` — pure dicts + helper functions, no imports
- `utils/ttrpg/pets.py` — pure dicts + stdlib only
- `utils/ttrpg/furniture.py` — pure dicts + stdlib only
- `utils/ttrpg/farming.py` — pure dicts + stdlib only
- `utils/ttrpg/calendar.py` — pure dicts + stdlib `datetime`/`hashlib`
- `utils/ttrpg/loot_tables.py` — pure dicts, no imports
- `utils/ttrpg/npc_registry.py` — pure dicts, no imports
- `utils/ttrpg/look_targets.py` — pure dicts, no imports
- `utils/ttrpg/quest_registry.py` — pure dicts, no imports
- `utils/ttrpg/pantheon.py` — pure dicts, no imports

### Logic files (have cross-imports, CANNOT be exec'd):
- `combat_engine.py`, `shop.py`, `character_manager.py`, `session_manager.py`
- `progression.py`, `dungeon.py`, `spine_dungeon.py`, `class_advancement.py`, `encounter_tables.py`
- All files under `utils/core/` and `utils/commands/`

## ⚠️ ABSOLUTE CRITICAL: Bulk Edit & Registry Safety

**NEVER use bulk edit tools (`multi_replace_file_content` or regex) on registry files without a POST-EDIT INTEGRITY AUDIT.**

Registry files (like `equipment_registry.py`) contain both large data dictionaries and critical helper functions (like `get_equipment`, `get_caravan_stock`). Bulk edits have a demonstrated risk of **Silent Deletion** — accidentally truncating the end of a file or overwriting mission-critical functions while modifying data entries. This has happened before and caused production outages.

### Mandatory Verification Steps for ALL Bulk Edits:
1.  **Functional Audit**: Immediately after any bulk edit, use `grep -n "def <function_name>"` to verify that all pre-existing helper functions still exist. For `equipment_registry.py`, always check for: `get_equipment`, `get_caravan_stock`.
2.  **Lexical Audit**: Ensure all backbone dictionaries (`WEAPONS`, `ARMOR`, `HEADGEAR`, `BOOTS`, `ACCESSORIES`, `CONSUMABLES`, `ALIASES`) have their opening AND closing braces intact. Run `grep -c "^}" path/to/file` and compare.
3.  **Syntax Check**: Always run `python3 -c "import ast; ast.parse(open('path/to/file').read())"` immediately after an edit.
4.  **No Truncation**: Never replace the entire content of a registry file with a truncated version. If you are unsure of the file's end, view it first with `tail -50` or `view_file`.
5.  **Count Verification**: For registry files, verify item counts haven't changed unexpectedly by exec'ing the file and printing `len(DICT_NAME)`.

**Failure to follow these steps is considered a critical system-breakage event.**

## Project Structure

```
├── Kaiacord.py                  # Bot entry point — DO NOT run or modify without full context
├── AGENTS.md                    # This file
├── utils/
│   ├── commands/                # Discord command dispatch
│   │   ├── registry.py                # Central command dispatcher
│   │   ├── art_handler.py             # !art fractal flame generation
│   │   ├── fishing_handler.py         # Fishing commands
│   │   ├── rpg_handler.py             # RPG command router
│   │   ├── dream_handler.py           # !dream commands
│   │   ├── help_handler.py            # !help
│   │   ├── memory_handler.py          # !memory commands
│   │   ├── selfmodel_handler.py       # !selfmodel regeneration
│   │   ├── social_handler.py          # Bluesky/X social posting
│   │   ├── system_handler.py          # System/admin commands
│   │   └── sysmon_handler.py          # !sysmon monitoring
│   ├── ttrpg/                   # Game logic + RPG command handlers
│   │   ├── monster_registry.py        # 335 monster stat blocks
│   │   ├── equipment_registry.py      # 433 items across 7 tiers
│   │   ├── combat_engine.py           # Combat resolution (DEF soft-cap + global cap)
│   │   ├── class_advancement.py       # 10 advanced classes, proc logic
│   │   ├── dungeon.py                 # Procedural dungeon generation (overworld)
│   │   ├── spine_dungeon.py           # 77-floor Spine of the World mega-dungeon
│   │   ├── build_spine_layouts.py     # Offline build script for spine_layouts.json
│   │   ├── encounter_tables.py        # Floor/zone encounter pools
│   │   ├── character_manager.py       # Per-user character sheet I/O (async, locked)
│   │   ├── session_manager.py         # Session state persistence
│   │   ├── progression.py             # XP, leveling, stat growth
│   │   ├── shop.py                    # Buy/sell logic across 3 shops
│   │   ├── housing.py, farming.py, pets.py, alchemy.py, furniture.py
│   │   ├── quest_registry.py          # 9 quests (L1–L15)
│   │   ├── npc_registry.py            # NPC definitions
│   │   ├── calendar.py                # Seasons, weather, holidays (13 special days)
│   │   ├── loot_tables.py             # Drop tables by tier
│   │   ├── dice_engine.py             # Dice rolling
│   │   ├── world.py, world_state.py   # World map and state
│   │   ├── rpg_combat_handler.py      # Combat/dungeon/duel command handler
│   │   ├── rpg_core_handler.py        # Movement, calendar, scout, pray, misc
│   │   ├── rpg_housing_handler.py     # Housing/farming/pets command handler
│   │   ├── rpg_shop_handler.py        # Buy/sell/bulk-sell command handler
│   │   ├── rpg_social_handler.py      # NPC talk, quests, deliver
│   │   ├── rpg_views.py               # Discord UI views & button factories
│   │   └── rpg_prompt_builder.py      # LLM narration prompt construction
│   ├── core/                    # Kaia cognitive pipeline
│   │   ├── message_processor.py       # Main intelligence pipeline (~1900 lines)
│   │   ├── background_tasks.py        # Afterthoughts, dawn task, presence loops
│   │   ├── kaia_dream.py              # Dream engine, belief extraction, identity stream
│   │   ├── kaia_art.py                # Fractal flame renderer (CPU-only, NumPy/SciPy)
│   │   ├── kaia_presence.py           # Discord presence & mood-aware status text
│   │   ├── kaia_reactions.py          # Non-verbal emoji reaction system
│   │   ├── kaia_mood.py               # Persistent emotional state (valence/arousal/energy)
│   │   ├── kaia_monologue.py          # Background inner thought stream
│   │   ├── kaia_proactive.py          # Autonomous conversation initiation (7-source engine)
│   │   ├── memory_anchors.py          # Cross-session episodic memory callbacks
│   │   ├── relationship_manager.py    # Per-user relationship event store
│   │   ├── kaia_intelligence.py       # Context weaving, intent parsing
│   │   ├── curiosity_scanner.py       # Unresolved mention detection
│   │   ├── hallucination_detector.py  # Post-generation fabrication guard
│   │   ├── kaia_rag.py                # RAG system coordinator
│   │   ├── kaia_rag_indexer.py        # Document indexing and embedding
│   │   ├── kaia_rag_query.py          # RAG query execution
│   │   ├── kaia_rag_retriever.py      # BM25/hybrid retrieval
│   │   ├── kaia_rag_persistence.py    # RAG logging, persistence, pre-warming
│   │   ├── context_optimizer.py       # Context window management
│   │   ├── response_filter.py         # Bot-speak cleanup (BotSpeakFilter)
│   │   └── sanitizer.py               # Output sanitization
│   ├── social/                  # Social & Forum integrations
│   │   ├── kaia_forum.py              # P99 forum client & crawler
│   │   ├── forum_tasks.py             # Periodic forum scheduler tasks
│   │   ├── kaia_social_responder.py   # Responder dispatch for Bluesky & Twitter
│   │   ├── social_response_generator.py # LLM response generation for social platforms
│   │   └── kaia_identities.py         # Identity linking database (Discord ID <-> Forum UID)
│   └── infrastructure/          # Bot infrastructure
│       ├── system/
│       │   ├── bot_state.py           # Global state, relationships, mood persistence
│       │   ├── app_context.py         # Dependency injection hub
│       │   ├── yaml_config.py         # Configuration loader
│       │   ├── messaging.py           # Discord message utilities
│       │   └── rate_limiter.py        # Command rate limiting
│       ├── logging/
│       │   └── kaia_logger.py         # Structured logging
│       ├── gpu/
│       │   ├── gpu_memory_manager.py  # GPU task queue with priority scheduling
│       │   └── gpu_manager.py         # Ollama GPU options
│       └── monitoring/
│           ├── btop_dashboard_v2.py   # Live curses monitoring dashboard
│           ├── async_task_registry.py # Background task lifecycle tracking
│           └── watchdog.py            # Event loop health monitor
├── docs/
│   ├── ttrpg/                         # TTRPG design documents
│   │   ├── aethelgard_system.md       # System spec — READ BEFORE MODIFYING COMBAT
│   │   ├── aethelgard_lore_bible.md   # World-building canon
│   │   └── ttrpg_report.md            # TTRPG-specific audit
│   └── reports/                       # Phase reports, roadmaps, process docs
│       ├── master_report.md           # System status, metrics, and roadmap (Phases 55+)
│       ├── audit_report.md            # Unified production, log, and persona audits
│       ├── history.md                 # Consolidated development history (Phases 1–54)
│       └── evolution_proposals.md     # Pending proposals currently under discussion
├── config/                      # Bot configuration (YAML)
├── memory/                      # Runtime data — NEVER COMMIT
│   ├── ttrpg/characters/        # Per-user JSON character sheets
│   ├── relationships/           # Per-user relationship event files
│   ├── art/                     # Generated fractal flame PNGs + JSON sidecars
│   ├── beliefs.json             # Kaia's revisable belief store (50-cap)
│   ├── bot_state.json           # Interaction tracking, familiarity, mood floats
│   ├── identity_stream.md       # Rolling identity evolution journal (3000-char cap)
│   ├── growth_log.jsonl         # Append-only growth event ledger
│   ├── forum_moderation_log.jsonl # Append-only moderation action log for RLHF/fine-tuning
│   ├── proactive_topics.json    # Proactive initiation diversity log (14-day decay)
│   ├── memory_anchors.json      # Episodic memory anchors (50-cap, weight decay)
│   └── rag_storage/             # RAG indices, continuity file, BM25 caches
└── knowledge_base/              # RAG knowledge files (books, documents, user logs)
```

## Coding Standards

### Python Style
- Python 3.14+ features are fine (`match`, `|` union types, etc.)
- Use `secrets` module for security-sensitive randomness (combat rolls, loot drops, token generation). `random` is acceptable for non-security contexts (dream file shuffling, world event variety, layout scrambling in build scripts).
- Async functions use `asyncio.to_thread()` for file I/O (see `character_manager.py` pattern)
- Atomic file writes: write to `.tmp`, then `os.replace()` (see `session_manager.py`, `relationship_manager.py`, `bot_state.py`)
- All long-running CPU work (fractal rendering, etc.) must be wrapped in `asyncio.to_thread()` to avoid blocking the event loop

### Registry Files (equipment_registry.py, monster_registry.py)
- Items are Python dicts, not JSON
- **Item properties MUST be at 8-space indent** inside their sub-dict. Watch for `"droppable_only": True` at 4-space indent — this is a known recurring bug that silently corrupts data by associating the property with the wrong parent dict
- Every monster key used in `ENCOUNTER_TABLES` MUST have a matching entry in `MONSTERS`
- Shop stock lists (`HEMLOCK_STOCK_*`, `PELLS_STOCK_*`) are manually maintained — new buyable items need both the item dict AND the stock list updated
- Equipment stat budgets by tier: See `docs/ttrpg/ttrpg_report.md` for current balance targets. Do not add items that exceed tier budgets without updating the documentation first
- Current counts: **339 monsters** (37 boss-tier), **447 active unique equipment items** across 7 tiers

### Kaia Cognitive Pipeline
- **All 26 behavioral features** (tone mirroring, time-of-day, conversational fatigue, relationship stages, mood vector, monologue, memory anchors, conversational stance, etc.) are lightweight system prompt injections in `message_processor.py`. They do NOT call the LLM — they're pure Python heuristics.
- **Every behavioral injection is wrapped in `try/except Exception: pass`** to ensure non-critical features never crash the main response path. This is mandatory for all new injections.
- **Dream reflections, identity stream, and self-model auto-regen** all pass through `_sanitize_repetitive_starts()` to prevent linguistic drift loops.
- **Relationship events** are stored per-user in `memory/relationships/` with atomic writes and a 100-event cap.
- **Beliefs** are stored in `memory/beliefs.json` with a 50-belief cap, atomic writes, and revision tracking.
- **Memory anchors** are stored in `memory/memory_anchors.json` with a 50-anchor cap, weight decay, and automatic pruning below 0.1 weight.
- **Proactive initiation** is rate-limited to 2 messages/day with a 6-hour minimum gap between messages. Topic diversity is tracked in `memory/proactive_topics.json`.

### Project 1999 Forum & Social Operations
- **Moderation Draft Queue**: All auto-generated posts and tech support replies must be routed to `#kaia-opolis` as drafts with interactive Accept/Reject views first before being submitted to the forum.
- **Zero-Hallucination Support Policy**: Technical support replies must use strict BM25/hybrid RAG grounding from verified Project 1999 wiki documents (`knowledge_base/wiki/`) and synthesized troubleshooting cheatsheets (`knowledge_base/troubleshooting/`). Hallucination checks must run on the final response, and the mandatory support disclaimer footer must be appended: `"Disclaimer: I am an AI agent and might make mistakes and hopefully a human comes by soon to help you if I was unable to"`.
- **Capped Scraping & Caching**: Scrapers for off-topic and technical discussion forums must run once per 6 hours, drafting a maximum of 2-3 posts per run. Deep history profile scrapes are limited to 20 post pages and 10 thread pages, cached for 4 hours (history) and 1 hour (profile data) to minimize network operations.

### LLM Call Paths

Kaia utilizes multiple distinct LLM call paths depending on the context. Do not assume all generations pass through the same pipeline.

| Call Path | Entry Point | Context / Pipeline | Key Features / Safety Layers |
|---|---|---|---|
| **Discord Chat** | `MessageProcessor.process()` | Full `MessageContext` | 26-feature cognitive pipeline, RAG/memory retrieval, intent classification, 10-layer post-generation safety pipeline (hallucination detection, bot-speak filter, etc.) |
| **Forum Auto-Post** | `background_tasks.py` -> `_make_forum_auto_post_task()` | System + User message format | Stripped-down LLM call (`ollama_client.chat`), bypasses `MessageProcessor` and cognitive pipeline. Uses `BotSpeakFilter.harden()` post-generation. |
| **Forum Technical Support** | `background_tasks.py` -> `_make_forum_support_task()` | System + User message format | Stripped-down LLM call, grounded via BM25/hybrid RAG, automatic support disclaimer footer append, bypasses `MessageProcessor`. |
| **Social Media Responder** | `kaia_social_responder.py` | Direct Ollama call | Bypasses `MessageProcessor`. Specialized social response generation context. |
| **Dream Engine** | `kaia_dream.py` | Persona + Dream prompt | Bypasses `MessageProcessor`. Dream summary generation and belief extraction. |
| **Inner Monologue** | `kaia_monologue.py` | Persona + Monologue prompt | Bypasses `MessageProcessor`. Background inner thought generation. |

### Common Agent Mistakes

- **Modifying the Wrong Pipeline**: Do not modify `message_processor.py` for behaviors intended to affect background or automated tasks (forums, social media, dreams) that bypass `MessageProcessor` entirely. Always trace the actual `ollama_client` call path.
- **Prompt Instruction Stacking**: Avoid solving generation issues by endlessly adding prompt instructions (such as contradictory negative constraints or style rules) on top of each other. This results in instruction overload, leading the LLM to leak/echo instructions in its output. Instead, refine the prompt architecture and split system instructions from user inputs.
- **Ignoring User Feedback/Corrections**: If the user states a fix did not work, do not blame the bot not restarting or double down on assumptions. Stop and re-verify the active call path and check if the code you modified is actually imported and executed in that path.
- **Scope Creep & Instruction Disobedience**: If a prompt states that your output is updating a specific file (e.g. `docs/reports/audit_report.md`), do NOT modify any other files in the codebase (such as logic, registries, or configs). Document findings and proposed fixes inside the report as requested, but do not apply them to the codebase unless the user explicitly requests you to execute the fix.


### Logging & Monitor Standards
- **Live Log Elevation**: Core cognitive actions (monologue generation, dream summaries, belief shifts, episodic anchor formations), scraper operations, and emotional vector changes must use `log_info` or `log_warning` to ensure visibility in the live curses dashboard panel.
- **Unified Stats Tracking**: All generated forum drafts, approvals, and rejections must be persisted in `memory/stats.json` and thread-safely registered in `StatsTracker` to populate the middle/right dashboard panes.

### Architecture Rules
- **Python handles all deterministic game state/math.** Never delegate combat resolution, stat calculations, or inventory management to the LLM.
- **Kaia (the LLM) handles narration only.** She receives combat results and narrates them. The LLM generates flavor text, not game state.
- **Per-user JSON character sheets** live in `memory/ttrpg/characters/`. Always use `character_manager.load()` / `character_manager.save()` — never read/write character files directly. Character manager uses per-user async locks to prevent race conditions.
- The defense soft-cap in `combat_engine.py` is intentional design: `min(10, raw) + max(0, raw-10)//2`. Do not remove or bypass it.
- The global DEF cap (`level * 1.5 + 12`) is intentional design. Do not remove or bypass it.
- The GPU (RTX 3060, 12GB) is fully reserved by Ollama. Do NOT use CUDA, Numba, PyCUDA, or any GPU-backed library for non-LLM work. CPU + NumPy only for rendering.
- All Ollama calls must go through `gpu_memory_manager` with appropriate `GPUTaskPriority` to prevent VRAM contention.

## Do NOT Touch

- `.env` — Contains bot tokens and API keys
- `memory/` — Runtime user data, never commit to version control
- `Kaiacord.py` — Main bot file, requires full context to modify safely. Do not modify without reading the entire file first.
- `knowledge_base/kaia_persona.md` — Kaia's personality definition. Changes here alter her entire behavioral baseline.
- `config/` — Bot configuration files. Changes require understanding downstream effects across all subsystems.

## Commit Conventions

- Commit messages: `[area] Brief description` (e.g., `[ttrpg] Add missing owlbear stat block`)
- Areas: `ttrpg`, `fishing`, `combat`, `housing`, `alchemy`, `core`, `docs`, `config`, `kaia`, `art`, `infra`, `social`
- One logical change per commit — don't mix balance changes with bug fixes

## Current System Status

See `docs/reports/audit_report.md` for the latest production audit and `docs/ttrpg/ttrpg_report.md` for the TTRPG-specific audit.

**System health: A-tier. All subsystems operational. Both the TTRPG and Kaia cognitive pipeline are production-stable.**

Key facts:
- 339 monsters (37 boss-tier), 447 active unique equipment items across 7 tiers
- 12 quests covering L1–L15 (all progression gaps resolved)
- 10 advanced classes with unique procs and passives
- 77-floor Spine of the World mega-dungeon with Resonance Lift checkpoints
- 2 shop locations (Hemlock's, Caravan)
- Full cognitive pipeline (26 features): emotional arc, monologue, proactive initiation, relationship stages, dreams, beliefs, memory anchors, conversational stance, tone mirroring
- Calendar with 13 special days, 4 seasons, deterministic weather — all buffs wired
- Fractal flame art system (CPU-only, NumPy/SciPy, 20 variation functions, 10 palettes, adaptive DE)
- Project 1999 Forum Integration: automated 6h scraping loops, post-moderation review queue, profile caching, and zero-hallucination tech support RAG verification
