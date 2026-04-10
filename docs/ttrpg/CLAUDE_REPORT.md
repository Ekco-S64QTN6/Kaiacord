# Aethelgard TTRPG — Comprehensive Code Review (Synthesized)
*Reviewed from full source sync · April 2026*

---

## 1. Executive Summary

The Aethelgard TTRPG subsystem is structurally sound and effectively isolated from the core Discord bot's RAG/LLM logic to guarantee determinism in game mechanics. The game utilizes strict data registries, synchronous Python math for all state determination, and asynchronous hooks strictly for narration.

However, the codebase has accumulated significant technical debt and critical friction points. The primary concerns synthesized across reviews are:
- **Critical Functionality Failures:** Active bugs breaking bait consumption, news background tasks, moogle deliveries, and dungeon interactions.
- **Dead Features:** 9 furniture bonuses that are documented and purchasable but silently do nothing.
- **Economy & Combat Balance:** Mythic fishing creates a gil singularity, late-game bosses overpower maxed player defense, and the Shadowknight lifesteal infinitely outscales parity. 
- **Code Maintainability:** `rpg_handler.py` is approaching 7,500 lines as a monolithic file, which is an immediate architectural hazard.

---

## 2. Bug Inventory

### 🔴 CRITICAL
- **BUG-01 — `BiteView.on_timeout()` uses legacy bait key:** `fishing_stats["bait_count"]` is referenced but the registry migrated to `bait_stock`. Bait is never consumed on escape.
  - *Fix:* Replace timeout block with mirror of `_handle_cast` miss logic to decrement `bait_stock[current_bait]`.
- **BUG-02 — `log_debug` missing in `background_tasks.py`:** Causes `NameError` crash on news refresh invocation.
  - *Fix:* Add `log_debug` to top imports.
- **BUG-03 — Moogle weekly delivery always fails:** Pet state (`fed_today = False`) resets in the loop *before* the Monday moogle scan executes.
  - *Fix:* Move Monday moogle check above the character processing loop.
- **BUG-04 — `DungeonView` status directly passes interaction:** Missing `.response.defer()` causes "Unknown Interaction" failures for players.
  - *Fix:* Standardize to use `_make_status_btn` component constructor.
- **BUG-05 — Duplicate `ARMOR` keys:** Identical copies of `"invoker_vestment"`, `"arcanist_shroud"`, etc. exist in progression sections, creating silent overwrite risks. 
  - *Fix:* Dedup registry by removing the class progression copies.

### 🟠 HIGH
- **BUG-06 — Special day ATK/DEF bonuses fail to propagate:** Modifiers in `weather["effect"]` are wired to non-existent string keys. World state ATK/DEF is always 0.
- **BUG-07 — `_handle_scout` ignores `home_scout` (War Map):** The 3,000g Tactical War Map furniture bonus is completely missing from the scout guard validation. 
- **BUG-08 — `_handle_abandon` missing from `RPGFullLocationView`:** Quest map inline abandon buttons work, but location routing dispatch avoids declaring it.

### 🟡 MEDIUM
- **BUG-09 — Gilded mushroom "drowns if watered" mechanic is text-only:** Players suffer no consequence for watering them.
- **BUG-10 — `check_and_reset_hunts` and dawn task duplicate logic:** Both deduct 3 HP for stripping the `ale_warmth` condition.
- **BUG-11 — Subprocess Unsafe Run:** `run_news_update()` executes `script_path` blindly without checking `os.path.exists`.

### 🟢 VERIFIED / RESOLVED (From Previous Sweeps)
- *Resolved:* `_handle_scout` now successfully imports global `MONSTER_TABLES` (no longer a stale enum).
- *Resolved:* `format_sheet` successfully exposes underlying player status conditions natively.
- *Resolved:* Hunt cost consumed pre-spawn (`sheet["hunts_today"] += 1` executes before saving to protect from crash manipulation).

---

## 3. Balance Analysis

### 3.1 Economy Breaking Loops
- **Mythic Fishing Singularity:** `Heart of Aeridor` lists a `50,000g` base line but can roll up to `125,000g`. It eclipses 10+ hours of ruin hunting (800g/day yields) in a single cast. 
  - *Mitigation:* Hard-cap Mythic at 2,000g and Legendary at 500g, or impose a daily limit from Gregor.
- **Crystal Bait ROI:** Crystal bait (100g) grants +30 weight rolls, bumping mythic chance to 3.1%. 2,000g investment returns massive profit loop.

### 3.2 Combat Power Curves
- **Unavoidable Boss Damage Gap:** At max level (10), player Defense hard-caps at **27**. Bosses feature an early +18 ATK Base mod on `d20` (`19 - 38` range). Bosses will consistently strike near-guaranteed hits on "Tank" builds. 
- **Shadowknight Lifesteal Limitless:** Shadowknight has a `15%` max outgoing damage siphon. Over a 15-round boss run throwing crits for 40 damage, it can sustain effectively indefinitely. Outpaces Paladin's rigid +3 `heal_on_kill`.
  - *Mitigation:* Introduce a round-heal cap of `min(heal, 5)`.
- **T5 Black Lotus Distortion:** Grants +6 ATK. Overrides combat math. (Shadowblade +9 ATK stack = near 100% hit rate across the system).
- **Hunt Max Stacking:** Combining ale, inn rest, pets, and Ranger classes allows up to 10 hunts/day. A daily total cap of 8 should be formalized.

---

## 4. Code Quality Assessment

| Assessment | Details | Recommendation |
|:---|:---|:---|
| **Handler Monolith** | `rpg_handler.py` exceeds 7,300 lines and is hitting maintainable critical mass. | **High Priority:** Deconstruct to `rpg_views.py`, `dungeon_handler.py`, `housing_handler.py`, `shop_handler.py`, `combat_handler.py` and map back to root handler. |
| **Inconsistent Buttons** | Three varied patterns exist for handling button clicks. (Deferred callbacks, Raw Interactions, and Silent Sending). | Adopt `_make_status_btn` standard for complete UI alignment. |
| **Inline Registries** | `utils/ttrpg/encounter_tables.py` correctly links the arrays, but `rpg_handler.py` contains inline hardcoded dict structures mapping legacy quests or dialog prompts. | Migrate embedded response dicts to `npc_registry.py` and `quest_registry.py`. |

---

## 5. Performance Review

**No critical performance bottlenecks found.** The codebase leverages `asyncio.to_thread` for all disk I/O, maintaining the `GPUTaskPriority.CHAT` cap for LLM ingestion flawlessly.

**Minor Finding Adjustments:**
- `_make_shop_view` issues an unoptimized `await load(uid)` internally simply to render the sell dropdown instead of ingesting the parameter directly. 
-  Multiple identical `save(sheet)` directives stack sequentially inside quest handlings (`_handle_hunts`), requiring redundant locking writes. 

---

## 6. Dead & Incomplete Code

| Feature / File | Status | Impact / Location |
|---|---|---|
| `balance_model.py` | **Dead** – Uses stale formulas mismatched to `combat_engine.py` | **Delete** or Rewire dynamically. |
| `bank_cap` (Vault Chest) | **Dead** — 500g cap never enforced | `furniture.py` / `_handle_bank_deposit` |
| `home_atk` (Weapon Rack) | **Dead** — +1 ATK never read | `furniture.py` / `combat_engine.py` |
| `local_atk` (Trophy Mount) | **Dead** — +2 ATK never read | `furniture.py` / `combat_engine.py` |
| `talk_xp` (Bookshelf) | **Dead** — +5 XP missing | `furniture.py` / `_handle_talk` |
| `home_scout` (War Map) | **Dead** — Scout bypassed via BUG-07 | `furniture.py` / `_handle_scout` |
| `session_manager.action` | **Dead** — Log generated but unused | `session_manager.py` |

---

## 7. Unified Actionable Recommendations

### 🔴 Immediate (Core Functionality Loss)
1. **[R-01] BUG-01 Fix `BiteView.on_timeout()`:** Update legacy `bait_count` dict access to `bait_stock` block matching `_handle_cast`.
2. **[R-02] BUG-02 Fix `log_debug` Import:** Add log_debug to `background_tasks.py` dependencies.
3. **[R-03] BUG-03 Move Moogle Delivery Execution:** Shift Monday Dawn pet check above the character file resets.
4. **[R-04] BUG-04 Fix `DungeonView`:** Swap raw custom `_status_cb` with a `_make_status_btn` injection. 
5. **[R-05] BUG-05 Sanitize `ARMOR` Duplications:** Purge class-progression repeated items from `equipment_registry.py`. 

### 🟠 Near Term (Balance & Sub-Feature Loss)
6. **[R-06] Fix Weather Propagation (BUG-06):** Inject parsing strings `"atk_bonus"` logic accurately to `background_tasks.py` tracking. 
7. **[R-07] Hook Furniture Triggers:** Enforce `home_scout` validations in `_handle_scout` and apply `bank_cap`, `home_atk`, etc., to their respective operational flows. 
8. **[R-08] Hard-Cap Mythic Fish Value:** Reign in `sell_value` multiplier returns in `fishing_engine.py`. 
9. **[R-09] Limit Shadowknight Lifesteal:** Append `min(heal, 5)` bounded restraints to `combat_engine.py`. 
10. **[R-10] Handle Gilded Mushroom Death (BUG-09):** Formally enforce drowned logic check in farming code evaluation stages. 
11. **[R-11] Delete Dead Weight:** Delete `balance_model.py`. 

### 🔵 Long Term (Architectural Strategy)
12. **[R-12] Componentize `rpg_handler.py`:** Execute sweeping file separation mapping out dedicated Shop, UI, Dungeon, World, Combat, Housing routines decoupled from the main parent. 
13. **[R-13] Shift Vestigial Session TTRPG Structs:** Migrate `session_manager` multi-user combat states into isolated single user definitions within main char sheet storage properties. 
14. **[R-14] Redefine Boss/Player DEF Ceilings:** Address static hit curves across End-Game raid bosses against max gear limits.