"""
forest_events.py — LORD-style random forest events for Aethelgard
==================================================================

Each event:
  - Costs 1 hunt (same as combat)
  - Is resolved entirely in Python
  - Returns an (outcome_dict, narration_context) for Kaia to voice
  - Never involves LLM decision-making

Event keys and what they do:

  sylvan_sprites      — Fairy garden equivalent. Heals HP. Pure gift.
  moogle_sighting     — Moogle spotted. Bonus gil or extra hunt.
  injured_silvani     — Person in distress. Help = XP + blessing. Ignore = nothing.
  old_man_riddle      — Stat check for a reward. INT/WIS based.
  chocobo_tracks      — Follow them = bonus hunt tomorrow. Don't = nothing.
  aeridor_fragment    — Find a ruin shard. Sell to Hemlock or keep for XP.
  gilded_mushroom     — Find something valuable. Gil reward.
  veiled_elder        — The Veiled offer cryptic wisdom. Temporary stat buff.
  timid_tonberry      — Young tonberry. It runs. But it drops something.
  mognet_delivery     — A moogle asks you to carry a letter. Reward on completion.
  crystal_resonance   — Aeridorian resonance pulse. XP surge or HP drain.
"""

import secrets
from datetime import date


def resolve_event(event_key: str, sheet: dict) -> dict:
    """
    Resolve a forest event. Returns a result dict:
    {
        "event_key": str,
        "title": str,
        "outcome": str,          # SHORT mechanical summary for Python output
        "xp": int,
        "gil": int,
        "hp_change": int,        # positive = heal, negative = damage
        "condition_add": str,    # condition to add, or ""
        "condition_remove": str, # condition to remove, or ""
        "extra_hunt": bool,      # grants +1 hunt today
        "item_add": str,         # item key to add to inventory, or ""
        "narration_hook": str,   # fed to Kaia for flavor narration
    }
    """
    handlers = {
        "sylvan_sprites":    _sylvan_sprites,
        "moogle_sighting":   _moogle_sighting,
        "injured_silvani":   _injured_silvani,
        "old_man_riddle":    _old_man_riddle,
        "chocobo_tracks":    _chocobo_tracks,
        "aeridor_fragment":  _aeridor_fragment,
        "gilded_mushroom":   _gilded_mushroom,
        "veiled_elder":      _veiled_elder,
        "timid_tonberry":    _timid_tonberry,
        "mognet_delivery":   _mognet_delivery,
        "crystal_resonance": _crystal_resonance,
    }
    handler = handlers.get(event_key, _sylvan_sprites)
    return handler(sheet)


def _base() -> dict:
    return {
        "event_key": "", "title": "", "outcome": "",
        "xp": 0, "gil": 0, "hp_change": 0,
        "condition_add": "", "condition_remove": "",
        "extra_hunt": False, "item_add": "",
        "narration_hook": "",
    }


def _sylvan_sprites(sheet: dict) -> dict:
    """Fairy garden equivalent. Restores HP. Pure gift."""
    r = _base()
    r["event_key"] = "sylvan_sprites"
    r["title"] = "✨ Sylvan Sprites"

    missing = sheet["hp"]["max"] - sheet["hp"]["current"]
    heal = min(missing, secrets.randbelow(8) + 4)  # 4-11 HP

    if missing == 0:
        r["outcome"] = "You're already at full health. The sprites regard you curiously and drift away."
        r["xp"] = 5
        r["narration_hook"] = (
            "The sprites found the player already uninjured. They lingered, "
            "curious, then scattered back into the canopy."
        )
    else:
        r["hp_change"] = heal
        r["xp"] = 10
        r["outcome"] = f"The sprites heal {heal} HP."
        r["narration_hook"] = (
            f"A cluster of small luminous creatures — barely visible in the green light — "
            f"settled around the player and restored {heal} HP before vanishing upward "
            f"into the canopy without a sound."
        )
    return r


def _moogle_sighting(sheet: dict) -> dict:
    """Moogle spotted. Coin flip: bonus gil OR extra hunt today."""
    r = _base()
    r["event_key"] = "moogle_sighting"
    r["title"] = "🎪 Moogle Sighting"

    outcome = secrets.randbelow(2)
    if outcome == 0:
        gil = (secrets.randbelow(3) + 1) * 10  # 10, 20, or 30 gil
        r["gil"] = gil
        r["xp"] = 8
        r["outcome"] = f"The moogle drops a pouch of {gil} gil and disappears."
        r["narration_hook"] = (
            f"A small white creature with a red pom-pom — unmistakably a moogle — "
            f"emerged from the undergrowth, regarded the player with round black eyes, "
            f"dropped a coin pouch ({gil} gil), said 'kupo,' and was gone."
        )
    else:
        r["extra_hunt"] = True
        r["xp"] = 8
        r["outcome"] = "The moogle grants an extra hunt today. (+1 hunt)"
        r["narration_hook"] = (
            "A moogle appeared at the treeline. It studied the player, nodded once "
            "as if confirming something, pressed a small folded note into their hand "
            "— 'kupo' — and vanished. The note said nothing. But somehow there's "
            "energy left in the legs for one more run."
        )
    return r


def _injured_silvani(sheet: dict) -> dict:
    """Person in distress. Help them = XP + blessing. Classic LORD maiden event."""
    r = _base()
    r["event_key"] = "injured_silvani"
    r["title"] = "🌿 Injured Silvani Hunter"

    # Always help — player has no choice in !rpg hunt auto-resolve
    # But outcome varies by player WIS
    wis_mod = (sheet.get("stats", {}).get("wis", 10) - 10) // 2
    roll = secrets.randbelow(10) + 1 + wis_mod

    if roll >= 6:
        # Successfully helped — their gratitude = XP + small heal
        xp = 25
        heal = secrets.randbelow(5) + 3
        r["xp"] = xp
        r["hp_change"] = heal
        r["item_add"] = "healing_herb"
        r["outcome"] = f"You helped the Silvani hunter. +{xp} XP, +{heal} HP. They also gave you a healing herb."
        r["narration_hook"] = (
            "A Silvani — skin shifting between bark-brown and pale — was caught under "
            "a fallen branch at the treeline. The player freed them. The Silvani said "
            "nothing in any language, pressed a handful of medicinal herbs into the "
            "player's hands, and disappeared back into the wood."
        )
    else:
        # Helped but struggled — just the XP
        r["xp"] = 15
        r["outcome"] = "You helped the Silvani hunter. +15 XP."
        r["narration_hook"] = (
            "A Silvani hunter, injured and barely visible against the bark, "
            "was helped back to their feet. They moved off without looking back. "
            "Whether it was gratitude or simply survival instinct is unclear."
        )
    return r

def _old_man_riddle(sheet: dict) -> dict:
    """Old man with a test — INT check for reward. LORD's old man event."""
    r = _base()
    r["event_key"] = "old_man_riddle"
    r["title"] = "🧙 The Old Man's Riddle"

    int_mod = (sheet.get("stats", {}).get("int", 10) - 10) // 2
    roll = secrets.randbelow(12) + 1 + int_mod
    dc = 8

    if roll >= dc:
        reward_type = secrets.randbelow(3)
        if reward_type == 0:
            xp = 30
            r["xp"] = xp
            r["outcome"] = f"You answered correctly. +{xp} XP."
            r["narration_hook"] = (
                "An old man sat on a stone at the path's edge — no pack, no reason "
                "to be there. He posed a riddle without greeting. The player answered "
                "correctly. The old man nodded, said 'good,' and was gone by the time "
                "they looked back."
            )
        elif reward_type == 1:
            gil = 20 + (sheet.get("level", 1) * 5)
            r["gil"] = gil
            r["xp"] = 15
            r["outcome"] = f"You answered correctly. +{gil} gil, +15 XP."
            r["narration_hook"] = (
                "The old man's riddle was obscure — something about what walks on "
                "the Aeridor stones at midnight. The player gave the right answer. "
                f"He flipped a coin purse ({gil} gil) at them without a word and walked "
                "off the path into nothing."
            )
        else:
            r["xp"] = 20
            r["condition_add"] = "sharp_mind"
            r["outcome"] = "You answered correctly. +20 XP. Sharp Mind (next INT check +2)."
            r["narration_hook"] = (
                "The riddle was about the Silent Ones — their nature, their silence, "
                "their purpose. The player gave an answer that surprised even them. "
                "The old man smiled once, briefly. Something clicked behind the eyes."
            )
    else:
        r["xp"] = 5
        r["outcome"] = "You couldn't answer. The old man shrugs. +5 XP for trying."
        r["narration_hook"] = (
            "The old man at the path's edge asked a riddle. The player didn't have "
            "the answer. He shrugged — 'next time' — and wandered back into the trees. "
            "He didn't seem disappointed. He seemed like he expected it."
        )
    return r


def _chocobo_tracks(sheet: dict) -> dict:
    """Follow chocobo tracks = bonus hunt tomorrow. FF classic."""
    r = _base()
    r["event_key"] = "chocobo_tracks"
    r["title"] = "🐦 Chocobo Tracks"

    today = date.today().strftime("%Y-%m-%d")
    r["xp"] = 12
    r["condition_add"] = f"chocobo_bonus_{today}"
    r["extra_hunt"] = True
    r["outcome"] = "You followed the tracks. +1 hunt today. The chocobo was long gone."
    r["narration_hook"] = (
        "Large three-toed tracks in the mud — unmistakable, if you know what a chocobo "
        "is. The player followed them for a while. The creature was gone, but the trail "
        "led through terrain that turned out to be a shortcut. There's time for one more "
        "hunt today."
    )
    return r


def _aeridor_fragment(sheet: dict) -> dict:
    """Find an Aeridor ruin shard. Sell or keep for XP."""
    r = _base()
    r["event_key"] = "aeridor_fragment"
    r["title"] = "💎 Aeridor Fragment"

    xp = 20 + (sheet.get("level", 1) * 3)
    r["xp"] = xp
    r["item_add"] = "aeridor_shard"
    r["outcome"] = f"Found an Aeridor crystal shard. +{xp} XP. Added to inventory. Sell to Hemlock for 30 gil."
    r["narration_hook"] = (
        "Half-buried in the root system of a deadfall — a crystalline fragment, "
        "Aeridorian in origin. It hums at a frequency that's more felt than heard. "
        "The light inside it doesn't come from outside."
    )
    return r


def _gilded_mushroom(sheet: dict) -> dict:
    """Find something valuable. Gil reward. LORD's 'find gems' event."""
    r = _base()
    r["event_key"] = "gilded_mushroom"
    r["title"] = "🍄 Gilded Mushroom"

    r["item_add"] = "gilded_mushroom"
    r["xp"] = 8
    r["outcome"] = "Found gilded mushrooms. Hemlock in Oakhaven will buy these."
    r["narration_hook"] = (
        "Growing in the shadow of a moss-covered stone — gilded mushrooms, "
        "rare enough to be worth something. Hemlock would want them. "
        "The player pocketed them."
    )
    return r


def _veiled_elder(sheet: dict) -> dict:
    """The Veiled offer cryptic wisdom. Temporary buff. LORD's hag/stranger event."""
    r = _base()
    r["event_key"] = "veiled_elder"
    r["title"] = "👁️ A Veiled Elder"

    # Different buff depending on class
    char_class = sheet.get("class", "Warrior")
    class_buffs = {
        "Warrior": ("battle_focus",  "STR checks +1 until next combat"),
        "Ranger":  ("forest_sight",  "DEX checks +1 until next combat"),
        "Mage":    ("resonance_link","INT checks +2 until next combat"),
        "Rogue":   ("shadow_step",   "DEX checks +2 until next combat"),
        "Cleric":  ("divine_clarity","WIS checks +2 until next combat"),
    }
    condition, effect_text = class_buffs.get(char_class, ("veiled_blessing", "+1 to next check"))

    r["condition_add"] = condition
    r["xp"] = 15
    r["outcome"] = f"The Veiled elder spoke. {effect_text}."
    r["narration_hook"] = (
        "One of the Veiled — pale, silver-haired, face in the hood's shadow — "
        "was standing in the path as if they'd been waiting. They said something "
        "in a language that shouldn't have been comprehensible. It was. "
        "They stepped off the path and were gone."
    )
    return r


def _timid_tonberry(sheet: dict) -> dict:
    """Young tonberry. It runs. But drops something. FF easter egg."""
    r = _base()
    r["event_key"] = "timid_tonberry"
    r["title"] = "🔪 Timid Tonberry"

    outcome = secrets.randbelow(3)
    if outcome == 0:
        gil = secrets.randbelow(41) + 60  # 60-100 gil — tonberries are rich
        r["gil"] = gil
        r["xp"] = 30
        r["outcome"] = f"It dropped its coin pouch running away. {gil} gil. You feel guilty."
        r["narration_hook"] = (
            "A small robed figure — no taller than a knee — emerged from the undergrowth "
            "carrying a lantern and a chef's knife. It saw the player. Its enormous eyes "
            "went wide. It turned and ran, dropping a coin pouch in its panic. "
            "The lantern light receded into the dark. You feel, obscurely, like the villain."
        )
    elif outcome == 1:
        r["xp"] = 40
        r["item_add"] = "tonberry_knife"
        r["outcome"] = "It fled and left its knife behind. +40 XP. Acquired: Tonberry's Knife."
        r["narration_hook"] = (
            "The small robed creature bolted the moment it saw you — abandoning its "
            "famous chef's knife in the dirt in its haste. You picked it up. "
            "It's surprisingly well-balanced. And deeply unnerving to hold."
        )
    else:
        r["xp"] = 20
        r["outcome"] = "It ran before you could react. +20 XP for the encounter."
        r["narration_hook"] = (
            "Something small and robed crossed the path ahead. It carried a lantern. "
            "It stopped. It looked at you. You looked at it. "
            "It turned and walked — with tremendous dignity — back into the trees."
        )
    return r


def _mognet_delivery(sheet: dict) -> dict:
    """Moogle asks you to carry a letter. Reward on next town visit. FF9 mognet."""
    r = _base()
    r["event_key"] = "mognet_delivery"
    r["title"] = "📬 Mognet Delivery"

    r["xp"] = 10
    r["item_add"] = "mognet_letter"
    r["condition_add"] = "mognet_pending"
    r["outcome"] = (
        "A moogle handed you a letter for delivery to Oakhaven. "
        "+10 XP. Deliver it with `!rpg deliver` in town for a reward."
    )
    r["narration_hook"] = (
        "A moogle appeared from behind a tree root, waving a sealed envelope "
        "with both paws. 'Kupo! Kupo-po!' It gestured toward Oakhaven with "
        "urgency that seemed disproportionate to a letter. "
        "You took it. The moogle gave a relieved bow and vanished."
    )
    return r


def _crystal_resonance(sheet: dict) -> dict:
    """Aeridorian resonance pulse. XP surge OR HP drain. Risk/reward."""
    r = _base()
    r["event_key"] = "crystal_resonance"
    r["title"] = "🔮 Crystal Resonance"

    # INT modifier affects outcome
    int_mod = (sheet.get("stats", {}).get("int", 10) - 10) // 2
    roll = secrets.randbelow(10) + 1 + int_mod

    if roll >= 7:
        xp = 35 + (sheet.get("level", 1) * 5)
        r["xp"] = xp
        r["outcome"] = f"You attuned to the resonance. +{xp} XP."
        r["narration_hook"] = (
            "A crystalline formation half-buried in the ruin wall began vibrating "
            "at a frequency that moved through bone rather than air. "
            "The player stood still and let it. Something opened briefly and closed. "
            "The XP gain feels like knowledge rather than combat experience."
        )
    else:
        damage = secrets.randbelow(5) + 3
        r["hp_change"] = -damage
        r["xp"] = 10
        r["outcome"] = f"The resonance rejected you. -{damage} HP, +10 XP."
        r["narration_hook"] = (
            "A buried crystal pulsed with Aeridorian resonance — the old energy, "
            "the deep kind. The player reached toward it. It pushed back. "
            "Not violently. Just: no. The recoil cost real HP."
        )
    return r
