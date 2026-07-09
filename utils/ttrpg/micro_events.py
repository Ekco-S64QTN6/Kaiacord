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

def _has_space(sheet: dict) -> bool:
    return len(sheet.get("inventory", [])) < 50

def _weather_discovery(sheet: dict) -> tuple[bool, str]:
    weather = get_weather()
    w_type = weather.get("name", "Clear") if weather else "Clear"
    
    if w_type in ("Storming", "Raining") and _has_space(sheet):
        sheet.setdefault("inventory", []).append("aeridor_shard")
        return True, (
            "⚡ *A flash of lightning strikes an ancient mossy trunk ahead. "
            "With a deafening crack, the wood splits, dislodging a glowing Aeridor Crystal Shard "
            "which you quickly pocket.*"
        )
    elif w_type == "Foggy" and _has_space(sheet):
        sheet.setdefault("inventory", []).append("lucky_charm")
        return True, (
            "🌫️ *Navigating through the thick grey fog, your foot kicks a small metallic object. "
            "It is a copper Lucky Charm, half-buried in the damp soil.*"
        )
    elif _has_space(sheet):
        sheet.setdefault("inventory", []).append("copper_ring")
        return True, (
            "☀️ *The warm afternoon sun gleams off a reflective metallic circle in the dust. "
            "You brush off the dirt to find a simple Copper Ring.*"
        )
    return False, ""

def _wanderer_encounter(sheet: dict) -> tuple[bool, str]:
    roll = secrets.randbelow(2)
    if roll == 0 and _has_space(sheet):
        sheet.setdefault("inventory", []).append("tonic")
        return True, (
            "🧭 *You cross paths with a wandering merchant on the Trade Road. "
            "He offers a warm smile and hands you a free Tonic. 'Stay safe out here, friend,' he mutters.*"
        )
    else:
        # Add Blessed condition
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
    elif streak >= 30 and _has_space(sheet):
        sheet.setdefault("inventory", []).append("hi_potion")
        return True, (
            f"⚔️ *A Watchtower guard patrolling the path recognizes you. 'I've heard of your streak, "
            f"adventurer. Keep Oakhaven safe.' He slips a Hi-Potion into your pack.*"
        )
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
        if _has_space(sheet):
            sheet.setdefault("inventory", []).append("lucky_charm")
            return True, (
                "🌠 *A brilliant shooting star cuts across the dark night canopy. "
                "Tracing its descent, you find a small glowing pebble in the grass—a Lucky Charm.*"
            )
    return False, ""
