---
description: Environment rules, gotchas, and best practices for working in the Kaiacord project
---

# Kaiacord Agent Environment Guide

## Critical: Python Runtime is NOT Available for Imports

This project is a **live Discord bot** (Kaiacord). The module dependency chain includes `discord.py`, async event loops, and bot token validation. This means:

- **`import` of ANY module under `utils/` will hang indefinitely** because the import chain eventually touches Discord client initialization or async setup code.
- `python3 -c "from utils.ttrpg.monster_registry import MONSTERS"` → **HANGS FOREVER**
- `python3 -m py_compile utils/ttrpg/monster_registry.py` → **MAY HANG** (depends on terminal state)

### What DOES Work

1. **`ast.parse()`** — Parse files for syntax validation without executing them:
   ```bash
   python3 -c "import ast; ast.parse(open('utils/ttrpg/monster_registry.py').read()); print('OK')"
   ```

2. **`exec()` on isolated files** — Only if the file has no imports from `utils/`:
   ```bash
   python3 -c "exec(open('utils/ttrpg/monster_registry.py').read()); print(len(MONSTERS))"
   ```
   This works for pure-data files like registries. It will FAIL for files that `import` from other project modules.

3. **`grep` / `view_file` / static analysis** — Always works. Prefer this for validation.

### Rules for Agents

- **NEVER** set `WaitDurationSeconds` above 10 for Python commands in this project. If it hasn't finished in 10 seconds, it's hanging.
- **NEVER** try to `import` from `utils/` directly. Use `ast.parse()` or `exec()` on isolated files.
- **ALWAYS** use `timeout 10` prefix on Python commands as a safety net:
  ```bash
  timeout 10 python3 -c "..."
  ```
- If a command hangs, **terminate it immediately** and switch to static analysis (grep/view_file). Do not retry the same approach.

---

## Project Structure

```
Kaiacord/
├── Kaiacord.py          # Main bot entry point (DO NOT run)
├── utils/
│   ├── commands/        # Discord command handlers (rpg_handler.py, fishing_handler.py)
│   ├── ttrpg/           # TTRPG game logic (pure Python data + logic)
│   │   ├── monster_registry.py    # ~1750 lines, monster stat blocks + encounter tables
│   │   ├── equipment_registry.py  # ~1150 lines, all gear/consumable definitions
│   │   ├── combat_engine.py       # Combat resolution, defense soft-cap
│   │   ├── class_advancement.py   # Advanced class bonuses
│   │   ├── progression.py         # XP, leveling, daily hunts
│   │   ├── calendar.py            # Seasons, weather, special days
│   │   ├── dungeon.py             # Procedural dungeon generation
│   │   ├── shop.py                # Buy/sell logic
│   │   ├── housing.py             # Player housing tiers
│   │   ├── farming.py             # Crop growth system
│   │   ├── pets.py                # Pet registry and passives
│   │   ├── alchemy.py             # Brewing recipes
│   │   ├── loot_tables.py         # Drop tables by tier
│   │   └── dice_engine.py         # Dice rolling, stat checks
│   └── core/            # Bot infrastructure, RAG, background tasks
├── docs/ttrpg/          # Design docs, system spec, lore bible
├── memory/ttrpg/        # Runtime data (character sheets, sessions, housing)
├── config/              # Bot configuration
└── knowledge_base/      # RAG knowledge files
```

## Data Files vs Logic Files

**Data-heavy files** (can be `exec()`'d in isolation — they're mostly dicts):
- `monster_registry.py` — MONSTERS dict, ENCOUNTER_TABLES
- `equipment_registry.py` — WEAPONS, ARMOR, HEADGEAR, BOOTS, ACCESSORIES, CONSUMABLES
- `pets.py` — PET_REGISTRY
- `furniture.py` — FURNITURE dict
- `farming.py` — CROPS dict (has `from datetime import date` but that's stdlib, fine)
- `calendar.py` — SPECIAL_DAYS, WEATHER_TABLES, SEASONAL_MONSTERS

**Logic files** (import from other utils modules — CANNOT be exec'd alone):
- `combat_engine.py`, `shop.py`, `character_manager.py`, `session_manager.py`, `progression.py`, `dungeon.py`

## Registry File Conventions

Equipment and monster registries use Python dicts (not JSON). When editing:

- **Indentation matters.** Item properties must be at 8-space indent inside their dict. Watch for `"droppable_only": True` at wrong indent level — this is a known recurring bug.
- **Encounter tables reference monster keys.** Always verify new encounter table entries exist in the `MONSTERS` dict.
- **ALIASES dict** at the bottom of `equipment_registry.py` maps old/short names to canonical keys. Update when adding items.
- **Shop stock lists** (`HEMLOCK_STOCK_*`) are manually maintained — adding a new buyable item requires editing both the item dict AND the stock list.

## TTRPG Balance Guidelines

Refer to `docs/ttrpg/Aethelgard_TTRPG_Review.md` for the full audit. Key numbers:

| Tier | Weapon ATK+DMG Budget | Armor DEF Budget | Accessory ATK+DEF Budget |
|---|---|---|---|
| 1 | 2-4 | 1-2 | 1-2 |
| 2 | 4-6 | 2-4 | 2-3 |
| 3 | 7-9 | 4-5 | 3-4 |
| 4 | 10-13 | 5-7 | 4-5 |
| 5 | 14-18 | 7-9 | 5-6 |

## Version Control

The project uses Git. Always check `git diff` and `git log -5` before starting work to understand recent changes.
