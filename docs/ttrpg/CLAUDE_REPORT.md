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

# Aethelgard TTRPG — Comprehensive Code Review
*Full source analysis across 42 files · April 2026*

---

## 1. Executive Summary

The Aethelgard system is architecturally sound in its core principle—deterministic Python handles all state, LLM handles narration only—and the combat/progression math is largely correct. However, the codebase carries significant accumulated debt. Six bugs cause **complete feature failures** (players pay real gil for furniture that silently does nothing; weather never actually modifies combat). The economy has an existential flaw in the fishing system where a single mythic catch can deliver 125,000g, rendering the entire hunting economy irrelevant. `rpg_handler.py` has grown to ~7,500 lines and is approaching unmaintainability. On the positive side: the concurrent locking architecture in `character_manager.py` is well-designed, dungeon generation is elegant, and the event/encounter pipeline is robust.

**Priority summary:** 5 critical bugs to fix now, 9 dead furniture features to wire up, 1 economy collapse to cap, and 1 file to decompose before it becomes unworkable.

---

## 2. Bug Inventory

### 🔴 CRITICAL — Causes crashes or total feature failure

---

**BUG-01 · `BiteView.on_timeout()` uses defunct bait key**
`fishing_handler.py`, lines in `on_timeout()`

```python
# CURRENT (broken) — bait_count was migrated away
bait_count = fishing_stats.get("bait_count", 0)
if bait_count > 0:
    fishing_stats["bait_count"] = bait_count - 1
```

The entire system migrated to `bait_stock` via `patch_fishing.py`, but `on_timeout` was never updated. When a fish escapes, bait is **never consumed**. Players can fish indefinitely after the first pack runs dry on misses.

**Fix:**
```python
# In BiteView.on_timeout(), replace the bait block with:
if "bait_count" in fishing_stats:
    old_bait = fishing_stats.get("bait", "earthworm")
    fishing_stats.setdefault("bait_stock", {})[old_bait] = fishing_stats.pop("bait_count", 0)
bait_stock = fishing_stats.get("bait_stock", {})
current_bait = fishing_stats.get("bait", "earthworm")
if bait_stock.get(current_bait, 0) > 0:
    bait_stock[current_bait] -= 1
fishing_stats["bait_stock"] = bait_stock
```

---

**BUG-02 · `log_debug` called but never imported in `background_tasks.py`**
`utils/core/background_tasks.py`, inside `run_news_update()`

```python
log_debug(f"Invoking {script_path} via {sys.executable}")
```

`log_debug` is not in the import list at the top of the file (`log_action, log_success, log_error, log_info, log_warning` only). This causes a `NameError` crash on every news refresh invocation, silently killing that background task.

**Fix:** Add `log_debug` to the import:
```python
from utils.infrastructure.logging.kaia_logger import (
    log_action, log_success, log_error, log_info, log_warning, log_debug
)
```

---

**BUG-03 · `DungeonView` status button passes raw `interaction` as `msg`**
`rpg_handler.py`, `DungeonView.__init__()` status button callback

```python
async def _status_cb(interaction: discord.Interaction):
    ...
    # BUG: passes raw interaction object as the 'msg' parameter
    await _handle_status(self._ctx, interaction, _make_interaction_send(interaction), ...)
```

`_handle_status` calls `msg.channel.send(...)` on its second parameter. A raw `interaction` object has no `.channel.send()` method compatible with this usage—it silently fails or throws `AttributeError` depending on which attribute is accessed first. Every "Status" button press inside a dungeon is broken.

**Fix:**
```python
async def _status_cb(interaction: discord.Interaction):
    if str(interaction.user.id) != self._uid:
        try: await interaction.response.send_message("Not yours.", ephemeral=True)
        except discord.NotFound: pass
        return
    try:
        await interaction.response.defer()
    except discord.NotFound:
        pass
    fake = _InteractionMsg(interaction)
    await _handle_status(
        self._ctx, fake, _make_interaction_send(interaction),
        "", self._uid, self._uname, self._is_owner
    )
```

---

**BUG-04 · `voice_of_silence_armor` defined twice with conflicting stats**
`utils/ttrpg/equipment_registry.py`

The ARMOR dict contains two definitions of `"voice_of_silence_armor"`. Python silently overwrites the first with the second:

| | First definition | Second definition (wins) |
|---|---|---|
| `defense_bonus` | 7 | **11** |
| `stat_bonus` | `{"wis": 3}` | **absent** |
| `hp_bonus` | 8 | **absent** |

Players equipping "Voice of Silence Armor" get +11 DEF flat instead of +7 DEF, +3 WIS, +8 HP. The WIS bonus is particularly significant for Clerics/Shamans. The class progression section at the bottom of the Cleric armor block overwrites the correctly-specced version higher up.

**Fix:** Delete the second definition (in the Cleric class progression section). It is identical except for the stripped bonuses.

---

**BUG-05 · Weather effects never propagate to world state**
`utils/core/background_tasks.py`, dawn task

```python
effect = weather.get("effect")
if effect:
    if "atk" in effect: state["atk_mod"] += effect["atk"]    # key never exists
    if "def" in effect: state["def_mod"] += effect["def"]    # key never exists
    if "xp"  in effect: state["xp_mult"] *= effect["xp"]    # key never exists
    if "gil" in effect: state["gil_mult"] *= effect["gil"]   # key never exists
```

Weather effects in `calendar.py` use `{"type": "xp_bonus", "value": 5}` format. The dawn task checks for literal keys `"atk"`, `"def"`, `"xp"`, `"gil"` which never exist. `world_state.atk_mod` and `world_state.def_mod` are always 0. **All weather bonuses and penalties are silently ignored.** The Autumn "clear" `+5 XP` per kill, Winter "frost" `+3 Gil`, Summer "hot" HP penalty from heavy armor—none of these ever fire.

**Fix:**
```python
effect = weather.get("effect")
if effect:
    effect_type  = effect.get("type", "")
    effect_value = effect.get("value", 0)
    if effect_type == "xp_bonus":
        state["xp_mult"] = state.get("xp_mult", 1.0) + (effect_value / 100.0)
    elif effect_type == "gil_bonus":
        state["gil_mult"] = state.get("gil_mult", 1.0) + (effect_value / 100.0)
    elif effect_type == "armor_penalty":
        state["def_mod"] = state.get("def_mod", 0) + effect_value
    # encounter_mod, level_gate, scout_blocked handled at point-of-use in handlers
```

---

### 🟠 HIGH — Feature completely non-functional

---

**BUG-06 · Nine furniture bonuses purchased but never applied**
`utils/ttrpg/furniture.py` defines bonuses; none of the below are connected to game logic:

| Furniture | Cost | Bonus Type | Dead Because |
|---|---|---|---|
| Weapon Rack | 100g | `home_atk: +1` | Not read by `combat_engine.py` |
| Trophy Mount | 250g | `local_atk: +2` | Not read by `combat_engine.py` |
| Bookshelf | 200g | `talk_xp: +5` | Not applied in `_handle_talk` |
| War Map | 3,000g | `home_scout: 1` | Not checked in `_handle_scout` |
| Vault Chest | 1,500g | `bank_cap: +500` | Not enforced in `_handle_bank_deposit` |
| Stone Throne | 5,000g | `home_cha: +5` | Not applied to NPC/shop CHA calc |

Players pay real gil for furniture whose description explicitly states a bonus they never receive. Wiring these up is largely mechanical.

**Fixes (each is a small targeted change):**

```python
# furniture.py/combat_engine.py — home_atk / local_atk
# In _resolve_combat(), after pet_bonuses:
furniture_bonuses = get_home_bonuses(load_housing(uid)) if uid else {}
home_atk_bonus = furniture_bonuses.get("home_atk", 0)
local_atk_bonus = furniture_bonuses.get("local_atk", 0) if sheet.get("location") == home_location else 0
attack_mod += home_atk_bonus + local_atk_bonus

# _handle_talk() — talk_xp
# After saving sheet post-talk, add:
furniture_bonuses = get_home_bonuses(load_housing(uid))
talk_xp_bonus = furniture_bonuses.get("talk_xp", 0)
if talk_xp_bonus:
    sheet["xp"] += talk_xp_bonus
    await save(sheet)

# _handle_scout() — home_scout
housing = load_housing(uid)
home_bonuses = get_home_bonuses(housing) if housing else {}
if sheet.get("location") != "watchtower" and not home_bonuses.get("home_scout"):
    return await msg.channel.send(...)  # existing location check

# _handle_bank_deposit() — bank_cap
from utils.ttrpg.furniture import get_home_bonuses
from utils.ttrpg.housing import load_housing
housing = load_housing(uid)
bonus = get_home_bonuses(housing) if housing else {}
base_cap = 10000  # baseline bank cap
cap = base_cap + bonus.get("bank_cap", 0)

# _handle_talk() — home_cha
# Pass furniture cha bonus into the context dict:
cha_mod += furniture_bonuses.get("home_cha", 0) if sheet.get("location") == "housing_district" else 0
```

---

**BUG-07 · Gilded mushroom death mechanic is text-only**
`utils/ttrpg/farming.py`, `_handle_water_crops`

The crop data specifies `"no_water": True` with the description "watering kills it," but `_handle_water_crops` unconditionally waters every plot:

```python
for p in plots:
    if not p.get("watered_today"):
        p["watered_today"] = True    # mushroom gets watered, nothing happens
        p["watered_count"] = p.get("watered_count", 0) + 1
```

**Fix:** Skip (and kill) `no_water` crops:
```python
for p in plots:
    crop_data = CROPS.get(p.get("crop_key", ""), {})
    if crop_data.get("no_water"):
        # Watering a gilded mushroom kills it
        plots_to_remove.append(p)  # collect for removal after loop
        killed_count += 1
        continue
    if not p.get("watered_today"):
        p["watered_today"] = True
        p["watered_count"] = p.get("watered_count", 0) + 1
        watered_count += 1
```

---

**BUG-08 · Moogle weekly delivery has a race condition at midnight**
`utils/core/background_tasks.py`

The Monday moogle delivery checks `pet.get("fed_today")` in housing files. However, `progression.check_and_reset_hunts()` (triggered by `character_manager.load()`) resets housing `fed_today` flags as part of the daily reset. If any player loads their character at exactly midnight on Monday—common if someone is playing—the `reset_daily_pets()` call fires and clears `fed_today` to `False` before the dawn task's moogle check reaches their housing file. Delivery silently skipped.

**Fix:** Replace the `fed_today` check with a weekly timestamp:
```python
# In housing files, track last delivery date
from datetime import date
today = date.today().isoformat()
for h in all_housing:
    if h.get("last_moogle_delivery") == today:
        continue  # already delivered today
    for pet in h.get("pets", []):
        if pet["key"] == "moogle":
            # Check if moogle was active (owned >= 1 day)
            if pet.get("days_owned", 0) >= 1:
                loot = get_loot("easy")
                if loot:
                    h.setdefault("mailbox", []).append({...})
                    h["last_moogle_delivery"] = today
                    save_housing(h)
                    break
```

---

### 🟡 MEDIUM — Incorrect behavior in specific conditions

---

**BUG-09 · `PERMANENT_CONDITIONS` / `DAWN_PERMANENT` defined independently in two files**

`progression.py`: `PERMANENT_CONDITIONS = {"blessed", "mognet_pending"}`
`background_tasks.py`: `DAWN_PERMANENT = {"blessed", "mognet_pending"}`

These must stay in sync forever but have no shared source of truth. Define once in `progression.py`, import in `background_tasks.py`.

---

**BUG-10 · `_handle_brew` button rows can overflow with many recipes**

With 10 known recipes, `row=i % 4` distributes buttons across rows 0–3. The `_make_status_btn` appended without a `row` argument auto-places into the first non-full row (likely row 0 or 1), creating an invisible collision. Should be `row=4` explicitly:
```python
view.add_item(_make_status_btn(ctx, uid, uname, is_owner, row=4))
```

---

**BUG-11 · `_handle_accept` duel HP threshold inconsistency**

Duel refuses if `<= 1` HP but blackout triggers at `<= 0`. A player at exactly 1 HP is blocked from dueling but also blocked from most other combat by UX. These should align: `< 1` for duel refusal.

---

**BUG-12 · `_dungeon_combat_round` loot fallback only fires if no item dropped for 5 attempts but CAN be None from a single roll**

```python
gear = get_gear_loot(tier)
attempts = 0
while not gear and attempts < 5:
    gear = get_gear_loot(tier)
    attempts += 1
```

`get_gear_loot` CAN legitimately return `None` (the "none" weight entry is 6% for boss tier). After 5 `None` rolls, the fallback gil payout fires. This is fine logic but the 5-retry loop means boss fights always try to give gear, potentially over-rewarding on rare tier tables. The retry loop should be removed; if the table rolls "none," accept that as "no drop."

---

## 3. Balance Analysis

### 3.1 Fishing Economy Singularity — **Severity: Critical**

`fishing_engine.py`, `calculate_catch_value()`

```python
if cat in ("mythic", "legendary", "epic"):
    value = min(int(fish["sell_value"] * 2.5), value)
```

`Heart of Aeridor`: `sell_value = 50,000g` → hard cap = **125,000g**
`What Hangs on the Gods' Hook`: `sell_value = 25,000g` → cap = **62,500g**

Crystal Bait costs 100g and gives a ~3% mythic hit chance after roll stacking. Expected value per cast with Crystal Bait: ~0.03 × 87,500 (midpoint mythic) = **~2,625g per cast** against a 100g bait cost. This completely inverts the entire hunting economy—a player can out-earn a full day of dungeon runs in minutes.

**Fix:** Hard-cap all fish sell values in the data:

| Category | Current max | Proposed max |
|---|---|---|
| Mythic | 125,000g | 2,500g |
| Legendary | ~5,000g | 800g |
| Epic | ~1,000g | 300g |
| Rare | ~250g | 150g |

Additionally, introduce a daily sell cap to Gregor (e.g., 3,000g/day) for rare+ fish.

---

### 3.2 Blood Sword + Shadowknight Lifesteal Double-Dip

`combat_engine.py` weapon proc section + `class_advancement.py`

On a critical hit with Blood Sword equipped as a Shadowknight:
1. **Shadowknight lifesteal** (15% of `player_damage`) fires via `apply_advanced_class_to_combat`
2. **Blood Sword proc** (50% crit chance, 1d6 drain) fires separately and also heals for proc damage

At level 10 with max gear, a crit can deal ~60 damage:
- Shadowknight lifesteal: 60 × 0.15 = **9 HP healed**
- Blood Sword 50% crit proc: avg 3.5 × 0.5 = **~1.75 HP healed per round**
- Total: **~10.75 HP per round sustained**

Against late bosses dealing ~20–35 damage per round, this doesn't create an infinite loop, but it makes the Shadowknight substantially tankier than other melee classes with no counterplay. The Shadowknight should be a glass-cannon archetype, not a sustain tank.

**Fix in `class_advancement.py`**, in `apply_advanced_class_to_combat`:
```python
if advanced == "Shadowknight":
    if player_damage > 0 and bonuses.get("lifesteal_pct"):
        steal = max(1, min(6, int(player_damage * bonuses["lifesteal_pct"])))  # cap at 6/round
        result["heal_amount"] += steal
```

Also in `combat_engine.py` Blood Sword proc section, add:
```python
if wp_element == "drain":
    drain_heal = min(wp_extra, 4)  # separate cap on drain procs
    sheet["hp"]["current"] = min(sheet["hp"]["max"], sheet["hp"]["current"] + drain_heal)
```

---

### 3.3 Black Lotus Class-Lock Gap — **Severity: Medium**

`equipment_registry.py`, ACCESSORIES

`black_lotus`: `{"attack_bonus": 6, "value": 55000}` — **no `classes` restriction**.

Any class can equip +6 ATK for 55,000g. A Level 10 Mage with `int: 20` (+5 mod), `flame_scepter` (+5 ATK, +4 dmg), and Black Lotus (+6 ATK) hits total +16 to hit against any DEF. Against the highest-DEF boss (Adamantine Plate Guardian at DEF ~22+10=32... wait let me recalculate: monsters have flat DEF, not player-style). Boss DEF 26 → needs d20 roll ≥ 10 for a 55% hit rate. This is acceptable for an endgame Mage build costing 55k, but the lack of any class gate means a Level 1 character with borrowed gil can equip it immediately.

**Fix:** Add `"classes": ["Warrior", "Paladin", "Shadowknight", "Rogue", "Shadowblade"]` — heavy gear should be melee-locked at minimum.

---

### 3.4 Hunt Count Stack — **Severity: Low**

`progression.py`, `get_max_hunts()`

Current maximum achievable hunt count (no exploit, all legitimate):
- Base: 5
- Ale drink: +1
- Inn rest pending: +1
- Chocobo Chick pet (fed): +1
- Hunter/Ranger advanced class: +1

**Maximum: 9 hunts/day** if Ranger has a Chocobo and drinks at the inn. With `Hunter's Draught` consumable (use anytime): 10 hunts. This multiplies XP gain substantially. Consider a **hard ceiling of 8** regardless of stacking:

```python
return min(8, MAX_HUNTS_PER_DAY + ale_bonus + rest_bonus + pet_bonus + class_hunt_bonus)
```

---

### 3.5 `page_256` FF Easter Egg — Loot Concern

`monster_registry.py`, hard tier; `aeridor_ruins` encounter table, weight 3

`page_256`: HP 1, ATK 1, DEF 1, XP 300, Gil 200, tier "hard"

Grants hard-tier loot from a monster that cannot fight back. The 3/total_weight chance at Aeridor is low (~0.4%), but players who know about it may farm Aeridor specifically for the weight. Consider removing it from the loot table or flagging it `"droppable_only": False` so it generates no gear.

---

## 4. Code Quality Assessment

### 4.1 `rpg_handler.py` — The Monolith Problem

At ~7,500 lines, this is the single biggest maintainability risk. Current cohesion failures:

- **UI views** (`RPGFullLocationView`, `DungeonView`, `RPGCombatView`, `BossApproachView`, `MailMenuView`, etc.) are defined inside the handler module, making them untestable in isolation
- **Domain handlers** (housing, dungeon, shop, combat, world) are all siblings in one flat namespace
- **Import at call site** is used extensively because the file can't be imported cleanly by other modules

**Proposed decomposition:**

```
utils/commands/
├── rpg_handler.py          # ~500 lines — top-level dispatch only
├── rpg_views.py            # All discord.ui.View subclasses
├── handlers/
│   ├── combat_handler.py   # _handle_hunt, _handle_attack, _handle_flee, _handle_duel
│   ├── dungeon_handler.py  # All _dungeon_* functions, DungeonView, DungeonCombatView
│   ├── housing_handler.py  # All _handle_*home*, farming, pets, furniture
│   ├── shop_handler.py     # _handle_shop, buy, sell, sell_all, brew
│   ├── world_handler.py    # _handle_go, look, map, weather, calendar, scout
│   └── npc_handler.py      # _handle_talk, rumor, bard_song, mail
```

This is a multi-session refactor. Start by extracting dungeon (cleanest isolation) and housing (second largest block).

---

### 4.2 Three Competing Button Patterns

Pattern A: `_handler_map` dict dispatch (RPGFullLocationView)
Pattern B: Inline callback with `_InteractionMsg` wrapper (most handlers)
Pattern C: Raw interaction passed directly (BUG-03 above is an example of the failure mode)

**Standard to adopt:** Pattern B everywhere, with Pattern A only for the main location view. Explicitly ban Pattern C by adding a lint note in `AGENTS.md`.

```python
# Canonical pattern — every button callback should look like this:
async def _callback(interaction: discord.Interaction):
    if str(interaction.user.id) != self._uid:
        try: await interaction.response.send_message("not yours.", ephemeral=True)
        except discord.NotFound: pass
        return
    try:
        await interaction.response.defer()
    except discord.NotFound:
        return
    fake = _InteractionMsg(interaction)
    send_fn = _make_interaction_send(interaction)
    await _handle_whatever(ctx, fake, send_fn, args, uid, uname, is_owner)
```

---

### 4.3 Leftover One-Time Migration Scripts

`patch_weapons.py` and `patch_pantheon_integrations.py` in the repo root are one-time data patchers. They should be deleted immediately. If accidentally re-run, `patch_weapons.py` would silently corrupt `equipment_registry.py` (it does file string replacement with no idempotency check). Add to `CONTRIBUTING.md`: "Never commit patch scripts; apply and delete."

---

### 4.4 `LOCATION_ACTIONS` Dict — Defined, Never Used

`rpg_handler.py`, lines ~870–940

```python
LOCATION_ACTIONS = {
    "housing_district": [...],
    "tricklebrook_pond": [...],
    ...
}
```

This dict is populated with ~100 lines of string content but never referenced anywhere in the codebase. It appears to be a leftover from a planned help/map feature that was superseded by `_LOCATION_BUTTONS`. Delete it.

---

### 4.5 `_make_shop_view` Double Character Load

`rpg_handler.py`, `_make_shop_view()`

```python
async def _make_shop_view(ctx, msg, uid, uname, is_owner, items):
    ...
    sheet = await load(uid)  # <-- fresh load
```

This is called immediately after most handlers that already loaded and potentially modified the sheet. The fresh `load()` acquires the per-user asyncio lock, reads from disk, and may trigger the daily reset check—all redundant work.

**Fix:** Add `sheet` as an optional parameter:
```python
async def _make_shop_view(ctx, msg, uid, uname, is_owner, items, sheet=None):
    if sheet is None:
        sheet = await load(uid)
```

Pass the existing sheet from all call sites.

---

### 4.6 Duplicate `ARMOR` Definitions

`equipment_registry.py` contains these keys defined twice (class progression sections at the bottom redeclare items from the general sections above):

- `invoker_vestment` — identical both times (harmless, wasteful)
- `void_vestment` — identical both times
- `arcanist_shroud` — identical both times
- `archmage_robe` — only in one place, fine
- `voice_of_silence_armor` — **different** (BUG-04 above)

Remove all duplicates from the class progression sections. Python dict order means the last definition always wins.

---

## 5. Performance Review

### 5.1 `get_available_fish` — Per-Cast Full Iteration

`fishing.py`, `get_available_fish()`

Called on every cast. For each of the 6 rarity categories in the bait ceiling, it iterates all 250 fish:
```python
for key, fish in FISH.items():
    if fish["category"] not in ceiling: continue
    if season not in fish["seasons"]: continue
    if time_of_day not in fish["time_of_day"]: continue
```

That's up to 1,500 dict accesses per cast. Low absolute cost (~1ms), but it's called hundreds of times per day across all players.

**Fix:** Precompute a `FISH_BY_SEASON_TIME_CATEGORY` index at module import:
```python
# At module bottom, after FISH definition:
from collections import defaultdict
_FISH_INDEX: dict[tuple, list] = defaultdict(list)
for _k, _v in FISH.items():
    for _s in _v["seasons"]:
        for _t in _v["time_of_day"]:
            _FISH_INDEX[(_s, _t, _v["category"])].append((_k, _v))

def get_available_fish(season, time_of_day, bait_key):
    ceiling = BAIT_RARITY_CEILING.get(bait_key, list(CATEGORY_RARITY_WEIGHT.keys()))
    result = {}
    for cat in ceiling:
        pool = _FISH_INDEX.get((season, time_of_day, cat), [])
        result[cat] = pool if pool else [(k, v) for k, v in FISH.items() if v["category"] == cat]
    return result
```
This reduces per-cast work by ~98%.

---

### 5.2 `TIER_COUNTS` Computed at Import But Never Used

`monster_registry.py`, end of file:
```python
TIER_COUNTS = {
    "trivial": len(list_by_tier("trivial")),
    "easy":    len(list_by_tier("easy")),
    ...
}
```

`list_by_tier()` iterates the full `MONSTERS` dict (120+ entries) 6 times at import. `TIER_COUNTS` is never referenced in any handler or game logic. Delete it.

---

### 5.3 Sequential `save()` Calls in Quest Completion

`_handle_attack`, `_handle_talk` — quest completion paths

Both handlers call `await save(sheet)` inside the quest task tracking block, then `await save(sheet)` again after `check_level_up()`, then potentially broadcast another embed. Each save acquires the per-user asyncio lock. In the common case (no quest completion), this is fine. On quest completion, there are 2–3 redundant saves. Consolidate to one final save after all modifications.

---

### 5.4 Session Save on Every Combat Round — Acceptable

`_handle_attack` calls `await save_session(s)` after every round to persist monster HP. This is necessary for the resumption feature (BUG prevents smooth resumption anyway per BUG-03). The cost is one async lock + JSON write per attack, which is fine for the current scale.

---

### 5.5 `check_and_reset_hunts` Saves Housing on Every First-Load of Day

`progression.py`:
```python
housing = load_housing(str(sheet.get("user_id", "")))
if housing and housing.get("last_farm_reset") != today:
    housing = reset_daily_farm(housing)
    housing = reset_daily_pets(housing)
    save_housing(housing)
```

This triggers on the first character load of each day, which is expected. The slight inefficiency is it does a housing load + save even for players who have no housing. Add a guard:
```python
housing = load_housing(str(sheet.get("user_id", "")))
if housing and housing.get("last_farm_reset") != today:
```
Actually this check already exists. The load itself is the only unnecessary cost for non-housing players. Consider storing `has_housing: bool` in the character sheet as a fast-path sentinel.

---

## 6. Incomplete Features / Dead Code

| Item | File | Status | Impact |
|---|---|---|---|
| `balance_model.py` | `utils/ttrpg/balance_model.py` | Complete dead code; uses wrong formulas, wrong data, ignored | **Delete** |
| `LOCATION_ACTIONS` dict | `rpg_handler.py` | Defined, never referenced | **Delete** |
| `action_log` field | `session_manager.py` | Created in `create_session()`, never written to or read | Harmless; clean up |
| `TIER_COUNTS` | `monster_registry.py` | Computed at import, never read | **Delete** |
| Patch scripts | repo root | `patch_weapons.py`, `patch_pantheon_integrations.py` | **Delete** |
| `caravan_active` world state | `world_state.py` + `background_tasks.py` | Set but not used to gate caravan access | Wire up or remove |
| `session_manager` multi-monster | `session_manager.py` | Infrastructure for party combat that was never built; now single-player only | Simplify or remove |
| `ANSI_WHITE` constant | `rpg_ui.py` | Imported in some places, used in none | Remove |
| `_handle_accept` quest path | `rpg_handler.py` | Quest acceptance via `!rpg accept` is only reachable through duel flow; quest accept is handled by NPC talk buttons | Dead command path, misleading |
| Forestry `bloom_creeper` / `summer_hornet` | `monster_registry.py` | Only appear in seasonal tables for spring/summer, but no spring/summer overworld hunting content yet—`whisperwood_edge` seasonal tables are correct | Dormant, not dead |

### Partially-Implemented Features

**`class_advancement.py` Shaman `nature_heal_on_event`**
The Shaman has `"nature_heal_on_event": 4` in its bonuses dict but `apply_advanced_class_to_combat` only handles combat. The event narration pipeline (`_apply_and_narrate_event`) never checks for this bonus. Shamans should heal 4 HP after forest events—implement in `_apply_and_narrate_event`:
```python
if sheet.get("advanced_class") == "Shaman":
    from utils.ttrpg.class_advancement import ADVANCED_CLASSES
    for opts in ADVANCED_CLASSES.values():
        if "Shaman" in opts:
            heal_amt = opts["Shaman"]["bonuses"].get("nature_heal_on_event", 0)
            if heal_amt:
                sheet["hp"]["current"] = min(sheet["hp"]["max"], sheet["hp"]["current"] + heal_amt)
            break
```

**`calendar.py` `shop_special` Effects Not Fully Wired**
`SPECIAL_DAYS` entries like Grimstone Trade Fair have:
```python
"shop_special": {"extra_stock": ["longsword", "half_plate", "steel_blade"], ...}
```
`shop.py`'s `get_shop_inventory()` correctly reads `special.get("shop_special")` and adds items—this part works. However, `shop_special.get("item")` (Festival of Fools lucky_charm) tries to add items to ALL registries. `lucky_charm` is a consumable but the code checks all 5 gear registries. Since consumables are handled separately, the lucky_charm never appears in the festival shop. Fix: check CONSUMABLES registry too:
```python
elif k in CONSUMABLES and k not in consumables_keys:
    consumables_keys.append(k)
```

---

## 7. Actionable Recommendations

### 🔴 Priority 1 — Fix This Week (Critical Bugs)

| ID | Action | File | Effort |
|---|---|---|---|
| R-01 | Fix `BiteView.on_timeout()` bait consumption | `fishing_handler.py` | 15 min |
| R-02 | Add `log_debug` import | `background_tasks.py` | 2 min |
| R-03 | Fix `DungeonView` status callback to use `_InteractionMsg` | `rpg_handler.py` | 10 min |
| R-04 | Delete duplicate `voice_of_silence_armor` from class section | `equipment_registry.py` | 5 min |
| R-05 | Fix weather effect parsing in dawn task | `background_tasks.py` | 20 min |
| R-06 | Cap mythic fish sell values at 2,500g, legendary at 800g | `fishing.py` sell_value fields | 30 min |

---

### 🟠 Priority 2 — Fix This Sprint (High Impact)

| ID | Action | File | Effort |
|---|---|---|---|
| R-07 | Wire up all 6 dead furniture bonuses | `rpg_handler.py`, `combat_engine.py` | 2–3 hours |
| R-08 | Implement gilded mushroom death on watering | `farming.py`, `_handle_water_crops` | 30 min |
| R-09 | Add Shadowknight lifesteal cap (6 HP/round) | `class_advancement.py` | 10 min |
| R-10 | Fix moogle delivery to use timestamp instead of `fed_today` | `background_tasks.py` | 45 min |
| R-11 | Implement Shaman `nature_heal_on_event` | `rpg_handler.py` `_apply_and_narrate_event` | 20 min |
| R-12 | Fix `shop_special` consumable handling for festival items | `shop.py` | 15 min |
| R-13 | Pass `sheet` to `_make_shop_view` to eliminate double load | `rpg_handler.py` | 30 min |
| R-14 | Add class restriction to `black_lotus` | `equipment_registry.py` | 5 min |

---

### 🟡 Priority 3 — Fix This Month (Code Health)

| ID | Action | File | Effort |
|---|---|---|---|
| R-15 | Unify `PERMANENT_CONDITIONS` / `DAWN_PERMANENT` into shared constant | `progression.py` → import in `background_tasks.py` | 10 min |
| R-16 | Delete `balance_model.py`, `LOCATION_ACTIONS`, `TIER_COUNTS`, patch scripts | Various | 30 min |
| R-17 | Remove duplicate ARMOR dict entries | `equipment_registry.py` | 20 min |
| R-18 | Precompute `FISH_BY_SEASON_TIME_CATEGORY` index | `fishing.py` | 45 min |
| R-19 | Standardize button callback pattern; document in `AGENTS.md` | `rpg_handler.py` | 1 hour |
| R-20 | Add daily fishing sell cap (3,000g/day from Gregor) | `fishing_handler.py`, `fishing_engine.py` | 1 hour |

---

### 🔵 Priority 4 — Architectural (Plan Now, Execute Over Multiple Sessions)

| ID | Action | Effort |
|---|---|---|
| R-21 | Decompose `rpg_handler.py` into sub-handler modules (start with `dungeon_handler.py`) | 3–5 sessions |
| R-22 | Evaluate `session_manager.py` for deprecation; migrate monster state to dungeon file | 1 session |
| R-23 | Add `has_housing` sentinel to character sheet to skip housing load for new players | 30 min + migration |
| R-24 | Formalize hunt count hard ceiling at 8 | `progression.py` | 10 min |

---

**Net assessment:** Fixing R-01 through R-06 eliminates all active functionality failures. R-07 through R-14 deliver ~9 features players paid for but never received. R-21 is the most strategically important long-term investment—at 7,500 lines, `rpg_handler.py` is actively blocking multiple contributors from working in parallel and every bug fix in it risks collateral damage.