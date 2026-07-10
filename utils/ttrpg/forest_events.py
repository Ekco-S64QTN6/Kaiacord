import secrets
from datetime import date


def resolve_event(event_key: str, sheet: dict) -> dict:
    """
    Resolve a forest event. Returns a result dict.
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
        # New events
        "whisper_in_bark":   _whisper_in_bark,
        "cactuar_sighting":  _cactuar_sighting,
        "abandoned_camp":    _abandoned_camp,
        "strange_statue":    _strange_statue,
        "echo_of_aeridor":   _echo_of_aeridor,
        "dream_walker":      _dream_walker,
        "twin_wisps":        _twin_wisps,
        "lost_merchant":     _lost_merchant,
        "ancient_coin":      _ancient_coin,
        "missing_persons_found": _missing_persons_found,
        "blue_flame_echo":   _blue_flame_echo,
        "strangers_coin":    _strangers_coin,
        "moved_boundary":    _moved_boundary,
        "watching_silvani":  _watching_silvani,
        "early_bloom":       _early_bloom,
        "wagon_tracks":      _wagon_tracks,
        "unclaimed_lantern": _unclaimed_lantern,
        "silent_chorus":     _silent_chorus,
        "sap_slicked_roots": _sap_slicked_roots,
        "uninvited_guest":   _uninvited_guest,
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


# ─── Original events ──────────────────────────────────────────────────────────

def _sylvan_sprites(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "sylvan_sprites"
    r["title"] = "✨ Sylvan Sprites"
    missing = sheet["hp"]["max"] - sheet["hp"]["current"]
    heal = min(missing, secrets.randbelow(8) + 4)
    if missing == 0:
        r["outcome"] = "You're already at full health. The sprites regard you curiously and drift away."
        r["xp"] = 5
        r["narration_hook"] = "The sprites found the player already uninjured. They lingered, curious, then scattered back into the canopy."
    else:
        r["hp_change"] = heal
        r["xp"] = 10
        r["outcome"] = f"The sprites heal {heal} HP."
        r["narration_hook"] = (
            f"A cluster of small luminous creatures settled around the player and restored {heal} HP "
            f"before vanishing upward into the canopy without a sound."
        )
    return r


def _moogle_sighting(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "moogle_sighting"
    r["title"] = "🎪 Moogle Sighting"
    outcome = secrets.randbelow(2)
    if outcome == 0:
        gil = (secrets.randbelow(3) + 1) * 10
        r["gil"] = gil
        r["xp"] = 8
        r["outcome"] = f"The moogle drops a pouch of {gil} gil and disappears."
        r["narration_hook"] = (
            f"A small white creature with a red pom-pom emerged from the undergrowth, "
            f"dropped a coin pouch ({gil} gil), said 'kupo,' and was gone."
        )
    else:
        r["extra_hunt"] = True
        r["xp"] = 8
        r["outcome"] = "The moogle grants an extra hunt today. (+1 hunt)"
        r["narration_hook"] = (
            "A moogle appeared at the treeline. It studied the player, nodded once as if confirming something, "
            "pressed a small folded note into their hand — 'kupo' — and vanished. "
            "The note said nothing. But somehow there's energy left in the legs for one more run."
        )
    return r


def _injured_silvani(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "injured_silvani"
    r["title"] = "🌿 Injured Silvani Hunter"
    wis_mod = (sheet.get("stats", {}).get("wis", 10) - 10) // 2
    roll = secrets.randbelow(10) + 1 + wis_mod
    if roll >= 6:
        xp = 25
        heal = secrets.randbelow(5) + 3
        r["xp"] = xp
        r["hp_change"] = heal
        r["item_add"] = "healing_herb"
        r["outcome"] = f"You helped the Silvani hunter. +{xp} XP, +{heal} HP. They gave you a healing herb."
        r["narration_hook"] = (
            "A Silvani caught under a fallen branch at the treeline. The player freed them. "
            "The Silvani pressed a handful of medicinal herbs into the player's hands and disappeared back into the wood."
        )
    else:
        r["xp"] = 15
        r["outcome"] = "You helped the Silvani hunter. +15 XP."
        r["narration_hook"] = (
            "A Silvani hunter, injured and barely visible against the bark, was helped back to their feet. "
            "They moved off without looking back."
        )
    return r


def _old_man_riddle(sheet: dict) -> dict:
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
            r["narration_hook"] = "An old man sat on a stone at the path's edge and posed a riddle. The player answered correctly. The old man nodded, said 'good,' and was gone."
        elif reward_type == 1:
            gil = 20 + (sheet.get("level", 1) * 5)
            r["gil"] = gil
            r["xp"] = 15
            r["outcome"] = f"You answered correctly. +{gil} gil, +15 XP."
            r["narration_hook"] = f"The old man's riddle was obscure. The player gave the right answer. He flipped a coin purse ({gil} gil) at them and walked off the path into nothing."
        else:
            r["xp"] = 20
            r["condition_add"] = "sharp_mind"
            r["outcome"] = "You answered correctly. +20 XP. Sharp Mind (next INT check +2)."
            r["narration_hook"] = "The riddle was about the Silent Ones. The player gave an answer that surprised even them. The old man smiled once, briefly."
    else:
        r["xp"] = 5
        r["outcome"] = "You couldn't answer. The old man shrugs. +5 XP for trying."
        r["narration_hook"] = "The old man at the path's edge asked a riddle. The player didn't have the answer. He shrugged and wandered back into the trees."
    return r


def _chocobo_tracks(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "chocobo_tracks"
    r["title"] = "🐦 Chocobo Tracks"
    r["xp"] = 12
    r["extra_hunt"] = True
    r["outcome"] = "You followed the tracks. +1 hunt today. The chocobo was long gone."
    r["narration_hook"] = (
        "Large three-toed tracks in the mud. The player followed them for a while. "
        "The creature was gone, but the trail led through terrain that turned out to be a shortcut. "
        "There's time for one more hunt today."
    )
    return r


def _aeridor_fragment(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "aeridor_fragment"
    r["title"] = "💎 Aeridor Fragment"
    xp = 20 + (sheet.get("level", 1) * 3)
    r["xp"] = xp
    r["item_add"] = "aeridor_shard"
    r["outcome"] = f"Found an Aeridor crystal shard. +{xp} XP. Added to inventory. Sell to Hemlock for 30 gil."
    r["narration_hook"] = (
        "Half-buried in the root system of a deadfall — a crystalline fragment, Aeridorian in origin. "
        "It hums at a frequency that's more felt than heard. The light inside it doesn't come from outside."
    )
    return r


def _gilded_mushroom(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "gilded_mushroom"
    r["title"] = "🍄 Gilded Mushroom"
    r["item_add"] = "gilded_mushroom"
    r["xp"] = 8
    r["outcome"] = "Found gilded mushrooms. Hemlock in Oakhaven will buy these."
    r["narration_hook"] = (
        "Growing in the shadow of a moss-covered stone — gilded mushrooms, rare enough to be worth something. "
        "Hemlock would want them."
    )
    return r


def _veiled_elder(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "veiled_elder"
    r["title"] = "👁️ A Veiled Elder"
    char_class = sheet.get("class", "Warrior")
    advanced = sheet.get("advanced_class", "")
    class_buffs = {
        "Warrior":    ("battle_focus",   "STR checks +1 until next combat"),
        "Ranger":     ("forest_sight",   "DEX checks +1 until next combat"),
        "Mage":       ("resonance_link", "INT checks +2 until next combat"),
        "Rogue":      ("shadow_step",    "DEX checks +2 until next combat"),
        "Cleric":     ("divine_clarity", "WIS checks +2 until next combat"),
        "Paladin":    ("holy_aura",      "STR +2, DEF +1 until next combat"),
        "Shadowknight": ("dark_embrace", "ATK +2, lifesteal active until next combat"),
        "Necromancer": ("death_sight",   "INT +3 vs undead until next combat"),
        "Wizard":     ("arcane_surge",   "INT +3 until next combat"),
        "Hunter":     ("predator_eye",   "DEX +2, crit range -1 until next combat"),
        "Warden":     ("roots_aura",     "DEF +3 until next combat"),
        "Shadowblade": ("void_step",     "DEX +3, crit on 17 until next combat"),
        "Trickster":  ("golden_tongue",  "Gil +2 per kill until next combat"),
        "High Priest": ("divine_word",   "WIS +3, next heal +5"),
        "Shaman":     ("world_speak",    "Next forest event: +15 XP, DEF +2"),
    }
    lookup = advanced if advanced in class_buffs else char_class
    condition, effect_text = class_buffs.get(lookup, ("veiled_blessing", "+1 to next check"))
    r["condition_add"] = condition
    r["xp"] = 15
    r["outcome"] = f"The Veiled elder spoke. {effect_text}."
    r["narration_hook"] = (
        "One of the Veiled — pale, silver-haired, face in the hood's shadow — was standing in the path as if they'd been waiting. "
        "They said something in a language that shouldn't have been comprehensible. It was. "
        "They stepped off the path and were gone."
    )
    return r


def _timid_tonberry(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "timid_tonberry"
    r["title"] = "🔪 Timid Tonberry"
    outcome = secrets.randbelow(3)
    if outcome == 0:
        gil = secrets.randbelow(41) + 60
        r["gil"] = gil
        r["xp"] = 30
        r["outcome"] = f"It dropped its coin pouch running away. {gil} gil. You feel guilty."
        r["narration_hook"] = (
            "A small robed figure carrying a lantern and a chef's knife. It saw the player. Its enormous eyes went wide. "
            "It turned and ran, dropping a coin pouch in its panic. The lantern light receded into the dark."
        )
    elif outcome == 1:
        r["xp"] = 40
        r["item_add"] = "tonberry_knife"
        r["outcome"] = "It fled and left its knife behind. +40 XP. Acquired: Tonberry's Knife."
        r["narration_hook"] = (
            "The small robed creature bolted the moment it saw you — abandoning its famous chef's knife in the dirt. "
            "You picked it up. It's surprisingly well-balanced. And deeply unnerving to hold."
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
        "A moogle appeared from behind a tree root, waving a sealed envelope with both paws. "
        "'Kupo! Kupo-po!' It gestured toward Oakhaven with urgency that seemed disproportionate to a letter. "
        "You took it. The moogle gave a relieved bow and vanished."
    )
    return r


def _crystal_resonance(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "crystal_resonance"
    r["title"] = "🔮 Crystal Resonance"
    int_mod = (sheet.get("stats", {}).get("int", 10) - 10) // 2
    roll = secrets.randbelow(10) + 1 + int_mod
    if roll >= 7:
        xp = 35 + (sheet.get("level", 1) * 5)
        r["xp"] = xp
        r["outcome"] = f"You attuned to the resonance. +{xp} XP."
        r["narration_hook"] = (
            "A crystalline formation half-buried in the ruin wall began vibrating at a frequency that moved through bone rather than air. "
            "The player stood still and let it. Something opened briefly and closed."
        )
    else:
        damage = secrets.randbelow(5) + 3
        r["hp_change"] = -damage
        r["xp"] = 10
        r["outcome"] = f"The resonance rejected you. -{damage} HP, +10 XP."
        r["narration_hook"] = (
            "A buried crystal pulsed with Aeridorian resonance. The player reached toward it. It pushed back. "
            "Not violently. Just: no. The recoil cost real HP."
        )
    return r


# ─── NEW EVENTS ───────────────────────────────────────────────────────────────

def _whisper_in_bark(sheet: dict) -> dict:
    """An old tree speaks. Cryptic lore + WIS-based reward."""
    r = _base()
    r["event_key"] = "whisper_in_bark"
    r["title"] = "🌳 The Whisper in the Bark"

    wis_mod = (sheet.get("stats", {}).get("wis", 10) - 10) // 2
    roll = secrets.randbelow(10) + 1 + wis_mod

    if roll >= 7:
        xp = 28
        r["xp"] = xp
        r["condition_add"] = "tree_memory"
        r["outcome"] = (
            f"You listened. +{xp} XP. *Tree Memory* — the Whisperwood acknowledges you. "
            "Next forest encounter: -2 damage from natural sources."
        )
        r["narration_hook"] = (
            "An enormous oak, ancient enough to predate Oakhaven. The player pressed an ear to the bark. "
            "Something spoke — not words exactly, but impressions. Old things. Long things. "
            "The forest is watching. It has opinions. For once, it seems pleased."
        )
    else:
        r["xp"] = 10
        r["outcome"] = "The tree said nothing useful. +10 XP for listening anyway."
        r["narration_hook"] = (
            "The player stood at the base of an old oak and listened. "
            "The bark made no sound. The wind made no sound. "
            "For about thirty seconds, everything was very quiet. Then a bird screamed somewhere above and it was over."
        )
    return r


def _cactuar_sighting(sheet: dict) -> dict:
    """Rare cactuar spotted. DEX check to catch it for a big reward."""
    r = _base()
    r["event_key"] = "cactuar_sighting"
    r["title"] = "🌵 Cactuar Sighting"

    dex_mod = (sheet.get("stats", {}).get("dex", 10) - 10) // 2
    roll = secrets.randbelow(20) + 1 + dex_mod

    if roll >= 18:  # Very hard — this thing moves fast
        xp = 200
        gil = 120
        r["xp"] = xp
        r["gil"] = gil
        r["outcome"] = f"You caught it. Somehow. +{xp} XP, +{gil} gil. You are never doing that again."
        r["narration_hook"] = (
            "A cactuar. It was there for perhaps one second before it bolted — "
            "faster than anything that looks like a cactus has any right to move. "
            "The player's reflexes were, somehow, sufficient. The cactuar stared up, defeated, "
            "then pressed a coin pouch into the player's hand and vanished with its remaining dignity."
        )
    elif roll >= 12:
        xp = 50
        r["xp"] = xp
        r["hp_change"] = -10  # 1000 needles
        r["outcome"] = f"You got close. It fired 1000 needles and ran. -{10} HP, +{xp} XP."
        r["narration_hook"] = (
            "The player got within striking distance. The cactuar responded with 1000 needles — "
            "somehow that many, somehow that fast — and vanished while the player was blinking. "
            "The XP was for trying."
        )
    else:
        r["xp"] = 20
        r["outcome"] = "You saw a cactuar. It saw you. It left. +20 XP for the experience."
        r["narration_hook"] = (
            "There, at the edge of a clearing: a cactuar. Small, spiny, arms slightly raised. "
            "It looked at the player. The player looked at it. "
            "It ran away at speeds that don't make physical sense."
        )
    return r


def _abandoned_camp(sheet: dict) -> dict:
    """Someone left a camp in a hurry. Loot and ominous hints."""
    r = _base()
    r["event_key"] = "abandoned_camp"
    r["title"] = "🏕️ Abandoned Camp"

    level = sheet.get("level", 1)
    find_roll = secrets.randbelow(6)

    if find_roll < 2:
        # Good find
        r["xp"] = 15
        r["item_add"] = "bandage"
        r["gil"] = secrets.randbelow(20) + 10
        r["outcome"] = f"Found supplies. +{r['gil']} gil, bandage added to inventory. +{r['xp']} XP."
        r["narration_hook"] = (
            "A campsite, cold. The fire pit is days dead. Someone left a bedroll, "
            "a half-eaten pack of dried meat, and a small coin purse they clearly didn't mean to leave. "
            "There's no sign of struggle. That almost makes it worse."
        )
    else:
        r["xp"] = 12
        r["item_add"] = "torch"
        r["outcome"] = f"Found a torch and some clues. +{r['xp']} XP."
        r["narration_hook"] = (
            "Someone camped here. Recently enough that the ash is still soft. "
            "A torn piece of leather armor near the treeline. A torch, unlit, dropped on the path. "
            "No blood. No drag marks. Just... gone. "
            "The player pockets the torch and moves on quickly."
        )
    return r


def _strange_statue(sheet: dict) -> dict:
    """An Aeridorian statue — INT/WIS check for lore reward vs. trap."""
    r = _base()
    r["event_key"] = "strange_statue"
    r["title"] = "🗿 Strange Statue"

    int_mod = (sheet.get("stats", {}).get("int", 10) - 10) // 2
    wis_mod = (sheet.get("stats", {}).get("wis", 10) - 10) // 2
    roll = secrets.randbelow(12) + 1 + max(int_mod, wis_mod)

    if roll >= 9:
        xp = 35
        r["xp"] = xp
        r["condition_add"] = "aeridorian_attunement"
        r["outcome"] = (
            f"You understood the gesture. +{xp} XP. "
            "*Aeridorian Attunement* — +1 to ATK in the ruins until next rest."
        )
        r["narration_hook"] = (
            "A stone figure the height of two men, carved in a style that predates Aeridor. "
            "One hand raised, palm out — not a threat. An acknowledgment. "
            "The player made the same gesture back, not knowing why. "
            "The statue's eyes (carved stone, closed) seemed fractionally less closed."
        )
    else:
        damage = secrets.randbelow(6) + 4
        r["hp_change"] = -damage
        r["xp"] = 8
        r["outcome"] = f"You triggered something. -{damage} HP. +{r['xp']} XP."
        r["narration_hook"] = (
            "A stone figure in a clearing, one hand raised. The player reached toward it. "
            "The hand moved. Not much — just enough to hit. "
            "The stone is very hard."
        )
    return r


def _echo_of_aeridor(sheet: dict) -> dict:
    """A moment of Aeridorian memory — passive XP and lore."""
    r = _base()
    r["event_key"] = "echo_of_aeridor"
    r["title"] = "🔮 Echo of Aeridor"

    level = sheet.get("level", 1)
    xp = 25 + level * 4
    r["xp"] = xp
    r["outcome"] = f"+{xp} XP. A fragment of what this place used to be."
    r["narration_hook"] = (
        "The player stepped into a spot where the air felt different. Denser. Older. "
        "For about ten seconds, they saw something — not a vision exactly. An impression. "
        "High towers. Lights. People who moved with the certainty of people who don't know "
        "their civilization is six hundred years from ending. "
        "Then it was just forest again."
    )
    return r


def _dream_walker(sheet: dict) -> dict:
    """A figure who shouldn't be here — encounter with a dreaming Silvani."""
    r = _base()
    r["event_key"] = "dream_walker"
    r["title"] = "💤 The Dream Walker"

    # This event always grants something — it's about a dreaming Silvani
    char_class = sheet.get("class", "Warrior")
    hp_max = sheet["hp"]["max"]
    missing = hp_max - sheet["hp"]["current"]
    heal = min(missing, secrets.randbelow(6) + 5)

    r["xp"] = 20
    r["hp_change"] = heal
    r["outcome"] = f"They healed you while speaking in a language you don't know. +{heal} HP, +20 XP."
    r["narration_hook"] = (
        "A Silvani, standing in the middle of the path, eyes open but not seeing. "
        "Their hands moved through gestures that seemed like argument — "
        "with someone the player couldn't see, in a conversation the player couldn't hear. "
        "When the Silvani's hands touched the player's arm in passing, "
        f"something closed. {heal} HP restored. "
        "The Silvani walked off the path without waking."
    )
    return r


def _twin_wisps(sheet: dict) -> dict:
    """Two wisps — follow both for reward, follow one for confusion, ignore both to be safe."""
    r = _base()
    r["event_key"] = "twin_wisps"
    r["title"] = "🕯️🕯️ Twin Wisps"

    roll = secrets.randbelow(3)

    if roll == 0:
        # Followed correctly — double reward
        xp = 30
        gil = secrets.randbelow(25) + 20
        r["xp"] = xp
        r["gil"] = gil
        r["outcome"] = f"You followed correctly. +{xp} XP, +{gil} gil."
        r["narration_hook"] = (
            "Two wisps, moving in parallel at knee height. Most people follow one. "
            "The player followed both — or rather, walked the path between them. "
            "The space between two wisps, it turns out, is safe. "
            "At the end: a small cache of gil tucked under a stone."
        )
    elif roll == 1:
        # Followed one — got turned around, lost a hunt
        r["xp"] = 10
        r["extra_hunt"] = False
        r["hp_change"] = -5
        r["outcome"] = "You followed one. It led you in a circle. -5 HP, +10 XP."
        r["narration_hook"] = (
            "Two wisps. The player followed the left one. "
            "Forty minutes later, they were back where they started — "
            "scratched from undergrowth, HP down, with a strong sense of having been mocked."
        )
    else:
        # Ignored both — they stayed, gave blessing
        r["xp"] = 15
        r["condition_add"] = "wisp_ward"
        r["outcome"] = "You ignored both. They gave you a ward. +15 XP."
        r["narration_hook"] = (
            "Two wisps approached. The player stopped moving and watched them. "
            "The wisps circled once, twice. Finding no takers for their usual game, "
            "they settled. One touched the player's shoulder briefly before both drifted away. "
            "Something feels lighter."
        )
    return r

def _lost_merchant(sheet: dict) -> dict:
    """A lost merchant needing directions. Charisma/Wisdom reward."""
    r = _base()
    r["event_key"] = "lost_merchant"
    r["title"] = "🧭 The Lost Merchant"
    
    gil_reward = secrets.randbelow(40) + 20
    r["gil"] = gil_reward
    r["xp"] = 15
    r["outcome"] = f"You pointed them toward Oakhaven. +{gil_reward} gil, +15 XP."
    r["narration_hook"] = (
        "A merchant leading a very tired pack mule, thoroughly lost in the Whisperwood. "
        "The player pointed them back toward the Oakhaven Trade Road. "
        f"The merchant pressed a handful of coins ({gil_reward} gil) into the player's hand "
        "and hurried off before the forest could change its mind about letting them leave."
    )
    return r

def _ancient_coin(sheet: dict) -> dict:
    """Find an ancient Aeridorian coin."""
    r = _base()
    r["event_key"] = "ancient_coin"
    r["title"] = "🪙 Ancient Coin"
    
    r["xp"] = 25
    r["item_add"] = "lucky_charm" # reusing lucky charm as a valuable trinket
    r["outcome"] = "You found a strange, heavy coin. +25 XP. Acquired: Lucky Charm."
    r["narration_hook"] = (
        "Half-buried in the mud on the trail: a coin. Not gil. It's too heavy, the metal is dark, "
        "and the face stamped on it belongs to an Aeridorian king who died before Oakhaven was built. "
        "It feels warm to the touch. The player pocketed it."
    )
    return r


def _missing_persons_found(sheet: dict) -> dict:
    """Find a missing villager."""
    r = _base()
    r["event_key"] = "missing_persons_found"
    r["title"] = "📋 Missing Person Found"
    
    from utils.ttrpg.world_state import load_world_state, save_world_state
    wstate = load_world_state()
    name = wstate.get("missing_person_name", "a lost traveler")
    
    # End the event in world state
    wstate["missing_person_loc"] = ""
    wstate["missing_person_name"] = ""
    wstate["missing_person_expiry"] = 0
    save_world_state(wstate)
    
    # Award player
    r["xp"] = 100
    r["gil"] = 100
    sheet["reputation"] = sheet.get("reputation", 0) + 10
    
    r["outcome"] = f"You found {name} safe and escorted them back. +100 XP, +100 gil, +10 Reputation."
    r["narration_hook"] = (
        f"While scouting, you heard a faint call. Huddled under a roots shelter was {name}, "
        "terrified but alive. You kept watch, shared your rations, and guided them back safely. "
        "The family wept, Elder Elara nodded in silent approval, and you were rewarded for your valor."
    )
    return r


def _blue_flame_echo(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "blue_flame_echo"
    r["title"] = "🔵 The Blue Flame's Echo"
    wis_mod = (sheet.get("stats", {}).get("wis", 10) - 10) // 2
    roll = secrets.randbelow(10) + 1 + wis_mod
    dc = 9
    if roll >= dc:
        r["xp"] = 15
        r["condition_add"] = "sharp_mind"
        r["outcome"] = "A blue flame flickers, bringing an unsettling clarity to your mind. +15 XP, Sharp Mind (next INT check +2)."
        r["narration_hook"] = (
            "A low blue fire flickered briefly on a rotten stump before vanishing. "
            "A sudden, cold clarity washed over your thoughts, leaving you strangely focused "
            "but looking over your shoulder."
        )
    else:
        r["xp"] = 5
        r["hp_change"] = -3
        r["outcome"] = "The eerie light flares, burning your hand. -3 HP, +5 XP."
        r["narration_hook"] = (
            "A pale blue light flared from the roots. It pulsed once, demanding something "
            "you couldn't understand, and scorched your skin before fading to grey ash."
        )
    return r


def _strangers_coin(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "strangers_coin"
    r["title"] = "🎴 A Stranger's Coin"
    if secrets.randbelow(100) < 15:
        r["xp"] = 25
        r["item_add"] = "aeridor_shard"
        r["outcome"] = "You found a coin that isn't currency at all—it is a crystal fragment. +25 XP, Acquired: Aeridor Crystal Shard."
        r["narration_hook"] = (
            "You picked up a coin-shaped object. As you rubbed the grime away, the metal "
            "dissolved, leaving a tiny humming crystalline fragment in your palm. It is an Aeridorian shard."
        )
    else:
        gil = 15 + secrets.randbelow(21)
        r["xp"] = 10
        r["gil"] = gil
        r["outcome"] = f"You found a coin of strange mint. +10 XP, +{gil} gil."
        r["narration_hook"] = (
            f"Tucked between two paving stones was a thick, dark coin of unfamiliar design. "
            f"It is worth some gil ({gil} gil) to a collector, though its face remains unrecognizable."
        )
    return r


def _moved_boundary(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "moved_boundary"
    r["title"] = "🌲 The Moved Boundary"
    r["xp"] = 20
    r["outcome"] = "You notice a boundary marker stake shifted twelve feet from its original spot. +20 XP."
    r["narration_hook"] = (
        "A boundary marker stake, marked with Elara's seal, stands in a patch of fresh mud. "
        "The ground beneath it has no tracks—yet it sits precisely twelve feet deeper into the overworld than it did yesterday."
    )
    return r


def _watching_silvani(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "watching_silvani"
    r["title"] = "👀 The Watching Silvani"
    cha_mod = (sheet.get("stats", {}).get("cha", 10) - 10) // 2
    roll = secrets.randbelow(10) + 1 + cha_mod
    dc = 8
    if roll >= dc:
        gil = 20 + secrets.randbelow(21)
        r["xp"] = 15
        r["gil"] = gil
        r["outcome"] = f"A silent figure observed you from the branch and left a purse. +15 XP, +{gil} gil."
        r["narration_hook"] = (
            "A Silvani hunter crouched silently on a high branch. They watched you for a long "
            "moment, then dropped a leather pouch on the moss below before melting into the green canopy."
        )
    else:
        r["xp"] = 8
        r["outcome"] = "A silent watcher evaluated you from above, then slipped away. +8 XP."
        r["narration_hook"] = (
            "You felt eyes upon you. High up in the branches, a leaf-wrapped figure stood still as stone, "
            "evaluating your stride. When you blinked, they had vanished without a sound."
        )
    return r


def _early_bloom(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "early_bloom"
    r["title"] = "🌱 Early Bloom"
    r["xp"] = 10
    r["item_add"] = "silver_moss"
    r["outcome"] = "You gathered silvermoss blooming ahead of its season. +10 XP, Acquired: Silvermoss."
    r["narration_hook"] = (
        "A patch of silvermoss glows softly in the damp soil. It is blooming far too early in the cycle, "
        "its pale filaments damp and cold. You carefully harvested it."
    )
    return r


def _wagon_tracks(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "wagon_tracks"
    r["title"] = "🛒 Wagon Tracks"
    if secrets.randbelow(2) == 0:
        gil = 10 + secrets.randbelow(16)
        r["xp"] = 10
        r["gil"] = gil
        r["outcome"] = f"You found lost guild cargo along the tracks. +10 XP, +{gil} gil."
        r["narration_hook"] = (
            f"Heavy, deep wagon tracks gouge the Trade Road. Along the edge, you found a dropped "
            f"Guild lockbox containing {gil} gil."
        )
    else:
        r["xp"] = 10
        r["condition_add"] = "sharp_mind"
        r["outcome"] = "You found dropped guild survey notes on the road. +10 XP, Sharp Mind (next INT check +2)."
        r["narration_hook"] = (
            "You found a discarded piece of parchment detailing Guild survey points. "
            "Studying the terrain notes gives you a keen understanding of the local contours."
        )
    return r


def _unclaimed_lantern(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "unclaimed_lantern"
    r["title"] = "🏮 The Unclaimed Lantern"
    dex_mod = (sheet.get("stats", {}).get("dex", 10) - 10) // 2
    roll = secrets.randbelow(10) + 1 + dex_mod
    dc = 10
    if roll >= dc:
        r["xp"] = 12
        r["item_add"] = "torch"
        r["outcome"] = "You successfully salvaged the unclaimed lantern. +12 XP, Acquired: Torch."
        r["narration_hook"] = (
            "A small brass lantern burned quietly on a mossy root. You approached with light steps "
            "and claimed the lantern before the unseen watcher could object."
        )
    else:
        r["xp"] = 5
        r["hp_change"] = -4
        r["outcome"] = "You reached for the lantern but triggered a grudge. -4 HP, +5 XP."
        r["narration_hook"] = (
            "You reached for the lantern. A cold needle-like prick struck your wrist from the dark, "
            "forcing you to recoil as a low, dry chuckle faded into the fog."
        )
    return r


def _silent_chorus(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "silent_chorus"
    r["title"] = "👂 The Silent Chorus"
    int_mod = (sheet.get("stats", {}).get("int", 10) - 10) // 2
    roll = secrets.randbelow(10) + 1 + int_mod
    dc = 9
    if roll >= dc:
        xp = 15 + sheet.get("level", 1) * 3
        r["xp"] = xp
        r["outcome"] = f"You tuned in to the frequency of the ruins. +{xp} XP."
        r["narration_hook"] = (
            f"For a few heartbeats, the low hum of the stone structures aligned perfectly. "
            f"You understood the shape of the silence, gaining a flash of deep insight (+{xp} XP)."
        )
    else:
        r["xp"] = 5
        r["outcome"] = "The humming ruins remained just out of reach. +5 XP."
        r["narration_hook"] = (
            "You stopped and strained to hear the rhythm in the ruins. It vibrated your teeth "
            "but slipped away before you could grasp the pattern."
        )
    return r


def _sap_slicked_roots(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "sap_slicked_roots"
    r["title"] = "🍯 Sap-Slicked Roots"
    r["xp"] = 8
    r["item_add"] = "honey_sap"
    if secrets.randbelow(100) < 30:
        dmg = secrets.randbelow(2) + 1
        r["hp_change"] = -dmg
        r["outcome"] = f"You slipped and scraped yourself, but collected honeysap. -{dmg} HP, +8 XP, Acquired: Honey Sap."
        r["narration_hook"] = (
            f"You climbed the root structure to harvest honeysap, but the bark was slick. "
            f"You slipped, scraping your thigh (-{dmg} HP), but held onto the jar."
        )
    else:
        r["outcome"] = "You gathered sweet honeysap from the slick roots. +8 XP, Acquired: Honey Sap."
        r["narration_hook"] = (
            "Sticky, amber honeysap oozed from the fissures of the ancient root system. "
            "You harvested a clean vial without losing your footing."
        )
    return r


def _uninvited_guest(sheet: dict) -> dict:
    r = _base()
    r["event_key"] = "uninvited_guest"
    r["title"] = "🦇 The Uninvited Guest"
    wis_mod = (sheet.get("stats", {}).get("wis", 10) - 10) // 2
    roll = secrets.randbelow(12) + 1 + wis_mod
    dc = 12
    if roll >= dc:
        r["xp"] = 25
        r["gil"] = 30
        r["condition_add"] = "wisp_ward"
        r["outcome"] = "You stood firm under the stalker's gaze. +25 XP, +30 Gil, Wisp Ward condition granted."
        r["narration_hook"] = (
            "A distorted shadow crouched over the trail. Instead of fleeing, you met its hollow gaze. "
            "It shivered, spat a shard of bone and coins onto the dirt, and bounded away, leaving you warded."
        )
    else:
        r["xp"] = 5
        r["hp_change"] = -6
        r["outcome"] = "The stalker lashed out from the shadows. -6 HP, +5 XP."
        r["narration_hook"] = (
            "A figure of grey rags and sharp claws lunged. You evaded the worst of it, "
            "but a cold strike tore your cloak (-6 HP) before it vanished into the undergrowth."
        )
    return r
