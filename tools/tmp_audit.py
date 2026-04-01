"""Audit equipment_registry.py for missing class tags, loot table gaps, and Hemlock stock issues."""
import sys
sys.path.insert(0, "/home/ekco/github/Kaiacord")

from utils.ttrpg.equipment_registry import (
    WEAPONS, ARMOR, HEADGEAR, BOOTS, ACCESSORIES,
    HEMLOCK_STOCK_WEAPONS, HEMLOCK_STOCK_ARMOR,
    HEMLOCK_STOCK_HEADGEAR, HEMLOCK_STOCK_BOOTS, HEMLOCK_STOCK_ACCESSORIES,
)

print("=" * 70)
print("1. ITEMS MISSING 'classes' TAG")
print("=" * 70)

for label, registry in [("WEAPONS", WEAPONS), ("ARMOR", ARMOR), ("HEADGEAR", HEADGEAR), ("BOOTS", BOOTS), ("ACCESSORIES", ACCESSORIES)]:
    for key, item in registry.items():
        if "classes" not in item:
            print(f"  {label}: {key:30s}  tier={item.get('tier','?')}  name={item['name']}")

print()
print("=" * 70)
print("2. ALL NEW CLASS-SPECIFIC ITEMS BY TIER (for loot table audit)")
print("=" * 70)

# Collect all class-specific new-section items (those defined in multi-line dict format)
for label, registry in [("WEAPONS", WEAPONS), ("ARMOR", ARMOR), ("HEADGEAR", HEADGEAR), ("BOOTS", BOOTS), ("ACCESSORIES", ACCESSORIES)]:
    for tier in range(1, 6):
        items_at_tier = [(k, v) for k, v in registry.items() if v.get("tier") == tier]
        if items_at_tier:
            for k, v in items_at_tier:
                pass  # just collecting
    # Print tier breakdown
    for tier in range(1, 6):
        items = [(k, v) for k, v in registry.items() if v.get("tier") == tier]
        if items:
            print(f"\n  {label} Tier {tier}:")
            for k, v in items:
                classes = v.get("classes", ["ANY"])
                print(f"    {k:35s} classes={classes}")

print()
print("=" * 70)
print("3. HEMLOCK STOCK VALIDATION")
print("=" * 70)

# Check for broken references
for label, stock, registry in [
    ("WEAPONS", HEMLOCK_STOCK_WEAPONS, WEAPONS),
    ("ARMOR", HEMLOCK_STOCK_ARMOR, ARMOR),
    ("HEADGEAR", HEMLOCK_STOCK_HEADGEAR, HEADGEAR),
    ("BOOTS", HEMLOCK_STOCK_BOOTS, BOOTS),
    ("ACCESSORIES", HEMLOCK_STOCK_ACCESSORIES, ACCESSORIES),
]:
    missing = [k for k in stock if k not in registry]
    if missing:
        print(f"  BROKEN {label} in Hemlock stock: {missing}")
    else:
        print(f"  {label} stock OK ({len(stock)} items)")

print()
print("=" * 70)
print("4. LOOT TABLE VALIDATION")
print("=" * 70)

# Check that loot table references exist
from utils.ttrpg.loot_tables import get_loot
from utils.ttrpg.shop import find_item

# Manually parse loot table keys since they're inside the function
import inspect
source = inspect.getsource(get_loot)

# Extract all item keys from the loot table source
import re
# Match quoted strings in the tables
all_loot_keys = set(re.findall(r'"([a-z_]+)"', source))
all_loot_keys.discard("none")
all_loot_keys.discard("trivial")
all_loot_keys.discard("easy")
all_loot_keys.discard("medium")
all_loot_keys.discard("hard")
all_loot_keys.discard("deadly")
all_loot_keys.discard("boss")

# Check each loot key resolves
broken_loot = []
for key in sorted(all_loot_keys):
    item = find_item(key)
    if not item:
        broken_loot.append(key)

if broken_loot:
    print(f"  BROKEN loot table references: {broken_loot}")
else:
    print(f"  All {len(all_loot_keys)} loot table keys resolve correctly")

# Count new items NOT in any loot table
print()
print("=" * 70)
print("5. NEW ITEMS NOT IN ANY LOOT TABLE (should they be?)")
print("=" * 70)

for label, registry in [("WEAPONS", WEAPONS), ("ARMOR", ARMOR), ("HEADGEAR", HEADGEAR), ("BOOTS", BOOTS), ("ACCESSORIES", ACCESSORIES)]:
    for k, v in registry.items():
        if k not in all_loot_keys:
            # Check aliases too
            from utils.ttrpg.equipment_registry import ALIASES
            aliased = any(alias_key in all_loot_keys for alias_key, alias_val in ALIASES.items() if alias_val == k)
            # Check legacy compatibility
            legacy = any(WEAPONS.get(lk) is v for lk in all_loot_keys if lk in WEAPONS) if label == "WEAPONS" else False
            if not aliased and not legacy:
                print(f"  {label}: {k:35s} tier={v.get('tier','?'):2} NOT in loot tables")
