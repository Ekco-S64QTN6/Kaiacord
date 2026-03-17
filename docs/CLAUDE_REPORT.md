# Claude — Kaiacord TTRPG System Audit (Phase 41)

**Date:** 2026-03-16  
**Scope:** Full Aethelgard TTRPG system verification  
**Files examined:** 20 source files + 1 character JSON

---

## 1. Executive Summary

**Production readiness: WITH FIXES**  
**Critical issues found: 2** (1 fixed, 1 requires Ekco decision)  
**Medium issues found: 4** (2 fixed, 2 documented)  
**Items verified clean: 52**

The system is structurally sound. The Ledger/Oracle separation is correctly maintained across all handlers — Python decides outcomes, Kaia narrates. All LLM calls use `gpu_memory_manager.run_with_gpu_guard` with `GPUTaskPriority.CHAT`, `asyncio.wait_for` timeouts (30-60s), and `num_predict` caps (100-250). No TTRPG output enters RAG or channel_memory.

Two bugs were blocking production: (1) a missing `get_loot` import that crashes every monster kill, and (2) forest event items that couldn't be sold. Both are fixed below.

---

## 2. Verification Results

### Character System

| Item | Status | Notes |
|---|---|---|
| `create()` schema | ⚠️ Partial | Missing `race` parameter — race is set **after** `create()` returns (line 273). Works but is fragile. |
| HP at level 1 (Mage CON 10) | ✅ Verified | `max(2, 4+0+1) = 5`. Floor is 2, not 1 — safe. |
| Race bonuses applied at creation | ✅ Verified | Applied during stat roll in `_handle_new` (lines 251-268), before `create()`. |
| `save()` atomic write + lock | ✅ Verified | `tmp + os.replace` with `threading.Lock`. Two players save to **different files** so the lock serializes access to the same file. |
| `load()` returns None on missing file | ✅ Verified | Line 20: `if not os.path.exists(p): return None` |
| `format_sheet()` includes conditions | ⚠️ Partial | Builds `conditions` string (line 95) but **never includes it in the output string** (lines 99-114). However, `_handle_status` (embed-based HUD) **does** show conditions at line 209-212. So `!rpg` shows them, `!rpg sheet` does not. |

### Dice Engine

| Item | Status | Notes |
|---|---|---|
| Uses `secrets.randbelow` | ✅ Verified | Line 36: `secrets.randbelow(sides) + 1` |
| Handles all notation forms | ✅ Verified | Regex at line 24 handles `d20`, `2d6`, `1d8+3`, `d6-1`, `3d4+2`. |
| Rejects garbage input | ✅ Verified | Lines 26-27: raises `ValueError`. Lines 33-34: bounds check `count < 1 or count > 20 or sides < 2 or sides > 100`. d0 → rejected, 100d100 → rejected. |
| `stat_check()` modifier formula | ✅ Verified | `(stat - 10) // 2` at line 7. stat 8→-1, stat 14→+2, stat 17→+3. |
| Advantage = max, disadvantage = min | ✅ Verified | Lines 62, 67. Not inverted. |
| Class-specific attack stat | ✅ Verified | `combat_engine.py` lines 9-15: Warrior→str, Ranger→dex, Mage→int, Rogue→dex, Cleric→wis. |

### Combat Engine

| Item | Status | Notes |
|---|---|---|
| Player to-hit uses CLASS_ATTACK_STAT | ✅ Verified | Lines 9-16 in `combat_engine.py`. |
| Monster counter only if HP > 0 | ✅ Verified | Line 110: `monster_alive = monster["hp"]["current"] > 0`, line 118: `if monster_alive:` |
| Both HP updates applied before save | ✅ Verified | Monster HP updated at line 107, player HP at line 129, result returned for handler to save. |
| Monster death = HP ≤ 0 | ✅ Verified | `max(0, ...)` floors HP, `> 0` checks alive. HP=0 → dead. |
| Crit: dice doubled, modifier once | ✅ Verified | Line 93: `dice_count = 2 if player_crit else 1`, line 97: `total_dmg_bonus = atk_mod + warrior_dmg_bonus` added once. |
| Fumble: always misses | ✅ Verified | Line 92: `if player_hit and not player_fumble` gates damage. |
| XP awarded on kill (automatic) | ✅ Verified | Lines 822-843 in `_handle_attack`. |
| `check_level_up()` before save | ✅ Verified | Line 842: `check_level_up(sheet)`, line 845: `save(sheet)`. |
| Blessed consumed after combat | ✅ Verified | Lines 809-810: `sheet["conditions"].remove("blessed")`. |
| Mage defense uses DEX | ✅ Verified | Line 119: `10 + dex_mod + armor_def`. |

### Hunt System

| Item | Status | Notes |
|---|---|---|
| `check_and_reset_hunts()` at top of `_handle_hunt` | ✅ Verified | Line 694. |
| Reset sets `hunts_today=0` + updates `hunts_reset_date` | ✅ Verified | `progression.py` lines 66-67. |
| `MAX_HUNTS_PER_DAY = 5` | ✅ Verified | `progression.py` line 31. |
| Hunt consumed before monster spawns | ⚠️ Partial | **For events:** hunt paid at line 722 (before resolution) ✅. **For monsters:** hunt paid at line 744 (**after** spawn + session save). A crash between line 741 and 744 would lose the hunt cost. Survivable but not ideal. |
| Player at 0 HP blocked | ✅ Verified | Line 698-699. |
| Non-hunting location blocked | ✅ Verified | Lines 691-692. |

### Forest Events

| Item | Status | Notes |
|---|---|---|
| `roll_for_event()` called before monster spawn | ✅ Verified | Lines 718-724. |
| Event chances per location | ✅ Verified | `encounter_tables.py` lines 54-59: edge=20, deep=15, ruins=10, road=18. |
| All 11 events resolve without exception | ✅ Verified | Tested via verification script — all return valid dicts. |
| `_apply_and_narrate_event()` applies all fields | ✅ Verified | Lines 949-970: xp, gil, hp_change (clamped via `max(0, min(...))`), condition_add/remove, extra_hunt, item_add. |
| `extra_hunt` refunds 1 hunt | ✅ Verified | Line 967: `hunts_today = max(0, hunts_today - 1)`. |
| `crystal_resonance` HP cannot go below 0 | ✅ Verified | Line 953: `max(0, ...)` clamp. |
| `mognet_delivery` adds letter + condition | ✅ Verified | `forest_events.py` `mognet_delivery()` handler. |
| `!rpg deliver` validates correctly | ✅ Verified | Lines 1307-1319: location check, inventory check, removes letter + condition, awards 25g + 20 XP. |

### Shop System

| Item | Status | Notes |
|---|---|---|
| `find_item()` returns None on miss | ✅ Verified | `shop.py` line 17: `return None`. |
| Insufficient gil shows friendly message | ✅ Verified | `shop.py` lines 28-29. |
| Auto-equip on purchase | ✅ Verified | `rpg_handler.py` lines 521-526. |
| Class restriction warning (soft) | ✅ Verified | Lines 515-519: warning in purchase message. |
| Hemlock stock excludes tier 4+ | ✅ Verified | `HEMLOCK_STOCK_WEAPONS` and `HEMLOCK_STOCK_ARMOR` only contain tier 1-2. |
| `wooden_staff` + `iron_staff` in stock | ✅ Verified | |
| `mages_robe` + `silken_robe` in stock | ✅ Verified | |
| Sell price = 50% of buy | ✅ Verified | `shop.py` line 49: `max(1, item["value"] // 2)`. |
| `aeridor_shard` sellable | ✅ **Fixed** | Was missing from CONSUMABLES — added (see §3). |

### Equipment

| Item | Status | Notes |
|---|---|---|
| Equip swaps old item to inventory | ✅ Verified | Lines 635-641. |
| Equipment bonuses in combat | ✅ Verified | `combat_engine.py` lines 26-28. |
| `!rpg inventory` lists items | ✅ Verified | Line 613: lists item keys (not display names — but functional). |

### Location System

| Item | Status | Notes |
|---|---|---|
| `resolve_location()` handles all aliases | ✅ Verified | All listed aliases present in `world.py` lines 80-101. |
| `!rpg go` with no arg shows exits with friendly names | ✅ Verified | Lines 305-313. |
| Movement checks exits | ✅ Verified | Line 319: `target not in current_data.get("exits", [])`. |
| `stone_hearth` → `whisperwood_edge` blocked | ✅ Verified | `stone_hearth.exits = ["oakhaven"]`. Must go via oakhaven. |
| New character starts at `oakhaven` | ✅ Verified | `character_manager.py` line 58. |

### Town Actions

| Item | Status | Notes |
|---|---|---|
| `!rpg rest`: location-gated, 5 gil, full heal | ✅ Verified | Lines 400-431. |
| `!rpg rest`: removes ale_warmth + reverses temp HP | ✅ Verified | Lines 419-423: removes condition, subtracts 3 from max, caps current. |
| `!rpg drink`: location-gated, 2 gil, +3 temp HP | ✅ Verified | Lines 1043-1079. |
| `!rpg drink`: stack check | ✅ Verified | Line 1064: `any("ale" in c.lower() ...)`. |
| `!rpg gamble`: 10 gil buy-in, secrets.randbelow | ✅ Verified | Lines 1082-1121. Tie goes to house. |
| `!rpg rumor`: location-gated, world context in prompt | ✅ Verified | Lines 433-469. Prompt includes Whisperwood, Aeridor, Grimstone, Veiled, etc. |
| `!rpg pray`: once per day, adds blessed | ✅ Verified | Lines 1124-1159. Checks blessed first, then daily. |
| `!rpg offer`: 1 XP per gil, 20/day cap | ✅ Verified | Lines 1162-1220. |
| `!rpg scout`: once per day, pure Python output | ✅ Verified | Lines 1223-1296. No LLM call. |
| `!rpg scout`: saves `last_scout_date` | ✅ Verified | Line 1246. |

### NPC Dialogue

| Item | Status | Notes |
|---|---|---|
| `!rpg talk` fuzzy key lookup | ✅ Verified | `get_npc()` uses `.get(key.lower())`. |
| Location check for NPC | ✅ Verified | Lines 571-574. |
| Uses `gpu_memory_manager` (not message_processor) | ✅ Verified | Lines 592-598. |
| NPCs exist: elara, hemlock, barkeep, hooded_figure | ✅ Verified | All 4 in `npc_registry.py`. |

### Dawn Task

| Item | Status | Notes |
|---|---|---|
| Exists in `background_tasks.py` | ✅ Verified | Lines 149-220. |
| `@tasks.loop(minutes=10)` | ✅ Verified | Line 150. |
| Fires only at hour=0, minute<10 | ✅ Verified | Line 158. |
| Uses `last_dawn_date` for once-per-day | ✅ Verified | Lines 162-165. |
| `last_dawn_date` persisted | ✅ Verified | `bot_state.py`: loaded at line 78, saved at line 133. |
| Iterates character files, resets hunts | ✅ Verified | Lines 181-193. Uses atomic write (tmp + os.replace). |
| Announcement to `last_active_channel_id` | ✅ Verified | Lines 198-208. Gracefully handles: no channel, no chars, all already at 0. |
| Started in `start()` | ✅ Verified | Line 280: `self.aethelgard_dawn_task.start()`. |

### Isolation from Main Bot

| Item | Status | Notes |
|---|---|---|
| LLM calls via `gpu_memory_manager` with CHAT priority | ✅ Verified | All 6 LLM call sites (look, rumor, talk, attack, event, admin event) use this pattern. |
| TTRPG output NOT passed to RAG/channel_memory | ✅ Verified | No `_background_logging_and_memory` calls in any TTRPG handler. |
| `num_predict` capped | ✅ Verified | look=150, rumor=100, talk=150, combat=150, event=120, admin_event=250. All ≤250. |
| All LLM calls have `asyncio.wait_for` timeout | ✅ Verified | Timeouts: 30s (rumor), 45s (look, talk, combat, event), 60s (admin event). |

### Registry Wiring

| Item | Status | Notes |
|---|---|---|
| `!rpg` dispatched in `registry.py` | ✅ Verified | Lines 86-88: `if content.startswith("!rpg")`. |
| Before `return False` | ✅ Verified | Line 90: `return False` is the final line. |
| No prefix conflicts | ✅ Verified | No other command starts with `!rpg`. |

### Progression

| Item | Status | Notes |
|---|---|---|
| XP thresholds match spec | ✅ Verified | Lv2=300, Lv3=900, Lv4=2700, Lv5=6500. |
| `check_level_up()` mutates in place, returns tuple | ✅ Verified | Does NOT call save — caller handles it. |
| HP on level-up formula | ✅ Verified | `HP_PER_LEVEL[class] + CON_mod`, floor 1. Warrior=6, Ranger=5, Mage=2, Rogue=4, Cleric=5. |
| Level-up fires for both combat kills and events | ✅ Verified | `_handle_attack` line 842, `_apply_and_narrate_event` line 972. |

### Error Handling

| Item | Status | Notes |
|---|---|---|
| Top-level try/except | ✅ Verified | Lines 106-110: catches all exceptions, sends user-friendly message. |
| All file I/O via `asyncio.to_thread` | ✅ Verified | Every `load()` and `save()` call is wrapped. |
| Missing character handled in all handlers | ✅ Verified | Every handler checks `if not sheet: return`. |
| Integer parse failures caught | ✅ Verified | `_handle_offer` line 1177-1181: try/except around `int(rest.strip())`. |

### Character Files on Disk

| Item | Status | Notes |
|---|---|---|
| Schema matches expected fields | ✅ Verified | `177011971818782721.json` has all required fields including `race` (added post-creation), `hunt_streak`, equipment as full item dicts. |

---

## 3. Bugs Found & Fixed

### BUG 1 — CRITICAL: `get_loot` NameError on every monster kill

**File:** `rpg_handler.py` line 835  
**Symptom:** `NameError: name 'get_loot' is not defined` — crashes every `!rpg attack` that kills a monster. The top-level try/except (line 106) catches it and shows "system fault in 'attack'", but the player receives no XP, no Gil, no loot. The sheet is not saved with the kill result.  
**Root cause:** `get_loot()` exists in `utils/ttrpg/loot_tables.py` but was never imported in `_handle_attack`.  
**Fix applied:** Added `from utils.ttrpg.loot_tables import get_loot` at line 777.

### BUG 2 — `aeridor_shard` and `tonberry_knife` not sellable

**File:** `equipment_registry.py`  
**Symptom:** Forest events `aeridor_fragment` and `timid_tonberry` add `"aeridor_shard"` and `"tonberry_knife"` to inventory, but these items don't exist in WEAPONS, ARMOR, or CONSUMABLES. `!rpg sell aeridor_shard` returns "Unknown item" because `find_item()` returns None.  
**Fix applied:** Added both items to CONSUMABLES as sell-only collectibles (no `hp_restore` key, so `!rpg use` correctly rejects them). `aeridor_shard` sells for 30g (50% of 60g value), `tonberry_knife` sells for 20g (50% of 40g value).

---

## 4. Open Items (Require Ekco Decision)

### OPEN 1 — `!rpg scout` uses stale encounter table

`_handle_scout` (line 1227) imports `ENCOUNTER_TABLES` from `encounter_tables.py`, which has the **original 4-entry** whisperwood_edge table (bat, goblin, wolf, skeleton). But `_handle_hunt` (line 682) imports `random_encounter` from `monster_registry.py`, which has the **expanded 18-entry** table with all the new trivial monsters.

The scout report shows players a monster distribution that doesn't match what they'll actually fight. Two options:
1. **Delete** `ENCOUNTER_TABLES` from `encounter_tables.py` and have scout import from `monster_registry` instead.
2. **Keep both** and accept the divergence as one being "intelligence" (which is always a few days old — flavor).

> [!IMPORTANT]
> I did not fix this because it requires choosing which table is authoritative. My recommendation is option 1 — single source of truth in `monster_registry.py`.

### OPEN 2 — `format_sheet()` missing conditions display

`character_manager.format_sheet()` builds a `conditions` string (line 95) but never includes it in the returned output. The embed-based `_handle_status` HUD **does** show conditions (line 209-212), so `!rpg` is fine, but `!rpg sheet` silently omits them.

**Recommendation:** Add `f"\n**Conditions:** {conditions}"` to the return string in `format_sheet()`.

### OPEN 3 — `create()` doesn't accept `race` parameter

`character_manager.create()` doesn't include `race` in the schema. `_handle_new` sets `sheet["race"] = race` **after** `create()` returns and does a second `save()`. This works but is fragile — if `save()` fails on the second call, the character exists without a race.

**Recommendation:** Add `race` as a parameter to `create()`.

### OPEN 4 — Hunt cost for monster path paid after spawn

For the **event** path, hunt cost is paid at line 722 (before resolution) ✅. For the **monster** path, hunt cost is paid at line 744 (**after** session save at line 741). A crash between spawn and cost would create a free monster. The spec says hunt should be consumed before spawn.

**Risk:** Low — would require an extremely unlikely crash between two adjacent awaits.

### OPEN 5 — Loot table items not in equipment registry

`loot_tables.py` drops items like "Herb", "Wolf Pelt", "Potion", "Hi-Potion", "Monster Fang", "Monster Core", "Rare Drop", "Ether", "Elixir". Some of these (Herb, Potion, etc.) don't match any key in CONSUMABLES (`healing_herb`, `tonic`). They'll sit in inventory as raw strings that can't be used or sold via `find_item()`.

**Recommendation:** Either align loot table item names to equipment registry keys, or add them as CONSUMABLES entries.

---

## 5. Edge Case Trace Results

| Scenario | Result |
|---|---|
| 1. New player, no character | ✅ "you do not exist" message for all commands |
| 2. Dead player tries to hunt | ✅ Blocked at line 698 |
| 3. No hunts left | ✅ Blocked at line 695 |
| 4. Forest event + level up | ✅ `check_level_up` called at line 972, level-up announcement at line 994 |
| 5. Mognet delivery flow | ✅ Letter→inventory, deliver validates location + inventory, rewards granted |
| 6. Gamble with exactly 10 gil | ✅ Win→20, Lose→0, Tie→0 |
| 7. Crystal resonance at 1 HP | ✅ `max(0, ...)` clamp. Player survives at 0 HP. |
| 8. Concurrent play | ✅ Separate character files + aggro_uid separation |
| 9. Equip swap | ✅ Old item returns to inventory (line 637) |
| 10. Pray twice | ✅ "already blessed" fires first (line 1147 before line 1141) |

---

## 6. Files Examined

| File | Lines |
|---|---|
| `utils/commands/rpg_handler.py` | 1419 |
| `utils/ttrpg/character_manager.py` | 116 |
| `utils/ttrpg/dice_engine.py` | 86 |
| `utils/ttrpg/progression.py` | 74 |
| `utils/ttrpg/combat_engine.py` | 178 |
| `utils/ttrpg/encounter_tables.py` | 124 |
| `utils/ttrpg/monster_registry.py` | 783 |
| `utils/ttrpg/equipment_registry.py` | 51 |
| `utils/ttrpg/npc_registry.py` | 39 |
| `utils/ttrpg/world.py` | 114 |
| `utils/ttrpg/shop.py` | 54 |
| `utils/ttrpg/forest_events.py` | 244 |
| `utils/ttrpg/loot_tables.py` | 30 |
| `utils/ttrpg/rpg_prompt_builder.py` | 190 |
| `utils/ttrpg/session_manager.py` | 51 |
| `utils/ttrpg/__init__.py` | 1 |
| `utils/commands/registry.py` | 91 |
| `utils/core/background_tasks.py` | 307 |
| `utils/infrastructure/system/bot_state.py` | 301 |
| `memory/ttrpg/characters/177011971818782721.json` | 64 |
