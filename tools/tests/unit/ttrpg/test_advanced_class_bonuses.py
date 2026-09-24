"""Every bonus an advanced class advertises is applied somewhere.

Shaman's "Forest XP bonus" was defined (+20%) and printed in the class
description, and nothing ever read it.
"""
from pathlib import Path

from utils.ttrpg.class_advancement import ADVANCED_CLASSES

# Bonuses implemented by checking the class name rather than reading the key.
BY_CLASS_NAME = {
    "int_to_atk": ("combat_engine.py", 'adv_class == "Wizard"'),
    "wis_to_atk": ("combat_engine.py", 'adv_class == "High Priest"'),
    "crit_damage_bonus": ("combat_engine.py", 'adv_class == "Shadowblade"'),
    "heal_mult": ("rpg_core_handler.py", "heal_mult"),
    "gamble_edge": ("rpg_core_handler.py", "has_gamble_edge"),
}


def test_every_advertised_bonus_is_read():
    ttrpg = Path("utils/ttrpg")
    sources = {p.name: p.read_text(encoding="utf-8") for p in ttrpg.glob("*.py")}
    readers = "".join(v for k, v in sources.items() if k != "class_advancement.py")
    own = sources["class_advancement.py"].split("def get_title", 1)[1]   # code, not the table
    keys = {k for opts in ADVANCED_CLASSES.values() for d in opts.values() for k in d.get("bonuses", {})}
    unread = []
    for key in sorted(keys):
        if key in BY_CLASS_NAME:
            fname, marker = BY_CLASS_NAME[key]
            if marker not in sources[fname]:
                unread.append(f"{key} (expected {marker!r} in {fname})")
        elif f'"{key}"' not in readers and f'"{key}"' not in own:
            unread.append(key)
    assert not unread, unread


def test_shaman_forest_xp_applies_only_in_the_forest():
    src = Path("utils/ttrpg/rpg_combat_handler.py").read_text(encoding="utf-8")
    assert src.count('_b.get("forest_xp_bonus") and sheet.get("location") in FOREST_LOCATIONS') == 2


# ── Pets ────────────────────────────────────────────────────────────

def test_every_pet_passive_is_applied():
    """Wisp Lantern's +5% XP (1,000 gil) and Iron Pup's extra chests were
    advertised and applied nowhere."""
    from utils.ttrpg.pets import PET_REGISTRY
    ttrpg = Path("utils/ttrpg")
    code = "".join(p.read_text(encoding="utf-8") for p in ttrpg.glob("*.py") if p.name != "pets.py")
    keys = {d["passive"] for d in PET_REGISTRY.values()} | {
        k for d in PET_REGISTRY.values() for k in d.get("extra", {})}
    by_pet = {"weekly_delivery": 'p["key"] == "moogle"'}      # delivered on feeding
    missing = [k for k in sorted(keys)
               if (by_pet[k] if k in by_pet else f'"{k}"') not in code]
    assert not missing, missing


def test_extras_are_summed_with_the_main_passive():
    from utils.ttrpg.pets import get_pet_passive
    housing = {"pets": [{"key": "iron_pup", "fed_today": True},
                        {"key": "aeridor_construct", "fed_today": True},
                        {"key": "wisp_lantern", "fed_today": False}]}
    b = get_pet_passive(housing)
    assert b == {"def_bonus": 4, "extra_chest_pct": 0.05}
