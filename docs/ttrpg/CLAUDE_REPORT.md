# Aethelgard TTRPG — Comprehensive System Review
*April 21, 2026 · Full codebase audit · 19,933 lines across 37 modules · Post-L15 expansion + Phase 6 final cleanup*

---

## 1. Executive Summary

The Aethelgard TTRPG is in **A-tier operational health**. Six phases of development — handler decomposition (Phase 1), L15 expansion (Phase 2), seasonal/calendar integration (Phase 3), async I/O optimization (Phase 4), economy/quest rebalancing (Phase 5), and final bug fixes + async migration (Phase 6) — have brought the system to production maturity.

**All identified bugs have been resolved.** This review identifies **0 active bugs**, **2 structural improvement notes** (purely maintainability, no functional impact), and **1 content gap**. The system is clean, performant, and ready for content-focused development.

**Full Validation Suite — All Passing:**
- ✅ All 37 modules pass `ast.parse()` syntax check
- ✅ All 223 monster keys resolve correctly from encounter tables
- ✅ All loot table item keys exist in equipment registries (383 items: 121 weapons, 59 armor, 61 headgear, 46 boots, 50 accessories, 46 consumables)
- ✅ `get_equipment()` and `get_caravan_stock()` helper functions intact
- ✅ Zero `import random` violations — `secrets` module used exclusively for all RNG
- ✅ Zero bare `except:` clauses in TTRPG codebase
- ✅ Zero synchronous `load_housing()` calls in async handlers — all migrated to `load_housing_async()`
- ✅ Furniture bonuses (`home_brewing`, `daily_training`, `home_pray`, `home_scout`, `home_bank`) wired
- ✅ Weather effects (`scout_blocked`, `xp_bonus`, `gil_bonus`, `level_gate`, `armor_penalty`) wired
- ✅ Calendar special day buffs wired to combat, dungeon, rest, pray, offer, gamble handlers
- ✅ `SEASONAL_FARM_BONUSES` wired to `farming.harvest_crop()`
- ✅ `SEASONAL_SHOP` wired to Hemlock's stock
- ✅ XP cap enforcement at L15/256001 across all XP paths
- ✅ Dungeon persistence methods fully async
- ✅ `broadcast.log_world_event()` uses `asyncio.to_thread`
- ✅ Dawn task cleanup of `_winter_resolve_applied` and `_new_year_applied` confirmed
- ✅ Quest system: 9 quests (L1, L3, L4, L5, L7, L9, L11, L13, L15)
- ✅ `get_season_day()` correctly handles winter year-wrap (Dec 1→day 1, Jan 1→day 32, Feb 15→day 77)

---

## 2. Bug Inventory

### All Bugs Resolved ✅

**No active bugs remain.** All issues identified across six audit phases have been fixed and verified.

### Phase 6 Fixes (April 21, 2026)

| ID | Fix | Verification |
|---|---|---|
| ✅ BUG-N7 | **Replaced `import random` with `secrets.randbelow()`** in boss loot path (`rpg_combat_handler.py`). Changed `random.random() < 0.4` → `secrets.randbelow(10) < 4`. | `grep "import random" utils/ttrpg/` → zero violations (only `random_encounter` function name remains) |
| ✅ BUG-N8 | **Migrated all `load_housing()` to `await load_housing_async()`** across **all async handlers** — 15 total call sites across `rpg_combat_handler.py` (6), `rpg_core_handler.py` (3), `rpg_housing_handler.py` (3), `rpg_social_handler.py` (1), `rpg_views.py` (2). | `grep "from utils.ttrpg.housing import load_housing$" utils/ttrpg/` → only 3 results, all in **sync** functions (`progression.py:138,158`, `character_manager.py:97`) which are correct |
| ✅ BUG-N9 | **Fixed `get_season_day()` year-wrap logic** in `calendar.py`. The old code broke on `m > today.month` for December when the current month was Jan/Feb. | Test results: Dec 1→1, Jan 1→32, Feb 15→77, Mar 1→1, Jun 1→1, Jul 1→31, Sep 1→1, Oct 31→61, Dec 15→15. All correct. |
| ✅ CQ-N5 | **Migrated remaining 8 sync `load_housing()`** calls in non-combat async handlers to `await load_housing_async()`. | Zero sync `load_housing` calls in async functions remain |
| ✅ CQ-N6 | **Fixed `_dungeon_move` and `RenameHouseModal`** — both now use async housing I/O (`load_housing_async`, `save_housing_async`). | Included in CQ-N5 migration |

### Previously Resolved (All Confirmed Still Fixed)

- ✅ XP cap enforcement at L15/256001 across all paths
- ✅ `broadcast.log_world_event()` wrapped in `asyncio.to_thread`
- ✅ `world_state.py` bare `except:` narrowed to specific exception types
- ✅ Mognet letter consumption fixed (single `.remove()`)
- ✅ Duel non-lethal cap applied after all proc damage
- ✅ Dawn task cleanup of stale holiday flags
- ✅ `_is_wealthiest` refactored to background thread
- ✅ Dead `SEASONAL_ITEMS` dict removed
- ✅ `gauntlets` alias collision resolved

---

## 3. Balance Analysis

### 3.1 Equipment Stat Budgets — Well-Controlled

| Tier | ATK + DMG Budget | Die | Proc | Drop Source |
|---|---|---|---|---|
| T1 | 0–1 | d6 | — | Shop + loot |
| T2 | 4–7 | d8 | — | Shop + loot |
| T3 | 8–14 | d8/d10 | 1d4–1d6 | Loot only |
| T4 | 12–15 | d10 | 1d6 | Loot only |
| T5 | 17–21 | d10/d12 | 1d8 | Boss loot |
| T6 | 20–21 | d12 | 1d10 | Boss loot (deadly/boss) |
| T7 | 22–24 | d12 | 1d12 | Boss loot only (weight 1) |

Defensive gear DEF ranges: T1(0–3), T2(2–6), T3(6–8), T4(8–10), T5(9–12), T6(8–15), T7(10–18). The gear soft-cap (`min(10, raw) + max(0, raw-10)//2`) correctly prevents DEF stacking from becoming degenerate.

### 3.2 Monitoring Notes

| ID | Finding | Severity | Status |
|---|---|---|---|
| BAL-3 | **Shadowblade crit_threshold: 17** with Voidstep Blade produces the highest sustained DPR. Low HP pool (Rogue d5 HP/level) provides a natural counterbalance. | 🟡 Monitor | No action unless player feedback indicates degenerate endgame. |
| BAL-5 | **DEF global cap** (`level * 1.5 + 12`) tops at 34 at L15. Boss ATK mod 18 + d20 still hits on 16+. | 🟢 Info | Working as designed. |

### 3.3 Power Curve Summary

```
Level  Player ATK (avg)  Player DEF (avg)  Monster HP (tier)        Verdict
1-3    +3 to +5          13-15             10-50 (triv/easy)        Balanced — 2-4 rounds
4-6    +8 to +12         17-20             60-100 (medium)          Balanced — gear matters
7-9    +14 to +18        22-25             80-150 (hard/deadly)     Slightly easy — DEF cap helps
10-12  +18 to +24        25-30             150-400 (boss/deadly)    Well-tuned — T6 gear arrives
13-15  +24 to +28        30-34             300-680 (boss)           Challenging — T7 gear is rare
```

---

## 4. Code Quality Assessment

### 4.1 Architecture — Strong

| Module | Lines | Role |
|---|---|---|
| `rpg_views.py` | 2,408 | Discord UI views & button factories |
| `rpg_core_handler.py` | 2,344 | Movement, calendar, scout, pray, NPC, misc commands |
| `monster_registry.py` | 1,701 | 223 monster stat blocks |
| `equipment_registry.py` | 1,534 | 383 items across 7 tiers |
| `rpg_combat_handler.py` | 1,517 | Hunt, attack, dungeon combat, duel |
| `rpg_housing_handler.py` | 941 | Housing, farming, pets, furniture |
| `dungeon.py` | 875 | Procedural dungeon generation |
| `rpg_social_handler.py` | 618 | NPC talk, quests, deliver |
| `forest_events.py` | 583 | 20 forest event handlers |
| `class_advancement.py` | 511 | 10 advanced classes, proc logic |

### 4.2 Remaining Structural Notes (No Bugs)

| ID | File | Note | Effort | Impact |
|---|---|---|---|---|
| CQ-N3 | [rpg_core_handler.py](file:///home/ekco/github/Kaiacord/utils/ttrpg/rpg_core_handler.py) | At 2,344 lines, this is the largest module. A future split into `rpg_navigation_handler.py` and `rpg_world_handler.py` would improve maintainability. Not a bug — the code works correctly as-is. | 🟡 2-3h | 🟢 Maintainability only |
| CQ-N4 | Multiple handlers | **Boilerplate import blocks** (lines 1–48) duplicated across 5 handler files. Could extract to a shared `rpg_handler_base.py`. Not a bug — just reduces import repetition. | 🟡 1h | 🟢 Maintainability only |

### 4.3 Positive Patterns

- **Atomic writes** (`tmp` → `os.replace()`) used consistently across all persistence layers ✓
- **Per-user async locks** in `character_manager.py` prevent race conditions ✓
- **`secrets` module** used exclusively for all RNG — zero violations ✓
- **No bare `except:`** clauses in TTRPG codebase ✓
- **All housing I/O in async handlers uses non-blocking `load_housing_async()`** ✓
- **`save_housing_async()`** used in modal callbacks (rename house) ✓
- **Equipment key resolution** (`_eq_key()`) cleanly handles both string and dict slot formats ✓
- **Deterministic weather** via date-seeded hash — all players see the same weather ✓
- **Calendar special day buffs** fully wired to all gameplay handlers ✓
- **Quest-aware encounter nudge** increases quest-target spawn rates ✓
- **Dawn task** properly cleans up all transient flags ✓

### 4.4 Sync `load_housing()` Usage — Fully Correct

Only 3 sync `load_housing()` calls remain in the entire codebase, all in **synchronous functions** where async is not available:

| File | Line | Function | Context |
|---|---|---|---|
| `progression.py` | 138 | `get_max_hunts()` | `def` (sync) — correct |
| `progression.py` | 158 | `hunts_remaining()` | `def` (sync) — correct |
| `character_manager.py` | 97 | `load()` | Already wrapped in `asyncio.to_thread()` at line 98 — correct |

---

## 5. Performance Review

**No performance issues remain.** All prior items resolved:

- ✅ Inline imports in `encounter_tables.py` moved to module level
- ✅ `_FISH_INDEX` and `_CAT_FALLBACK` lookup indexes built at import time
- ✅ `_is_wealthiest` uses background thread caching
- ✅ Dawn task character loop wrapped in `asyncio.to_thread`
- ✅ Dungeon persistence methods fully async
- ✅ **All housing I/O in async handlers now uses non-blocking `load_housing_async()`** (Phase 6)

---

## 6. Content & Feature Status

### 6.1 Quest Coverage

| Level Range | Quests | Names | Status |
|---|---|---|---|
| L1–L4 | 3 | A Stranger in the Mud, The Darkening Woods, Sister Maren's Request | ✅ Good |
| L5–L7 | 2 | The Aeridorian Signal, What Sleeps Beneath | ✅ Good |
| L8–L10 | 1 | The Final Silence | 🟡 Thin — L8 and L10 have no dedicated quests |
| L11–L15 | 3 | The Waking Metal, The Darkening, The Last Guardian | ✅ Good |

**Remaining gap:** The L8–L10 range has only a single quest (L9). Adding 1–2 quests at L8 and L10 would fill the mid-game progression gap. The quest infrastructure in `quest_registry.py` makes this trivial.

### 6.2 System Feature Completeness

| Feature | Status | Notes |
|---|---|---|
| Combat engine | ✅ Complete | DEF soft-cap, global cap, class procs, weapon procs, fully async housing I/O |
| Dungeon system | ✅ Complete | MST generation, 5 difficulty tiers, themed monster pools, boss scaling to L15 |
| Class advancement | ✅ Complete | 10 advanced classes with unique passives, procs, and titles through L15 |
| Equipment | ✅ Complete | 383 items across 7 tiers with class restrictions and proc effects |
| Housing | ✅ Complete | 4 tiers, furniture bonuses, farming, pets, bank access, async I/O everywhere |
| Farming | ✅ Complete | 5 crop types, seasonal bonuses, watering, furniture yield bonuses |
| Pets | ✅ Complete | 6 pet types with daily feeding and unique passives |
| Alchemy | ✅ Complete | 10+ recipes, ingredient discovery, no XP rewards (balanced) |
| Calendar | ✅ Complete | 13 special days, 4 seasons, deterministic weather, all buffs wired, year-wrap fixed |
| Forest events | ✅ Complete | 20 unique events with stat-based outcomes and Kaia narration |
| Shop system | ✅ Complete | Buy/sell/bulk sell, CHA modifier, reputation scaling, buyback |
| Fishing | ✅ Complete | Rod-based system with seasonal fish, O(1) lookups |
| Broadcast | ✅ Complete | World event log, level-up announcements, death broadcasts |

---

## 7. Actionable Recommendations (Prioritized)

### Priority 1 — Content

| # | Task | Files | Effort | Impact |
|---|---|---|---|---|
| 1 | **Add 1–2 quests** for the L8 and L10 range to fill the mid-game gap. | `quest_registry.py` | 🟠 1–2h | 🟠 Content — player retention in mid-game |

### Priority 2 — Future Maintainability (No Functional Impact)

| # | Task | Files | Effort | Impact |
|---|---|---|---|---|
| 2 | **Extract shared handler boilerplate** into `rpg_handler_base.py` (CQ-N4). | Multiple handlers | 🟡 1h | 🟢 Reduces import duplication |
| 3 | **Split `rpg_core_handler.py`** (2,344 lines) into navigation and world sub-handlers (CQ-N3). | `rpg_core_handler.py` | 🟡 2–3h | 🟢 Improves file organization |
| 4 | **Monitor Shadowblade endgame DPR** (BAL-3). | `class_advancement.py` | — | 🟢 Balance monitoring only |

---

## 8. System Health Scorecard

| Area | Grade | Notes |
|---|---|---|
| **Architecture** | A | Clean handler decomposition. Deterministic game math / LLM narration split enforced. |
| **Data Integrity** | A | All 223 monsters, 383 items, 9 quests cross-validated. No orphan keys. |
| **Combat Balance** | A- | Power curve well-controlled L1–L15. DEF soft-cap + global cap working. Minor Shadowblade outlier to monitor. |
| **Content Depth** | A- | 223 monsters, 383 equipment items, 20 forest events, 9 quests, 10 classes. Thin at L8–L10. |
| **Feature Completeness** | A | Calendar/seasonal data fully wired. All subsystems operational. |
| **Code Quality** | A | Zero `random` violations. Zero bare `except:`. All async handlers use non-blocking I/O. Consistent patterns throughout. |
| **Performance** | A | No bottlenecks. All housing I/O non-blocking. Pre-computed lookups. Background thread caching. |
| **Documentation** | A | `aethelgard_system.md` v0.3.0, lore bible, this report all current. |

**Overall: A-tier. All identified bugs resolved. System is production-ready and suitable for content-focused sprints.**

---

## Appendix A: Audit Changelog

### Phase 6: Final Bug Fixes & Async Migration (April 21, 2026)

| ID | Change | Files Modified |
|---|---|---|
| ✅ BUG-N7 | Replaced `import random` → `secrets.randbelow()` in boss loot | `rpg_combat_handler.py` |
| ✅ BUG-N8 | Migrated 6 `load_housing()` → `await load_housing_async()` in combat handler | `rpg_combat_handler.py` |
| ✅ BUG-N9 | Fixed `get_season_day()` winter year-wrap | `calendar.py` |
| ✅ CQ-N5 | Migrated 8 additional `load_housing()` → `await load_housing_async()` across handlers | `rpg_core_handler.py`, `rpg_housing_handler.py`, `rpg_social_handler.py`, `rpg_views.py` |
| ✅ CQ-N6 | `RenameHouseModal` now uses `save_housing_async()` | `rpg_views.py` |

**Total Phase 6 changes:** 6 files modified, 15 sync→async migrations, 1 RNG policy fix, 1 calendar logic fix.

### Phase 5: Economy & Quest Rebalancing (April 19–21, 2026)

- ✅ Rebalanced endgame monster HP, removed XP from alchemy, updated furniture bonuses
- ✅ Rebalanced quest rewards, added encounter spawn nudge for active quests
- ✅ Centralized sell price calculation, removed bank interest mechanic

### Phase 4: Maintenance & Optimization (April 18, 2026)

- ✅ BUG-N1–N6: Async I/O consistency, duel safety, Mognet fix, holiday flag cleanup
- ✅ PERF-N1–N3: Fishing lookups, encounter table imports, wealth caching

### Phase 2–3: L15 Expansion & Calendar Integration (April 18, 2026)

- ✅ 78 new equipment items (T6/T7), dungeon tier 5, boss scaling to L15
- ✅ Calendar special day buffs and seasonal shop/farm bonuses fully wired

### Phase 1: Handler Decomposition (March–April 2026)

- ✅ `rpg_handler.py` split into 6 focused modules, circular imports resolved, XP cap enforcement

---

*Review performed against `utils/ttrpg/` (19,933 lines, 37 modules), `utils/core/background_tasks.py`, and `docs/ttrpg/`.*
*All changes verified via full syntax check (37/37 modules pass), functional calendar regression tests (9/9 dates correct), registry integrity audits (383 items, 223 monsters), and grep-based policy compliance scans (0 `random` violations, 0 bare `except:`, 0 sync housing in async context).*