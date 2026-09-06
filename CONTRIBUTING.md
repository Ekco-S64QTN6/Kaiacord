# Contributing to Kaiacord

Thanks for your interest in contributing. This guide covers how to submit changes that will actually get merged.

## Before You Start

1. **Read `AGENTS.md`** — it covers runtime constraints, project structure, and coding standards.
2. **Read the relevant design doc** before modifying any system:
   - Combat/classes/equipment → `docs/ttrpg/aethelgard_system.md`
   - Lore, NPCs, world → `docs/ttrpg/aethelgard_lore_bible.md`
   - Balance targets & TTRPG audit → `docs/ttrpg/ttrpg_report.md`
3. **Check open issues** — if someone's already working on it, coordinate.

## Running and Validating

You need Python 3.12+, a virtualenv with `requirements.txt` installed, and — for anything that
actually generates text — a running Ollama. You do **not** need a Discord token to validate most
changes.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### What to run

```bash
# Full suite (current baseline: 182 passed, 3 skipped)
venv/bin/python3 -m pytest tools/tests/unit/ tools/tests/integration/ -q

# Import and exercise the code you changed — this is the strongest check
venv/bin/python3 -c "from utils.ttrpg.combat_engine import *; print('ok')"

# Syntax check
venv/bin/python3 -c "import ast,io; ast.parse(io.open('utils/ttrpg/your_file.py').read())"

# Data-only registries can be exec'd in isolation
timeout 10 venv/bin/python3 -c "exec(open('utils/ttrpg/monster_registry.py').read()); print(len(MONSTERS))"
```

Use `venv/bin/python3`, not the system interpreter — the system one lacks the dependencies and
`python3 -m pytest` will simply collect zero tests.

> [!NOTE]
> Earlier versions of this guide said imports from `utils/` "hang forever due to Discord client
> initialization". That is not accurate — imports complete normally. Please do import and call
> the code you are changing; it catches far more than a syntax check.

**Don't run `python Kaiacord.py`** to test a change. That starts a live Discord client against a
real token. Import the module and call the function instead.

## How to Contribute

### 1. Fork & Branch

```bash
git checkout -b your-branch-name
```

Branch naming: `fix/description`, `feat/description`, or `balance/description`.

### 2. Make Your Changes

- **One logical change per PR.** Don't mix a bug fix with a balance pass.
- Follow the coding standards in `AGENTS.md`.
- Use `secrets` for security-relevant randomness (combat rolls, loot, tokens). `random` is
  fine for flavour (dream shuffling, world-event variety).
- Use atomic writes (`write .tmp` → `os.replace()`) for any file I/O.

### 3. Validate

At minimum, run syntax checks on every file you touched:

```bash
venv/bin/python3 -c "import ast,io; ast.parse(io.open('utils/ttrpg/your_file.py').read())"
```

If you modified a data registry, verify referential integrity:

```bash
# Check that all encounter table keys resolve to real monsters
timeout 10 venv/bin/python3 -c "
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

See `docs/ttrpg/ttrpg_report.md` for current balance state. Good first contributions:

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

## Licensing

Kaiacord is released under the [MIT License](LICENSE). By submitting a pull request you agree
that your contribution is licensed under the same terms.
