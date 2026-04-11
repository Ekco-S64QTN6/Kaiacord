# Aethelgard TTRPG — Comprehensive Code Review
*April 11, 2026 · Full codebase audit*

---

## 1. Executive Summary

The system is architecturally sound: deterministic Python handles all game logic, the LLM narrates only, and the concurrent locking pattern in `character_manager.py` and `session_manager.py` is well-designed. The dungeon MST generation, fishing engine, alchemy discovery, and class proc systems are all robust.

---

## 2. Bug Inventory

### ✅ RESOLVED (Final Stabilization Pass - April 11, 2026)

| ID | Sev | Bug / Action Item | File | Fix Details |
|---|---|---|---|---|
| BUG-A | 🔴 | `_get_active_view` bypassed for buff potions | `rpg_handler.py` | Added `_get_active_view` to the embered/fortified/hunt/xp boost branches. |
| BUG-C | 🔴 | Buffs consumed on stun/miss | `combat_engine.py` | Now safely retained if player is stunned or monster doesn't hit back. |
| BAL | 🔴 | Gil inflation from Mythic Fishing | `fishing.py` | Mythic capped at 800g base value, Legendary at 300g down from 2500g. |
| BUG-E | 🔴 | Lore item sell crash | `rpg_handler.py` | Added `elaras_token` to `PROTECTED_KEYS`. |
| BUG-D | 🟠 | `check_and_reset_hunts` race condition | `rpg_handler.py` | Persisted dictionary directly after reset prior to UI generation loop. |
| BUG-F | 🟠 | Duel uses `str` instead of real stats | `rpg_handler.py` | Fully loads equipment dictionaries to map true combat stats in Duels. |
| BUG-G | 🟠 | Stale gil in bank deposit "All" | `rpg_handler.py` | Replaced rigid cached amounts with live retrieval on async confirmation. |
| BUG-H | 🟠 | `mognet_letter` multiple delivery exploit | `rpg_handler.py` | Filtered list recreation purges all redundant letter copies per reward. |
| BUG-I | 🟡 | `get_max_hunts` ceiling bypass | `progression.py` | Built trackable `"hunt_bonus"` flag in dictionary to securely cap at 8 limits. |
| BAL-2 | 🟡 | Black Lotus Overtuned | `equipment_reg..` | Reduced ATK from +6 to +4. |
| BAL-3 | 🟡 | Warden passives weak | `class_advance..` | Fully integrated `heal_on_combat_end` and `xp_bonus_pct` across handlers. |
| PERF-1| 🟡 | Reverse alias overhead | `shop.py` | Memoized alias dictionary into global interpreter cache to bypass O(n). |
| PERF-2| 🟡 | `_is_wealthiest` brute-force scanning | `class_advance..` | Built custom memory TTL caching resolving full DB scans down to 1 check per min. |
| PERF-3| 🟡 | Housing blocking the async thread | `housing.py` | Integrated `asyncio.to_thread` I/O wrappers for intensive housing interfaces. |
| PERF-4| 🟡 | Inline Combat Imports | `combat_engine.py`| Purged nested cyclic calls causing hitches across hot calculation bounds. |
| DEBT-1| 🟡 | Deprecated UI Vault Chest bonus | `furniture.py` | Swapped `bank_cap` for functional daily +5% `interest_bonus` compound loops. |
| DEBT-2| 🟡 | Duplicate Item Definitions | `equipment_reg..` | Removed `invoker_vestment`, `void_vestment`, and `arcanist_shroud` duplicates. |
| DEBT-3| 🟡 | Dead code constants/NPCs | `monster_registry.py`| Scrubbed `sephiroth_echo`, `whisperwood_deep_night`, and `BOSS_GIL_DROP`. |

---

### ✅ Architectural Refactor Completed (April 11, 2026)
- **`rpg_handler.py` Decomposition**: Successfully split the 7,000+ line monolith into component modules:
  - `rpg_combat_handler.py`
  - `rpg_shop_handler.py`
  - `rpg_core_handler.py`
  - `rpg_social_handler.py`
  - `rpg_housing_handler.py`
  - `rpg_views.py`
- **Dependency Stabilization**: Built custom localized lazy-loading closure dispatchers tightly bound inside `rpg_views.py` `RPGFullLocationView` to completely eliminate Discord UI cyclic/circular import hang crashes without dropping UI hook state constraints.
- **Dungeon UI Persistence Fix**: Standardized dungeon combat state detection in `_get_active_view` and `!rpg status`. Previously, using a potion mid-dungeon-fight would accidentally swap the UI to the exploration (arrow) view due to a legacy `in_combat` vs `active_combat` key mismatch.
- **Data Parity Validated**: Completed 100% dynamic smoke-test sweep validating completely identical logic paths pre- and post-refactor.

### ✅ Post-Refactor Bug Fixes
- **`progression.py` kwargs**: Restored `housing` kwargs missing from `check_and_reset_hunts` logic.
- **LLM Grammar Hallucinations**: Updated `npc_registry.py` and `rpg_prompt_builder.py` format rules to strictly enforce third-person limited perspectives, solving physical misalignments generated for ambiguous NPC cues (e.g. Hooded Figure).
- **Shop Equip Logic Constraints**: Auto-equip on `!rpg buy` now mirrors the strict rules of `!rpg equip`, fully rejecting mismatching core and advanced classes, returning the item safely to the inventory with a stern compatibility warning. Removed visual clutter of eligible class names inside the UI shop view.

---

## 3. Actionable Recommendations (Prioritized)

### ✅ All Identified Phase 2 Remediation Objectives Completed 
System is structurally isolated, tested under mock execution, and stabilized. All architectural debt has been securely paid and processed.