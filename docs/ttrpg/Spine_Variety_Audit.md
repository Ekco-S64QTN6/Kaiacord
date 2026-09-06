# Comprehensive TTRPG System Review — Spine of the World Focus

*April 30, 2026 · Full codebase audit · Focus: Spine Dungeon creature variety, bugs, balance*

---

## 1. Executive Summary

The Aethelgard TTRPG is in **strong operational health overall**, but the Spine of the World mega-dungeon has **one critical bug and one major content problem** that significantly degrade the endgame experience:

1. **🔴 `NameError: is_spine`** — The boss warning system in `_dungeon_move` references an undefined variable `is_spine`, which will crash the game when a player approaches any boss room in **any** dungeon (Spine or overworld). This is a **live crash bug**.

2. **🔴 Extreme monster repetition** — All 77 floors share only **5 floor templates** with **16 hardcoded monster keys** total. `iron_golem` appears in **90 combat rooms**. A player traversing the Spine fights the same 3-4 creatures per zone for 15 consecutive floors.

3. **🟡 Spine encounter table unused in dungeon rooms** — The excellent 45-creature `ENCOUNTER_TABLES["spine_of_the_world"]` is only used for *overworld hunts*. Dungeon room monsters are hardcoded in `spine_layouts.json`, bypassing the encounter table entirely.

**Verdict:** The Spine's content infrastructure (45 unique monsters, 5 zone-specific pools, 77 stair guardians, 50 unique equipment items) is excellent. The problem is a plumbing bug: the layout builder hardcodes the same 16 monsters from the 5 template files instead of drawing from the per-zone encounter pools.

---

## 2. Bug Inventory

### 🔴 BUG-R18: `NameError: is_spine` in `_dungeon_move` boss warning (CRASH)

| Field | Detail |
|---|---|
| **Severity** | 🔴 Critical — crashes the game |
| **File** | [rpg_views.py](../../utils/ttrpg/rpg_views.py#L2294) |
| **Line** | 2294 |
| **Description** | `BossApproachView(ctx_obj, uid, uname, is_owner, direction, is_spine=is_spine)` — the variable `is_spine` is never defined in `_dungeon_move()`. The `state` dict is loaded but never queried for `is_spine`. |
| **Trigger** | Any player approaching an uncleared boss room in **any** dungeon (Spine or overworld procedural). The `warn_key` check at line 2280 fires, then line 2294 crashes with `NameError`. |
| **Impact** | Complete game halt. Player cannot proceed past any boss room. |
| **Fix** | Add `is_spine = state.get("is_spine", False)` before line 2280, or inline it in the constructor call: `is_spine=state.get("is_spine", False)`. |

### 🟡 BUG-R19: Spine dungeon rooms use hardcoded monsters instead of encounter pools

| Field | Detail |
|---|---|
| **Severity** | 🟡 Major — content degradation, not a crash |
| **File** | [build_spine_layouts.py](../../utils/ttrpg/build_spine_layouts.py) |
| **Description** | The 5 floor templates (`F1M` through `F5M`) hardcode `monster_key` values like `"hydra"`, `"iron_golem"`, `"dark_rider"`. Since all 77 floors reuse these 5 templates (floors 1-15 all use F1M, 16-30 all use F2M, etc.), the same 3-4 creatures repeat on every floor within a zone. |
| **Data** | Only **16 unique monster keys** across all **663 combat rooms** in 77 floors. `iron_golem` appears in **90 rooms**. Meanwhile, the `ENCOUNTER_TABLES["spine_of_the_world"]` has **45 unique creatures** in 5 zone-specific pools — but they're never used for dungeon rooms. |
| **Fix** | Modify `build_spine_layouts.py` to **randomly assign `monster_key` from the zone's encounter pool** instead of hardcoding from the template. Each floor should draw from its zone's pool in `ENCOUNTER_TABLES["spine_of_the_world"]`. See Proposed Changes below. |

### 🟢 CQ-R5: Duplicate `ether` in medium consumable loot tier

| Field | Detail |
|---|---|
| **Severity** | 🟢 Trivial — cosmetic |
| **File** | [loot_tables.py](../../utils/ttrpg/loot_tables.py#L306-L307) |
| **Lines** | 306-307 |
| **Description** | Two separate `("ether", 5)` and `("ether", 11)` tuples in the medium consumable tier. Functionally correct (combined weight = 16) but untidy. Should be merged to `("ether", 16)`. |

### Previously identified, still present:
- **CQ-R2**: Dead `bone_shield_passive` — referenced in [combat_engine.py](../../utils/ttrpg/combat_engine.py#L54) lines 54/154 and [rpg_core_handler.py](../../utils/ttrpg/rpg_core_handler.py#L420-L421) lines 420-421. No advanced class defines this bonus. Always evaluates to 0.

---

## 3. Balance Analysis — Spine Dungeon

### 3.1 Monster Difficulty Curve in the Spine

The Spine dungeon is set to `difficulty: 5` (max). The `_dungeon_move` handler applies these caps to non-boss Spine mobs:

```
MOB_HP_CAPS  = {5: 180}
MOB_ATK_CAPS = {5: 22}  (further capped by level-based ATK: level*1.5+2)
```

**Finding:** The Spine encounter table creatures have wildly varying base stats:

| Zone | Creature | Base HP | Base ATK | Tier | After D5 Scaling (×1.60) | After D5 Cap |
|---|---|---|---|---|---|---|
| Working Tunnels | blind_cave_leech | 45 | 8 | easy | 72 HP, 12 ATK | 72/12 ✅ |
| Working Tunnels | foremans_enforcer | 110 | 15 | medium | 176 HP, 24 ATK | 176/22 ✅ |
| Heart of Mountain | core_warped_behemoth | 450 | 38 | deadly | 720 HP, 60 ATK | **180/22** ⚠️ |
| Heart of Mountain | crystal_golem | 450 | 33 | deadly | 720 HP, 52 ATK | **180/22** ⚠️ |

> [!WARNING]
> **All Spine mobs are capped to the same 180 HP / 22 ATK regardless of floor depth.** A Floor 1 encounter and a Floor 77 encounter feel identical in difficulty because the D5 cap flattens everything. The rich stat variety in the monster registry (45-450 HP, 8-38 ATK) is completely negated by the uniform cap.

**Recommendation:** The Spine should use **floor-based scaling** instead of a flat difficulty cap. Proposed formula:

```python
# Floor-based HP/ATK scaling for Spine
spine_hp_cap  = 80 + (floor_num * 3)    # F1: 83,  F40: 200, F77: 311
spine_atk_cap = 12 + (floor_num // 5)   # F1: 12,  F40: 20,  F77: 27
```

This preserves the early-floor accessibility while making deeper floors progressively harder, matching the zone-specific monster stat budgets.

### 3.2 Stair Guardians — Well-Designed

The 77 stair guardians are properly scaled by floor depth:
- F1 (Foreman Kregg): 280 HP, 22 ATK — appropriate early boss
- F40 (The First Miner): appropriate mid-dungeon boss
- F77 (The Mountain Heart): 900 HP, 38 ATK, 38 DEF — endgame superboss

Guardian combat is handled separately from normal room combat (through `_descend_cb`), so guardians bypass the D5 mob caps. This is correct behavior.

### 3.3 Loot Tier by Depth — Correct

```python
def _loot_tier(floor_num):
    if floor_num <= 25: return 3   # hard tier
    if floor_num <= 50: return 4   # deadly tier
    return 5                        # boss tier
```

This maps correctly to the loot tables and Spine equipment tiers (Upper Set T4 for floors 1-40, Lower Set T5 for 41-77).

---

## 4. The Monster Variety Problem — Detailed Analysis

### 4.1 Root Cause

`build_spine_layouts.py` defines 5 floor templates with hardcoded monster keys:

```python
F1M = {
    "F": {"type":"monster", "monster_key":"hydra"},      # same on all 15 floors
    "H": {"type":"monster", "monster_key":"dark_rider"},  # same on all 15 floors
    "L": {"type":"monster", "monster_key":"bone_devil"},  # same on all 15 floors
    ...
}
```

When generating floor N, the builder picks template `F1M` (for N≤15), `F2M` (N≤30), etc. The `get_dynamic_lore()` function modifies room *descriptions* per floor but never touches `monster_key`. The result:

| Zone | Floors | Template | Hardcoded Monsters | Reps per Monster |
|---|---|---|---|---|
| Working Tunnels | 1-15 | F1M | hydra, dark_rider×3, bone_devil, iron_golem×2, manticore | ~15 each |
| Bone Warrens | 16-30 | F2M | death_tyrant×2, shadow_lich×2, bone_devil×3, dark_rider | ~15 each |
| Sunken Forge | 31-45 | F3M | iron_golem×4, dragon×3, iron_giant_ff, adamantoise | ~15 each |
| Deep Dark | 46-60 | F4M | mindflayer×3, behemoth×2, beholder, wyvern×2, shadow_lich | ~15 each |
| Heart of Mountain | 61-77 | F5M | iron_giant_ff×4, great_behemoth×3, storm_giant×2 | ~17 each |

### 4.2 Meanwhile, Unused Creature Pools

The `ENCOUNTER_TABLES["spine_of_the_world"]` already has 45 creatures in 5 perfectly themed pools:

| Zone Pool | Creatures | Notes |
|---|---|---|
| working_tunnels | 9 | tunnel_crawler, abandoned_miner_ghoul, cave_troll, blind_cave_leech, rust_lung_miner, chittering_skitterer, iron_blight_bat, subterranean_prowler, foremans_enforcer |
| bone_warrens | 9 | bone_weaver_spider, crypt_stalker, ossuary_golem, marrow_hound, crypt_warden, whispering_skull_swarm, ash_wraith, ossified_terror, entombed_scholar |
| sunken_forge | 9 | forge_fire_elemental, slag_horror, iron_sentinel, slag_crawler_spine, ignited_sentinel, smoldering_ash_walker, molten_slime, brass_plated_hound, forge_fire_wisp |
| deep_dark | 9 | void_stalker, abyssal_crawler, mind_flayer_outcast, void_touched_weaver, deep_stalker, abyssal_leech_spine, eyeless_horror, resonance_warped_troll, the_lurking_shadow |
| heart_of_mountain | 9 | crystal_golem, resonance_wraith, core_guardian, pulse_walker, crystalline_abomination, flesh_forged_construct, the_mountains_white_blood, aeridorian_echo, core_warped_behemoth |

**Additionally**, there are 20+ dragons and bosses from the broader bestiary that thematically fit different Spine zones but aren't in any pool.

---

## 5. Proposed Changes

### Fix 1: BUG-R18 — Define `is_spine` in `_dungeon_move`

#### [MODIFY] [rpg_views.py](../../utils/ttrpg/rpg_views.py#L2262)

Add `is_spine = state.get("is_spine", False)` after the state is loaded (around line 2262), before the boss warning block.

---

### Fix 2: Dynamic monster assignment in `build_spine_layouts.py`

#### [MODIFY] [build_spine_layouts.py](../../utils/ttrpg/build_spine_layouts.py)

Instead of using the hardcoded `monster_key` from template metadata, the `build()` function should randomly select from the appropriate zone's encounter pool for each combat room. The zone is determined by floor number.

**Key changes:**
1. Import `ENCOUNTER_TABLES` from `monster_registry.py`
2. Map floor ranges to zone keys: `1-15 → working_tunnels`, `16-30 → bone_warrens`, etc.
3. In the `build()` function, for any room with type `monster` or `guard`, replace the template's `monster_key` with a random pick from the zone pool
4. Regenerate `spine_layouts.json`

#### [REGENERATE] [spine_layouts.json](../../utils/ttrpg/spine_layouts.json)

After modifying the builder, regenerate the 4MB JSON file. Each of the ~663 combat rooms will now have a random monster from its zone's 9-creature pool instead of repeating the same hardcoded monster.

---

### Enhancement 3: Expand zone pools to 15+ creatures each

#### [MODIFY] [monster_registry.py](../../utils/ttrpg/monster_registry.py#L2256)

Expand each zone pool from 9 to 15+ creatures by incorporating thematically appropriate existing monsters from the broader bestiary, plus adding ~20 new Spine-exclusive creatures. The goal is that a player traversing 15 floors of a zone encounters a different creature in almost every room.

**Proposed expanded pools:**

| Zone | Current | Add from Bestiary | New Creatures | Total |
|---|---|---|---|---|
| Working Tunnels (1-15) | 9 | cave_troll, kobold, giant_rat_mtg, stirge, fire_beetle | +5 new mine-themed (pit_viper, rubble_golem, gas_spore, ore_mimic, tunnel_wyrm) | ~19 |
| Bone Warrens (16-30) | 9 | skeleton, ghoul, ghost, wight, wraith, revenant, dullahan | +4 new undead (bone_amalgam, corpse_lantern, charnel_crawler, burial_mimic) | ~20 |
| Sunken Forge (31-45) | 9 | iron_golem, bomb, grenade | +5 new forge-themed (crucible_ooze, bellows_construct, anvil_golem, chain_horror, furnace_wight) | ~17 |
| Deep Dark (46-60) | 9 | beholder, mindflayer, umber_hulk, hook_horror, grimlock | +4 new void-themed (void_lamprey, psychic_leech, null_wraith, thought_eater) | ~18 |
| Heart of Mountain (61-77) | 9 | storm_giant, elder_treant, ancient_red_dragon | +5 new endgame (resonance_golem, vessel_husk, core_parasite, mountain_nerve, tithe_collector) | ~17 |

> [!IMPORTANT]
> New monsters should follow the stat budgets for their zone tiers:
> - Working Tunnels: easy/medium (30-110 HP, 8-15 ATK)
> - Bone Warrens: medium/hard (70-150 HP, 12-18 ATK)
> - Sunken Forge: hard/deadly (100-250 HP, 15-25 ATK)
> - Deep Dark: hard/deadly (150-350 HP, 20-30 ATK)
> - Heart of Mountain: deadly (200-450 HP, 25-38 ATK)

---

### Enhancement 4: Floor-based scaling for Spine mobs (optional)

#### [MODIFY] [rpg_views.py](../../utils/ttrpg/rpg_views.py#L2343)

Replace the flat D5 caps in `_dungeon_move` with floor-aware scaling when `state.get("is_spine")`:

```python
if state.get("is_spine"):
    floor_num = state.get("floor_num", 1)
    mob_hp_cap = 80 + (floor_num * 3)
    mob_atk_cap = 12 + (floor_num // 5)
else:
    mob_hp_cap = MOB_HP_CAPS.get(diff, 180)
    mob_atk_cap = MOB_ATK_CAPS.get(diff, 22)
```

---

## 6. Verification Plan

### Automated
1. `python3 -c "import ast; ast.parse(open('utils/ttrpg/rpg_views.py').read())"` — syntax check
2. `python3 -c "import ast; ast.parse(open('utils/ttrpg/build_spine_layouts.py').read())"` — syntax check
3. `python3 -c "import ast; ast.parse(open('utils/ttrpg/monster_registry.py').read())"` — syntax check
4. Regenerate `spine_layouts.json` and verify:
   - All `monster_key` values in combat rooms resolve in `MONSTERS`
   - No `null` monster keys in combat rooms
   - Each zone has ≥9 unique monster keys across its 15 floors
   - `stairs_up_key` and `stairs_down_key` present on all floors
5. `grep -n "is_spine" utils/ttrpg/rpg_views.py` — verify the variable is defined before use

### Manual
- Enter Spine dungeon and traverse floors 1-5, confirming varied creature encounters
- Approach a boss room and confirm no crash (BUG-R18 fix)

---

## 7. Code Quality Notes

### Still Present from Previous Report
| ID | File | Note | Status |
|---|---|---|---|
| CQ-R2 | `combat_engine.py` | Dead `bone_shield_passive` references | 🟢 No functional impact |
| CQ-R3 | `housing.py` + `progression.py` | Double daily reset | 🟢 No functional impact |
| CQ-R4 / CQ-R5 | `loot_tables.py` | Duplicate `ether` entry in medium tier | 🟢 Cosmetic |
| CQ-N3 | `rpg_core_handler.py` | 2,344 lines — could split | 🟢 Maintainability |
| CQ-N4 | Multiple handlers | Boilerplate import blocks | 🟢 Maintainability |

### New Observations
| ID | File | Note | Effort | Impact |
|---|---|---|---|---|
| CQ-R6 | `build_spine_layouts.py` L42-43 | `import secrets` inside loop body — should be at module level | 🟢 Trivial | 🟢 Cleanliness |
| CQ-R7 | `build_spine_layouts.py` L465 | Import from `utils.ttrpg.spine_dungeon` inside `main()` — stair guardians loaded but never actually used in layout generation | 🟢 Trivial | 🟢 Dead code |
| CQ-R8 | `spine_dungeon.py` L38 | `GRID_SIZE = 15` constant unused — layouts use `layout["grid_size"]` from JSON which is 24 | 🟢 Trivial | 🟢 Dead constant |
| CQ-R9 | `spine_dungeon.py` L154 | `import copy` inside function body — should be at module level | 🟢 Trivial | 🟢 Cleanliness |

---

## 8. Prioritized Recommendations

| Priority | Task | Files | Effort | Impact |
|---|---|---|---|---|
| 🔴 P0 | **Fix `is_spine` NameError** (BUG-R18) — live crash bug | `rpg_views.py` | 🟢 5min | 🔴 Blocks all boss encounters |
| 🔴 P1 | **Randomize Spine room monsters from zone pools** — fix repetition | `build_spine_layouts.py`, `spine_layouts.json` | 🟡 30min | 🔴 Core gameplay quality |
| 🟠 P2 | **Expand zone pools to 15-20 creatures each** — add variety | `monster_registry.py` | 🟡 1-2h | 🟠 Content depth |
| 🟡 P3 | **Floor-based scaling for Spine mobs** — progressive difficulty | `rpg_views.py` | 🟢 15min | 🟡 Balance improvement |
| 🟢 P4 | **Merge duplicate ether entry** (CQ-R5) | `loot_tables.py` | 🟢 1min | 🟢 Cleanliness |
| 🟢 P5 | **Remove dead `bone_shield_passive`** (CQ-R2) | `combat_engine.py`, `rpg_core_handler.py` | 🟢 15min | 🟢 Dead code cleanup |
| 🟢 P6 | **Add L8/L10 quests** to fill mid-game gap | `quest_registry.py` | 🟠 1-2h | 🟡 Content gap |

---

## Open Questions

> [!IMPORTANT]
> **Question 1:** Should I proceed with implementing P0 (crash fix) and P1 (randomized monsters from zone pools) immediately? These are the two highest-priority items and are independent of the expanded pool work.

> [!IMPORTANT]
> **Question 2:** For the expanded creature pools (P2), do you want me to create the ~20 new Spine-exclusive monsters, or would you prefer to just pull from the existing 310-creature bestiary to fill out the pools? Creating new ones adds more flavor but takes more effort.

> [!IMPORTANT]  
> **Question 3:** For floor-based scaling (P3), the current D5 cap makes all Spine mobs feel the same difficulty. Do you want progressive scaling so Floor 60+ mobs are noticeably harder than Floor 1 mobs, or do you prefer the current flat difficulty?
