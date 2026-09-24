"""Every key a TTRPG table names exists in the registry it points into.

A misspelt key in a weighted table is silent: the roll lands on it and the
player gets nothing, or the lookup returns None and a caller falls through.
"""
import ast
import inspect

from utils.ttrpg import alchemy, encounter_tables, forest_events, loot_tables
from utils.ttrpg import monster_registry as mr
from utils.ttrpg.equipment_registry import get_equipment


def _weighted_keys(fn):
    tree = ast.parse(inspect.getsource(fn))
    return {n.elts[0].value for n in ast.walk(tree)
            if isinstance(n, ast.Tuple) and len(n.elts) == 2
            and isinstance(n.elts[0], ast.Constant) and isinstance(n.elts[0].value, str)
            and isinstance(n.elts[1], ast.Constant) and isinstance(n.elts[1].value, int)}


def test_loot_tables_name_real_items():
    keys = _weighted_keys(loot_tables.get_gear_loot) | _weighted_keys(loot_tables.get_consumable_loot)
    assert keys, "no weighted entries found — re-point this test"
    assert not sorted(k for k in keys - {"none"} if get_equipment(k) is None)


def test_alchemy_names_real_items_and_recipes():
    bad = [k for r in alchemy.ALCHEMY_RECIPES.values()
           for k in r["ingredients"] + [r["result"]] if get_equipment(k) is None]
    for table in (alchemy.INGREDIENT_DISCOVERS, alchemy.SECONDARY_DISCOVERS):
        for ingredient, recipes in table.items():
            if get_equipment(ingredient) is None:
                bad.append(ingredient)
            bad += [r for r in (recipes if isinstance(recipes, (list, tuple)) else [recipes])
                    if r not in alchemy.ALCHEMY_RECIPES]
    assert not bad, bad


def test_encounters_name_real_monsters():
    bad = []

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            if len(x) == 2 and isinstance(x[0], str) and isinstance(x[1], (int, float)):
                if x[0] not in mr.MONSTERS:
                    bad.append(x[0])
            else:
                for y in x:
                    walk(y)

    walk(mr.ENCOUNTER_TABLES)
    walk(encounter_tables.QUEST_ENCOUNTER_OVERRIDES)
    assert not bad, bad


def test_every_rollable_event_has_a_handler():
    src = inspect.getsource(forest_events.resolve_event)
    handlers = {k.value for k in [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Dict)][0].keys}
    rolled = {ek for t in encounter_tables.EVENTS.values() for ek, _ in t}
    assert rolled - handlers == set()
