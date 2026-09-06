# Historical Development & Audit Archive
*Combined historical reports, balance audits, and resolved bugs for Aethelgard TTRPG.*

# Phase 14: Balance Hardening & Content Expansion — July 9, 2026
*Unified player/monster stat compression, mid-game quest additions, 50-item inventory cap, and overworld/bestiary expansion.*

---

## Key Achievements

### 1. Stat & DEF Compression
- **Weapon ATK/DMG Caps:** Restructured weapon ATK scaling to cap at +3 ATK max and +3 flat damage max (for Tier 7 weapons). Capped elemental weapon procs at 1d12 (T7).
- **Defensive Gear Calibration:** standard armor DEF capped at max 8, headgear at max 3, boots at max 3, accessories at max 2.
- **Stat/HP Bonus Limits:** Removed all stat modifications from headgear, boots, and accessories. Capped armor stat modifiers to a maximum of +1 per stat, and capped gear HP bonuses at +5. Modified 43 items across the database.
- **Monster Registry Recalibration:** Balanced the stats of all 339 existing monsters to align with compressed player budgets, ensuring healthy hit/miss ratios (~50-65% hit rate).

### 2. Mid-Game Quest Additions
- Added 3 new quests to fully resolve the Level 8 to Level 10 progression gap:
  - **The Merchant's Gambit** (Pell, Level 8) - Escort cargo, rewards `potion_standard`.
  - **Shadows Over Grimstone** (Valdric, Level 9) - Clear dungeon construct breach, rewards `ironbark_tonic`.
  - **The Tithe Collector** (Elara, Level 10) - Defeat Tithe Collector in ruins, rewards `void_band`.

### 3. Inventory Capacity Cap
- Implemented a hard limit of **50 items** in a player's inventory using a custom `CappedList` class in character sheets.
- Overflow protections prevent item generation on purchases (`shop.py`), brewing (`alchemy.py`), or combat looting.

### 4. Overworld & Content Expansion
- Added **26 new overworld monsters** (total bestiary: 365).
- Integrated **Day/Night encounter shifts** (undead spawn rates doubled at night, 25% chance to scale hunts up one tier).
- Added **Overworld travel micro-events** and streak rewards.

### 5. Integrity & Safety Fixes
- Corrected non-existent quest reward keys (`ironbark_potion` -> `ironbark_tonic` in `deep_hunt` and `grimstone_shadows`).
- Cleared duplicate/dead variables in `combat_engine.py` DEF checks.
- Migrated legacy user sheets to comply with the 50-item inventory cap (dropping overflow potions/consumables to keep sheets valid).

---

# Shop Restructure — Action Plan
*Equipment economy rebalance, droppable-only loot, and Hemlock/Caravan split*

---

## What the script does

`restructure_equipment.py` applies four transformations in a single run:

| Pass | What changes |
|---|---|
| 1+2 | Rewrites every `"value": N` field across all item dicts (handles both single-line and multi-line formats) |
| 3+4 | Injects `"droppable_only": True` into ~35% of T2+ items |
| 5 | Replaces `get_caravan_stock()` with the tier-aware, droppable-filtered version |
| 6 | Replaces all six `HEMLOCK_STOCK_*` lists with T1-only rosters |

---

## New price tiers

| Tier | Range | Where |
|---|---|---|
| T1 | 8g – 75g | Hemlock — starter gear |
| T2 | 250g – 420g | Caravan (purchasable) or drop |
| T3 | 750g – 1300g | Caravan (purchasable subset) or drop |
| T4 | 2200g – 3700g | Drop only |
| T5 | 5500g – 55 000g | Drop only |

---

## Step-by-step execution

### Step 1 — Run the script

```bash
# From project root
python scripts/restructure_equipment.py (removed — historical reference) \
    utils/ttrpg/equipment_registry.py \
    utils/ttrpg/equipment_registry.py
```

Expected output:
```
Done → utils/ttrpg/equipment_registry.py
  droppable_only injected : ~148
  price targets confirmed : ~268/268
```

### Step 2 — Remove legacy `HEMLOCK_STOCK_*.extend()` calls

The previous gear-injection session (Part 7 of the class-gear PR) added `.extend()` calls at the bottom of `equipment_registry.py` that append T2+ items back into Hemlock's lists. **These must be removed**, otherwise they override what the script just wrote.

Search for and delete the following block near the bottom of `equipment_registry.py`:

```python
# ── Add to Hemlock's stock (lower tier new items) ────────────────────────────
HEMLOCK_STOCK_WEAPONS.extend([
    "hunting_bow", "skinning_knife", ...
])
HEMLOCK_STOCK_ARMOR.extend([...])
HEMLOCK_STOCK_HEADGEAR.extend([...])
# etc.
```

The new `HEMLOCK_STOCK_*` base lists written by the script already contain all correct T1 entries — the extend calls are now redundant and harmful.

### Step 3 — Update `get_caravan_stock()` call sites in `shop.py`

Open `utils/ttrpg/shop.py`. Find `get_shop_inventory()` and verify the caravan branch looks like this (no changes needed if it already calls `get_caravan_stock()` directly):

```python
if location == "caravan":
    gear_keys, consumable_keys = get_caravan_stock()   # ← already correct
    ...
```

The new `get_caravan_stock()` returns `(List[str], List[str])` — same signature — so no other changes to `shop.py` are required.

### Step 4 — Verify the `_handle_shop` UI row budget

In `rpg_handler.py`, the `_make_shop_view()` function caps buy rows at 3 (75 items max). The new Caravan will surface roughly 40–55 non-droppable T2/T3 items — safely under the 75-item cap.

Verify the cap comment still reads:

```python
chunks = [items[i:i + 25] for i in range(0, len(items), 25)]
for chunk in chunks:
    if current_row >= 3: break  # Max 3 buy rows (75 items total)
```

No change needed — the budget is fine.

### Step 5 — Sanity check: can players still sell droppable loot?

Yes. The `droppable_only` flag is checked only in `get_caravan_stock()` (and Hemlock's static lists don't include them). It is **not** checked in `process_sell()` — players can always sell any item to Hemlock. This is correct and intentional.

### Step 6 — Verify file parses cleanly

```bash
python3 -c "import utils.ttrpg.equipment_registry; print('Import OK')"
```

---

## Droppable-only item breakdown (148 total)

### T2 locked behind combat (~11 items)
Items that exist in the registry as T2 but are class-gated enough that they should only drop:
`shadow_blade`, `assassin_stiletto`, `silver_mace`, `scouts_leathers`, `battle_plate`, `battle_visor`, `phantom_hood`, `iron_greaves`, `shadow_treads`, `iron_gauntlets`, `shadow_ring`

### T3 mostly drop (~28 items)
The named/fancy T3 gear. The generic ones (`flame_sword`, `steel_greatsword`, `temple_hammer`, `whisperwood_recurve`, etc.) **remain purchasable** at the Caravan for 750–900g.

### T4 all drop (49 items)
Every T4 item. Players must hunt dungeons or rare world encounters. The price column in the registry is preserved for `process_sell()` so Hemlock pays out correctly when players want to off-load loot.

### T5 all drop (60 items)
Every T5 item. End-game treasures only.

---

## What the Caravan now sells (example subset)

| Item | Price | Classes |
|---|---|---|
| Iron Greatsword | 285g | Warrior |
| Composite Bow | 290g | Ranger |
| Crystal Wand | 272g | Mage |
| Shadow Garb | 275g | Rogue |
| Shrine Chainmail | 278g | Cleric/Warrior |
| Steel Greatsword | 845g | Warrior |
| Whisperwood Recurve | 820g | Ranger |
| Aeridor Wand | 920g | Mage |
| Temple Hammer | 820g | Cleric |
| Knights Plate | 900g | Warrior |
| Phantom Weave ❌ drop | — | Rogue |
| Mithral Shirt ❌ drop | — | Warrior/Ranger/Rogue |

---

## What Hemlock now sells

**Weapons (14):** Shortbow, Rusty Hand Axe, Rusty Stiletto, Rusty Mace, Wooden Staff, Hunting Bow, Skinning Knife, Rusted Greatsword, Apprentice Wand, Novice Focus, Shiv, Throwing Knife, Iron Flail, Acolyte's Mace

**Armor (9):** Leather Armor, Mage's Robe, Bronze Armor, Fur Cloak, Iron Plating, Ranger's Vest, Cutpurse Leathers, Novice Robes, Acolyte's Vestments

**Headgear (9):** Iron Helm, Scout's Hood, Mage's Cap, Bronze Helm, Soldier's Cap, Ranger's Hat, Shadow Cap, Ember Cowl, Novice Hood

**Boots (5):** Worn Boots, Heavy Boots, Tracker's Boots, Soft Slippers, Bronze Sabatons

**Accessories (4):** Copper Ring, Warrior's Bracer, Scout's Bracer, Scholar's Bracelet

**Consumables (5):** Healing Herb, Bandage, Tonic, Torch, Antidote

---

## Files changed

| File | Change |
|---|---|
| `utils/ttrpg/equipment_registry.py` | Prices + droppable_only + get_caravan_stock() + HEMLOCK_STOCK_* |
| `utils/ttrpg/equipment_registry.py` | Manual: remove legacy `.extend()` calls (Step 2) |
| No other files need changes | shop.py, rpg_handler.py interfaces are unchanged |


---


# Aethelgard TTRPG Balance Audit Report

**Date:** March 18, 2026
**Simulation Scope:** 1,000 Total Hunts (200 per class)
**Locations Tested:** Whisperwood Edge, Trade Road, Whisperwood Deep, Aeridor Ruins

## Executive Summary
The Aethelgard TTRPG core systems (Combat, Progression, Events) are **stable**. The simulation encountered zero logic errors or infinite loops across 1,000 simulated encounters. However, there is a significant early-game imbalance regarding class survivability, specifically for the Mage and Cleric.

## Simulation Data (Level 1-4 Progression)

| Class | Win Rate | Deaths | XP/Hunt | Avg HP Loss/Hunt |
| :--- | :--- | :--- | :--- | :--- |
| **Warrior** | 97.7% | 4 | 30.6 | 7.0 |
| **Ranger** | 93.0% | 11 | 26.8 | 7.3 |
| **Rogue** | 90.5% | 15 | 25.3 | 5.5 |
| **Cleric** | 84.2% | 26 | 24.1 | 9.1 |
| **Mage** | 70.9% | 46 | 18.7 | 5.1 |

## Key Findings

### 1. The "Mage One-Shot" Problem
Mages start with significantly lower HP (4 + CON) than Warriors (10 + CON). In the early game (Whisperwood Edge), even "Trivial" monsters like Goblins (Attack 3) deal an average of 4.5 damage per hit. 
- **Effect:** A Level 1 Mage is often reduced to critical HP or killed in a single lucky hit from a trivial enemy.
- **Data Point:** Mage deaths (46) were **11.5x higher** than Warrior deaths (4).

### 2. Cleric Sustain vs. Tankiness
Clerics suffered the highest "Average HP Loss" (9.1) because they lack the high DEX/AC of Rogues/Rangers and the raw HP of Warriors. They "face-tank" damage but lack the mitigation to survive consistently at Level 1-2.

### 3. Progressive Location Scaling
The transition from `whisperwood_edge` (Level 1-3) to `trade_road` and `whisperwood_deep` (Level 4+) is well-tuned. XP per hunt scales linearly, and classes that survived the early "hump" reached Level 4 consistently.

## Bug Audit
- **Infinite Combat:** No cases found. All combats resolved within expected round limits.
- **Logic Crashes:** Zero exceptions thrown during 1,000 rounds of `_resolve_combat`.
- **Event Integrity:** Forest events (Sylvan Sprites, Moogle, etc.) functioned perfectly, correctly awarding XP/Gil and applying HP changes.

## Recommendations

### [IMMEDIATE] Mage Early-Game Buff
Adjust `dice_engine.py` to give Mages a slightly higher base HP die or a flat "Level 1" bonus to prevent instant death.
- *Current:* 1d4 (Avg 2.5)
- *Proposed:* 1d6 (Avg 3.5) or +2 Flat HP at Level 1.

### [BALANCE] Cleric AC Tweaks
Consider allowing Clerics to start with `leather_armor` instead of unarmored to bridge the gap until they can afford better gear.

### [LONG-TERM] Scaling Review
As players reach Level 10+, the "Deadly" tier monsters (Behemoth, Dragon) may require secondary defenses (Damage Reduction or Evasion) to remain viable for non-Warrior classes.

---

## Post-Buff Verification (March 18, 01:45)
Following the implementation of the Mage HP buff and Cleric starting armor, a second 1,000-hunt simulation was conducted.

| Class | Original Win Rate | **New Win Rate** | **Death Reduction** |
| :--- | :--- | :--- | :--- |
| **Warrior** | 97.7% | 91.5% | - |
| **Ranger** | 93.0% | 90.9% | - |
| **Rogue** | 90.5% | 90.3% | - |
| **Cleric** | 84.2% | 84.0% | (Stabilized) |
| **Mage** | 70.9% | **87.9%** | **-58% deaths** |

**Conclusion:** The "Mage One-Shot" problem is resolved. Early-game survivability is now normalized across all classes within a 7% spread.


---


# Aethelgard TTRPG — Master Development Report

This document synthesizes the initial 72-Hour Development Report, the comprehensive Deep Code Review & Balance Report, and the most recent Dungeon and Architecture Overhauls into a single source of truth detailing the current state of the Aethelgard TTRPG system. 

---

## 1. Social & Exploration Architecture

**Scout Randomization**  
Completely overhauled the static `!rpg scout` command. It now provides three weighted random sightings per area, includes danger indicators (icons), seasonal monster notes, and randomized guard flavor text.

**World Event Broadcasts**  
Established a real-time announcement system that posts milestones to the `#aethelgard` channel:
- Level-up announcements with evolving flavor text.
- Rare loot discoveries (Rare/Epic/Boss tiers).
- Advanced class milestones.
- **Dungeon Broadcasts:** Added explicit victory framing (naming the deceased boss), specific monster call-outs on player death, and contextual "crack in the stone" escape flavor for fleeing.

**Caravan Merchant**  
Introduced the "Corvus Road Trading Co." caravan as a time-bound noon event featuring location-aware shop UI. It maintains a strict 1-gear-per-customer purchase limit and a specialized inventory focused on essential tier-III survival consumables (Health Potions, Lightstones, Gold Needles, Maiden's Kisses, and Softs).

**Consumable Quantity Picker**  
Streamlined shop transactions by adding a dynamic quantity selector, drastically improving menu UX and eliminating the need to buy items one at a time.

**"Silent Ones" World Event**  
Added a new randomized background game-state event that modifies global XP and gold reward rates.

---

## 2. Dungeon Systems Overhaul

**Room-First MST Generation System**  
Dungeons now utilize a high-performance room-first generation algorithm using Minimum Spanning Trees (MST) for guaranteed pathing:
- **Topology & Connectivity:** Rooms are placed randomly as discrete cells and connected via a Prim's algorithm MST. Extra "loop" edges are injected between nearby branches to eliminate linear "spike" layouts and forced backtracking.
- **Topological Intelligence:** Automated BFS analysis calculates distance from start and node degrees to intelligently assign room types. Bosses are mathematically restricted to topological dead-ends to prevent soft-locks.
- **Hub & Reward Rooms:** High-degree junction nodes transformed into Guard Checkpoints, while single-degree dead-ends are guaranteed to contain Shrines or Treasure to encourage full exploration.
- **Reachability Pruning:** A post-generation BFS pass prunes any isolated tiles or non-functional corridor segments, ensuring absolute map integrity.
- **Minimum Encounter Threat:** Maintains a `_guarantee_minimum_monsters` pass ensuring at least 5+ combat encounters exist per instance regardless of layout randomness.

**Boss Room Warnings & Retreats**  
Implemented atmospheric narrative cues and a direct retreat mechanism when players transition into an antechamber, improving player agency and allowing them to back out before committing to highly lethal boss encounters.

**Stat-Based Trap Mechanics**  
Replaced legacy flat-damage traps with a dynamic stat-based dexterity save. 
- Trap DC scales with dungeon difficulty `9 + (difficulty * 3)`.
- Rolls `d20 + DEX mod + Luck + Class bonuses`. 
- Incorporates bespoke Rogue disarming flavor and heavily punishing scaling damage on failure.

**Quest Encounter Overrides**  
Added synthetic location key injection seamlessly altering random encounters during specific quests (e.g., injecting the `trade_road_maren` key to wildly boost Bandit spawn rates when a player is actively on Sister Maren's quest).

---

## 3. Combat & Balance Refinements

**Defense Soft-Cap**  
Fixed a critical bug where player defense accumulated additively across five slots with no cap, leading to unhittable players by mid-game. Introduced a diminishing return soft-cap: the first 10 bonus defense points provide full value, with remainder halved. *(Note: Uncapped components from Pet/Weather/Class buffs remain an open architecture issue prioritized for upcoming sprints).*

**Tier-Scaled Monster Lethality**  
- **Hit Modifiers:** Scaled monster hit modifiers drastically based on their tier, rather than simply halving their flat ATK stat.
- **Damage Output:** Replaced the static `1d6` damage floor for all monsters. Trivial monsters deal `1d4`, Hard monsters deal `2d6`, and Bosses throw `3d6`, ensuring combat threat scales appropriately with the player's HP curve.
- **Monster Critical Hits (Nat 20s):** Fleshed out critical hits for monsters. When a monster rolls a Natural 20, they now guarantee absolute maximum damage from their tier dice pool (e.g., bypassing a random roll to deal a flat 18 damage on naturally thrown 3d6).

**Encounter Scaling & Safeguards**
- **Overworld Tier Windowing:** Overhauled encounter tables to enforce both a `min_tier` and `max_tier` per player level. Level 4-5 players are now strictly shielded from inadvertently spawning Deadly or Boss-tier monsters (300+ HP) during exploration.
- **Dungeon Boss Loot Tier Dynamics:** Boss rewards dynamically scale up dynamically with player levels now (clamping correctly at `"boss"` for endgame players) rather than relying on a hardcoded `"hard"` tier definition.
- **Dungeon Aggressive Boss Caps:** Reworked boss scaling logic to be generously forgiving at early levels (30% multiplier down from 45%) while strictly capping structural boss health and attack thresholds per player level.

**Class Features Activated**  
Implemented numerous previously silent advanced class features:
- **Cleric / High Priest:** Properly applied `heal_mult` values to potions (e.g. 1.5x restoration).
- **Hunter / Trickster / Ranger:** Wired in all XP and Gil percentage multipliers on kills.
- **Trickster:** Implemented the signature `gamble_edge` advantage logic.
- **Warrior:** Halved and formally documented an invisible flat damage output bonus that was previously drastically skewing DPS balance.

**Equipment Registry Migration**  
Overhauled the core equipment registry architecture to standardize item lookups, creating a robust background migration script that successfully transferred legacy character inventory data to the new unified keys. Introduced missing gap-tier items like `Silverleaf` directly into `CONSUMABLES` and wired it into interactive NPC hubs.

**Event Pacing Adjustments**  
Rebalanced field exploration pacing by reducing the baseline `EVENT_CHANCE` for random hunting encounters, ensuring events feel more meaningful and less repetitious.

---

## 4. System Stability & Bug Fixes

**Encounter Routing Repaired**  
Fixed a catastrophic bug where hunts relied on legacy 4-monster stubs. Fully integrated the 120+ monster bestiary and properly routed the 9 newly-written forest events that were previously unreachable in `encounter_tables.py`.

**Quest Integration & NPC Dialogue State Tracking**
Completely decoupled commercial transactions (like purchasing farming seeds) out of active dialogue UX `ActionRows`, eliminating severe Discord View state-conflicts that had previously caused Quest markers to silently halt progression.

**Dynamic World Hooks Enabled (The Calendar)**
Wired the massive payload of `calendar.py` deterministic variables straight into the combat and hub engines:
- `encounter_mod`: Tier bounds naturally shift (e.g. adding 1 to indexes causing 'Amber Nights') and undead swarms spawn cleanly from `encounter_tables.py`.
- `shop_special`: Hemlock accurately loads special-event items into arrays conditionally on Fair days.
- `solstice_blessing` and `shrine_gift`: Built handlers in the `!rpg pray/offer` block to accommodate high-level XP multiplier limits and mystery item drops for real-time holy days.

**Combat Resumption UI Resiliency**  
Implemented a robust state-persistence system for dungeon and field combat, allowing players to resume active encounters without progress loss after UI timeouts. Fixed ANSI color bar rendering leakages so resumed combat embeds render clean mono-spaced health bars.

**Renamed Item Commerce Bug**  
Resolved an inventory string matching bug that was preventing customized, user-renamed equipment from being recognized or properly sold to merchants.

**Timeout Exception Catching**  
Integrated widespread `defer()` calls and exception handling for interaction timeouts to eliminate Discord "Unknown Interaction" errors.

---

## 5. Fishing Economy & Gathering Systems

**Economic Fixes (The Gil Sink)**
Eliminated the infinite-gil generation exploit by closing loopholes surrounding starter equipment and bait requirements:
- **Mandatory Bait:** Removed the previous `earthworm` exemption. Fishing without bait is strictly impossible, requiring a permanent, consistent gil sink for all players.
- **Breakable Starter Gear:** Fixed an issue where the `birchwood_rod` never broke and had a `0g` cost. The rod now costs `15g` and inherits an 8% snap chance, formally wrapping the early game into the economy and forcing repurchases.
- **Progressive Snap Rates:** All rods now have bespoke break probabilities inversely scaling with their quality (from 8% for basic birch to 2% for the Aeridorian Spire).
- **None-State Handling:** Wired safety hooks across the system preventing KeyErrors if a player's rod snaps mid-catch, dynamically rendering `None` UI blocks and blocking future casts.

**Bag Capacity Architecture**
Added a strict bag limit system to prevent infinite passive fish hoarding.
- Default limit is 20 catches. 
- Integrated a new "Bag Upgrades" selection directly into Gregor's Shop UI, allowing progression to the 100-capacity "Gregor's Chest".

---

## 6. Comprehensive Audit Findings (Remaining Technical Debt)

While recent overhauls solved the critical and highest priority bugs, the following infrastructure discrepancies remain prioritized for coming development cycles:

### Priority: Outstanding Balance Vectors 🟡
- **Uncapped non-gear DEF**: Soft caps currently skip Pet buffs, world state DEF buffs, and Advanced class buffs entirely. This needs addressing.
- **Lifesteal looping**: Shadowknight sustain loops (`class_advancement.py`) trivialize endurance fights because healing hasn't received a per-combat ceiling limit yet.
- **Pet Multi-Stacking**: There are no guards preventing the stacking of identical pet bonuses (i.e. bringing 5 Tonberry companions to grant a +10 flat combat modifier).
- **Hard Tier Splitting**: The "Hard" index contains both soft glass-cannons (Tonberry) and raid bosses (Balor). An intermediary "Elite" or `power_rating` scalar system should be explored to keep level 7 players from being instantly executed.
- **Weapon & Accessory Caps**: T5 items (specifically `Ultima Weapon` and `Black Lotus`) exceed the TTRPG mathematical budget guidelines by approximately 60%.

### Priority: Code Maintenance and Extensibility 🔵
- **`balance_model.py`:** ~~Deleted~~ — was completely stale and has been removed.
- **Registry Structure:** Current structures place deep reliance on 8-space dictionary indentions. A move toward a flat JSON-schema with dedicated Python loaders would prevent future data corruption limits.
- **Furniture Buffs:** All 9 furniture bonuses are now fully wired and operational (as of April 2026).
- **Moogle Tracking:** Mognet Delivery now uses timestamp-based tracking (`last_moogle_delivery`) and is operational.

*(Note: See `ttrpg_report.md` for the most current system status and bug inventory.)*


---

# Old Resolved Bugs (from April 11 ttrpg_report)

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

**Previously fixed:**
- 🔴 Banking crash (`load_housing` missing import)
- 🔴 Warden `forest_def_bonus` never fired
- 🔴 Solstice offering XP multiplier not applied
- 🟠 Training dummy didn't grant hunts when pool was full
- 🟠 `PERMANENT_CONDITIONS` duplicated across two files
- 🟡 Hunt count had no hard ceiling
- 🟡 Dungeon combat missing furniture ATK bonus
- 🗑️ Dead code removed: `balance_model.py`, `LOCATION_ACTIONS`, `TIER_COUNTS`
