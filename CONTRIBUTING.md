# Contributing to Kaiacord

Thanks for your interest in contributing. This guide covers how to submit changes that will actually get merged.

## Before You Start

1. **Read `AGENTS.md`** — it covers runtime constraints, project structure, and coding standards.
2. **Read the relevant design doc** before modifying any system:
   - Combat/classes/equipment → `docs/ttrpg/aethelgard_system.md`
   - Lore, NPCs, world → `docs/ttrpg/aethelgard_lore_bible.md`
   - Known bugs & balance issues → `docs/ttrpg/Aethelgard_TTRPG_Review.md`
3. **Check open issues** — if someone's already working on it, coordinate.

## ⚠️ You Cannot Run This Project Locally

Kaiacord is a live Discord bot. Running it requires bot tokens, an Ollama instance, and a configured environment. **Do not attempt to start the bot** as part of your contribution workflow.

### What You Can Do

```bash
# Syntax validation (no imports, no hanging)
python3 -c "import ast; ast.parse(open('path/to/file.py').read())"

# Validate data-only files (monster_registry, equipment_registry, pets, farming, furniture)
timeout 10 python3 -c "exec(open('utils/ttrpg/monster_registry.py').read()); print(len(MONSTERS))"

# Grep for broken references
grep -rn "some_key" utils/ttrpg/
```

### What You Cannot Do

```bash
# ❌ These all hang forever due to Discord client initialization
python3 -c "from utils.ttrpg.combat_engine import ..."
python3 -m pytest
python3 Kaiacord.py
```

## How to Contribute

### 1. Fork & Branch

```bash
git checkout -b your-branch-name
```

Branch naming: `fix/description`, `feat/description`, or `balance/description`.

### 2. Make Your Changes

- **One logical change per PR.** Don't mix a bug fix with a balance pass.
- Follow the coding standards in `AGENTS.md`.
- Use `secrets` for randomness, never `random`.
- Use atomic writes (`write .tmp` → `os.replace()`) for any file I/O.

### 3. Validate

At minimum, run syntax checks on every file you touched:

```bash
python3 -c "import ast; ast.parse(open('utils/ttrpg/your_file.py').read())"
```

If you modified a data registry, verify referential integrity:

```bash
# Check that all encounter table keys resolve to real monsters
timeout 10 python3 -c "
exec(open('utils/ttrpg/monster_registry.py').read())
missing = [k for loc, table in ENCOUNTER_TABLES.items() for k, w in table if k not in MONSTERS]
print('BROKEN REFS:', missing) if missing else print('OK')
"
```

### 4. Commit

```
[area] Brief description

# Examples:
[ttrpg] Add owlbear stat block
[combat] Cap pet DEF bonus in soft-cap calculation
[alchemy] Add elixir and hi-potion recipes
[docs] Update balance review with T5 audit
```

Areas: `ttrpg`, `combat`, `fishing`, `housing`, `alchemy`, `core`, `docs`, `config`, `social`

### 5. Open a PR

- Describe **what** you changed and **why**.
- If it's a balance change, include the before/after numbers.
- If it's a bug fix, describe how to reproduce the bug.

## What We're Looking For

Check `docs/ttrpg/Aethelgard_TTRPG_Review.md` for the full list. Good first contributions:

### 🟢 Easy Picks
- Add missing alchemy recipes (only 2 exist, infrastructure supports many more)
- Add monster stat blocks for gaps in tier coverage
- Fix data consistency issues in registries
- Improve item descriptions and flavor text

### 🟡 Medium
- Wire calendar special day effects (`encounter_mod`, `shop_special`, `shrine_gift`) to handlers
- Integrate furniture bonuses (`home_brewing`, `daily_training`, `home_pray`) into `rpg_handler.py`
- Expand seasonal monster pools

### 🔴 Hard (Coordinate First)
- Combat engine balance changes (defense soft-cap, lifesteal caps)
- `rpg_handler.py` modifications (2000+ line file, high blast radius)
- New game systems (require design doc approval first)

## Do NOT Touch

- `.env` — Secrets. Not committed. Not your problem.
- `memory/` — Live player data. Never committed.
- `Kaiacord.py` — Bot entry point. Requires full context to modify safely.
- `knowledge_base/kaia_persona.md` — Kaia's personality. Off limits.
- `config/` — Bot configuration. Coordinate with maintainer.

## Code Review

All PRs are reviewed by a human before merge. Common rejection reasons:

1. **Broke referential integrity** — added an item to a loot table but not the registry
2. **Wrong indentation** — `droppable_only` at 4-space instead of 8-space indent (see `AGENTS.md`)
3. **Balance violation** — item stats exceed the tier budget table
4. **Scope creep** — PR does three unrelated things
5. **No validation** — didn't even syntax-check the files

## Questions?

Open an issue with the `question` label.
