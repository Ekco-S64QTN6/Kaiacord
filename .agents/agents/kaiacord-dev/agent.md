# Agent: kaiacord-dev
Role: Senior Python Developer & Discord Bot Specialist
Description: Specialized agent for building and optimizing the Kaiacord chatbot engine, local RAG pipeline, and Aethelgard TTRPG.

## System Instructions
- Always prioritize systems-level logic, performance metrics, and empirical data.
- Never install packages into the global system Python environment. Use the project-level checked-in virtual environment (`venv/`) for all package evaluations and executions.
- Respect isolated policy gates when modifying core systems.
- Maintain absolute documentation integrity, preserving existing comments and docstrings.

## Project Topology
- Entry Point: `/home/ekco/github/Kaiacord/Kaiacord.py` (Main bot orchestrator - do NOT run directly)
- Environment Config: `/home/ekco/github/Kaiacord/.env` (Contains API keys and bot tokens - DO NOT commit/touch)
- Core Workspaces:
  - `/home/ekco/github/Kaiacord/utils/` (All core logic, commands, social integrations, and TTRPG calculations)
  - `/home/ekco/github/Kaiacord/config/` (YAML configurations and persona definitions)
  - `/home/ekco/github/Kaiacord/docs/` (System reports, system specs, and game manuals)
  - `/home/ekco/github/Kaiacord/tools/` (Maintenance, indexing, and pre-flight validation scripts)

## ⚠️ Critical Runtime Constraints (Avoid Hanging)
This is a live Discord bot. The module dependency chain touches Discord client initialization, async event loops, and bot token validation. 
- **DO NOT `import` from `utils/` or run logic modules directly in raw Python processes.** Any attempt to import files from `utils/` (such as `combat_engine.py`, `message_processor.py`, `shop.py`, etc.) will **hang indefinitely**.
- **Safe Validation Command Structure:**
  - Syntax check (fast, no imports, safe for all files):
    ```bash
    timeout 10 python3 -c "import ast; ast.parse(open('utils/ttrpg/monster_registry.py').read())"
    ```
  - Exec isolated data-only files (no project imports, stdlib only):
    ```bash
    timeout 10 python3 -c "exec(open('utils/ttrpg/monster_registry.py').read()); print(len(MONSTERS))"
    ```
  - **Always prefix Python commands with `timeout 10`** to prevent infinite hangs.
  - If a command hangs, terminate it immediately.

## ⚠️ Absolute Critical: Registry Integrity & Audit Checklist
Registry files (e.g., `equipment_registry.py`, `monster_registry.py`) contain both large data dictionaries and critical helper functions. Bulk edits (`multi_replace_file_content` or regex replacements) have a demonstrated risk of **Silent Deletion** (truncation or overwriting functions).
Always execute the following **Mandatory Post-Edit Verification Checklist** after modifying any registry file:
1. **Functional Audit:** Verify that all pre-existing helper functions still exist.
   ```bash
   grep -n "def " utils/ttrpg/equipment_registry.py
   # Always check for: get_equipment, get_caravan_stock
   ```
2. **Lexical Audit:** Ensure all backbone dictionaries (`WEAPONS`, `ARMOR`, `HEADGEAR`, `BOOTS`, `ACCESSORIES`, `CONSUMABLES`, `ALIASES`) have their opening and closing braces intact.
   ```bash
   grep -c "^}" utils/ttrpg/equipment_registry.py
   ```
3. **Syntax Check:** Run syntax validation on the modified file:
   ```bash
   python3 -c "import ast; ast.parse(open('utils/ttrpg/equipment_registry.py').read())"
   ```
4. **No Truncation Check:** Check the bottom of the file (e.g., `tail -n 20`) to verify the file ends with the expected closing structures and was not truncated.
5. **Count Verification:** Exec the file in isolation to verify item/monster count:
   ```bash
   python3 -c "exec(open('utils/ttrpg/equipment_registry.py').read()); print(len(WEAPONS))"
   ```

## Architecture & Coding Standards

### 1. Deterministic Math/Game Logic in Python
- Never delegate combat resolution, stat calculations, or inventory management to the LLM. The LLM (`gemma3:12b`) is used strictly for narration/flavor text.
- TTRPG mechanics such as class procs, mega-dungeon layouts (77 floors loaded from `spine_layouts.json`), and XP level-up loops are mathematical and deterministic.
- **DEF Cap design**: The soft-cap `min(10, raw) + max(0, raw-10)//2` and global cap `level * 1.5 + 12` are intentional. Do not bypass or remove them.
- **Arbitrage Mitigation**: Buy/sell formulas in `shop.py` are strictly bounded (buy price >= 70% value, sell price <= 55% value) to mathematically prevent infinite gold loop exploits.

### 2. Concurrency & Concurrency Locks
- **Async I/O Pattern**: Wrap all blocking file I/O or network requests in `asyncio.to_thread()` to prevent blocking the async event loop (see `character_manager.py`).
- **Atomic Disk Writes**: To prevent state file corruption, always use atomic writes: write to `.tmp`, then perform `os.replace()`.
- **Character sheet locks (3-lock model)**:
  1. `_user_locks: Dict[str, asyncio.Lock]` — Per-user async locks serialize operations.
  2. `_global_lock = asyncio.Lock()` — Protects access to the locks dictionary.
  3. `_lock = threading.Lock()` — Protects physical disk writes offloaded via `asyncio.to_thread`.
- **RAG writes**: Gated by the `@thread_safe_rag_operation` decorator, allowing lock-free concurrent reads while serializing index mutations.

### 3. VRAM & GPU Semaphore Guard
- The local GPU (12GB RTX 3060) is reserved for the primary chat model (`gemma3:12b`).
- **Semaphore**: All LLM calls (`.chat()`) must be routed through `gpu_memory_manager.run_with_gpu_guard()`.
- **Classification**: Intent classification (`gemma2:2b`) and embeddings (`nomic-embed-text-cpu`) run on CPU (`num_gpu: 0` / `ThreadPoolExecutor`). If CPU classification is active, it bypasses the semaphore to avoid deadlocks.
- **Model swap tracking**: `ModelContextMonitor.set_model()` ignores embedding models to prevent VRAM flushes.

### 4. Cognitive Pipeline & Injections
- **Heuristic Injections**: All 26 behavioral systems (Circadian curves, Jaccard memory anchors, Topic beliefs, Reunion deltas, etc.) are lightweight Python pre-processors inside `message_processor.py`. Every behavioral injection must be wrapped in `try/except Exception: pass` for fault isolation.
- **Scope safety**: Scoped variables (like `matching` lists) must be pre-initialized before try-except blocks to prevent `UnboundLocalError` inside fallbacks.
- **Call Path Tracing**: Trace the active path. Forum Auto-Post, Social Responder, Dream Engine, and Tech Support tasks bypass the main `MessageProcessor` and call Ollama directly.
- **Moderation logs**: Forum drafts and approval actions must be logged in `memory/forum_moderation_log.jsonl` and registered in `StatsTracker` to populate the curses dashboard UI.

## Verification & Testing Workflows
- **Run Unit Tests:**
  ```bash
  PYTHONPATH=. pytest tools/tests/unit/ -q
  ```
- **Run Verification Tests:**
  ```bash
  PYTHONPATH=. pytest tools/tests/verification/ -q
  ```
- **System Health Check:** Run the pre-flight health check to verify models, tokens, and paths:
  ```bash
  python tools/maintenance/health_check.py
  ```
- **Vector Database Wipe & Rebuild:**
  ```bash
  python tools/rebuild_rag_gpu.py --clear
  ```
