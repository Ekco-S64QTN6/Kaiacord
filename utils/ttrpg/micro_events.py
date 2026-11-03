"""
micro_events.py — Overworld Micro-Events System for Aethelgard
================================================================
Triggers small, atmospheric events during travels, hunts, and overworld exploration.
"""

import secrets
from datetime import datetime
from utils.ttrpg.calendar import get_weather

def trigger_micro_event(sheet: dict) -> tuple[bool, str]:
    """
    Attempt to trigger a random micro-event.
    Returns (event_triggered, narration_text).
    """
    # 15% baseline chance to trigger a micro-event during overworld activities
    if secrets.randbelow(100) >= 15:
        return False, ""

    events = [
        _weather_discovery,
        _wanderer_encounter,
        _streak_recognition,
        _time_of_day_event
    ]
    
    # Choose and execute a random event handler
    handler = secrets.choice(events)
    return handler(sheet)

def _has_space(sheet: dict, item: str) -> bool:
    """Compatibility wrapper around the shared unique-item capacity policy."""
    from utils.ttrpg.inventory_capacity import can_add_item
    return can_add_item(sheet.get("inventory", []), item)

def _grant_micro_event_item(sheet: dict, item: str) -> str:
    from utils.ttrpg.inventory_capacity import grant_item_or_mail
    return grant_item_or_mail(sheet, item, "Overworld Discovery")


def _weather_discovery(sheet: dict) -> tuple[bool, str]:
    weather = get_weather()
    w_key = weather.get("key", "clear") if weather else "clear"

    # Keyed on the weather key: names differ by season ("Raining" in spring,
    # "Rain" otherwise), so matching the name missed most rain.
    if w_key in ("storm", "rain"):
        delivery = _grant_micro_event_item(sheet, "aeridor_shard")
        if delivery:
            story = (
                "⚡ *A flash of lightning strikes an ancient mossy trunk ahead. "
                "With a deafening crack, the wood splits, dislodging a glowing Aeridor Crystal Shard "
                "which you quickly pocket.*"
            )
            if delivery == "mailbox":
                story += " The moogles have sent the shard to your mailbox because your bag was full."
            return True, story
    elif w_key == "fog":
        delivery = _grant_micro_event_item(sheet, "lucky_charm")
        if delivery:
            story = (
                "🌫️ *Navigating through the thick grey fog, your foot kicks a small metallic object. "
                "It is a copper Lucky Charm, half-buried in the damp soil.*"
            )
            if delivery == "mailbox":
                story += " The moogles have sent the charm to your mailbox because your bag was full."
            return True, story
    elif w_key in ("clear", "hot"):
        delivery = _grant_micro_event_item(sheet, "copper_ring")
        if delivery:
            story = (
                "☀️ *The warm afternoon sun gleams off a reflective metallic circle in the dust. "
                "You brush off the dirt to find a simple Copper Ring.*"
            )
            if delivery == "mailbox":
                story += " The moogles have sent the ring to your mailbox because your bag was full."
            return True, story
    return False, ""

def _wanderer_encounter(sheet: dict) -> tuple[bool, str]:
    roll = secrets.randbelow(2)
    if roll == 0:
        delivery = _grant_micro_event_item(sheet, "tonic")
        if delivery:
            story = (
                "🧭 *You cross paths with a wandering merchant on the Trade Road. "
                "He offers a warm smile and hands you a free Tonic. 'Stay safe out here, friend,' he mutters.*"
            )
            if delivery == "mailbox":
                story += " The moogles have sent the tonic to your mailbox because your bag was full."
            return True, story

    # The pilgrim outcome remains available on the other roll, or if an
    # invalid registry result prevents the merchant reward from being issued.
    conds = sheet.setdefault("conditions", [])
    if "blessed" not in conds:
        conds.append("blessed")
        return True, (
            "✨ *An old pilgrim of the Silent Ones stops to pray with you. "
            "You feel a light, warm blessing settle over you, guiding your next steps (+2 to rolls).*"
        )
    return False, ""

def _streak_recognition(sheet: dict) -> tuple[bool, str]:
    streak = sheet.get("hunt_streak", 0)
    if streak > 0 and streak % 10 == 0:
        bonus_gil = 50
        bonus_xp = 50
        sheet["gil"] = sheet.get("gil", 0) + bonus_gil
        sheet["xp"] = sheet.get("xp", 0) + bonus_xp
        return True, (
            f"🔥 *Your momentum is legendary! You pause to catch your breath, reflecting on your "
            f"consecutive victories. Your focus sharpens (+{bonus_xp} XP, +{bonus_gil} Gil).*"
        )
    elif streak >= 30:
        delivery = _grant_micro_event_item(sheet, "hi_potion")
        if delivery:
            story = (
                f"⚔️ *A Watchtower guard patrolling the path recognizes you. 'I've heard of your streak, "
                f"adventurer. Keep Oakhaven safe.' He slips a Hi-Potion into your pack.*"
            )
            if delivery == "mailbox":
                story += " The moogles have sent the Hi-Potion to your mailbox because your bag was full."
            return True, story
    return False, ""

def _time_of_day_event(sheet: dict) -> tuple[bool, str]:
    hour = datetime.now().hour
    # Morning
    if 6 <= hour < 12:
        heal = 5
        sheet["hp"]["current"] = min(sheet["hp"]["max"], sheet["hp"]["current"] + heal)
        return True, (
            f"🌅 *A sylvan sprite dances briefly in the warm morning light, sprinkling sparkling dew "
            f"over your minor cuts before drifting away (+{heal} HP).*")
    # Night
    elif hour >= 18 or hour < 6:
        delivery = _grant_micro_event_item(sheet, "lucky_charm")
        if delivery:
            story = (
                "🌠 *A brilliant shooting star cuts across the dark night canopy. "
                "Tracing its descent, you find a small glowing pebble in the grass—a Lucky Charm.*"
            )
            if delivery == "mailbox":
                story += " The moogles have sent the charm to your mailbox because your bag was full."
            return True, story
    return False, ""
