"""
forest_events_rare.py — rarer forest events, night-only events and easter eggs.

Each handler is pure: it returns the same result dict as forest_events and
never touches disk. Two optional keys are read by the hunt handler:

  lore_add   — a lore page ID, a set ID ("aeridor"), or "any" (utils/ttrpg/lore.py)
  broadcast  — True: the find is posted to #aethelgard as town news

Which of these can be rolled is decided by ``adjust_table`` (night-only events,
the noon events that boost them) and ``roll_legendary`` (the easter eggs).
"""
import secrets
import time
from datetime import datetime

from utils.ttrpg import lore

# Rolled before the location table, once per forest event. 1 in 120 forest
# events is a legendary one; with five event rolls a day that is roughly one
# a month for a player who hunts daily.
LEGENDARY_ONE_IN = 120
LEGENDARY = {
    # key: locations it can happen in
    "door_in_the_oak": ("whisperwood_edge", "whisperwood_deep"),
    "the_tablet":      ("aeridor_ruins", "whisperwood_deep"),
    "gilded_stag":     ("whisperwood_edge", "whisperwood_deep", "trade_road"),
}

# Only rolled between 18:00 and 06:00 (a Starfall noon event lets stars fall by day).
NIGHT_ONLY = {"fallen_star", "quiet_hunter"}
# Events that hand out lore pages; a Wandering Scholar noon event doubles them.
LORE_EVENTS = {"cartographers_cairn", "fallen_courier", "songstone", "lantern_shrine"}


def _base(key: str, title: str) -> dict:
    return {
        "event_key": key, "title": title, "outcome": "",
        "xp": 0, "gil": 0, "hp_change": 0,
        "condition_add": "", "condition_remove": "",
        "extra_hunt": False, "item_add": "",
        "narration_hook": "", "lore_add": "", "broadcast": False,
    }


def is_night(hour: int | None = None) -> bool:
    hour = datetime.now().hour if hour is None else hour
    return hour >= 18 or hour < 6


def _active(wstate: dict, key: str, now: float | None = None) -> bool:
    try:
        return float((wstate or {}).get(key, 0) or 0) > (time.time() if now is None else now)
    except (TypeError, ValueError):
        return False


def adjust_table(table: list, wstate: dict, *, hour: int | None = None, now: float | None = None) -> list:
    """The location's event table as it stands right now."""
    starfall = _active(wstate, "starfall_until", now)
    scholar = _active(wstate, "lore_scholar_until", now)
    night = is_night(hour)
    out = []
    for key, weight in table:
        if key in NIGHT_ONLY and not night and not (starfall and key == "fallen_star"):
            continue
        if key == "fallen_star" and starfall:
            weight *= 3
        if key in LORE_EVENTS and scholar:
            weight *= 2
        out.append((key, weight))
    return out or list(table)


def roll_legendary(location: str, wstate: dict | None = None) -> str | None:
    """One in LEGENDARY_ONE_IN forest events is an easter egg, if one lives here."""
    eligible = [k for k, locs in LEGENDARY.items() if location in locs]
    if not eligible or secrets.randbelow(LEGENDARY_ONE_IN) != 0:
        return None
    return secrets.choice(eligible)


def _stat_mod(sheet: dict, stat: str) -> int:
    return (sheet.get("stats", {}).get(stat, 10) - 10) // 2


def _lore_or_gil(r: dict, sheet: dict, ref: str, gil: int) -> bool:
    """Point the event at a lore page, or pay gil when there is none left to find."""
    probe = {"lore_pages": list(lore.owned(sheet))}
    target = lore.next_missing(probe, ref) if ref in lore.LORE_SETS else (None if ref in probe["lore_pages"] else ref)
    if target:
        r["lore_add"] = target
        return True
    r["gil"] += gil
    return False


# ─── Lore events ──────────────────────────────────────────────────────────────

def cartographers_cairn(sheet: dict) -> dict:
    r = _base("cartographers_cairn", "🧭 The Cartographer's Cairn")
    r["xp"] = 15
    if _lore_or_gil(r, sheet, "road", 25):
        r["outcome"] = "Under the top stone of a waymarker cairn: an oilcloth packet of notes. +15 XP."
    else:
        r["outcome"] = "The cairn holds a few coins left for the next traveller. +15 XP, +25 Gil."
    r["narration_hook"] = (
        "A cairn of flat stones by the roadside, built by someone careful. Wedged under the top stone was "
        "a packet wrapped in oilcloth, the kind cartographers use, left for whoever came next."
    )
    return r


def fallen_courier(sheet: dict) -> dict:
    r = _base("fallen_courier", "✉️ The Fallen Courier")
    r["xp"] = 20
    if _lore_or_gil(r, sheet, "aeridor", 40):
        r["outcome"] = "A courier's bones, still holding a sealed Aeridorian dispatch. +20 XP."
    else:
        r["outcome"] = "A courier's bones and a purse of old coin. You have read everything they carried. +20 XP, +40 Gil."
    r["narration_hook"] = (
        "Bones in a courier's harness, slumped against a pillar as if resting. The satchel's seal was "
        "Aeridorian and unbroken. Whatever the message was, it had been on its way for three hundred years."
    )
    return r


def songstone(sheet: dict) -> dict:
    r = _base("songstone", "🎵 The Songstone")
    roll = secrets.randbelow(20) + 1 + _stat_mod(sheet, "wis")
    if roll >= 11:
        r["xp"] = 20
        if _lore_or_gil(r, sheet, "silvani", 20):
            r["outcome"] = "You hum back the stone's note, and it answers with a verse. +20 XP."
        else:
            r["outcome"] = "The stone sings a verse you already know. You sing it with it. +20 XP, +20 Gil (left by an earlier listener)."
        r["narration_hook"] = (
            "A grey stone in a ring of moss, humming one low note. The player hummed it back. "
            "The stone changed key, and for a moment the whole clearing was singing in Silvani."
        )
    else:
        r["xp"] = 5
        r["hp_change"] = -4
        r["outcome"] = "You touch the humming stone and the note goes through your teeth. -4 HP, +5 XP."
        r["narration_hook"] = (
            "A humming stone. The player put a hand on it, which was the wrong thing to do: the note went "
            "up the arm and into the jaw, and the forest went very quiet afterwards, as if embarrassed."
        )
    return r


def lantern_shrine(sheet: dict) -> dict:
    r = _base("lantern_shrine", "🏮 The Lantern Shrine")
    if sheet.get("gil", 0) >= 10:
        r["gil"] = -10
        r["xp"] = 20
        if _lore_or_gil(r, sheet, "tonberry", 10):
            r["outcome"] = "You leave 10 Gil at a tiny lantern shrine. Something writes your name in a ledger. +20 XP."
        else:
            r["outcome"] = "You leave 10 Gil at the lantern shrine. A lantern dims, approving. +20 XP."
        r["narration_hook"] = (
            "A shrine no higher than a knee, crowded with tiny lanterns, each one lit. The player left a few "
            "coins. When they looked back, one lantern had gone out and a page of a ledger lay where it had been."
        )
    else:
        r["xp"] = 5
        r["outcome"] = "A tiny lantern shrine. You have nothing to leave. Every lantern turns slightly toward you. +5 XP."
        r["narration_hook"] = (
            "A shrine of small lanterns. The player had no coin to leave, and every flame leaned their way "
            "as they passed, the way a clerk leans over an unpaid account."
        )
    return r


# ─── Rare events ──────────────────────────────────────────────────────────────

def mirror_pool(sheet: dict) -> dict:
    r = _base("mirror_pool", "🪞 The Mirror Pool")
    if secrets.randbelow(2) == 0:
        r["xp"] = 25
        r["condition_add"] = "mirror_resolve"
        r["outcome"] = "Your reflection nods, a beat before you do. +25 XP, *Mirror Resolve* (+2 damage next fight)."
        r["narration_hook"] = (
            "A pool so still it looked like glass. The reflection in it nodded first, then drew its blade "
            "first, and the player found their own hand following, faster than usual."
        )
    else:
        r["xp"] = 20
        r["hp_change"] = -6
        r["outcome"] = "Your reflection reaches up out of the water. You pull back, scratched. -6 HP, +20 XP."
        r["narration_hook"] = (
            "A perfectly still pool. The reflection did not wait for the player to move. It reached for "
            "the surface from underneath, and the player stumbled back with four thin scratches on one wrist."
        )
    return r


def wandering_stall(sheet: dict) -> dict:
    r = _base("wandering_stall", "🎪 The Stall That Wasn't There")
    roll = secrets.randbelow(10)
    gem = "black_pearl" if roll == 0 else "opal" if roll < 4 else "pearl"
    r["xp"] = 10
    r["item_add"] = gem
    r["outcome"] = f"A peddler with no face you can remember gives you a {gem.replace('_', ' ')} for 'the walk'. +10 XP."
    r["narration_hook"] = (
        "A market stall stood alone at the roadside, cloth awning and all, with a peddler who insisted the "
        "player take something 'for the walk'. When the player looked back, there was only grass."
    )
    return r


def seven_crows(sheet: dict) -> dict:
    r = _base("seven_crows", "🐦‍⬛ Seven Crows")
    r["xp"] = 15
    if "oddity_seven" not in lore.owned(sheet):
        r["lore_add"] = "oddity_seven"
        r["condition_add"] = "lucky"
        r["outcome"] = "Seven crows, then eight. You feel oddly lucky. +15 XP, *Lucky*."
    else:
        r["outcome"] = "Seven crows on a branch. You count them twice. Still seven. +15 XP."
    r["narration_hook"] = (
        "Seven crows on one branch, all facing the same way. The player looked where they were looking and "
        "saw nothing. Looking back, there were eight, and the eighth was looking at the player."
    )
    return r


def the_other_hemlock(sheet: dict) -> dict:
    r = _base("the_other_hemlock", "👴 Old Man Hemlock?")
    r["xp"] = 20
    r["item_add"] = "hi_potion"
    if "oddity_hemlock" not in lore.owned(sheet):
        r["lore_add"] = "oddity_hemlock"
    r["outcome"] = "Old Man Hemlock, out for a walk, presses a Hi-Potion on you. +20 XP."
    r["narration_hook"] = (
        "Old Man Hemlock was on the forest path, an hour from town, in his shop apron. He asked after the "
        "weather and gave the player a Hi-Potion. Back in Oakhaven, Hemlock swore he had not left the counter all day."
    )
    return r


# ─── Night-only ───────────────────────────────────────────────────────────────

def fallen_star(sheet: dict) -> dict:
    r = _base("fallen_star", "🌠 A Fallen Star")
    r["xp"] = 30
    r["item_add"] = "aeridor_shard"
    r["broadcast"] = True
    if "oddity_star" not in lore.owned(sheet):
        r["lore_add"] = "oddity_star"
    r["outcome"] = "A star comes down in the trees. The stone is cold and humming. +30 XP, Aeridor Crystal Shard."
    r["narration_hook"] = (
        "A light crossed the sky and came down among the trees with no sound at all. In a ring of flattened "
        "ferns lay a stone, cold as a well, humming a note that set the player's teeth on edge."
    )
    return r


def quiet_hunter(sheet: dict) -> dict:
    r = _base("quiet_hunter", "🌑 The Quiet Hunter")
    roll = secrets.randbelow(20) + 1 + _stat_mod(sheet, "dex")
    if roll >= 12:
        r["xp"] = 25
        r["condition_add"] = "shadow_step"
        r["outcome"] = "Something stalks you all night and you never let it close. +25 XP, *Shadow Step* (+2 ATK next fight)."
        r["narration_hook"] = (
            "Something followed the player through the dark, always one tree behind. The player kept moving, "
            "kept the wind right, and by dawn had learned how it walked. It was a useful thing to learn."
        )
    else:
        r["xp"] = 10
        r["hp_change"] = -8
        r["outcome"] = "Something in the dark gets one swipe in and is gone. -8 HP, +10 XP."
        r["narration_hook"] = (
            "Something followed the player through the dark and, once, closed the distance. One swipe, "
            "three long cuts, and then nothing: no tracks, no breath, no sound."
        )
    return r


# ─── Legendary (easter eggs) ──────────────────────────────────────────────────

def door_in_the_oak(sheet: dict) -> dict:
    r = _base("door_in_the_oak", "🚪 The Door in the Oak")
    r["xp"] = 50
    r["hp_change"] = max(0, sheet["hp"]["max"] - sheet["hp"]["current"])
    r["extra_hunt"] = True
    r["broadcast"] = True
    if "oddity_door" not in lore.owned(sheet):
        r["lore_add"] = "oddity_door"
    r["outcome"] = ("A tiny door in an ancient oak. You knock. Someone inside says 'not yet' — and you feel "
                    "wholly rested. Full HP, +50 XP, a hunt returned.")
    r["narration_hook"] = (
        "A door the height of a cat, set into an oak older than Oakhaven, with a brass knocker polished by use. "
        "The player knocked. A polite voice said 'not yet', and the player walked on with no weariness in them at all."
    )
    return r


def the_tablet(sheet: dict) -> dict:
    r = _base("the_tablet", "🪨 The Tablet That Knew Your Name")
    name = sheet.get("character_name", "you")
    r["xp"] = 77
    r["gil"] = 77
    r["broadcast"] = True
    if "oddity_narrator" not in lore.owned(sheet):
        r["lore_add"] = "oddity_narrator"
    r["outcome"] = f"A tablet reads: **{name.upper()} — SOMEONE IS TELLING THIS STORY. WAVE.** You wave. +77 XP, +77 Gil."
    r["narration_hook"] = (
        f"A stone tablet, newer than the ruins around it, carved with {name}'s name and a line saying someone "
        "was telling this story and listening to the hum. The player waved. Somewhere, the story noted it."
    )
    return r


def gilded_stag(sheet: dict) -> dict:
    r = _base("gilded_stag", "🦌 The Gilded Stag")
    r["xp"] = 100
    r["item_add"] = "diamond"
    r["broadcast"] = True
    r["outcome"] = "A white stag with antlers of gold crosses your path and sheds a tine. It is a diamond. +100 XP."
    r["narration_hook"] = (
        "A white stag stepped out of the trees with antlers that caught the light like beaten gold. It looked "
        "at the player for a long moment, shook its head once, and something fell bright into the leaves."
    )
    return r


HANDLERS = {
    "cartographers_cairn": cartographers_cairn,
    "fallen_courier":      fallen_courier,
    "songstone":           songstone,
    "lantern_shrine":      lantern_shrine,
    "mirror_pool":         mirror_pool,
    "wandering_stall":     wandering_stall,
    "seven_crows":         seven_crows,
    "the_other_hemlock":   the_other_hemlock,
    "fallen_star":         fallen_star,
    "quiet_hunter":        quiet_hunter,
    "door_in_the_oak":     door_in_the_oak,
    "the_tablet":          the_tablet,
    "gilded_stag":         gilded_stag,
}
