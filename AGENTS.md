# AGENTS.md

> Instructions for AI coding agents working on this repository.

## Project Overview

**Kaiacord** is a Discord bot built with `discord.py 2.6.4` and Python 3.11+. It features:

- **Kaia** — An AI persona powered by Ollama (local LLM) with RAG retrieval via LlamaIndex
- **Aethelgard TTRPG** — A full turn-based RPG system (combat, classes, equipment, dungeons, housing, farming, pets, alchemy)
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

## Project Structure

```
├── Kaiacord.py              # Bot entry point — DO NOT run or modify without context
├── utils/
│   ├── commands/            # Discord command dispatch
│   │   ├── rpg_handler.py   # Main TTRPG command router (~2000 lines)
│   │   └── fishing_handler.py
│   ├── ttrpg/               # Game logic (pure Python)
│   │   ├── monster_registry.py    # Monster stat blocks + encounter tables
│   │   ├── equipment_registry.py  # All gear definitions (weapons/armor/etc)
│   │   ├── combat_engine.py       # Combat resolution
│   │   ├── class_advancement.py   # Advanced class system
│   │   ├── dungeon.py             # Procedural dungeon generation
│   │   ├── shop.py, housing.py, farming.py, pets.py, alchemy.py
│   │   ├── calendar.py            # Seasons, weather, holidays
│   │   ├── loot_tables.py         # Drop tables by tier
│   │   └── dice_engine.py         # Dice rolling
│   └── core/                # Bot infrastructure, RAG, background tasks
├── docs/ttrpg/              # Design documents
│   ├── aethelgard_system.md       # System spec — READ BEFORE MODIFYING COMBAT
│   ├── aethelgard_lore_bible.md   # World-building canon
│   └── Aethelgard_TTRPG_Review.md # Balance audit & known issues
├── config/                  # Bot configuration
├── memory/ttrpg/            # Runtime data (character sheets, sessions) — NEVER COMMIT
└── knowledge_base/          # RAG knowledge files
```

## Coding Standards

### Python Style
- Python 3.11+ features are fine (`match`, `|` union types, etc.)
- Use `secrets` module for randomness, never `random` (security requirement)
- Async functions use `asyncio.to_thread()` for file I/O (see `character_manager.py` pattern)
- Atomic file writes: write to `.tmp`, then `os.replace()` (see `session_manager.py`)

### Registry Files (equipment_registry.py, monster_registry.py)
- Items are Python dicts, not JSON
- **Item properties MUST be at 8-space indent** inside their sub-dict. Watch for `"droppable_only": True` at 4-space indent — this is a known recurring bug that silently corrupts data
- Every monster key used in `ENCOUNTER_TABLES` MUST have a matching entry in `MONSTERS`
- Shop stock lists (`HEMLOCK_STOCK_*`) are manually maintained — new buyable items need both the item dict AND the stock list updated
- Equipment stat budgets by tier:

| Tier | Weapon ATK+DMG | Armor DEF | Accessory ATK+DEF |
|------|---------------|-----------|-------------------|
| 1    | 2-4           | 1-2       | 1-2               |
| 2    | 4-6           | 2-4       | 2-3               |
| 3    | 7-9           | 4-5       | 3-4               |
| 4    | 10-13         | 5-7       | 4-5               |
| 5    | 14-18         | 7-9       | 5-6               |

### Architecture Rules
- **Python handles all deterministic game state/math.** Never delegate combat resolution, stat calculations, or inventory management to the LLM.
- **Kaia (the LLM) handles narration only.** She receives combat results and narrates them.
- **Per-user JSON character sheets** live in `memory/ttrpg/characters/`. Always use `character_manager.load()` / `character_manager.save()` — never read/write files directly.
- The defense soft-cap in `combat_engine.py` is intentional design. Do not remove or bypass it.

## Do NOT Touch

- `.env` — Contains bot tokens and API keys
- `memory/` — Runtime user data, never commit
- `Kaiacord.py` — Main bot file, requires full context to modify safely
- `knowledge_base/kaia_persona.md` — Kaia's personality definition
- `config/` — Bot configuration files

## Commit Conventions

- Commit messages: `[area] Brief description` (e.g., `[ttrpg] Add missing owlbear stat block`)
- Areas: `ttrpg`, `fishing`, `combat`, `housing`, `alchemy`, `core`, `docs`, `config`
- One logical change per commit — don't mix balance changes with bug fixes

## Known Issues & Open Work

See `docs/ttrpg/Aethelgard_TTRPG_Review.md` for the full audit. Priority items:

- Combat is too easy at high levels due to uncapped DEF stacking from pets/class/weather
- `balance_model.py` is completely stale — uses wrong formulas, wrong data
- Only 2 alchemy recipes exist despite full crafting infrastructure
- Calendar special day effects (`encounter_mod`, `shop_special`, `shrine_gift`) are defined but not wired to handlers
- Furniture bonuses (`home_brewing`, `daily_training`, `home_pray`, `home_scout`) need integration
