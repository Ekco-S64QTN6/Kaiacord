# Aethelgard TTRPG — System Status Report
*Last updated: April 11, 2026 · Comprehensive code review + bug fixes*

---

## 1. Executive Summary

The Aethelgard TTRPG subsystem is architecturally sound: deterministic Python handles all game state, the LLM (Kaia) handles narration only, and the concurrent locking in `character_manager.py` / `session_manager.py` is well-designed. The dungeon generation (MST + loop corridors), encounter pipeline, alchemy discovery system, and class proc system are all robust.

The recent user-reported bugs and balance issues have been **fixed this session**:
- 🔴 "The Wealthy" title used a static threshold (1000g on-hand) — now awards to the single richest player by total gil (on-hand + bank)
- 🔴 Consumable use inside dungeons fell back to Status view — now preserves Dungeon navigation/combat views
- 🔴 Massive economy inflation and equipment stat inversions — normalized all stats, explicitly mapped classes on gear, halved base values, and slashed shop sell rate from 50% to 25%.

**Previously fixed (prior session):**
- 🔴 Banking crash (`load_housing` missing import)
- 🔴 Warden `forest_def_bonus` never fired
- 🔴 Solstice offering XP multiplier not applied
- 🟠 Training dummy didn't grant hunts when pool was full
- 🟠 `PERMANENT_CONDITIONS` duplicated across two files
- 🟡 Hunt count had no hard ceiling
- 🟡 Dungeon combat missing furniture ATK bonus
- 🗑️ Dead code removed: `balance_model.py`, `LOCATION_ACTIONS`, `TIER_COUNTS`

**Remaining open items (not bugs — architectural debt):**
- Housing I/O blocks event loop (synchronous `threading.Lock`, no `asyncio.to_thread`)
- Fishing economy mythic values uncapped (125,000g possible)
- `rpg_handler.py` at ~7,200 lines needs decomposition
- `armor_penalty` weather effect unwired
- Vault Chest furniture bonus now does nothing (bank cap removed)

---

## 2. Bug Inventory

### ✅ RESOLVED — Fixed This Session

| ID | Sev | Bug | File | Fix |
|---|---|---|---|---|
| BUG-10 | 🔴 | "the Wealthy" title checks only on-hand `gil >= 1000` instead of ranking players by total wealth | `class_advancement.py:313` | Replaced static lambda with `_is_wealthiest()` that scans all character sheets, compares on-hand + bank. Requires 1000g minimum + must be richest player. |
| BUG-11 | 🔴 | Consumable use inside dungeon falls back to Status view, stranding players without navigation | `rpg_handler.py:992` | Rebuilt `_get_active_view` to query both overworld sessions and active dungeon states, restoring dungeon buttons properly. |
| BAL-01 | 🔴 | Wild equipment stat inversions + economy inflation via dungeon gear dumping | `equipment_registry.py` & `shop.py` | Slashed shop sell rate to 25%, halved T4/T5 base values, normalized all armor/weapon math, explicitly added advanced classes to items, and added Stardust Rod (T5). |
### ✅ RESOLVED — Fixed in Prior Sessions

| ID | Bug | Fix |
|---|---|---|
| BUG-01 | `NameError: load_housing` in bank deposit callback | Added local import inside closure |
| BUG-02 | Warden `forest_def_bonus` checked but never defined | Added `"forest_def_bonus": 2` to Warden bonuses |
| BUG-03 | Solstice offering `XP_MULT` computed but not applied | `s["xp"] += eligible * XP_MULT` |
| BUG-04 | Training dummy no-op when hunt pool at 0 | Always decrements `hunts_today` (floor 0) |
| BUG-06 | `PERMANENT_CONDITIONS` dual-defined | Single source in `progression.py` |
| BUG-07 | Hunt count could stack to 9+ | Hard cap at `MAX_HUNTS_CEILING = 8` |
| BUG-08 | Dungeon combat missing furniture ATK bonus | Added `home_atk` to dungeon `atk_mod_global` |
| BUG-09 | Cleric dead `atk_vs_undead` branch | Removed dead conditional |
| PREV-01–10 | Various furniture/UI wiring fixes | See prior report |

### 🟠 OPEN — Non-Critical

---

**OPEN-01 · `housing.py` synchronous I/O blocks the event loop**
`utils/ttrpg/housing.py`, lines 96–112

`load_housing()` and `save_housing()` use `threading.Lock()` + synchronous `open()`/`json.load()`. Unlike `character_manager.py` which wraps in `asyncio.to_thread()`, housing I/O blocks the Discord event loop.

**Impact:** Latency spikes under concurrent player activity.
**Fix:** Wrap in `asyncio.to_thread()` and update ~40 call sites. Effort: ~3 hours.

---

**OPEN-02 · `armor_penalty` weather effect unwired**
`calendar.py`, Summer "Sweltering" weather

Defines `{"type": "armor_penalty", "value": -2}` but no handler checks for this effect type.

**Fix:** Add check in hunt handler. Effort: 30 min.

---

**OPEN-03 · Vault Chest furniture now inert**
`furniture.py`, `bank_cap: +500`

Bank cap was removed per user request. The Vault Chest's bonus (`bank_cap: +500`) no longer does anything.

**Fix:** Repurpose to a new bonus (e.g., interest rate, sell price bonus) or remove from furniture registry. Effort: 15 min.

---

**OPEN-04 · `embered`/`fortified` buffs consumed even on miss**
`combat_engine.py:399-404`

Firebrew (+2 ATK) and Ironbark Tonic (+2 DEF) conditions are stripped at the end of *every* combat round, including rounds where the player is stunned or misses. Description says "until next combat" but implementation is "for one round."

**Impact:** Players feel cheated when a buffed stun round wastes their potion.
**Fix:** Only consume after the round where the buff actually applied. Effort: 20 min.

---

**OPEN-05 · `action_log` field in session_manager never written to**
`session_manager.py:62`

Created in `create_session()` as an empty list, never populated anywhere.

**Impact:** Dead data field. Low priority.

---

**OPEN-06 · Bank deposit "All" button captures stale amount**
`rpg_handler.py:5740`

The deposit callback captures `actual = sheet["gil"]` at embed creation time. If the player earns or spends gil before clicking, the amount is stale. Safe (overdraft check exists) but label is misleading.

**Fix:** Re-read sheet inside callback. Effort: 10 min.

---

## 3. Balance Analysis — Current State

### 3.1 Economy — Fishing Singularity (STILL OPEN)

The mythic fishing economy remains uncapped:
- `Heart of Aeridor`: sell_value=50,000g → up to **125,000g** with multiplier
- Crystal Bait (100g) gives ~3% mythic chance → expected value ~2,625g/cast
- This eclipses days of hunting/dungeon farming in a single cast

**Recommended caps:**

| Category | Current Max | Proposed Max |
|---|---|---|
| Mythic | 125,000g | 2,500g |
| Legendary | ~5,000g | 800g |
| Epic | ~1,000g | 300g |

### 3.2 Combat Balance — Healthy

- **DEF soft-cap** (`level * 1.5 + 12`): Working correctly.
- **Gear DEF soft-cap** (`first 10 full, remainder halved`): Working correctly.
- **Shadowknight lifesteal**: Capped at `min(6, int(dmg * 0.15))`. Balanced.
- **Warden**: `forest_def_bonus: 2` now firing. Still weakest advanced class — consider adding `heal_on_combat_end: 5`.
- **Hunt ceiling**: Hard-capped at 8.
- **Embered/Fortified**: Consumed after one round, not "until next combat." See OPEN-04.

### 3.3 Class Balance

| Class | Role | Status |
|---|---|---|
| Hunter | Crit DPS | ✅ Balanced (crit threshold 18, +2 ATK) |
| Shadowknight | Sustain DPS | ✅ Balanced (lifesteal capped at 6) |
| Trickster | Gamble edge | ✅ Balanced |
| Wizard | INT burst | ✅ Balanced (+3 flat bonus on hit) |
| Ranger | Hunt economy | ✅ Balanced |
| High Priest | WIS healer | ✅ Balanced (1.5x potion heal) |
| Paladin | Tank/undead slayer | ✅ Balanced |
| Warden | Tank | ⚠️ Weakest — `forest_def_bonus` works but needs identity buff |
| Shaman | Nature healer | ✅ Balanced |
| Shadowblade | Crit assassin | ✅ Balanced (+4 on crit) |
| Necromancer | Undead specialist | ✅ Balanced |

### 3.4 Furniture Economy — All Bonuses Wired

| Furniture | Cost | Bonus | Status |
|---|---|---|---|
| Weapon Rack | 100g | `home_atk: +1` | ✅ Overworld + dungeon |
| Trophy Mount | 250g | `local_atk: +2` | ✅ Home location only |
| Bookshelf | 200g | `talk_xp: +5` | ✅ |
| Stone Throne | 5,000g | `home_cha: +5` | ✅ |
| War Map | 3,000g | `home_scout: 1` | ✅ |
| Vault Chest | 1,500g | `bank_cap: +500` | ⚠️ Inert (bank cap removed) |
| Alchemy Table | 500g | `home_brewing: 1` | ✅ |
| Training Dummy | 400g | `daily_training: 1` | ✅ |
| Shrine Replica | 1,200g | `home_pray: 1` | ✅ |

### 3.5 Title System — Fixed

| Title | Condition | Status |
|---|---|---|
| the Unkillable | ≥10 deaths | ✅ |
| the Unmarked | 0 deaths + level ≥5 | ✅ |
| **the Wealthy** | **Richest player (on-hand + bank, min 1000g)** | ✅ **FIXED** |
| the Proven | ≥3 completed quests | ✅ |
| Hero of Oakhaven | reputation ≥100 | ✅ |
| the Unwelcome | reputation <-50 | ✅ |

**Note:** SPECIAL_TITLES are checked first and take priority. "the Unkillable" (10+ deaths) beats "the Wealthy" etc. This means a player cannot hold two special titles simultaneously — only the first match wins. This is intentional but may surprise players.

### 3.6 Loot Tables — Recently Adjusted

| Item | Deadly Weight | Boss Weight |
|---|---|---|
| Staff of the Magi | 3 (was 2) | 5 (was 4) |
| Holy Avenger | 3 (was 2) | 5 (was 4) |
| Vorpal Sword | 3 (was 2) | 5 (was 4) |

---

## 4. Code Quality Assessment

### 4.1 `rpg_handler.py` — ~7,200 Lines (Critical)

This is the #1 maintainability risk. Contains 40+ handlers, 8 View subclasses, 3 Modals, 70+ inline imports, and 3 competing button callback patterns.

### 4.2 Housing I/O Architecture Mismatch

| File | Lock Type | Async Wrapper | Event Loop Safe |
|---|---|---|---|
| `character_manager.py` | `threading.Lock` + `asyncio.Lock` | `asyncio.to_thread()` | ✅ |
| `session_manager.py` | `threading.Lock` + `asyncio.Lock` | `asyncio.to_thread()` | ✅ |
| **`housing.py`** | `threading.Lock` only | **None** | **❌ Blocks** |

### 4.3 `shop.py` reverse alias lookup is O(n)

Line 101: `reverse_aliases = {v: k for k, v in ALIASES.items()}` — rebuilds the entire reverse dict on every `find_item` call. Should be precomputed at module level.

### 4.4 `combat_engine.py` imports inside function body

Lines 30, 73, 156, 187, 323, 345, 378 — six `from ... import ...` statements inside `_resolve_combat`. These are needed to avoid circular imports but add latency per combat round.

---

## 5. Performance Review

No critical bottlenecks for 6 players. Minor improvements:

| Issue | Impact | Fix | Effort |
|---|---|---|---|
| Housing sync I/O (OPEN-01) | Blocks event loop | `asyncio.to_thread()` | 3 hours |
| `find_item` rebuilds reverse alias dict | Wasted cycles per call | Precompute at module level | 15 min |
| `_is_wealthiest` reads all char files | Disk I/O on every title display | Cache result with TTL or compute in background task | 30 min |
| 6 imports inside `_resolve_combat` | Import overhead per combat round | Pre-import at module level where safe | 20 min |

---

## 6. Incomplete Features / Dead Code

### Dead Code — Resolved
| Item | Status |
|---|---|
| `balance_model.py` | Deleted |
| `LOCATION_ACTIONS` | Deleted |
| `TIER_COUNTS` | Deleted |
| Cleric `atk_vs_undead` branch | Removed |
| `DAWN_PERMANENT` duplicate | Replaced with import |

### Remaining Stubs
| Item | File | Status |
|---|---|---|
| `action_log` field | `session_manager.py:62` | Created, never written |
| `caravan_active` world state | `world_state.py:17` | Set but doesn't gate caravan access |
| `SEASONAL_ITEMS` in calendar.py | `calendar.py:329-355` | Duplicate of data in equipment_registry |
| Vault Chest `bank_cap` | `furniture.py` | Inert — bank cap removed |

---

## 7. Actionable Recommendations

### 🔴 Priority 1 — Immediate

| ID | Action | File | Effort |
|---|---|---|---|
| R-01 | Cap mythic fish sell values | `fishing.py` | 30 min |
| R-02 | Add daily fishing sell cap | `fishing_handler.py` | 1 hour |
| R-03 | Repurpose Vault Chest bonus | `furniture.py` | 15 min |

### 🟠 Priority 2 — Near Term

| ID | Action | File | Effort |
|---|---|---|---|
| R-04 | Wire `armor_penalty` weather effect | `rpg_handler.py` | 30 min |
| R-05 | Fix `embered`/`fortified` consumption (OPEN-04) | `combat_engine.py` | 20 min |
| R-06 | Buff Warden: add `heal_on_combat_end: 5` | `class_advancement.py` | 15 min |
| R-07 | Cache `_is_wealthiest` result with TTL | `class_advancement.py` | 30 min |
| R-08 | Precompute reverse alias dict in `shop.py` | `shop.py` | 15 min |

### 🟡 Priority 3 — Technical Debt

| ID | Action | File | Effort |
|---|---|---|---|
| R-09 | Wrap `housing.py` I/O in `asyncio.to_thread()` | `housing.py` + 40 call sites | 3 hours |
| R-10 | Remove `SEASONAL_ITEMS` duplicate from `calendar.py` | `calendar.py` | 10 min |
| R-11 | Remove dead `action_log` field from session template | `session_manager.py` | 5 min |

### 🔵 Priority 4 — Architectural (Multi-Session)

| ID | Action | Effort |
|---|---|---|
| R-12 | Decompose `rpg_handler.py` into sub-handler modules | 3–5 sessions |

---

## 8. Files Modified This Session

| File | Changes |
|---|---|
| `utils/ttrpg/class_advancement.py` | Rewrote "the Wealthy" title to scan all players by total gil (on-hand + bank), minimum 1000g threshold |
| `utils/commands/rpg_handler.py` | Replaced 7× `_make_status_view` → `_make_hunt_status_view` in `_handle_use` so all consumable responses include Hunt button |
| `utils/ttrpg/loot_tables.py` | Bumped Staff of the Magi / Holy Avenger / Vorpal Sword drop weights |

**Also this session (prior turn):**
| File | Changes |
|---|---|
| `utils/commands/rpg_handler.py` | Removed bank cap; removed loot drop broadcasts; removed `LOCATION_ACTIONS` |
| `utils/ttrpg/class_advancement.py` | Added Warden `forest_def_bonus`; removed dead Cleric branch |
| `utils/ttrpg/progression.py` | Exported `PERMANENT_CONDITIONS`; added hunt ceiling |
| `utils/core/background_tasks.py` | Unified `DAWN_PERMANENT` import |
| `utils/ttrpg/monster_registry.py` | Deleted `TIER_COUNTS` |

---

**Net assessment:** All user-reported bugs (banking crash, title system, use-item buttons) are resolved. The system is stable for active play. The two remaining strategic priorities are: (1) capping the fishing economy, and (2) decomposing `rpg_handler.py`.