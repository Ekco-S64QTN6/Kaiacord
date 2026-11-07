"""
rare_spawns.py — rare variants of ordinary overworld monsters.

One overworld spawn in RARE_ONE_IN is a variant: the same creature (its key,
so quest kills still count) with a prefixed name, more HP, much better XP and
Gil, and a guaranteed drop of its own. ATK is not raised; the overworld ATK cap
in the hunt handler still applies afterwards. A Gilded Migration noon event
(``rare_spawn_boost_until`` in world state) makes them RARE_BOOSTED_ONE_IN.

Pure functions; the hunt handler owns the sheet, the session and the save.
"""
import secrets
import time

from utils.ttrpg.forest_events_rare import is_night

RARE_ONE_IN = 40
RARE_BOOSTED_ONE_IN = 10

VARIANTS = {
    "gilded": {
        "prefix": "Gilded", "emoji": "🪙", "hp": 1.3, "xp": 2.0, "gil": 5.0, "drop": "gem",
        "desc": "Gold leaf flecks its hide. Nobody put it there.",
    },
    "elder": {
        "prefix": "Elder", "emoji": "🌳", "hp": 1.6, "xp": 3.0, "gil": 2.0, "drop": "gear",
        "desc": "Older than it has any right to be. It has outlived everyone who hunted it.",
    },
    "pale": {
        "prefix": "Pale", "emoji": "🌫️", "hp": 1.4, "xp": 2.5, "gil": 2.0, "drop": "lore:any",
        "night_only": True,
        "desc": "Colourless, as if the night had worn it thin. It makes no sound at all.",
    },
    "whispering": {
        "prefix": "Whispering", "emoji": "🍃", "hp": 1.4, "xp": 2.5, "gil": 2.0, "drop": "lore:silvani",
        "locations": {"whisperwood_edge", "whisperwood_deep"},
        "desc": "The leaves around it repeat what it says. It is saying your name.",
    },
    "resonant": {
        "prefix": "Resonant", "emoji": "💎", "hp": 1.4, "xp": 2.5, "gil": 2.5, "drop": "lore:aeridor",
        "locations": {"aeridor_ruins"},
        "desc": "Crystal grows along its spine and rings faintly whenever it moves.",
    },
}

# Gems a Gilded variant can carry: (item, weight)
GEM_DROPS = [("opal", 50), ("black_pearl", 30), ("star_ruby", 15), ("diamond", 5)]
_TIER_UP = {"trivial": "easy", "easy": "medium", "medium": "hard", "hard": "deadly",
            "deadly": "boss", "boss": "boss"}


def _weighted(pairs):
    total = sum(w for _, w in pairs)
    r = secrets.randbelow(total)
    for key, w in pairs:
        if r < w:
            return key
        r -= w
    return pairs[-1][0]


def eligible_variants(location: str, *, hour: int | None = None) -> list[str]:
    night = is_night(hour)
    out = []
    for key, v in VARIANTS.items():
        if v.get("night_only") and not night:
            continue
        if "locations" in v and location not in v["locations"]:
            continue
        out.append(key)
    return out


def roll_variant(location: str, monster: dict, wstate: dict | None = None, *,
                 hour: int | None = None, now: float | None = None) -> str | None:
    """Which variant this spawn is, if any. Bosses and quest raiders never are."""
    if monster.get("tier") == "boss" or monster.get("is_blockade_raid"):
        return None
    try:
        boosted = float((wstate or {}).get("rare_spawn_boost_until", 0) or 0) > (time.time() if now is None else now)
    except (TypeError, ValueError):
        boosted = False
    if secrets.randbelow(RARE_BOOSTED_ONE_IN if boosted else RARE_ONE_IN) != 0:
        return None
    choices = eligible_variants(location, hour=hour)
    return secrets.choice(choices) if choices else None


def apply_variant(instance: dict, variant: str) -> dict:
    """Make a spawned monster instance into its rare variant, in place."""
    v = VARIANTS[variant]
    instance["rare_variant"] = variant
    instance["name"] = f"{v['prefix']} {instance.get('name', 'Creature')}"
    hp = instance.get("hp")
    if isinstance(hp, dict):
        top = max(1, int(hp.get("max", 1) * v["hp"]))
        instance["hp"] = {"current": top, "max": top}
    else:
        instance["hp"] = max(1, int((hp or 1) * v["hp"]))
    instance["xp"] = int(instance.get("xp", 10) * v["xp"])
    instance["gil"] = int(instance.get("gil", 5) * v["gil"])
    base = instance.get("desc") or instance.get("description") or ""
    instance["desc"] = f"{base} {v['desc']}".strip()
    return instance


def kill_rewards(sheet: dict, monster: dict) -> tuple[list[str], dict | None]:
    """The variant's own drop, granted onto the sheet: (loot lines, lore grant or None)."""
    variant = monster.get("rare_variant")
    if variant not in VARIANTS:
        return [], None
    from utils.ttrpg.inventory_capacity import grant_item
    from utils.ttrpg.shop import find_item

    def give(item_key, icon):
        info = find_item(item_key)
        name = info["name"] if info else item_key
        if grant_item(sheet, item_key):
            return f"{icon} {name}"
        return f"🎒 **[Inventory Full]** Left behind: {name}"

    drop = VARIANTS[variant]["drop"]
    grant = None
    lines = []
    if drop.startswith("lore:"):
        from utils.ttrpg.lore import grant_page
        grant = grant_page(sheet, drop.split(":", 1)[1])
        if grant is None:
            drop = "gem"          # every page already found: it carries a gem instead
    if drop == "gear":
        from utils.ttrpg.loot_tables import get_gear_loot
        tier = _TIER_UP.get(monster.get("tier", "medium"), "hard")
        gear = None
        for _ in range(6):
            gear = get_gear_loot(tier)
            if gear:
                break
        drop = "gem" if not gear else drop
        if gear:
            lines.append(give(gear, "⚔️"))
    if drop == "gem":
        lines.append(give(_weighted(GEM_DROPS), "💎"))
    return lines, grant
