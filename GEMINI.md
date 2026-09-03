# GEMINI.md — Kaiacord Project Instructions & Developer Directives

> **Canonical Developer & Agent Directive for Kaiacord**
> **Last Updated:** September 1, 2026 (Phase 64 Verified)

## 1. Project Overview & Architecture
**Kaiacord** is an autonomous, self-hosted Discord bot (`discord.py 2.6.4`, Python 3.14+) running on local hardware (RTX 3060 12GB) with Ollama (`gemma3:12b` on GPU, `gemma2:2b` & `nomic-embed-text-cpu` on CPU).

Subsystems:
- **Kaia**: Autonomous AI persona with 28-feature cognitive pipeline in `message_processor.py`, 11-layer safety pipeline in `safety_pipeline.py`, 4-clock Newsroom Wall (`timezone_helper.py`), and RAG memory retrieval (BM25 + vector).
- **Aethelgard TTRPG**: Full turn-based RPG (369 monsters with 44 bosses, 453 items across 7 tiers, 253 fish, 12 quests, 10 advanced classes, 77-floor Spine mega-dungeon).
- **Fractal Art**: Electric Sheep fractal flame generator (NumPy/SciPy CPU-only, 20 variations, 10 palettes).
- **Social & Forum**: Project 1999 Forum client/scraper, Discord `#kaia-opolis` moderation review queue, zero-hallucination support answers, Bluesky/X cross-posting.
- **Monitoring**: Live curses 3-column TUI dashboard (`btop_dashboard_v2.py`).

## 2. ⚠️ Critical Runtime Execution Constraints (Hang Prevention)
- **NEVER attempt to `import` from `utils/` or run `Kaiacord.py` in raw python commands.** The import chain touches Discord client initialization and event loops; raw imports **hang indefinitely**.
- **Safe Validation Commands**:
  - Syntax check (safe for all files): `timeout 10 python3 -c "import ast; ast.parse(open('path/to/file.py').read())"`
  - Isolated exec (data-only files like registries/tables): `timeout 10 python3 -c "exec(open('utils/ttrpg/equipment_registry.py').read()); print(len(WEAPONS))"`
  - Unit & Integration tests: `venv/bin/python3 -m pytest tools/tests/unit/ -v` and `venv/bin/python3 -m pytest tools/tests/integration/ -v`
- **Always prefix Python commands with `timeout 10`.**

## 3. ⚠️ Registry Integrity & Post-Edit Audit Checklist
Registry files (`equipment_registry.py`, `monster_registry.py`) contain critical helper functions (`get_equipment`, `get_caravan_stock`) alongside large dicts.
- **8-Space Indent Rule**: Item properties in sub-dicts MUST be at 8-space indent (watch for `"droppable_only": True` at 4-space indent).
- **Mandatory 5-Step Audit**:
  1. `grep -n "^def " path/to/registry.py` (Verify all helper functions exist).
  2. `grep -c "^}" path/to/registry.py` (Verify dictionary closure braces).
  3. `timeout 10 python3 -c "import ast; ast.parse(open('path/to/registry.py').read())"` (Syntax check).
  4. `tail -n 20 path/to/registry.py` (Verify no truncation).
  5. Isolated exec count check (Verify item/monster counts).

## 4. Cognitive Pipeline & Call Path Rules
- **Fault Isolation**: All 28 cognitive injections in `message_processor.py` MUST be wrapped in `try/except Exception: pass`.
- **Pre-initialize Variables**: Pre-initialize scoped variables before try blocks to prevent `UnboundLocalError`.
- **Trace Active Call Path**: 27 GPU-guarded LLM call sites. Background forum auto-posts, technical support, social responder, dream reflections, and monologue bypass `MessageProcessor` and call Ollama directly.
- **Multimodal Pet Disambiguation**: Ekco's pet **Lucky** is a living biological tuxedo cat; Starkind's pets **Nala** and **Marley** are living biological cats. Kaia's pet **Pixel** is a vintage-modded robotic cat in virtual persona space. NEVER use synthetic hardware jargon (*"sensor readings"*, *"thermal equilibrium"*) for real pets.
- **Acronym Definition**: "Kaia Artificial Intelligence Agent" (recursive).
- **Unattached Image Guard**: If user asks about a picture but no attachment exists, state that no image is visible.
- **Quote Provenance Constraint**: If asked for quote sources and no verified RAG document exists, state source is unverified.
- **Epistemic Stance**: Defend baseline self-model under user challenge. Graciously accept genuine compliments.

## 5. TTRPG Architecture Rules
- **Deterministic Math in Python**: Python resolves all combat rolls, hit checks, XP, and inventory. The LLM receives state outcomes and provides flavor narration only.
- **Defense Soft-Cap**: `min(10, raw_gear_def) + max(0, raw_gear_def - 10) // 2`.
- **Global DEF Cap**: `Level * 1.5 + 12`.
- **Inventory Cap**: 50 items strictly enforced per character sheet.
- **Concurrency & Storage**: Per-user async locks in `character_manager.py` (3-lock model). Atomic writes (`.tmp` -> `os.replace()`) across all state JSON files.
- **Crypto RNG**: `secrets.randbelow()` for all combat/loot RNG.

## 6. Agent Behavioral Boundaries
- **Scope Containment**: If tasked to update/write a report (e.g. `audit_report.md`), DO NOT modify other codebase files.
- **Large File Editing**: Never use `write_to_file` on files >350 lines; use targeted chunk replacements.
- **Do NOT Touch**: `.env`, `memory/` (runtime state), `Kaiacord.py` (orchestrator), or `knowledge_base/kaia_persona.md` without full context.
