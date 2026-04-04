# Aethelgard TTRPG — Deep Code Review & Balance Audit

> **Reviewer:** Senior Python Engineer / Senior Game Developer  
> **Date:** 2026-04-04  
> **Scope:** Full codebase pass across `utils/ttrpg/`, `utils/commands/rpg_handler.py`, `utils/commands/fishing_handler.py`, and `docs/ttrpg/`  
> **Priority System:** 🔴 Critical (game-breaking) · 🟡 High (balance/correctness) · 🔵 Medium (quality/UX) · ⚪ Low (cosmetic/future)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Critical Bugs (🔴)](#2-critical-bugs-)
3. [Balance Analysis & Power Curve](#3-balance-analysis--power-curve)
4. [Code Quality & Registry Issues](#4-code-quality--registry-issues)
5. [Incomplete Feature Hooks](#5-incomplete-feature-hooks)
6. [Combat Engine Deep Dive](#6-combat-engine-deep-dive)
7. [Equipment Scaling Report](#7-equipment-scaling-report)
8. [Monster Registry Audit](#8-monster-registry-audit)
9. [Dungeon System Review](#9-dungeon-system-review)
10. [Subsystem Reviews](#10-subsystem-reviews)
11. [Recommendations — Prioritized](#11-recommendations--prioritized)

---

## 1. Executive Summary

The Aethelgard TTRPG is a well-structured, feature-rich system with clean architectural boundaries (Python handles deterministic state; Kaia handles narration). However, it has accumulated several categories of debt:

**Critical:** 7 monster keys referenced in encounter tables have no stat definitions — these will crash encounters or produce empty results at runtime.

**Balance:** Player power scales faster than monster difficulty past level 5. The combination of additive gear bonuses across 5 equipment slots, class-level stat growth, pet passives, and advanced class modifiers creates a multiplicative power curve that outpaces the linear monster stat progression.

**Code Quality:** `equipment_registry.py` has formatting inconsistencies (mixed indentation levels for `droppable_only` keys) that haven't caused parse errors yet but are maintenance landmines. The `balance_model.py` standalone tool is completely out of sync with actual game formulas.

**Features:** Several systems (Mognet, Silent Ones event hooks, alchemy recipe depth, furniture bonuses) are partially implemented — they have data definitions but incomplete integration with the combat/reward loop.

---

## 2. Critical Bugs (🔴)

### 2.1 Missing Monster Definitions — Encounter Table Crash Risk

**Severity:** 🔴 Game-breaking  
**Files:** `monster_registry.py` (ENCOUNTER_TABLES section)  
**Impact:** If any of these keys are rolled, `MONSTERS.get(key)` returns `None`. Depending on how the caller handles this, it will either crash or silently skip the encounter.

**Missing keys confirmed by validation:**

| Location | Missing Key | Used In |
|---|---|---|
| `whisperwood_deep` | `owlbear` | Weight 8 |
| `whisperwood_deep` | `displacer_beast` | Weight 6 |
| `whisperwood_deep` | `ettercap` | Weight 4 |
| `whisperwood_deep` | `chimera_dd` | Weight 3 |
| `whisperwood_deep` | `serra_angel` | Weight 2 |
| `whisperwood_deep_night` | `hand_axe_goblin` | Weight 3 |
| `whisperwood_deep_night` | `skeleton_archer` | Weight 3 |

**Combined weight of broken entries:** 29 out of ~350 total weight in `whisperwood_deep` = **~8.3% of all Whisperwood Deep encounters are broken.**

**Fix:** Add stat blocks for all 7 monsters. Suggested stats based on their tier placement and naming conventions:

```python
# Add to MONSTERS dict:
"owlbear": {
    "name": "Owlbear",
    "hp": 75, "attack": 10, "defense": 13,
    "xp": 100, "gil": 20, "tier": "medium",
    "desc": "A feathered horror — part owl, part bear, all fury. It charges through undergrowth without slowing.",
},
"displacer_beast": {
    "name": "Displacer Beast",
    "hp": 65, "attack": 11, "defense": 14,
    "xp": 110, "gil": 25, "tier": "medium",
    "desc": "A six-legged panther that bends light around itself. It's never quite where it appears to be.",
},
"ettercap": {
    "name": "Ettercap",
    "hp": 55, "attack": 9, "defense": 12,
    "xp": 90, "gil": 18, "tier": "medium",
    "desc": "A spider-like humanoid that weaves traps of web and malice. Found near Whisperwood nests.",
},
"chimera_dd": {
    "name": "Chimera",
    "hp": 80, "attack": 11, "defense": 13,
    "xp": 115, "gil": 30, "tier": "medium",
    "desc": "Three heads, three breaths, one bad attitude. The goat head is the most dangerous — it bites.",
},
"serra_angel": {
    "name": "Serra Angel",
    "hp": 70, "attack": 10, "defense": 15,
    "xp": 120, "gil": 35, "tier": "medium",
    "desc": "A radiant winged warrior from a forgotten age. She guards something that no longer exists.",
},
"hand_axe_goblin": {
    "name": "Hand Axe Goblin",
    "hp": 20, "attack": 5, "defense": 9,
    "xp": 28, "gil": 7, "tier": "trivial",
    "desc": "A goblin with better equipment and worse manners. Throws hand axes before charging.",
},
"skeleton_archer": {
    "name": "Skeleton Archer",
    "hp": 22, "attack": 6, "defense": 10,
    "xp": 35, "gil": 8, "tier": "trivial",
    "desc": "A skeleton that still remembers how to draw a bow. Its aim is disturbingly good.",
},
```

### 2.2 Equipment Registry Indentation Inconsistency

**Severity:** 🔴 Silent data corruption risk  
**File:** `equipment_registry.py`

Several items have `"droppable_only": True` at **4-space indent** (dict sibling level) instead of **8-space indent** (inside the item's dict). Python still parses this as part of the parent dict, but it makes the `droppable_only` key a **sibling** of the item dict rather than a **member** of it.

**Example (lines 803-804):**
```python
    "forest_stride": {
        "name": "Forest Stride", "defense_bonus": 3, "value": 7800, "tier": 5,
        "classes": ["Ranger"],
    "droppable_only": True,   # ← This is at 4-space indent, OUTSIDE the sub-dict
    },
```

This means the closing `}` on line 804 actually closes `forest_stride`'s sub-dict AND the `droppable_only` becomes a key of the **parent** BOOTS dict, not of `forest_stride`. Since Python allows duplicate keys (later wins), this doesn't crash — but the `droppable_only` flag is **not attached to the item it belongs to**.

**Affected items (confirmed by visual inspection):**
- `BOOTS`: `forest_stride` (L803), `void_walkers` (L821), `silence_treads` (L843)
- `ACCESSORIES`: `iron_gauntlets` (L891), `champion_bracers` (L904), `void_focus` (L940), `shadow_ring` (L950), `forest_ring` (L922), `saints_medallion` (L976)

**Fix:** Move all `"droppable_only": True` to 8-space indent inside their respective item dicts.

### 2.3 Duplicate Monster Names

**Severity:** 🟡 Confusing, not crashing  

| Key 1 | Key 2 | Shared Name |
|---|---|---|
| `harpy` | `harpy_dd` | "Harpy" |
| `mindflayer` | `mind_flayer` | "Mindflayer" / "Mind Flayer" |
| `iron_giant` | `iron_giant_ff` | "Iron Giant" |
| `omega` | `omega_ff5` | "Omega" |
| `shinryu` | `shinryu_ff5` | "Shinryu" |

The `monster_registry.get()` function does fuzzy matching by name — these duplicates could cause the wrong monster to be returned when looked up by display name.

---

## 3. Balance Analysis & Power Curve

### 3.1 The Core Problem: Additive Slot Stacking

A fully-equipped level 7 character has **5 gear slots** contributing bonuses:

| Slot | Typical T4 DEF Bonus | Typical T4 ATK Bonus |
|---|---|---|
| Armor | +6 | — |
| Head | +4 | — |
| Boots | +3 | — |
| Accessory | +2 | +3 |
| Weapon | — | +7, d12+6 |
| **TOTAL GEAR** | **+15 DEF** | **+10 ATK** |

Add to this:
- Base stats: DEX mod +2 to +3 → effective DEF +12 to +13 on top of gear
- Class advancement bonuses (e.g., Berserker: +3 ATK flat; Paladin: +2 DEF)
- Pet passives: Tonberry (+2 combat bonus), Construct (+3 DEF)
- Furniture: Weapon Rack (+1 ATK), Trophy Mount (+2 ATK)

**Fully buffed Level 7 Warrior:**
- **Total effective ATK:** ~18-20 (vs. medium monster DEF 11-15)
- **Total effective DEF:** ~25-28 (vs. medium monster ATK 9-13)
- **HP:** ~65-80 (10 HD + CON mod per level + gear)

**Result:** This character trivializes the entire "medium" tier and most of "hard." The defense soft-cap (first 10 full, rest halved) helps but is not sufficient when total DEF reaches 25+.

### 3.2 Defense Soft-Cap Verification

From `combat_engine.py`, the defense formula:
```python
effective_def = 10 + (dex_mod)  # base
if armor_bonus <= 10:
    effective_def += armor_bonus
else:
    effective_def += 10 + (armor_bonus - 10) // 2
```

**Problem:** The soft-cap only applies to **armor_bonus** (the aggregate gear defense). It does NOT cap:
- Pet DEF bonuses (Construct: +3)
- Class advancement DEF bonuses (Paladin: +2)
- World state DEF mods (Resonance Surge: +2)

These bypass the soft-cap entirely and stack additively. A player with 15 gear DEF (soft-capped to 12.5 → 12) still gets +3 pet +2 class +2 weather = **+7 uncapped DEF on top**.

### 3.3 The Black Lotus Problem

**`black_lotus` accessory:** ATK +10, DEF +0, Value 55,000g, Tier 5.

This is an extreme outlier. The next highest accessory ATK bonus is Giant Strength Belt at +5. The Black Lotus **doubles** the ATK contribution of any other accessory. Combined with a T5 weapon (Ultima Weapon: ATK +12, d12+8), a single character can reach **+22 flat ATK** from weapon + accessory alone.

**Recommendation:** Cap Black Lotus at +6 ATK (in line with T5 budget) or make it a consumable/event item that provides a temporary buff rather than a permanent equipment piece.

### 3.4 Monster Power Curve vs. Player Power Curve

| Level | Player Eff. ATK (estimated) | Player Eff. DEF (estimated) | Player HP | Target Tier | Monster ATK | Monster DEF | Monster HP |
|---|---|---|---|---|---|---|---|
| 1 | 4-6 | 12-14 | 11-15 | Trivial | 2-5 | 7-12 | 6-20 |
| 3 | 7-10 | 14-17 | 22-30 | Easy | 5-8 | 8-12 | 20-55 |
| 5 | 12-16 | 18-23 | 38-50 | Medium | 8-13 | 11-15 | 50-110 |
| 7 | 16-22 | 23-28 | 55-75 | Hard | 12-17 | 13-17 | 80-180 |
| 10 | 20-30 | 28-35 | 75-100 | Deadly | 17-25 | 16-22 | 200-500 |

**Key insight:** Player ATK grows ~5x from L1 to L7. Monster DEF grows ~2x. Player DEF grows ~2x. Monster ATK grows ~4x. **Players hit more reliably as they level, while monsters hit less reliably.** This is the root cause of "combat is too easy."

### 3.5 Recommended Stat Budget per Tier

To bring equipment in line, I recommend the following **total stat budget** per item tier:

| Tier | Weapon Budget (ATK+DMG_BONUS) | Armor Budget (DEF) | Accessory Budget (ATK+DEF) |
|---|---|---|---|
| 1 | 2-4 | 1-2 | 1-2 |
| 2 | 4-6 | 2-4 | 2-3 |
| 3 | 7-9 | 4-5 | 3-4 |
| 4 | 10-13 | 5-7 | 4-5 |
| 5 | 14-18 | 7-9 | 5-6 |

Items exceeding these budgets are the primary source of power creep and should be adjusted down.

---

## 4. Code Quality & Registry Issues

### 4.1 equipment_registry.py — Structural Problems

**File size:** 1,146 lines, 64KB — largest file in the TTRPG module.

| Issue | Severity | Description |
|---|---|---|
| Mixed formatting | 🟡 | Some items are single-line dicts, others are multi-line. No consistent pattern. |
| Indentation bugs | 🔴 | `droppable_only` at wrong indent level (see §2.2). |
| No schema validation | 🟡 | Items can have missing keys (e.g., some accessories lack `attack_bonus`). |
| Hardcoded shop lists | 🔵 | `HEMLOCK_STOCK_*` are manually maintained string lists — adding a new T1 item requires editing both the item dict AND the stock list. |
| Alias duplication | 🔵 | `ALIASES` dict + `ALIASES.update()` at bottom — two places to maintain. |
| Classes reference non-existent advanced classes | ⚪ | Items reference `"Paladin"`, `"Wizard"`, `"Necromancer"`, `"Shadowblade"`, `"Shadowknight"`, `"Hunter"`, `"High Priest"`, `"Shaman"`, `"Trickster"` — these are advanced class names from `class_advancement.py` but the base class system only has 5 classes. This is forward-compatible but confusing. |

**Recommendation:** Migrate to a structured format:
```
data/ttrpg/weapons.json
data/ttrpg/armor.json
data/ttrpg/accessories.json
...
```
With a single `registry_loader.py` that validates schema on load.

### 4.2 monster_registry.py — Structural Problems

**File size:** 1,704 lines, 71KB — the single largest file.

| Issue | Severity | Description |
|---|---|---|
| Massive stat range within tiers | 🟡 | "Hard" tier has monsters ranging from 80 HP / 12 ATK (Tonberry) to 350 HP / 25 ATK (Balor). This is a 4x spread within a single tier. |
| Encounter tables embedded in same file | 🔵 | `ENCOUNTER_TABLES` at line 1394+ doubles the file size. Already partially moved to `encounter_tables.py` but the canonical data lives here. |
| Night encounter table references missing monsters | 🔴 | `whisperwood_deep_night` references `hand_axe_goblin` and `skeleton_archer` — neither exists. |
| Empty lines 1263-1279 | ⚪ | 17 blank lines between deadly and boss tiers. Cosmetic. |
| `SEASONAL_MONSTER_STATS` in `calendar.py` duplicates `MONSTERS` | 🔵 | `snow_bunny`, `ice_wisp`, `frost_wolf`, etc. exist in BOTH `monster_registry.MONSTERS` AND `calendar.SEASONAL_MONSTER_STATS`. If stats are updated in one, the other goes stale. |

### 4.3 balance_model.py — Completely Stale

This standalone balance tool defines its own `CLASSES`, `WEAPONS`, and `MONSTERS` dicts that have **no relation** to the actual game data. The formulas used (`(10 + mods) / (AC + 10)`) don't match the actual combat engine formulas (`d20 + STR mod + weapon_ATK vs. monster DEF`).

**Recommendation:** Either delete this file or rewrite it to import from the actual registries and use the actual combat formulas.

---

## 5. Incomplete Feature Hooks

### 5.1 Systems with Data But No Full Integration

| System | Data Defined In | Integration Status | What's Missing |
|---|---|---|---|
| **Mognet** | `pets.py` (Moogle weekly delivery), `encounter_tables.py` (mognet events) | ⚪ Stub | No delivery scheduler. No mognet_letter use handler. Items exist but do nothing. |
| **Silent Ones Events** | `calendar.py` (Solstice, Morvenna's Eve, Feast) | 🔵 Partial | `shrine_gift` flag defined but no item generation logic. Offer XP scaling defined but unclear if wired. |
| **Furniture Bonuses** | `furniture.py` | 🔵 Partial | `home_brewing`, `daily_training`, `home_pray`, `home_scout`, `home_cha`, `dungeon_xp` bonuses are defined but need verified integration in `rpg_handler.py`. |
| **Pet Passives** | `pets.py` | 🟡 Mostly Done | `get_pet_passive()` returns bonuses but `combat_heal`, `extra_hunt`, `def_bonus`, `weekly_delivery` need individual integration points. |
| **Weather Effects** | `calendar.py` | 🔵 Partial | `scout_blocked`, `armor_penalty`, `level_gate` effects are defined but need handler code to enforce them. |
| **Alchemy Expansion** | `alchemy.py` | 🟡 Working but shallow | Only 2 recipes (Antidote, Health Potion). The ingredient system supports more but no recipes exist for `dire_root`, `gilded_mushroom` as primary ingredients. |
| **Housing Visitor System** | `housing.py` (`visitors_today`) | ⚪ Stub | Field exists but no visit tracking, no player shop functionality. |
| **Caelindra's Mechanics** | Referenced in lore bible | ⚪ Not started | No code whatsoever. |

### 5.2 Event/Calendar System — Well Designed, Partially Wired

The `calendar.py` system is one of the strongest parts of the codebase — deterministic weather, seasonal encounters, special days with buffs. However:

- **`encounter_mod` effects** (e.g., Amber Night tier+1, winter snow +15% seasonal creatures) — unclear if `encounter_tables.random_encounter()` checks for these.
- **`shop_special` items** (Festival of Fools lucky charm, Grimstone Trade Fair extra stock) — `get_shop_inventory()` checks `SEASONAL_SHOP` but not `SPECIAL_DAYS[date].shop_special`.
- **`shrine_gift`** (Feast of the Silent Ones) — flag defined, no handler.

---

## 6. Combat Engine Deep Dive

### 6.1 Architecture (Correct)

`combat_engine.py` (336 lines) handles all combat resolution. Clean separation:
- `_resolve_combat()` — main loop, handles initiative, rounds, damage application
- Defense soft-cap applied correctly for gear DEF
- Tier-based monster damage scaling present
- Critical hit system (nat 20 = double damage) working

### 6.2 Issues Found

| Issue | Severity | Line(s) | Description |
|---|---|---|---|
| Uncapped non-gear DEF | 🟡 | Soft-cap block | Pet DEF (+3), class DEF (+2), weather DEF mods bypass the armor soft-cap. Should be included in the cap calculation. |
| Advanced class lifesteal | 🟡 | `class_advancement.py` | Shadowknight lifesteal + gear ATK creates a sustain loop that trivializes endurance fights. No per-combat cap on healing received. |
| No monster crit system | 🔵 | — | Players can crit on nat 20. Monsters cannot. This asymmetry favors players at all levels. |
| No flee penalty scaling | ⚪ | — | Fleeing from bosses should have a higher failure rate or HP cost than fleeing from trivial mobs. Currently uniform. |

### 6.3 Dungeon Boss Scaling — Well Handled

`dungeon.py._scale_boss_to_level()` (lines 565-591) is solid:
- Uses a `0.30 + (level-1)*0.08` multiplier (30% at L1, 100% at ~L10)
- Hard HP caps per level (L1: 35, L5: 80, L9: 220)
- Hard ATK caps per level (L1: 6, L5: 14, L9: 22)

This is correct design. The open-world encounter system should learn from this pattern.

---

## 7. Equipment Scaling Report

### 7.1 Weapon Scaling (Aggregated from registry)

| Tier | Count | ATK Range | DMG Die | DMG Bonus Range | Notes |
|---|---|---|---|---|---|
| 1 | ~18 | 1-2 | d6-d8 | 1-2 | Appropriate |
| 2 | ~20 | 2-4 | d8-d10 | 2-3 | Appropriate |
| 3 | ~25 | 4-6 | d8-d10 | 4-5 | Slightly aggressive on ATK |
| 4 | ~20 | 5-8 | d10-d12 | 6 | Masamune ATK+8 is an outlier at T4 |
| 5 | ~22 | 8-12 | d12 | 8 | Ultima Weapon ATK+12 is extreme |

**Outliers to address:**
- `ultima_weapon`: ATK +12, d12+8 — exceeds T5 budget by ~4 points. Recommend ATK +9.
- `black_lotus` (accessory): ATK +10 — addressed in §3.3.
- `excalibur_ff`: ATK +11 — slightly over budget. Recommend ATK +9.

### 7.2 Armor DEF Progression

| Tier | Count | DEF Range | Notes |
|---|---|---|---|
| 1 | ~12 | 1-3 | Clean |
| 2 | ~15 | 2-4 | Clean |
| 3 | ~12 | 4-6 | Clean |
| 4 | ~10 | 5-7 | Clean |
| 5 | ~10 | 7-10 | `adamantine_plate` DEF+10 is extreme |

### 7.3 Accessory Budget Violations

T5 accessories should have a combined ATK+DEF ≤ 6. Current violations:

| Item | ATK | DEF | Total | Issue |
|---|---|---|---|---|
| `black_lotus` | +10 | 0 | 10 | 66% over budget |
| `giant_belt` | +5 | 0 | 5 | Borderline |
| `champion_bracers` | +4 | +2 | 6 | At budget |
| `void_band` | +3 | +2 | 5 | Clean |

---

## 8. Monster Registry Audit

### 8.1 Tier Distribution

| Tier | Count | HP Range | ATK Range | DEF Range |
|---|---|---|---|---|
| Trivial | ~50 | 6-20 | 2-6 | 7-15 |
| Easy | ~38 | 20-65 | 5-9 | 8-14 |
| Medium | ~35 | 50-110 | 8-13 | 10-17 |
| Hard | ~32 | 80-350 | 12-25 | 13-22 |
| Deadly | ~30 | 200-999 | 13-35 | 16-30 |
| Boss | ~15 | 280-999 | 16-38 | 15-35 |

### 8.2 Internal Tier Consistency Issues

**"Hard" tier is the most problematic.** It contains:
- `tonberry`: 80 HP, 22 ATK, 13 DEF (glass cannon)
- `balor_dd`: 350 HP, 25 ATK, 22 DEF (raid boss)
- `storm_giant`: 300 HP, 22 ATK, 20 DEF (raid boss)

These should not be in the same tier. The encounter table `random_encounter()` filters by tier window:
```python
if player_level >= 7: min_tier, max_tier = "medium", "deadly"
```

A level 7 player can roll a Balor (350 HP, 25 ATK, 22 DEF) — that's a near-certain death for a solo player. The tier system needs sub-tiers or the encounter weight system needs to account for the monster's actual power within its tier.

**Recommendation:** Either:
1. Split "hard" into "hard" (80-180 HP, 12-18 ATK) and "elite" (180+ HP, 18+ ATK), or
2. Add a `power_rating` field to each monster and weight encounters by power rating instead of pure tier.

### 8.3 Duplicate Stat Definitions

Monsters defined in BOTH `monster_registry.MONSTERS` AND `calendar.SEASONAL_MONSTER_STATS`:
- `snow_bunny`, `ice_wisp`, `frost_wolf`, `snow_bandit`, `antler_stag`, `bloom_creeper`, `summer_hornet`

These are 7 monsters with **two copies of their stats in two files**. Currently in sync, but any edit to one that forgets the other will create a silent desync.

**Fix:** Delete `SEASONAL_MONSTER_STATS` from `calendar.py`. The seasonal encounter system only needs to reference monster keys, not carry its own stat blocks. The encounter tables already reference these monsters by key.

---

## 9. Dungeon System Review

### 9.1 Architecture — Excellent

`dungeon.py` (802 lines) is the best-architected file in the TTRPG module:
- Template-based layout generation (not random maze)
- Wing purpose system with themed room sequencing
- Structural rules (entry buffer, antechamber before boss, guaranteed shrine)
- Boss scaling with per-level caps
- Clean persistence (JSON save/load with atomic writes)

### 9.2 Issues

| Issue | Severity | Description |
|---|---|---|
| Wing purpose reuse | ⚪ | If dungeon has >6 wings, purposes repeat. Not a practical problem at current layout sizes. |
| Boss name collision | ⚪ | `generate_boss_name()` has ~225 unique combinations. Low chance of duplicates in practice. |
| No dungeon tier scaling | 🔵 | Difficulty 1/2/3 uses different layouts but monster pools are theme-based, not difficulty-scaled per room distance from entrance. Deeper rooms should be harder. |
| Map render assumes square grid | ⚪ | `render_map()` works but emoji alignment can break on mobile Discord clients. |

---

## 10. Subsystem Reviews

### 10.1 Shop System (`shop.py`) — Clean

- CHA discount correctly capped at 10%
- Reputation modifiers well-tuned (Outlaw: markup, Hero: discount)
- Caravan 1-gear limit properly enforced
- `find_item()` alias resolution handles edge cases well
- Sell price at 50% base is standard RPG convention

**One issue:** The `process_sell` reverse alias lookup (lines 164-168) iterates all aliases on every sell. With ~100 aliases this is fine, but consider building a reverse map at module load for O(1) lookups.

### 10.2 Housing (`housing.py`) — Clean but Shallow

- 4-tier progression (Hut → Keep) is well-balanced cost-wise
- Level gates prevent early rushing
- Furniture slot scaling is reasonable

**Missing:** No housing decay, no maintenance cost, no visitor interaction beyond a stub list. The system is complete enough to ship but lacks endgame depth.

### 10.3 Farming (`farming.py`) — Well Designed

- Growth timing is real-calendar-based (good)
- Watering mechanic adds daily engagement
- Gilded Mushroom anti-water mechanic is a nice touch
- Season bonuses encourage crop rotation

**Issue:** `is_harvestable()` only checks `days_grown >= growth_days`. The `no_water` path duplicates this exact check — the if/else is redundant.

### 10.4 Pets (`pets.py`) — Balanced but Uncapped

- Pet costs scale well (200g → 5000g)
- Food costs create daily maintenance sink
- Passives are thematic and varied

**Issue:** Multiple pets can stack the same passive type. Two Tonberry companions = +4 combat bonus. The `get_pet_passive()` function sums all fed pet bonuses without cap. This is limited by pet slots per housing tier (max 5 at Keep), but a player with 5 Tonberry companions gets +10 combat bonus, which is game-breaking.

**Fix:** Cap each passive type to its single-pet maximum value, OR enforce unique pet types per housing.

### 10.5 Calendar (`calendar.py`) — Excellent

Best subsystem in the project. Deterministic weather, seasonal encounters, special days. The TTRPG equivalent of a living world.

**Only issue:** No connection between `SPECIAL_DAYS[date].encounter_mod` and the encounter resolution code. The data exists but needs to be wired.

### 10.6 Session Manager (`session_manager.py`) — Correct but Minimal

- Per-channel async locking is properly implemented
- Two-layer lock pattern (global dict lock + per-channel lock) prevents races
- Atomic write with tmp+rename is correct

**Issue:** No session expiry. Stale sessions from crashed games persist forever. Add a `last_action_at` TTL check (e.g., expire after 2 hours of inactivity).

### 10.7 Character Manager (`character_manager.py`) — Solid

- Per-user async locking prevents race conditions
- Daily hunt reset correctly triggered on load
- Atomic write pattern consistent with session manager
- Starting equipment per class is reasonable

**Issue:** `equipment` dict uses `None` for empty slots but equipment resolution in `format_sheet()` handles this correctly with fallbacks. No issues found.

### 10.8 Alchemy (`alchemy.py`) — Functional but Tiny

Only 2 recipes. The crafting system infrastructure is sound (ingredient checking, XP on craft, recipe discovery on ingredient pickup), but the content is barely a proof of concept.

**Recommendation:** Add at minimum:
- Elixir recipe: `dire_root` + `silver_moss` → `elixir`
- Hi-Potion recipe: `blood_thistle` + `silver_moss` → `hi_potion`
- Panacea recipe: `dire_root` + `blood_thistle` + `gilded_mushroom` → `panacea`
- Ether recipe: `silver_moss` + `honey_sap` + `aeridor_shard` → `ether`

---

## 11. Recommendations — Prioritized

### 🔴 Priority 1 — Critical Fixes (Do Immediately)

1. **Add 7 missing monster stat blocks** to `MONSTERS` dict (§2.1). This is a runtime crash risk.
2. **Fix `droppable_only` indentation** in `equipment_registry.py` (§2.2). Move all instances to 8-space indent inside their item dicts. ~9 items affected.
3. **Delete `SEASONAL_MONSTER_STATS`** from `calendar.py` (§8.3). These duplicate `MONSTERS` entries and will desync.

### 🟡 Priority 2 — Balance Pass (Next Sprint)

4. **Apply total DEF soft-cap** that includes pet/class/weather bonuses, not just gear. Change combat engine to compute total_def first, then apply diminishing returns to the entire bonus (not just armor).
5. **Nerf Black Lotus** from ATK +10 to ATK +6. Nerf Ultima Weapon from ATK +12 to ATK +9. Nerf Excalibur from ATK +11 to ATK +9.
6. **Enforce unique pet types** per housing — prevent stacking identical pets.
7. **Split "hard" monster tier** into "hard" (L7-9 content) and "elite" (L9+ content), or add power-rating weighting to encounter resolution.
8. **Add per-combat lifesteal cap** (e.g., max 15 HP healed from lifesteal per fight) to prevent Shadowknight sustain loop.

### 🔵 Priority 3 — Code Quality (When Able)

9. **Migrate `equipment_registry.py`** to JSON data files + loader. This eliminates the formatting/indentation class of bugs entirely.
10. **Migrate `monster_registry.py`** similarly. Extract `ENCOUNTER_TABLES` to a separate data file.
11. **Delete or rewrite `balance_model.py`** — it currently provides false confidence in balance numbers.
12. **Wire calendar special day effects** (`encounter_mod`, `shop_special`, `shrine_gift`) to their respective handler functions.

### ⚪ Priority 4 — Feature Completion (Roadmap)

13. **Expand alchemy** to 6+ recipes using all existing ingredient types.
14. **Implement Mognet delivery** for Moogle pet passive.
15. **Wire furniture bonuses** (`home_brewing`, `daily_training`, `home_pray`, `home_scout`) to rpg_handler.
16. **Add session TTL** to session_manager (2-hour expiry).
17. **Add monster `power_rating`** field for within-tier encounter weighting.
18. **Implement weather enforcement** (`scout_blocked`, `armor_penalty`, `level_gate`).

---

*End of review. All findings are based on static analysis of the codebase as of 2026-04-04. Runtime testing is recommended to confirm the crash behavior of missing monster keys (§2.1) and validate the indentation issue severity (§2.2).*
