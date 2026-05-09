# AGENTS.md

> Instructions for AI coding agents working on this repository.
> Last updated: May 7, 2026

## Project Overview

**Kaiacord** is a Discord bot built with `discord.py 2.6.4` and Python 3.14+. It features:

- **Kaia** — An AI persona powered by Ollama (local LLM) with RAG retrieval via LlamaIndex, featuring a full cognitive pipeline (presence, mood, afterthoughts, relationship tracking, belief formation, dream reflections)
- **Aethelgard TTRPG** — A full turn-based RPG system (combat, classes, equipment, dungeons, housing, farming, pets, alchemy) with a 77-floor mega-dungeon
- **Fishing minigame** — Rod-based fishing economy
- **Social integrations** — Bluesky/X posting

Tech stack: `discord.py`, `ollama`, `llama-index`, `fastapi`, `aiohttp`, `PyYAML`, `python-dotenv`.

## ⚠️ Critical: Runtime Constraints

**This is a live Discord bot. You CANNOT import or run project modules directly.**

The import chain touches Discord client initialization, async event loops, and bot token validation. Any attempt to `import` from `utils/` will **hang indefinitely**.

### What works for validation:
```bash
# Syntax check (fast, no imports)
python3 -c "import ast; ast.parse(open('utils/ttrpg/monster_registry.py').read())"

# Data-only files can be exec'd in isolation (no cross-imports)
python3 -c "exec(open('utils/ttrpg/monster_registry.py').read()); print(len(MONSTERS))"

# Always use timeout as a safety net
timeout 10 python3 -c "..."
```

### What does NOT work:
```bash
# ❌ HANGS FOREVER — do not attempt
python3 -c "from utils.ttrpg.combat_engine import ..."
python3 -m pytest
python3 Kaiacord.py
```

### Data-only files (safe to `exec()` in isolation):
- `utils/ttrpg/monster_registry.py` — pure dicts
- `utils/ttrpg/equipment_registry.py` — pure dicts
- `utils/ttrpg/pets.py`, `furniture.py`, `farming.py` — pure dicts + stdlib only
- `utils/ttrpg/calendar.py` — pure dicts + stdlib `datetime`/`hashlib`

### Logic files (have cross-imports, CANNOT be exec'd):
- `combat_engine.py`, `shop.py`, `character_manager.py`, `session_manager.py`
- `progression.py`, `dungeon.py`, `class_advancement.py`, `encounter_tables.py`

## ⚠️ ABSOLUTE CRITICAL: Bulk Edit & Registry Safety

**NEVER use bulk edit tools (`multi_replace_file_content` or regex) on registry files without a POST-EDIT INTEGRITY AUDIT.**

Registry files (like `equipment_registry.py`) contain both large data dictionaries and critical helper functions (like `get_equipment`). Bulk edits have a demonstrated risk of "Silent Deletion"—accidentally truncating the end of a file or overwriting mission-critical functions while modifying data.

### Mandatory Verification Steps for ALL Bulk Edits:
1.  **Functional Audit**: Immediately after any bulk edit, use `grep -n "def <function_name>"` to verify that all pre-existing helper functions (e.g., `get_equipment`, `get_caravan_stock`) still exist.
2.  **Lexical Audit**: Ensure all backbone dictionaries (`WEAPONS`, `ARMOR`, `HEADGEAR`, `BOOTS`, `ACCESSORIES`, `CONSUMABLES`, `ALIASES`) have their opening AND closing braces intact.
3.  **Syntax Check**: Always run `python3 -c "import ast; ast.parse(open('path/to/file').read())"` immediately after an edit.
4.  **No Truncation**: Never replace the entire content of a registry file with a truncated version. If you are unsure of the file's end, VET it first with `tail` or `view_file`.

**Failure to follow these steps is considered a critical system-breakage event.**

## Project Structure

```
├── Kaiacord.py              # Bot entry point — DO NOT run or modify without context
├── utils/
│   ├── commands/            # Discord command dispatch
│   │   ├── rpg_combat_handler.py   # Combat, dungeon, duel commands
│   │   ├── rpg_core_handler.py     # Movement, calendar, scout, pray, misc
│   │   ├── rpg_housing_handler.py  # Housing, farming, pets, furniture
│   │   ├── rpg_shop_handler.py     # Buy/sell/bulk-sell across 3 shops
│   │   ├── rpg_social_handler.py   # NPC talk, quests, deliver
│   │   ├── rpg_views.py            # Discord UI views & button factories
│   │   └── fishing_handler.py
│   ├── ttrpg/               # Game logic (pure Python)
│   │   ├── monster_registry.py    # 335 monster stat blocks + encounter tables
│   │   ├── equipment_registry.py  # 383 items across 7 tiers
│   │   ├── combat_engine.py       # Combat resolution (DEF soft-cap + global cap)
│   │   ├── class_advancement.py   # 10 advanced classes, proc logic
│   │   ├── dungeon.py             # Procedural dungeon generation (overworld)
│   │   ├── spine_dungeon.py       # 77-floor Spine of the World mega-dungeon
│   │   ├── build_spine_layouts.py # Build script for spine_layouts.json (offline only)
│   │   ├── shop.py, housing.py, farming.py, pets.py, alchemy.py
│   │   ├── calendar.py            # Seasons, weather, holidays (13 special days)
│   │   ├── loot_tables.py         # Drop tables by tier
│   │   └── dice_engine.py         # Dice rolling
│   ├── core/                # Kaia cognitive pipeline
│   │   ├── message_processor.py   # Main message pipeline (~1750 lines)
│   │   ├── background_tasks.py    # Afterthoughts, dawn task, presence loops
│   │   ├── kaia_dream.py          # Dream engine, belief extraction, identity stream
│   │   ├── kaia_presence.py       # Discord presence & mood-aware status text
│   │   ├── kaia_reactions.py      # Non-verbal emoji reaction system
│   │   ├── kaia_rag_persistence.py # RAG logging, persistence, pre-warming
│   │   ├── kaia_rag_retriever.py  # BM25/hybrid retrieval
│   │   ├── relationship_manager.py # Per-user relationship event store
│   │   ├── kaia_intelligence.py   # Context weaving, intent parsing
│   │   ├── kaia_mood.py           # Persistent emotional state (valence/arousal/energy)
│   │   ├── kaia_monologue.py      # Background inner thought stream
│   │   ├── kaia_proactive.py      # Autonomous conversation initiation
│   │   └── memory_anchors.py      # Cross-session episodic memory callbacks
│   └── infrastructure/      # Bot infrastructure
│       ├── system/           # bot_state.py, yaml_config.py, messaging.py
│       ├── logging/          # kaia_logger.py
│       ├── gpu/              # GPU memory management for Ollama
│       └── monitoring/       # Async task registry, sysmon
├── docs/
│   ├── ttrpg/                     # TTRPG design documents
│   │   ├── aethelgard_system.md   # System spec — READ BEFORE MODIFYING COMBAT
│   │   ├── aethelgard_lore_bible.md # World-building canon
│   │   └── CLAUDE_REPORT.md       # TTRPG-specific audit (Phase 13, April 2026)
│   └── reports/                   # Phase reports, roadmaps, process docs
├── config/                  # Bot configuration
├── memory/                  # Runtime data — NEVER COMMIT
│   ├── ttrpg/characters/    # Per-user JSON character sheets
│   ├── relationships/       # Per-user relationship event files
│   ├── beliefs.json         # Kaia's revisable belief store
│   ├── bot_state.json       # Interaction tracking, familiarity data
│   ├── identity_stream.md   # Rolling identity evolution journal
│   ├── growth_log.jsonl     # Append-only growth event ledger
│   └── rag_storage/         # RAG indices, continuity file
└── knowledge_base/          # RAG knowledge files (books, documents, user logs)
```

## Coding Standards

### Python Style
- Python 3.14+ features are fine (`match`, `|` union types, etc.)
- Use `secrets` module for security-sensitive randomness (combat rolls, loot drops, token generation). `random` is acceptable for non-security contexts (dream file shuffling, world event variety, layout scrambling in build scripts).
- Async functions use `asyncio.to_thread()` for file I/O (see `character_manager.py` pattern)
- Atomic file writes: write to `.tmp`, then `os.replace()` (see `session_manager.py`, `relationship_manager.py`)

### Registry Files (equipment_registry.py, monster_registry.py)
- Items are Python dicts, not JSON
- **Item properties MUST be at 8-space indent** inside their sub-dict. Watch for `"droppable_only": True` at 4-space indent — this is a known recurring bug that silently corrupts data
- Every monster key used in `ENCOUNTER_TABLES` MUST have a matching entry in `MONSTERS`
- Shop stock lists (`HEMLOCK_STOCK_*`, `PELLS_STOCK_*`) are manually maintained — new buyable items need both the item dict AND the stock list updated
- Equipment stat budgets by tier: See `docs/ttrpg/CLAUDE_REPORT.md` for current balance targets and stat budgets by tier. Do not add items that exceed these budgets without updating the documentation first.

### Kaia Cognitive Pipeline
- **All 26 behavioral features** (tone mirroring, time-of-day, conversational fatigue, relationship stages, mood vector, monologue) are lightweight system prompt injections in `message_processor.py`. They do NOT call the LLM — they're pure Python heuristics.
- **Every behavioral injection is wrapped in `try/except Exception: pass`** to ensure non-critical features never crash the main response path.
- **Dream reflections, identity stream, and self-model auto-regen** all pass through `_sanitize_repetitive_starts()` to prevent linguistic drift loops.
- **Relationship events** are stored per-user in `memory/relationships/` with atomic writes and a 100-event cap.
- **Beliefs** are stored in `memory/beliefs.json` with a 50-belief cap, atomic writes, and revision tracking.

### Architecture Rules
- **Python handles all deterministic game state/math.** Never delegate combat resolution, stat calculations, or inventory management to the LLM.
- **Kaia (the LLM) handles narration only.** She receives combat results and narrates them.
- **Per-user JSON character sheets** live in `memory/ttrpg/characters/`. Always use `character_manager.load()` / `character_manager.save()` — never read/write files directly.
- The defense soft-cap in `combat_engine.py` is intentional design. Do not remove or bypass it.
- The global DEF cap (`level * 1.5 + 12`) is intentional design. Do not remove or bypass it.

## Do NOT Touch

- `.env` — Contains bot tokens and API keys
- `memory/` — Runtime user data, never commit
- `Kaiacord.py` — Main bot file, requires full context to modify safely
- `knowledge_base/kaia_persona.md` — Kaia's personality definition
- `config/` — Bot configuration files

## Commit Conventions

- Commit messages: `[area] Brief description` (e.g., `[ttrpg] Add missing owlbear stat block`)
- Areas: `ttrpg`, `fishing`, `combat`, `housing`, `alchemy`, `core`, `docs`, `config`, `kaia`
- One logical change per commit — don't mix balance changes with bug fixes

## Current System Status

See `docs/reports/Claude_Report.md` for the latest production audit and `docs/ttrpg/CLAUDE_REPORT.md` for the TTRPG-specific audit.

**System health: A-tier. All subsystems operational. Both the TTRPG and Kaia cognitive pipeline are production-stable.**

Key facts:
- 335 monsters (27 boss-tier), 383 equipment items across 7 tiers
- 9 quests covering L1–L15 (thin at L8–L10)
- 10 advanced classes with unique procs and passives
- 77-floor Spine of the World mega-dungeon with Resonance Lift checkpoints
- 3 shop locations (Hemlock's, Caravan, Pell's Depot)
- Full cognitive pipeline (26 features): emotional arc, monologue, proactive initiation, relationship stages, dreams, beliefs, tone mirroring
- Calendar with 13 special days, 4 seasons, deterministic weather — all buffs wired
