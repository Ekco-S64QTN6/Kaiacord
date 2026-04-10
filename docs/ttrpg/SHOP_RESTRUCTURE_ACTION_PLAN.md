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
python scripts/restructure_equipment.py \
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
