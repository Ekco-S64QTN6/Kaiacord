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
Introduced the "Corvus Road Trading Co." caravan as a time-bound noon event featuring location-aware shop UI, Tier III inventory, and a strict 1-gear-per-customer purchase limit.

**Consumable Quantity Picker**  
Streamlined shop transactions by adding a dynamic quantity selector, drastically improving menu UX and eliminating the need to buy items one at a time.

**"Silent Ones" World Event**  
Added a new randomized background game-state event that modifies global XP and gold reward rates.

---

## 2. Dungeon Systems Overhaul

**Template-Driven Layout System**  
Dungeons no longer rely on purely random walks. They now use D&D-style structural archetypes with logical progression:
- Defined entry buffers and spine corridors.
- Branching wings with distinct thematic purposes (e.g., Barracks, Vault Approach) dictating internal room generation.
- Empty `antechamber` rooms to build atmospheric tension immediately preceding a boss sanctum.
- **Layout Remediation:** Expanded `GRID_SIZE` to 8 and corrected layout branches to guarantee the designed 16–27 room minimums per map. 
- **Minimum Encounter Threat:** Added a post-generation `_guarantee_minimum_monsters` pass to ensure "empty" dungeons no longer occur, mechanically ensuring at least 5+ combat encounters exist per instance.

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
- **`balance_model.py`:** The independent modeling script has fallen completely out of sync with actual combat equations and should be purged or entirely refactored.
- **Registry Structure:** Current structures place deep reliance on 8-space dictionary identions. A move toward a flat JSON-schema with dedicated python loaders would prevent future data corruption limits.
- **Furniture Buffs:** The `home_pray` button operates successfully but `home_scout`, etc. still need to be explicitly interfaced.
- **Moogle Tracking:** Mognet Delivery logic currently only operates as stub hooks.

*(Note: Data audits and code assessments remain current as of Phase 41 Architectural Remediation).*
