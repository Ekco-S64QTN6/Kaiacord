import asyncio
import time
import uuid as _uuid
import os
import json
import traceback
import discord
import secrets
from utils.infrastructure.logging.kaia_logger import log_info, log_error, log_warning
from utils.infrastructure.system.yaml_config import config
from utils.ttrpg.world_state import get_current_state
from utils.ttrpg.character_manager import load, save, create, format_sheet, load_all
from utils.ttrpg.session_manager import load_session, save_session, create_session, end_session
from utils.ttrpg.progression import check_and_reset_hunts, hunts_remaining, check_level_up, MAX_HUNTS_PER_DAY, get_max_hunts, xp_to_next_level, XP_THRESHOLDS
from utils.ttrpg.class_advancement import (
    apply_advanced_class_to_combat, apply_advanced_class_to_sheet,
    get_advanced_options, get_title, ADVANCED_CLASSES
)
from utils.ttrpg.dungeon import _scale_boss_to_level, load_dungeon, save_dungeon
from utils.ttrpg.rpg_ui import TIER_ICONS, colored_bar, hp_bar, hp_label, CLASS_ICONS, LOCATION_ICONS, ANSI_GREEN, ANSI_RESET
from utils.social.kaia_social_responder import load_persona_async
from utils.ttrpg.world import LOCATION_DATA
from utils.ttrpg.encounter_tables import random_encounter
import utils.ttrpg.dice_engine as dice_engine
from utils.ttrpg.monster_registry import get as get_monster
from utils.ttrpg.shop import find_item
from utils.ttrpg.loot_tables import get_loot
from utils.ttrpg.broadcast import (
    log_world_event as _log_world_event,
    broadcast_world_event as _broadcast_world_event,
    level_up_flavor as _level_up_flavor,
    rare_loot_flavor as _rare_loot_flavor,
    _boss_approach_flavor
)

def _make_interaction_send(interaction: discord.Interaction):
    async def _send(channel, text, use_code_block=None):
        if use_code_block is None: use_code_block = False
        await interaction.followup.send(text)
    return _send

class _InteractionMsg:
    def __init__(self, interaction: discord.Interaction):
        self.channel = interaction.channel
        self.author = interaction.user


from utils.ttrpg.rpg_views import *

async def _handle_status(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.world import LOCATION_DATA
    # Resumption uses global imports now
    
    sheet = await load(uid)
    if not sheet:
        await msg.channel.send(embed=discord.Embed(
            description="You do not exist in Aethelgard. Type `!rpg new <Name> <Race> <Class>` to begin.",
            color=0xcc4444
        ))
        return
        
    # [LEVEL UP] Stat choice
    if sheet.get("_stat_choice_pending"):
        await _show_stat_choice(ctx, msg, send, sheet, uid, uname, is_owner)
        return
        
    loc = sheet.get("location", "oakhaven")
    loc_data = LOCATION_DATA.get(loc, {})
    loc_name = loc_data.get("name", loc.replace("_", " ").title())
    
    hp_cur = sheet["hp"].get("current", 1)
    hp_max = sheet["hp"].get("max", 1)
    
    xp_cur = sheet["xp"]
    xp_next = xp_to_next_level(sheet["level"])
    if xp_next:
        floor = XP_THRESHOLDS.get(sheet["level"], 0)
        progress = xp_cur - floor
        req = xp_next - floor
        xp_bar_str = colored_bar(progress, req, 14) + f" → Lv.{sheet['level'] + 1}"
    else:
        xp_bar_str = f"{ANSI_GREEN}██████████████{ANSI_RESET} (MAX)"
        
    gil = sheet.get("gil", 0)
    
    from utils.ttrpg.equipment_registry import WEAPONS, ARMOR as ARMOR_REG, HEADGEAR, BOOTS, ACCESSORIES
    
    # [RESUMPTION] Detect if we should add a "Resume Encounter" nudge
    resume_desc = ""
    chan_id = str(msg.channel.id)
    session = await load_session(chan_id)
    if session and session.get("combat_active"):
        # Check if author is in this fight
        mine = [m for m in session.get("monsters", []) if isinstance(m, dict) and m.get("aggro_uid") == uid]
        if mine:
            resume_desc = f"\n\n⚔️ **You are currently in combat here!**\nUse `!rpg hunt` to re-open the interface."
    
    # Resumption logic
    dungeon = load_dungeon(uid)
    dungeon_in_combat = False
    if dungeon and dungeon.get("active"):
        if dungeon.get("active_combat"):
            dungeon_in_combat = True
            resume_desc += f"\n\n⚔️ **You are currently in a dungeon combat!**\nUse `!rpg dungeon` to resume the fight."
        else:
            resume_desc += f"\n\n🏚️ **You are currently in a dungeon!**\nUse `!rpg dungeon` to resume exploring."

    def _eq_display(slot_val, registry, atk=False):
        if not slot_val: return "Unarmed" if atk else "Unarmored"
        if isinstance(slot_val, dict):
            data = slot_val
        else:
            data = registry.get(slot_val)
        if not data: return slot_val
        if atk:
            return f"{data['name']} (+{data.get('attack_bonus',0)} ATK, d{data.get('damage_die',4)})"
        return f"{data['name']} (+{data.get('defense_bonus',0)} DEF)"

    eq = sheet.get("equipment", {})
    w_str  = _eq_display(eq.get("weapon"), WEAPONS, atk=True)
    a_str  = _eq_display(eq.get("armor"),  ARMOR_REG)

    def _sub_eq_display(slot_val, registry):
        if not slot_val: return "—"
        if isinstance(slot_val, dict):
            data = slot_val
        else:
            data = registry.get(slot_val)
        if not data: return slot_val
        
        name = data.get('name', slot_val)
        atk = data.get('attack_bonus', 0)
        dfs = data.get('defense_bonus', 0)
        
        stats = []
        if atk: stats.append(f"+{atk} ATK")
        if dfs: stats.append(f"+{dfs} DEF")
        
        if stats:
            return f"{name} ({', '.join(stats)})"
        return name

    h_str  = _sub_eq_display(eq.get("head"),      HEADGEAR)
    b_str  = _sub_eq_display(eq.get("boots"),     BOOTS)
    ac_str = _sub_eq_display(eq.get("accessory"), ACCESSORIES)
    
    hunts = hunts_remaining(sheet)
    
    
    s = await load_session(str(msg.channel.id))
    in_combat = False
    if s and s.get("combat_active"):
        for m in s.get("monsters", []):
            if m.get("aggro_uid") == uid:
                in_combat = True
                break
                
    if dungeon_in_combat:
        in_combat = True
                
    # World State display
    from utils.ttrpg.calendar import get_weather
    weather = get_weather()
    state = get_current_state()
    world_info = f"{weather['emoji']} **{weather['name']}** — *{weather['desc']}*"
    if state.get("event", "none") != "none":
        world_info += f"\n📣 **Event:** {state['event_desc']}"
        
    pct_hp = hp_cur / hp_max if hp_max > 0 else 0
    if hp_cur <= 0:
        color = 0x8B0000   # dark red - dead
    elif in_combat:
        color = 0xFF4500   # orange-red - fighting
    elif pct_hp <= 0.3:
        color = 0xFF6B6B   # red - critical
    else:
        color = 0x2D5A27   # deep forest green - normal
        
    char_title = get_title(sheet)
    base_class = sheet.get("class", "Warrior")
    adv_class = sheet.get("advanced_class", "")
    # Format: (Title) AdvancedClass  or  (Title) BaseClass
    display_class = adv_class if (adv_class and adv_class != base_class) else base_class
    title_suffix = f" · *({char_title}) {display_class}*" if char_title != "Adventurer" else f" · *{display_class}*"
    adv_class_str = adv_class if (adv_class and adv_class != base_class) else base_class
    embed = discord.Embed(
        title=f"{CLASS_ICONS.get(sheet.get('class'), '⚔️')}  {sheet['character_name'].upper()}{title_suffix}",
        description=f"*{adv_class_str} Lv.{sheet['level']}  ·  {LOCATION_ICONS.get(loc, '🗺️')} {loc_name}*\n\n{world_info}{resume_desc}",
        color=color
    )
    
    embed.add_field(
        name="❤️ HP",
        value=f"```ansi\n{colored_bar(hp_cur, hp_max, 14)}\n``` {hp_label(hp_cur, hp_max)}",
        inline=False
    )
    embed.add_field(
        name="✨ XP",
        value=f"```ansi\n{xp_bar_str}\n``` {xp_cur}/{xp_next or 'MAX'}",
        inline=True
    )
    embed.add_field(name="💰 Gil", value=f"{gil}g", inline=True)
    
    # Empty field for grid alignment if needed, or rely on Discord's 3-column layout
    
    # Replace the individual weapon/armor/head/boots/accessory/hunts/reputation fields with:
    equip_str = (
        f"🗡️ {w_str}\n"
        f"🛡️ {a_str}\n"
        f"🪖 {h_str} 👢 {b_str}\n"
        f"💍 {ac_str}"
    )
    embed.add_field(name="⚔️ Equipment", value=equip_str, inline=True)
    
    rep = sheet.get("reputation", 0)
    rep_rank = "Neutral"
    if rep >= 100: rep_rank = "Hero"
    elif rep >= 50: rep_rank = "Trusted"
    elif rep < -50: rep_rank = "Outlaw"
    elif rep < -20: rep_rank = "Unwelcome"
    
    embed.add_field(name="📊 Stats", value=f"🎯 {hunts}/{get_max_hunts(sheet)} hunts\n🎭 {rep_rank} ({rep})", inline=True)
    
    
    conds = sheet.get("conditions", [])
    if conds:
        cond_str = ", ".join(c.title() for c in conds)
        embed.add_field(name="⚠️ Status Effects", value=cond_str, inline=False)
    
    if sheet.get("_advancement_pending", False) and not sheet.get("advanced_class"):
        from utils.ttrpg.class_advancement import get_advanced_options, apply_advanced_class_to_sheet
        options = get_advanced_options(sheet.get("class", ""))
        if options:
            embed.color = 0xffd700
            embed.description += "\n\n✨ **CLASS ADVANCEMENT AVAILABLE!** ✨\nYou have reached Level 5 and may choose an elite path. Your choice is permanent."
            
            sel_options = [discord.SelectOption(label=f"{adv} - {opts['description']}"[:100], value=adv) for adv, opts in options.items()]
            view = discord.ui.View(timeout=120)
            sel = discord.ui.Select(placeholder="Choose your path...", options=sel_options, row=0)
            
            async def _adv_cb(interaction: discord.Interaction):
                if str(interaction.user.id) != uid:
                    return await interaction.response.send_message("Not yours.", ephemeral=True)
                chosen = interaction.data["values"][0]
                await interaction.response.defer()
                s = await load(uid)
                if not s or not s.get("_advancement_pending"): return
                s = apply_advanced_class_to_sheet(s, chosen)
                s["_advancement_pending"] = False
                await save(s)
                flavor = options[chosen].get("flavor", f"You are now a {chosen}.")
                await interaction.followup.send(f"```\n{flavor}\n```\n*You are now a {chosen}! Type `!rpg` to view your stats.*")
                
            sel.callback = _adv_cb
            view.add_item(sel)
            return await msg.channel.send(embed=embed, view=view)

    view = RPGLocationView(ctx, msg, uid, uname, is_owner, loc)
    await msg.channel.send(embed=embed, view=view)


async def _handle_new(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.dice_engine import roll, CLASSES
    
    existing = await load(uid)
    if existing:
        return await msg.channel.send(embed=discord.Embed(
            description=f"You already have a character: **{existing['character_name']}**.\nSheets are permanent.",
            color=0x888888
        ))
    
    args = rest.split()
    if len(args) < 3:
        class_list = ", ".join(CLASSES.keys())
        return await msg.channel.send(embed=discord.Embed(
            description=f"Usage: `!rpg new <Name> <Race> <Class>`\nClasses: {class_list}",
            color=0x888888
        ))
    
    char_name = args[0]
    race = args[1].title()
    class_name = args[2].title()
    
    VALID_RACES = {"Human", "Elf", "Silvani", "Dwarf", "Glimmerkin", "Veiled"}
    if race not in VALID_RACES:
        return await msg.channel.send(embed=discord.Embed(
            description=f"Unknown race: **{race}**\nValid races: {', '.join(sorted(VALID_RACES))}",
            color=0xcc4444
        ))
    
    if class_name not in CLASSES:
        class_list = ", ".join(CLASSES.keys())
        return await msg.channel.send(embed=discord.Embed(
            description=f"Unknown class. Options: {class_list}",
            color=0xcc4444
        ))
    
    RACE_BONUSES = {
        "Human":    {"str": 1, "dex": 1, "con": 1, "int": 1, "wis": 1, "cha": 1},
        "Elf":      {"dex": 2, "int": 1, "wis": 1},
        "Silvani":  {"dex": 2, "wis": 2},
        "Dwarf":    {"con": 2, "str": 1},
        "Glimmerkin": {"cha": 2, "int": 1, "dex": 1},
        "Veiled":   {"int": 2, "cha": 2},
    }
    bonus_dict = RACE_BONUSES.get(race, {})
    
    stats_order = ["str", "dex", "con", "int", "wis", "cha"]
    rolled_stats = {}
    roll_log = []
    for stat in stats_order:
        dice = [roll("d6")[0] for _ in range(4)]
        base = sum(sorted(dice)[1:])  # drop lowest
        bonus = bonus_dict.get(stat, 0)
        rolled_stats[stat] = base + bonus
        bonus_str = f" (+{bonus} race)" if bonus else ""
        roll_log.append(f"{stat.upper()}: {sorted(dice)[1:]} = {base}{bonus_str} -> {rolled_stats[stat]}")
    
    sheet = await create(uid, uname, char_name, race, class_name, rolled_stats)
    
    embed = discord.Embed(
        title="✨ New Adventurer Registered",
        description=f"**{char_name}**, the {race} {class_name}, has entered Aethelgard.\n\n**Stat rolls (4d6 drop lowest + Race):**\n```\n" + "\n".join(roll_log) + "\n```\n\nYou awaken in Oakhaven Town Square. Type `!rpg` to view your HUD.",
        color=0xddcc88
    )
    await msg.channel.send(embed=embed)


async def _handle_sheet(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg sheet — detailed character sheet with computed combat stats."""
    from utils.ttrpg.equipment_registry import WEAPONS, ARMOR as ARMOR_REG, HEADGEAR, BOOTS, ACCESSORIES
    from utils.ttrpg.class_advancement import ADVANCED_CLASSES, get_title
    from utils.ttrpg.housing import load_housing
    from utils.ttrpg.pets import get_pet_passive
    from utils.ttrpg.dice_engine import STAT_MODIFIER, CLASSES

    # Support viewing another player's sheet
    target_id = str(msg.mentions[0].id) if getattr(msg, 'mentions', None) and msg.mentions else uid
    sheet = await load(target_id)
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="Character not found.", color=0xcc4444))

    # ── Basics ────────────────────────────────────────────────────────
    char_title = get_title(sheet)
    base_class = sheet.get("class", "Warrior")
    adv_class = sheet.get("advanced_class", "")
    display_class = adv_class if (adv_class and adv_class != base_class) else base_class
    title_suffix = f" · *({char_title})*" if char_title != "Adventurer" else ""
    loc = sheet.get("location", "oakhaven")
    from utils.ttrpg.world import LOCATION_DATA
    loc_name = LOCATION_DATA.get(loc, {}).get("name", loc.replace("_", " ").title())

    # ── Stat Modifiers ────────────────────────────────────────────────
    stats = sheet.get("stats", {})
    stat_order = ["str", "dex", "con", "int", "wis", "cha"]
    stat_lines = []
    for s in stat_order:
        val = stats.get(s, 10)
        mod = STAT_MODIFIER(val)
        mod_str = f"+{mod}" if mod >= 0 else str(mod)
        stat_lines.append(f"{s.upper()} {val:2d} ({mod_str})")
    # Format as two rows of three for compact display
    stats_block = f"{stat_lines[0]}  {stat_lines[1]}  {stat_lines[2]}\n{stat_lines[3]}  {stat_lines[4]}  {stat_lines[5]}"

    # ── Combat Stats (mirror combat_engine.py logic) ──────────────────
    CLASS_ATTACK_STAT = {
        "Warrior": "str", "Ranger": "dex", "Mage": "int",
        "Rogue": "dex", "Cleric": "wis",
    }
    if adv_class == "Wizard":
        atk_stat = "int"
    elif adv_class == "High Priest":
        atk_stat = "wis"
    else:
        atk_stat = CLASS_ATTACK_STAT.get(base_class, "str")
    atk_val = stats.get(atk_stat, 10)
    atk_mod = STAT_MODIFIER(atk_val)
    dex_mod = STAT_MODIFIER(stats.get("dex", 10))

    def _eq_key(val):
        if not val: return None
        return val.get("key") if isinstance(val, dict) else val

    eq = sheet.get("equipment", {})
    weapon    = WEAPONS.get(_eq_key(eq.get("weapon")))       or {}
    armor     = ARMOR_REG.get(_eq_key(eq.get("armor")))      or {}
    head      = HEADGEAR.get(_eq_key(eq.get("head")))        or {}
    boots_eq  = BOOTS.get(_eq_key(eq.get("boots")))          or {}
    accessory = ACCESSORIES.get(_eq_key(eq.get("accessory"))) or {}

    weapon_atk = weapon.get("attack_bonus", 0)
    weapon_dmg_die = weapon.get("damage_die", 4)
    weapon_dmg_bonus = weapon.get("damage_bonus", 0)
    acc_atk = accessory.get("attack_bonus", 0)
    armor_def = armor.get("defense_bonus", 0)
    head_def = head.get("defense_bonus", 0)
    boots_def = boots_eq.get("defense_bonus", 0)
    acc_def = accessory.get("defense_bonus", 0)

    # Advanced class bonuses
    adv_flat_atk = 0
    adv_flat_def = 0
    adv_bonus_info = []
    if adv_class:
        for base_opts in ADVANCED_CLASSES.values():
            if adv_class in base_opts:
                b = base_opts[adv_class].get("bonuses", {})
                adv_flat_atk = b.get("atk_bonus", 0) + b.get("spell_atk_bonus", 0)
                adv_flat_def = b.get("def_bonus", 0)
                if b.get("crit_threshold"):
                    adv_bonus_info.append(f"Crit on {b['crit_threshold']}+")
                if b.get("lifesteal_pct"):
                    adv_bonus_info.append(f"{int(b['lifesteal_pct']*100)}% Lifesteal")
                if b.get("heal_on_kill"):
                    adv_bonus_info.append(f"+{b['heal_on_kill']} HP on kill")
                if b.get("atk_vs_undead"):
                    adv_bonus_info.append(f"+{b['atk_vs_undead']} vs Undead")
                if b.get("death_resist"):
                    adv_bonus_info.append("Death Resist")
                if b.get("bone_shield_passive"):
                    adv_bonus_info.append(f"Bone Shield +{b['bone_shield_passive']}")
                if b.get("gil_bonus_pct"):
                    adv_bonus_info.append(f"+{int(b['gil_bonus_pct']*100)}% Gil")
                if b.get("xp_bonus_pct"):
                    adv_bonus_info.append(f"+{int(b['xp_bonus_pct']*100)}% XP")
                break

    # Pet bonuses
    housing = load_housing(str(sheet.get("user_id", target_id)))
    pet_bonuses = get_pet_passive(housing) if housing else {}
    pet_combat = pet_bonuses.get("combat_bonus", 0)
    pet_def = pet_bonuses.get("def_bonus", 0)

    total_atk = atk_mod + weapon_atk + acc_atk + adv_flat_atk + pet_combat
    raw_gear_def = armor_def + head_def + boots_def + acc_def
    effective_gear_def = min(10, raw_gear_def) + max(0, raw_gear_def - 10) // 2
    total_def = 10 + dex_mod + effective_gear_def + adv_flat_def + pet_def

    # Apply the same global cap used in combat_engine so the sheet is truthful
    player_level = sheet.get("level", 1)
    global_def_cap = int(player_level * 1.5) + 12
    effective_def = min(total_def, global_def_cap)

    # Damage string
    warrior_dmg_bonus = (sheet.get("level", 1) - 1) // 3 if base_class == "Warrior" else 0
    adv_dmg_flat = 3 if adv_class == "Wizard" else 0
    total_dmg_bonus = atk_mod + warrior_dmg_bonus + adv_dmg_flat + weapon_dmg_bonus
    dmg_sign = "+" if total_dmg_bonus >= 0 else ""
    dmg_str = f"1d{weapon_dmg_die}{dmg_sign}{total_dmg_bonus}" if total_dmg_bonus != 0 else f"1d{weapon_dmg_die}"

    # Crit threshold
    crit_thresh = 20
    if base_class == "Rogue": crit_thresh = 19
    if adv_class:
        for base_opts in ADVANCED_CLASSES.values():
            if adv_class in base_opts:
                stored = base_opts[adv_class].get("bonuses", {}).get("crit_threshold")
                if stored:
                    crit_thresh = stored
                break

    # ── Equipment Display ─────────────────────────────────────────────
    def _eq_name(slot_val, registry, default="—"):
        if not slot_val: return default
        if isinstance(slot_val, dict): return slot_val.get("name", default)
        return registry.get(slot_val, {}).get("name", default)

    equip_lines = [
        f"🗡️ {_eq_name(eq.get('weapon'), WEAPONS, 'Unarmed')}",
        f"🛡️ {_eq_name(eq.get('armor'), ARMOR_REG, 'Unarmored')}",
        f"🪖 {_eq_name(eq.get('head'), HEADGEAR)} 👢 {_eq_name(eq.get('boots'), BOOTS)}",
        f"💍 {_eq_name(eq.get('accessory'), ACCESSORIES)}",
    ]

    # ── Life Stats ────────────────────────────────────────────────────
    hp_cur = sheet["hp"].get("current", 1)
    hp_max = sheet["hp"].get("max", 1)
    xp_cur = sheet.get("xp", 0)
    xp_next = xp_to_next_level(sheet["level"])
    gil = sheet.get("gil", 0)
    bank = sheet.get("bank_balance", 0)
    deaths = sheet.get("deaths", 0)
    streak = sheet.get("hunt_streak", 0)
    completed_quests = len(sheet.get("completed_quests", []))
    active_quest = sheet.get("active_quest")
    known_recipes = len(sheet.get("recipes", []))
    secrets_found = len(sheet.get("secrets", []))
    conditions = sheet.get("conditions", [])
    hunts = hunts_remaining(sheet)
    max_hunts = get_max_hunts(sheet)

    # Reputation
    rep = sheet.get("reputation", 0)
    if rep >= 100: rep_rank = "Hero"
    elif rep >= 50: rep_rank = "Trusted"
    elif rep >= 20: rep_rank = "Known"
    elif rep < -50: rep_rank = "Outlaw"
    elif rep < -20: rep_rank = "Unwelcome"
    else: rep_rank = "Neutral"

    # Fishing stats
    fish_stats = sheet.get("fishing_stats", {})
    total_caught = fish_stats.get("total_caught", 0)
    species_count = len(fish_stats.get("species_caught", {}))

    # ── Build Embed ───────────────────────────────────────────────────
    embed = discord.Embed(
        title=f"📄  {sheet['character_name'].upper()}{title_suffix}",
        description=(
            f"*{sheet.get('race', '?')} {display_class} Lv.{sheet['level']}*\n"
            f"*{LOCATION_ICONS.get(loc, '🗺️')} {loc_name}*"
        ),
        color=0x4a6741
    )

    # Stats block
    embed.add_field(
        name="📊 Attributes",
        value=f"```\n{stats_block}\n```",
        inline=False
    )

    combat_lines = [
        f"⚔️ **ATK:** +{total_atk} to hit",
        f"🗡️ **DMG:** {dmg_str}",
        f"🛡️ **DEF:** **{effective_def}**" + (f" *(raw {total_def}, capped)*" if effective_def < total_def else ""),
        f"💥 **Crit:** {crit_thresh}+",
    ]
    embed.add_field(
        name="⚔️ Combat",
        value="\n".join(combat_lines),
        inline=True
    )

    # ATK/DEF breakdown
    atk_parts = [f"{atk_stat.upper()} mod +{atk_mod}"]
    if weapon_atk: atk_parts.append(f"Weapon +{weapon_atk}")
    if acc_atk: atk_parts.append(f"Acc +{acc_atk}")
    if adv_flat_atk: atk_parts.append(f"Class +{adv_flat_atk}")
    if pet_combat: atk_parts.append(f"Pet +{pet_combat}")

    def_parts = [f"Base 10", f"DEX mod +{dex_mod}"]
    if effective_gear_def: def_parts.append(f"Gear +{effective_gear_def}")
    if adv_flat_def: def_parts.append(f"Class +{adv_flat_def}")
    if pet_def: def_parts.append(f"Pet +{pet_def}")

    breakdown_lines = [
        f"ATK: {' + '.join(atk_parts)}",
        f"DEF: {' + '.join(def_parts)}" + (f" = {total_def} → cap {global_def_cap}" if effective_def < total_def else ""),
    ]
    if effective_def < total_def:
        breakdown_lines.append(f"*Level {player_level} cap: Lv×1.5+12 = {global_def_cap} effective DEF*")
    embed.add_field(
        name="🔬 Breakdown",
        value="\n".join(breakdown_lines),
        inline=True
    )

    # Equipment
    embed.add_field(
        name="🎽 Equipment",
        value="\n".join(equip_lines),
        inline=False
    )

    # Class passives
    if adv_bonus_info:
        embed.add_field(
            name=f"✨ {adv_class} Passives",
            value=" · ".join(adv_bonus_info),
            inline=False
        )

    # Vitals
    vitals = (
        f"❤️ HP: **{hp_cur}/{hp_max}**\n"
        f"✨ XP: **{xp_cur}/{xp_next or 'MAX'}**\n"
        f"💰 Gil: **{gil}g** (Bank: {bank}g)"
    )
    embed.add_field(name="💖 Vitals", value=vitals, inline=True)

    # Career stats
    career = (
        f"🎯 Hunts: **{hunts}/{max_hunts}** today\n"
        f"🔥 Streak: **{streak}** kills\n"
        f"💀 Deaths: **{deaths}**\n"
        f"📜 Quests: **{completed_quests}** done"
    )
    embed.add_field(name="📈 Career", value=career, inline=True)

    # Knowledge / Misc
    misc = (
        f"⚗️ Recipes: **{known_recipes}**\n"
        f"🔍 Secrets: **{secrets_found}**\n"
        f"🎣 Fish caught: **{total_caught}** ({species_count} sp.)\n"
        f"🎭 Rep: **{rep_rank}** ({rep})"
    )
    embed.add_field(name="📚 Knowledge", value=misc, inline=True)

    # Active quest
    if active_quest:
        from utils.ttrpg.quest_registry import get_quest
        q = get_quest(active_quest)
        q_name = q["name"] if q else active_quest.replace("_", " ").title()
        prog = sheet.get("quest_progress", {}).get(active_quest, [])
        total_tasks = len(q["tasks"]) if q else "?"
        embed.add_field(
            name="📜 Active Quest",
            value=f"**{q_name}** — {len(prog)}/{total_tasks} tasks",
            inline=False
        )

    # Conditions
    if conditions:
        cond_str = ", ".join(c.replace("_", " ").title() for c in conditions)
        embed.add_field(name="⚠️ Status Effects", value=cond_str, inline=False)

    embed.set_footer(text=f"!rpg sheet · {sheet.get('race', '?')} {display_class} · Created {__import__('datetime').datetime.fromtimestamp(sheet.get('created_at', 0)).strftime('%b %d, %Y')}")

    # ── View with navigation buttons ──────────────────────────────────
    loc = sheet.get("location", "oakhaven")
    if target_id == uid:
        view = RPGLocationView(ctx, msg, uid, uname, is_owner, loc)
    else:
        view = discord.ui.View(timeout=120)
        view.add_item(_make_status_btn(ctx, uid, uname, is_owner))

    await msg.channel.send(embed=embed, view=view)


async def _handle_advance(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg advance — choose an advanced class at level 5."""
    sheet = await load(uid)
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(
            description="No character found.", color=0xcc4444
        ))

    if not sheet.get("_advancement_pending"):
        if sheet.get("advanced_class"):
            adv = sheet["advanced_class"]
            return await msg.channel.send(embed=discord.Embed(
                description=f"You already advanced to **{adv}**.",
                color=0x888888
            ))
        if sheet["level"] < 5:
            return await msg.channel.send(embed=discord.Embed(
                description=f"Advancement unlocks at Level 5. You are Level {sheet['level']}.",
                color=0x888888
            ))
        return await msg.channel.send(embed=discord.Embed(
            description="No advancement pending.",
            color=0x888888
        ))

    base = sheet.get("class", "Warrior")
    options = get_advanced_options(base)
    if not options:
        sheet.pop("_advancement_pending", None)
        await save(sheet)
        return await msg.channel.send(embed=discord.Embed(
            description="No advanced paths available for your class.",
            color=0x888888
        ))

    embed = discord.Embed(
        title=f"⚔️ Advancement — {base} → ???",
        description=(
            f"**{sheet['character_name']}** has reached Level 5.\n\n"
            "The path ahead splits. Choose your specialization:"
        ),
        color=0xffcc00
    )

    view = discord.ui.View(timeout=120)
    for adv_name, adv_data in options.items():
        embed.add_field(
            name=f"**{adv_name}**",
            value=f"{adv_data['description']}\n*{adv_data['flavor']}*",
            inline=False
        )
        btn = discord.ui.Button(
            label=f"Choose {adv_name}",
            style=discord.ButtonStyle.primary,
            row=0
        )
        async def _choose(interaction: discord.Interaction, chosen=adv_name, data=adv_data):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("not your choice.", ephemeral=True)
                return
            s = await load(uid)
            s = apply_advanced_class_to_sheet(s, chosen)
            s.pop("_advancement_pending", None)
            await save(s)
            await interaction.response.send_message(embed=discord.Embed(
                title=f"✨ {s['character_name']} → {chosen}",
                description=f"*{data['flavor']}*\n\nYour path is set. The title *{get_title(s)}* is yours.",
                color=0xffcc00
            ))
            await _log_world_event(
                f"⚔️ **{s['character_name']}** advanced to **{chosen}**. Oakhaven noticed."
            )
            adv_embed = discord.Embed(
                title=f"⚔️ {s['character_name']} → {chosen}",
                description=f"*{data['flavor']}*",
                color=0xffcc00
            )
            adv_embed.set_footer(text=f"Now: {get_title(s)}")
            await _broadcast_world_event(ctx, adv_embed)
        btn.callback = _choose
        view.add_item(btn)

    await msg.channel.send(embed=embed, view=view)


async def _handle_go(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.world import LOCATION_DATA, resolve_location

    sheet = await load(uid)
    if not sheet: return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    current_loc_key = sheet.get("location", "oakhaven")
    current_loc = LOCATION_DATA.get(current_loc_key, {})

    if not rest.strip():
        color = LOCATION_COLORS.get(current_loc_key, 0x888888)
        embed = discord.Embed(
            title=f"📍 {current_loc.get('name', current_loc_key)}",
            description=f"*{current_loc.get('short', '')}*",
            color=color
        )
        view = RPGFullLocationView(ctx, msg, uid, uname, is_owner, current_loc_key)
        return await msg.channel.send(embed=embed, view=view)

    target = resolve_location(rest.strip())
    if not target or target not in LOCATION_DATA:
        return await msg.channel.send(embed=discord.Embed(description=f"Unknown location: `{rest.strip()}`", color=0xcc4444))

    if target == current_loc_key:
        return await msg.channel.send(embed=discord.Embed(description="You're already there.", color=0x888888))

    # --- Auto-path: BFS to find shortest route ---
    def _find_path(start, end):
        from collections import deque
        visited = {start}
        queue = deque([(start, [start])])
        while queue:
            node, path = queue.popleft()
            for neighbor in LOCATION_DATA.get(node, {}).get("exits", []):
                if neighbor == end:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return None

    direct = target in current_loc.get("exits", [])
    path = [current_loc_key, target] if direct else _find_path(current_loc_key, target)

    if not path:
        return await msg.channel.send(embed=discord.Embed(description=f"There's no route from here to **{LOCATION_DATA.get(target, {}).get('name', target)}**.", color=0xcc4444))

    # Move player to final destination
    sheet["location"] = target
    await save(sheet)

    # Build arrival embed
    loc_data = LOCATION_DATA.get(target, {})
    name = loc_data.get("name", target)
    actions = ["`!rpg look` — observe the surroundings"]
    color = LOCATION_COLORS.get(target, 0x888888)

    # Show travel path if multi-hop
    if len(path) > 2:
        via_names = [LOCATION_DATA.get(p, {}).get("name", p) for p in path[1:-1]]
        desc = f"*Traveling via {', '.join(via_names)}...*\n\n*{loc_data.get('short', '')}*"
    else:
        desc = f"*{loc_data.get('short', '')}*"

    embed = discord.Embed(
        title=f"📍 {name}",
        description=desc,
        color=color
    )
    rec = loc_data.get("recommended_level")
    if rec and sheet["level"] < rec - 1:
        embed.set_footer(text=f"⚠️ Recommended level {rec}+ — proceed with caution")

    view = RPGFullLocationView(ctx, msg, uid, uname, is_owner, target)
    await msg.channel.send(embed=embed, view=view)


async def _handle_look(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.world import LOCATION_DATA
    from utils.ttrpg.rpg_prompt_builder import build_look_prompt
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    
    sheet = await load(uid)
    if not sheet: return
    
    loc = sheet.get("location", "oakhaven")
    data = LOCATION_DATA.get(loc, {})

    # ── Handle `!rpg look at <target>` ───────────────────────────────────────
    look_target = rest.strip().lower()
    if look_target.startswith("at "):
        look_target = look_target[3:].strip()

    if look_target:
        from utils.ttrpg.look_targets import LOCATION_LOOK_TARGETS
        loc_targets = LOCATION_LOOK_TARGETS.get(loc, {})
        result = loc_targets.get(look_target)
        if not result:
            # fuzzy match — "the flame" → "flame", "offering" → "offering bowl"
            for key in loc_targets:
                if key in look_target or look_target in key:
                    result = loc_targets[key]
                    break
        if result:
            embed = discord.Embed(description=result, color=LOCATION_COLORS.get(loc, 0x888888))
            
            # Secret puzzle trigger
            if loc == "shrine" and look_target in ("flame", "altar"):
                secrets = sheet.setdefault("secrets", [])
                if f"look_{look_target}" not in secrets:
                    secrets.append(f"look_{look_target}")
                    embed.set_footer(text="A piece of the pattern clicks into place.")
                    from utils.ttrpg.character_manager import save
                    await save(sheet)
                    
                    if "look_flame" in secrets and "look_altar" in secrets and "symbol_of_the_silent_ones" not in sheet.get("inventory", []):
                        sheet.setdefault("inventory", []).append("symbol_of_the_silent_ones")
                        embed.add_field(
                            name="Secret Unlocked",
                            value="You understand the pattern now. You can picture the seal perfectly in your mind.\n*(Acquired: symbol_of_the_silent_ones)*",
                            inline=False
                        )
                        await save(sheet)
                        
            return await msg.channel.send(embed=embed)
        else:
            return await msg.channel.send(embed=discord.Embed(
                description=f"*{sheet['character_name']} studies the {look_target} carefully. Nothing unusual stands out.*",
                color=0x888888,
            ))

    # ── Generic location narration via Ollama ─────────────────────────────────
    
    prompt = build_look_prompt(
        sheet, 
        data.get("name", loc), 
        data.get("short", ""), 
        data.get("atmosphere", "generic outdoors")
    )
    
    persona = await load_persona_async()
    messages = [
        {"role": "system", "content": f"{persona}\n\n{prompt}"},
        {"role": "user", "content": f"{sheet['character_name']} looks around the area."}
    ]
    
    gpu_manager = OllamaGPUManager(config.chat_model)
    opts = gpu_manager.get_gpu_options(for_chat=True)
    opts["num_predict"] = 150
    opts["temperature"] = 0.85
    
    async with msg.channel.typing():
        try:
            resp = await gpu_memory_manager.run_with_gpu_guard(
                model_name=config.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(
                    ctx.ollama_client.chat(model=config.chat_model, messages=messages, options=opts, keep_alive=-1),
                    timeout=45.0
                ),
                task_id=f"rpg_look_{_uuid.uuid4().hex[:8]}"
            )
            narration = resp["message"]["content"].strip().replace("```", "")
            if narration: 
                # Create narration embed
                embed = discord.Embed(
                    title=f"📍 {data.get('name', loc)}",
                    description=f"*{narration}*",
                    color=LOCATION_COLORS.get(loc, 0x888888)
                )
                
                view = RPGFullLocationView(ctx, msg, uid, uname, is_owner, loc)
                await msg.channel.send(embed=embed, view=view)
        except Exception as e:
            log_error(f"[rpg look] {e}")


async def _handle_map(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.world import LOCATION_DATA

    sheet = await load(uid)
    if not sheet: return

    current_loc_key = sheet.get("location", "oakhaven")
    current_loc = LOCATION_DATA.get(current_loc_key, {})

    exits = current_loc.get("exits", [])
    exit_lines = []
    for key in exits:
        if key not in LOCATION_DATA: continue
        ld = LOCATION_DATA[key]
        name = ld.get("name", key.replace("_", " ").title())
        if ld.get("hunting"):
            name += "  ⚔️"
        rec = ld.get("recommended_level")
        if rec:
            name += f"  *(Lv.{rec}+)*"
        exit_lines.append(f"• {name}")

    desc = "\n".join(exit_lines) if exit_lines else "*No exits from here.*"
    desc += "\n\n*Select a destination from the dropdown below.*"

    embed = discord.Embed(
        title=f"🗺️ From {current_loc.get('name', current_loc_key)}",
        description=desc,
        color=0x4488cc
    )

    view = RPGFullLocationView(ctx, msg, uid, uname, is_owner, current_loc_key)
    await msg.channel.send(embed=embed, view=view)


async def _handle_rest(ctx, msg, send, rest, uid, uname, is_owner):
    sheet = await load(uid)
    if not sheet: return
    
    if sheet.get("location") != "stone_hearth":
        return await msg.channel.send(embed=discord.Embed(description="You need to be at the Stone Hearth inn to rest. (`!rpg go stone_hearth`)", color=0xcc4444))
        
    cost = 5
    if sheet.get("gil", 0) < cost:
        return await msg.channel.send(embed=discord.Embed(description=f"Mira shakes her head. \"Beds aren't free.\"\nYou need {cost} gil. You have {sheet.get('gil', 0)}g.", color=0xcc4444))
        
    hp_cur = sheet["hp"]["current"]
    hp_max = sheet["hp"]["max"]
    
    has_ale = "ale_warmth" in sheet.get("conditions", [])
    if hp_cur >= hp_max and not has_ale:
        return await msg.channel.send(embed=discord.Embed(description=f"**{sheet['character_name']}** is already at maximum health.\nMira raises an eyebrow. *\"You're paying for a room you won't use?\"*", color=0x888888))

    # Clear ale temp HP and condition BEFORE healing
    if "ale_warmth" in sheet.get("conditions", []):
        sheet["conditions"].remove("ale_warmth")
        sheet["hp"]["max"] -= 3  # remove the temp bonus
        sheet["hp"]["current"] = min(sheet["hp"]["current"], sheet["hp"]["max"])

    healed = sheet["hp"]["max"] - sheet["hp"]["current"]
    sheet["hp"]["current"] = sheet["hp"]["max"]
    sheet["gil"] -= cost

    sheet["inn_rest_pending"] = True

    await save(sheet)
    
    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=discord.Embed(
        description=f"🛏️ **{sheet['character_name']}** rests at the Stone Hearth. (-{cost} gil)\nHP restored: **+{healed}** (Full)\nRemaining gil: {sheet['gil']}g\n\n*You feel invigorated. (+1 Hunt tomorrow)*",
        color=0x44aa44
    ), view=view)


async def _handle_rumor(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_prompt_builder import build_rumor_prompt
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    
    sheet = await load(uid)
    if sheet and sheet.get("location") != "stone_hearth":
        return await msg.channel.send(embed=discord.Embed(description="You must be at the Stone Hearth to hear rumors. (`!rpg go stone_hearth`)", color=0xcc4444))
        
    prompt = build_rumor_prompt()
    persona = await load_persona_async()
    messages = [
        {"role": "system", "content": f"{persona}\n\n{prompt}"},
        {"role": "user", "content": "I sit at the bar. What are people talking about?"}
    ]
    
    gpu_manager = OllamaGPUManager(config.chat_model)
    opts = gpu_manager.get_gpu_options(for_chat=True)
    opts["num_predict"] = 100
    opts["temperature"] = 0.95
    
    async with msg.channel.typing():
        try:
            resp = await gpu_memory_manager.run_with_gpu_guard(
                model_name=config.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(
                    ctx.ollama_client.chat(model=config.chat_model, messages=messages, options=opts, keep_alive=-1),
                    timeout=30.0
                ),
                task_id=f"rpg_rumor_{_uuid.uuid4().hex[:8]}"
            )
            rumor = resp["message"]["content"].strip().replace("```", "")
            if rumor:
                embed = discord.Embed(
                    title="🗣️ Rumor Heard",
                    description=f"*{rumor}*",
                    color=0x888888
                )
                view = _make_status_view(ctx, msg, uid, uname, is_owner)
                await msg.channel.send(embed=embed, view=view)
        except Exception as e:
            log_error(f"[rpg rumor] {e}")


async def _handle_calendar(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.calendar import get_today_summary, SPECIAL_DAYS
    from datetime import date

    summary = get_today_summary()
    season = summary["season"]
    special = summary["special_day"]

    # Build upcoming events (next 14 days)
    today = date.today()
    upcoming = []
    for i in range(1, 15):
        from datetime import timedelta
        check = today + timedelta(days=i)
        day_data = SPECIAL_DAYS.get((check.month, check.day))
        if day_data:
            upcoming.append(f"**{check.strftime('%b %d')}** — {day_data['name']}")

    color_map = {
        "spring": 0x88cc88,
        "summer": 0xf5c842,
        "autumn": 0xd4703c,
        "winter": 0x88aacc,
    }

    embed = discord.Embed(
        title=f"{summary['season_emoji']} {summary['season_name']} — {summary['date']}",
        description=f"*{summary['season_flavor']}*",
        color=color_map[season]
    )

    if special:
        embed.add_field(
            name=f"✨ {special['name']}",
            value=f"{special['desc']}\n\n**Today's effect:** {special.get('buff_desc', 'None')}",
            inline=False
        )
    else:
        embed.add_field(
            name="Today",
            value="An ordinary day. The Whisperwood does not care about ordinary days.",
            inline=False
        )

    if upcoming:
        embed.add_field(
            name="Upcoming",
            value="\n".join(upcoming[:5]),
            inline=False
        )

    embed.set_footer(text="!rpg calendar — updated daily at dawn")
    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=embed, view=view)


async def _handle_weather(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg weather — check today's deterministic weather conditions."""
    from utils.ttrpg.calendar import get_weather, get_today_summary

    weather = get_weather()
    summary = get_today_summary()

    color_map = {
        "clear":        0xf5c842,
        "overcast":     0x9aabb5,
        "rain":         0x5b8fa8,
        "storm":        0x4a4a7a,
        "fog":          0xb0b8bb,
        "hot":          0xe8742a,
        "drought_wind": 0xd4a030,
        "snow":         0xc8ddf0,
        "blizzard":     0x8aaac8,
        "frost":        0x88ccee,
        "wind":         0xa0b8c0,
    }

    desc_lines = [f"*{weather['desc']}*"]

    effect = weather.get("effect")
    if effect:
        desc_lines.append(f"\n⚠️ **Today:** {effect['desc']}")

    embed = discord.Embed(
        title=f"{weather['emoji']} {weather['name']} — {summary['date']}",
        description="\n".join(desc_lines),
        color=color_map.get(weather["key"], 0x888888)
    )
    embed.set_footer(text=f"{summary['season_name']} · Weather changes at dawn")
    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=embed, view=view)


async def _handle_inventory(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.shop import find_item
    from utils.ttrpg.equipment_registry import WEAPONS, ARMOR as ARMOR_REG, HEADGEAR, BOOTS, ACCESSORIES
    from collections import Counter

    sheet = await load(uid)
    if not sheet: return

    # ── Equipped gear summary ────────────────────────────────────────────────
    def _eq_name(slot_val, registry):
        if not slot_val: return "—"
        if isinstance(slot_val, dict): return slot_val.get("name", "?")
        return registry.get(slot_val, {}).get("name", slot_val)

    eq = sheet.get("equipment", {})
    equipped_lines = (
        f"🗡️ {_eq_name(eq.get('weapon'), WEAPONS)}  "
        f"🛡️ {_eq_name(eq.get('armor'), ARMOR_REG)}  "
        f"🪖 {_eq_name(eq.get('head'), HEADGEAR)}\n"
        f"👢 {_eq_name(eq.get('boots'), BOOTS)}  "
        f"💍 {_eq_name(eq.get('accessory'), ACCESSORIES)}"
    )

    inventory = sheet.get("inventory", [])
    if not inventory:
        embed = discord.Embed(
            title="🎒 Inventory",
            description=f"**Equipped:**\n{equipped_lines}\n\n*Backpack is empty.*",
            color=0x888888
        )
        embed.set_footer(text="!rpg status  ·  !rpg help")
        view = _make_status_view(ctx, msg, uid, uname, is_owner)
        await msg.channel.send(embed=embed, view=view)
        return

    # ── Categorize inventory ─────────────────────────────────────────────────
    GEAR_SLOTS = [
        ("weapon",    "🗡️ WEAPONS"),
        ("armor",     "🛡️ ARMOR"),
        ("head",      "🪖 HEAD"),
        ("boots",     "👢 BOOTS"),
        ("accessory", "💍 ACCESSORIES"),
    ]
    SLOT_PREFIX = {k: label for k, label in GEAR_SLOTS}

    sections: dict[str, list[str]] = {k: [] for k, _ in GEAR_SLOTS}
    consumable_lines: list[str] = []
    misc_lines: list[str] = []

    inv_counts = Counter(inventory)

    for key, count in sorted(inv_counts.items(), key=lambda kv: (find_item(kv[0]) or {}).get("name", kv[0])):
        if key == "symbol_of_the_silent_ones":
            continue

        item = find_item(key)
        count_str = f" ×{count}" if count > 1 else ""

        if item:
            cat = item["category"]

            if cat == "weapon":
                proc_str = ""
                proc_data = item.get("proc")
                if proc_data:
                    proc_str = f"  {proc_data.get('emoji','⚡')}{proc_data['name']}"
                class_tag = _get_class_abbr_string(item)
                line = (
                    f"**{item['name']}**{count_str} — "
                    f"+{item['attack_bonus']} ATK, d{item['damage_die']}{proc_str}{class_tag}  "
                    f"*(sell: {item['value'] // 2}g)*"
                )
                sections["weapon"].append(line)

            elif cat == "armor":
                class_tag = _get_class_abbr_string(item)
                line = f"**{item['name']}**{count_str} — +{item['defense_bonus']} DEF{class_tag}  *(sell: {item['value'] // 2}g)*"
                sections["armor"].append(line)

            elif cat == "head":
                class_tag = _get_class_abbr_string(item)
                line = f"**{item['name']}**{count_str} — +{item['defense_bonus']} DEF{class_tag}  *(sell: {item['value'] // 2}g)*"
                sections["head"].append(line)

            elif cat == "boots":
                class_tag = _get_class_abbr_string(item)
                line = f"**{item['name']}**{count_str} — +{item['defense_bonus']} DEF{class_tag}  *(sell: {item['value'] // 2}g)*"
                sections["boots"].append(line)

            elif cat == "accessory":
                atk = item.get("attack_bonus", 0)
                dfs = item.get("defense_bonus", 0)
                stat_parts = []
                if dfs: stat_parts.append(f"+{dfs} DEF")
                if atk: stat_parts.append(f"+{atk} ATK")
                stat_str = ", ".join(stat_parts) if stat_parts else "cosmetic"
                class_tag = _get_class_abbr_string(item)
                line = f"**{item['name']}**{count_str} — {stat_str}{class_tag}  *(sell: {item['value'] // 2}g)*"
                sections["accessory"].append(line)

            elif cat == "consumable":
                val = item.get("value", 0)
                effect_str = _get_item_effect_string(item)
                # Helper returns " — effect", we want to strip the " — " prefix for the log if possible or just use it consistently.
                # Actually _get_item_effect_string returns " — restores 30 HP".
                # The log format was "**name** — effect".
                effect = effect_str.lstrip(" — ")
                consumable_lines.append(f"**{item['name']}**{count_str} — {effect}  *(sell: {val // 2}g)*")
            else:
                misc_lines.append(f"**{item['name']}**{count_str}")
        else:
            display = key.replace("_", " ").title()
            misc_lines.append(f"**{display}**{count_str} — *sell to Hemlock to find out*")

    # ── Build ordered section blocks ─────────────────────────────────────────
    section_blocks: list[tuple[str, list[str]]] = []
    for slot_key, slot_label in GEAR_SLOTS:
        if sections[slot_key]:
            section_blocks.append((slot_label, sections[slot_key]))
    if consumable_lines:
        section_blocks.append(("🧪 CONSUMABLES", consumable_lines))
    if misc_lines:
        section_blocks.append(("📦 MISC", misc_lines))

    # ── Pagination (keep sections whole where possible) ───────────────────────
    header = f"**Equipped:**\n{equipped_lines}\n\n"
    MAX_DESC = 4096
    HEADER_BUDGET = len(header) + 60
    BODY_BUDGET = MAX_DESC - HEADER_BUDGET

    pages: list[list[tuple[str, list[str]]]] = []
    current_page: list[tuple[str, list[str]]] = []
    current_len = 0

    for sect_name, sect_lines in section_blocks:
        block_text = f"**{sect_name}**\n" + "\n".join(sect_lines) + "\n\n"
        cost = len(block_text)
        if current_page and current_len + cost > BODY_BUDGET:
            pages.append(current_page)
            current_page = []
            current_len = 0
        current_page.append((sect_name, sect_lines))
        current_len += cost

    if current_page:
        pages.append(current_page)
    if not pages:
        pages = [[]]

    async def _send_page(page_idx, interaction=None):
        desc = header
        if len(pages) > 1:
            desc += f"*Page {page_idx + 1}/{len(pages)}*\n\n"

        if pages[page_idx]:
            for sect_name, sect_lines in pages[page_idx]:
                desc += f"**{sect_name}**\n"
                desc += "\n".join(sect_lines)
                desc += "\n\n"
        else:
            desc += "*Backpack is empty.*"

        embed = discord.Embed(
            title="🎒 Inventory",
            description=desc.rstrip(),
            color=0x8b7355
        )
        view = _make_inventory_view(
            ctx, msg, uid, uname, is_owner, inventory,
            page_idx, len(pages), _send_page
        )
        if interaction:
            await interaction.message.edit(embed=embed, view=view)
        else:
            await msg.channel.send(embed=embed, view=view)

    await _send_page(0)


async def _handle_equip(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.shop import find_item
    sheet = await load(uid)
    if not sheet: return
    
    if not rest.strip():
        return await msg.channel.send(embed=discord.Embed(description="Equip what? `!rpg equip <item>`", color=0x888888))
        
    item_key = rest.strip().lower().replace(" ", "_")
    from utils.ttrpg.equipment_registry import ALIASES
    item_key = ALIASES.get(item_key, item_key)
    if item_key not in sheet.get("inventory", []):
        return await msg.channel.send(embed=discord.Embed(description=f"You don't have `{item_key}` in your inventory.", color=0xcc4444))
        
    item = find_item(item_key)
    if not item or item["category"] not in ["weapon", "armor", "head", "boots", "accessory"]:
        return await msg.channel.send(embed=discord.Embed(description=f"`{item_key}` cannot be equipped.", color=0xcc4444))

    # Check class restriction
    item_classes = item.get("classes")
    char_class = sheet.get("class", "")
    adv_class  = sheet.get("advanced_class", "")
    if item_classes and char_class not in item_classes and adv_class not in item_classes:
        class_str = "/".join(item_classes)
        return await msg.channel.send(embed=discord.Embed(
            description=f"**{item['name']}** can only be used by: {class_str}.",
            color=0xcc4444
        ))

    # Unequip existing if slot filled
    slot = item["category"]
    old_val = sheet["equipment"].get(slot)
    if old_val:
        # Remove old HP bonus if it exists
        old_hp_bonus = old_val.get("hp_bonus", 0) if isinstance(old_val, dict) else 0
        if old_hp_bonus:
            sheet["hp"]["max"] = max(1, sheet["hp"]["max"] - old_hp_bonus)
            sheet["hp"]["current"] = min(sheet["hp"]["current"], sheet["hp"]["max"])

        # Handle both string keys and dict values
        old_key = old_val.get("key") if isinstance(old_val, dict) else old_val
        if old_key:
            sheet["inventory"].append(old_key)
        
    # Equip new
    # Add new HP bonus if it exists
    new_hp_bonus = item.get("hp_bonus", 0)
    if new_hp_bonus:
        sheet["hp"]["max"] += new_hp_bonus
        sheet["hp"]["current"] += new_hp_bonus

    sheet["inventory"].remove(item_key)
    sheet["equipment"][slot] = item
    await save(sheet)
    
    await msg.channel.send(embed=discord.Embed(description=f"Equipped **{item['name']}** as {slot}.", color=0x44aa44))


async def _handle_unequip(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.equipment_registry import WEAPONS, ARMOR as ARMOR_REG, HEADGEAR, BOOTS, ACCESSORIES

    sheet = await load(uid)
    if not sheet: return

    slot_aliases = {
        "weapon": "weapon", "sword": "weapon", "bow": "weapon", "axe": "weapon",
        "staff": "weapon", "dagger": "weapon", "blade": "weapon",
        "armor": "armor", "chest": "armor", "body": "armor", "robe": "armor",
        "head": "head", "helm": "head", "helmet": "head", "hat": "head", "hood": "head",
        "boots": "boots", "feet": "boots", "greaves": "boots",
        "accessory": "accessory", "ring": "accessory", "bracer": "accessory",
        "bracelet": "accessory", "amulet": "accessory",
    }

    eq = sheet.get("equipment", {})
    arg = rest.strip().lower()

    # Try to find slot by arg — either slot name/alias or item name
    target_slot = None
    if arg in slot_aliases:
        target_slot = slot_aliases[arg]
    else:
        # Match against equipped item names
        registries = {
            "weapon": WEAPONS, "armor": ARMOR_REG,
            "head": HEADGEAR, "boots": BOOTS, "accessory": ACCESSORIES
        }
        for slot, registry in registries.items():
            val = eq.get(slot)
            if not val: continue
            item_key = val.get("key") if isinstance(val, dict) else val
            item_name = (val.get("name") if isinstance(val, dict) else registry.get(val, {}).get("name", "")).lower()
            if arg and (arg in (item_key or "").lower() or arg in item_name):
                target_slot = slot
                break

    # No arg or no match — show select menu of equipped items
    if not target_slot or not eq.get(target_slot):
        equipped = [(slot, val) for slot, val in eq.items() if val]
        if not equipped:
            return await msg.channel.send(embed=discord.Embed(description="Nothing equipped.", color=0x888888))

        if not arg:
            # Build a select menu
            registries = {
                "weapon": WEAPONS, "armor": ARMOR_REG,
                "head": HEADGEAR, "boots": BOOTS, "accessory": ACCESSORIES
            }
            options = []
            for slot, val in equipped:
                name = val.get("name") if isinstance(val, dict) else registries.get(slot, {}).get(val, {}).get("name", val)
                options.append(discord.SelectOption(label=f"{slot.title()}: {name}", value=slot))

            view = discord.ui.View(timeout=60)
            sel = discord.ui.Select(placeholder="Unequip which item?", options=options, row=0)

            async def _sel_cb(interaction: discord.Interaction):
                if str(interaction.user.id) != uid:
                    await interaction.response.send_message("not yours.", ephemeral=True)
                    return
                chosen_slot = interaction.data["values"][0]
                await interaction.response.defer()
                fake_msg = _InteractionMsg(interaction)
                send_fn = _make_interaction_send(interaction)
                await _handle_unequip(ctx, fake_msg, send_fn, chosen_slot, uid, uname, is_owner)

            sel.callback = _sel_cb
            view.add_item(sel)
            view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
            return await msg.channel.send(embed=discord.Embed(description="Select an item to unequip:", color=0x888888), view=view)

        return await msg.channel.send(embed=discord.Embed(
            description=f"Nothing equipped in that slot matching `{arg}`.", color=0xcc4444
        ))

    # Unequip
    val = eq[target_slot]
    item_key = val.get("key") if isinstance(val, dict) else val
    item_name = val.get("name") if isinstance(val, dict) else item_key

    if item_key:
        sheet["inventory"].append(item_key)

    # Remove HP bonus
    hp_bonus = val.get("hp_bonus", 0) if isinstance(val, dict) else 0
    if hp_bonus:
        sheet["hp"]["max"] = max(1, sheet["hp"]["max"] - hp_bonus)
        sheet["hp"]["current"] = min(sheet["hp"]["current"], sheet["hp"]["max"])

    sheet["equipment"][target_slot] = None
    await save(sheet)

    await msg.channel.send(embed=discord.Embed(
        description=f"Unequipped **{item_name}** — moved to inventory.",
        color=0x44aa44
    ))


async def _handle_use(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.shop import find_item
    sheet = await load(uid)
    if not sheet: return
    
    item_key = rest.strip().lower().replace(" ", "_")
    from utils.ttrpg.equipment_registry import ALIASES
    item_key = ALIASES.get(item_key, item_key)
        
    if item_key not in sheet.get("inventory", []):
        return await msg.channel.send(embed=discord.Embed(description=f"You don't have `{item_key}`.", color=0xcc4444))
        
    item = find_item(item_key)
    if not item or item["category"] != "consumable":
        return await msg.channel.send(embed=discord.Embed(description=f"You can't use `{item_key}`.", color=0xcc4444))
        
    if "hp_restore" in item and item["hp_restore"] > 0:
        before = sheet["hp"]["current"]
        # Cleric/High Priest heal_mult bonus
        heal_mult = 1.0
        char_class = sheet.get("class", "")
        adv_class  = sheet.get("advanced_class", "")
        if adv_class == "High Priest":
            heal_mult = 1.5
        elif adv_class in ("Cleric", "") and char_class == "Cleric":
            heal_mult = 1.25
        actual_restore = int(item["hp_restore"] * heal_mult)
        sheet["hp"]["current"] = min(sheet["hp"]["current"] + actual_restore, sheet["hp"]["max"])
        healed = sheet["hp"]["current"] - before
        sheet["inventory"].remove(item_key)
        await save(sheet)
        combat_view = await _get_active_view(ctx, msg, uid, uname, is_owner)
        view = combat_view if combat_view else _make_status_view(ctx, msg, uid, uname, is_owner)
        await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. Restored {healed} HP ({before} → {sheet['hp']['current']})", color=0x44aa44), view=view)
    elif item.get("on_use") == "starter_kit":
        sheet["inventory"].remove(item_key)
        sheet["inventory"].extend(["bandage", "healing_herb", "torch"])
        await save(sheet)
        await msg.channel.send(embed=discord.Embed(description=f"You open the **{item['name']}**.\n\nObtained:\n• Bandage\n• Healing Herb\n• Torch (lore item)", color=0x44aa44))
    elif item.get("on_use") == "cure_poison":
        if "poisoned" in sheet.get("conditions", []):
            sheet["conditions"].remove("poisoned")
            sheet["inventory"].remove(item_key)
            await save(sheet)
            combat_view = await _get_active_view(ctx, msg, uid, uname, is_owner)
            view = combat_view if combat_view else _make_status_view(ctx, msg, uid, uname, is_owner)
            await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. The venom fades from your veins.", color=0x44aa44), view=view)
        else:
            await msg.channel.send(embed=discord.Embed(description=f"You aren't poisoned.", color=0xcc4444))
    elif item.get("on_use") == "luck_roll_bonus":
        if "lucky" not in sheet.get("conditions", []):
            if "conditions" not in sheet: sheet["conditions"] = []
            sheet["conditions"].append("lucky")
            sheet["inventory"].remove(item_key)
            await save(sheet)
            combat_view = await _get_active_view(ctx, msg, uid, uname, is_owner)
            view = combat_view if combat_view else _make_status_view(ctx, msg, uid, uname, is_owner)
            await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. You feel a sudden surge of confidence. (+1 to next hit roll)", color=0x44aa44), view=view)
        else:
            await msg.channel.send(embed=discord.Embed(description=f"You are already feeling pretty lucky.", color=0xcc4444))
    elif item.get("on_use") == "xp_boost":
        if "xp_boosted" not in sheet.get("conditions", []):
            if "conditions" not in sheet: sheet["conditions"] = []
            sheet["conditions"].append("xp_boosted")
            sheet["inventory"].remove(item_key)
            await save(sheet)
            combat_view = await _get_active_view(ctx, msg, uid, uname, is_owner)
            view = combat_view if combat_view else _make_status_view(ctx, msg, uid, uname, is_owner)
            await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. 🧪 Your mind sharpens. (+25% XP on next hunt)", color=0x44aa44), view=view)
        else:
            await msg.channel.send(embed=discord.Embed(description=f"You're already buzzing with experience tonic.", color=0xcc4444))
    elif item.get("on_use") == "hunt_bonus":
        sheet["inventory"].remove(item_key)
        # Grant a bonus hunt condition instead of decrementing to respect the hard ceiling
        sheet.setdefault("conditions", []).append("hunt_bonus")
        await save(sheet)
        from utils.ttrpg.progression import hunts_remaining as _hr, get_max_hunts as _gmh
        combat_view = await _get_active_view(ctx, msg, uid, uname, is_owner)
        view = combat_view if combat_view else _make_status_view(ctx, msg, uid, uname, is_owner)
        await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. 🏹 Your senses sharpen. (+1 bonus hunt today — {_hr(sheet)}/{_gmh(sheet)} remaining)", color=0x44aa44), view=view)
    elif item.get("on_use") == "atk_boost":
        if "embered" not in sheet.get("conditions", []):
            if "conditions" not in sheet: sheet["conditions"] = []
            sheet["conditions"].append("embered")
            sheet["inventory"].remove(item_key)
            await save(sheet)
            combat_view = await _get_active_view(ctx, msg, uid, uname, is_owner)
            view = combat_view if combat_view else _make_status_view(ctx, msg, uid, uname, is_owner)
            await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. 🔥 Fire courses through your arms. (+2 ATK until next combat)", color=0x44aa44), view=view)
        else:
            await msg.channel.send(embed=discord.Embed(description=f"You're already burning with firebrew.", color=0xcc4444))
    elif item.get("on_use") == "def_boost":
        if "fortified" not in sheet.get("conditions", []):
            if "conditions" not in sheet: sheet["conditions"] = []
            sheet["conditions"].append("fortified")
            sheet["inventory"].remove(item_key)
            await save(sheet)
            combat_view = await _get_active_view(ctx, msg, uid, uname, is_owner)
            view = combat_view if combat_view else _make_status_view(ctx, msg, uid, uname, is_owner)
            await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. 🛡️ Your skin hardens like bark. (+2 DEF until next combat)", color=0x44aa44), view=view)
        else:
            await msg.channel.send(embed=discord.Embed(description=f"You're already toughened by ironbark.", color=0xcc4444))
    else:
        await msg.channel.send(embed=discord.Embed(description=f"**{item['name']}** can't be used. Try selling it: `!rpg sell {item_key}`", color=0xcc4444))


async def _handle_drink(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg drink — buy an ale at the Stone Hearth. Costs 2 gil, +3 temporary HP."""

    sheet = await load(uid)
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    if sheet.get("location") != "stone_hearth":
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at the Stone Hearth to drink.\n`!rpg go stone_hearth`", 
            color=0xcc4444
        ))

    DRINK_COST = 2
    if sheet.get("gil", 0) < DRINK_COST:
        return await msg.channel.send(embed=discord.Embed(
            description=f"Mira glances at your coin purse and shakes her head.\nAn ale costs {DRINK_COST} gil. You have {sheet.get('gil', 0)}g.",
            color=0xcc4444
        ))

    # Grant temp HP by raising max temporarily (tracked via condition)
    TEMP_HP = 3
    already_drinking = any("ale" in c.lower() for c in sheet.get("conditions", []))
    if already_drinking:
        return await msg.channel.send(embed=discord.Embed(
            description="*Mira refills the tankard without comment.*\nYou're already feeling the first one. Another won't stack.",
            color=0x888888
        ))

    sheet["gil"] -= DRINK_COST
    sheet["hp"]["max"] += TEMP_HP
    sheet["hp"]["current"] = min(sheet["hp"]["current"] + TEMP_HP, sheet["hp"]["max"])
    sheet.setdefault("conditions", []).append("ale_warmth")
    await save(sheet)

    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=discord.Embed(
        description=(
            f"🍺 Mira slides a tankard across. (-{DRINK_COST} gil)\n"
            f"Temp HP: +{TEMP_HP} ({sheet['hp']['current']}/{sheet['hp']['max']})\n"
            f"*+1 hunt cap until next rest.* ({hunts_remaining(sheet)}/{get_max_hunts(sheet)} available)\n"
            f"*Clears on rest.*"
        ), color=0x44aa44), view=view)


async def _handle_fountain(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg fountain — drink from the healing spring at the Shrine. Once per day, full heal."""
    from datetime import date

    sheet = await load(uid)
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    if sheet.get("location") != "shrine":
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at the Shrine of the Silent Ones to drink from the fountain.\n`!rpg go shrine`",
            color=0xcc4444
        ))

    today = date.today().strftime("%Y-%m-%d")
    if sheet.get("last_fountain_date") == today:
        return await msg.channel.send(embed=discord.Embed(
            description="💧 *The spring's waters are still. You've already partaken today.*\nIts magic needs time to replenish.",
            color=0x888888
        ))

    sheet["hp"]["current"] = sheet["hp"]["max"]
    sheet["last_fountain_date"] = today
    await save(sheet)

    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=discord.Embed(
        description=f"💧 **{sheet['character_name']} drinks from the spring.**\nYour wounds stitch closed. You are fully recovered. (HP: {sheet['hp']['current']}/{sheet['hp']['max']})\n*Clears when you next rest.*",
        color=0x44aa44
    ), view=view)


async def _handle_gamble(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg gamble — dice game at the Stone Hearth. 10 gil buy-in."""

    sheet = await load(uid)
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    if sheet.get("location") != "stone_hearth":
        return await msg.channel.send(embed=discord.Embed(
            description="The dice game only happens at the Stone Hearth.", 
            color=0xcc4444
        ))

    BUY_IN = 10
    if sheet.get("gil", 0) < BUY_IN:
        return await msg.channel.send(embed=discord.Embed(
            description=f"The buy-in is {BUY_IN} gil. you have {sheet.get('gil', 0)}g.\n*A weathered man across the table doesn't look up from his cards.*",
            color=0xcc4444
        ))

    # Roll d6 vs d6. Tie goes to house.
    # Trickster gamble_edge check
    has_gamble_edge = False
    adv = sheet.get("advanced_class", "")
    if adv == "Trickster":
        has_gamble_edge = True

    if has_gamble_edge:
        # Roll twice, take best
        player_roll = max(secrets.randbelow(6) + 1, secrets.randbelow(6) + 1)
    else:
        player_roll = secrets.randbelow(6) + 1
        
    house_roll  = secrets.randbelow(6) + 1

    sheet["gil"] -= BUY_IN

    if player_roll > house_roll:
        winnings = BUY_IN * 2
        sheet["gil"] += winnings
        result_line = f"🎲 You rolled **{player_roll}**, they rolled **{house_roll}**. You win!"
        gil_line = f"+{BUY_IN} gil (net). Total: {sheet['gil']}g"
    elif player_roll < house_roll:
        result_line = f"🎲 You rolled **{player_roll}**, they rolled **{house_roll}**. You lose."
        gil_line = f"-{BUY_IN} gil. Total: {sheet['gil']}g"
    else:
        result_line = f"🎲 You both rolled **{player_roll}**. House takes ties."
        gil_line = f"-{BUY_IN} gil. Total: {sheet['gil']}g"

    await save(sheet)

    gamble_view = discord.ui.View(timeout=60)

    gamble_again_btn = discord.ui.Button(
        label="🎲 Gamble Again", style=discord.ButtonStyle.secondary, row=0
    )

    async def _gamble_again_cb(interaction: discord.Interaction):
        if str(interaction.user.id) != uid:
            await interaction.response.send_message("```\nnot your table.\n```", ephemeral=True)
            return
        await interaction.response.defer()
        fake_msg = _InteractionMsg(interaction)
        send_fn = _make_interaction_send(interaction)
        await _handle_gamble(ctx, fake_msg, send_fn, "", uid, uname, is_owner)

    gamble_again_btn.callback = _gamble_again_cb
    gamble_view.add_item(gamble_again_btn)
    gamble_view.add_item(_make_status_btn(ctx, uid, uname, is_owner))

    await msg.channel.send(embed=discord.Embed(
        description=f"{result_line}\n{gil_line}",
        color=0x44aa44 if player_roll > house_roll else 0xcc4444
    ), view=gamble_view)


async def _handle_pray(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg pray — once per day blessing at the Shrine of the Silent Ones."""
    from datetime import date

    sheet = await load(uid)
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444), ephemeral=True)

    from utils.ttrpg.housing import load_housing
    from utils.ttrpg.furniture import get_home_bonuses
    _housing = load_housing(uid)
    _has_shrine_replica = (
        _housing 
        and sheet.get("location") == "housing_district"
        and "shrine_replica" in _housing.get("furniture", [])
    )
    if sheet.get("location") != "shrine" and not _has_shrine_replica:
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at the Shrine of the Silent Ones to pray.\n`!rpg go shrine`\n\n*Or purchase a Shrine Replica for your home.*",
            color=0xcc4444
        ), ephemeral=True)

    from utils.ttrpg.calendar import get_special_day
    special = get_special_day()
    if special and special.get("shrine_gift"):
        today = date.today().strftime("%Y-%m-%d")
        if sheet.get("shrine_gift_date") != today:
            sheet["shrine_gift_date"] = today
            from utils.ttrpg.loot_tables import get_consumable_loot
            gift = get_consumable_loot("hard") or "elixir"
            sheet.setdefault("inventory", []).append(gift)
            await save(sheet)
            return await msg.channel.send(embed=discord.Embed(
                title="🎁 Feast of the Silent Ones",
                description=f"A small bundle was left at the threshold.\n**You received a {gift.replace('_',' ').title()}!**",
                color=0xd4a843
            ))

    # Once per day check
    today = date.today().strftime("%Y-%m-%d")
    last_pray = sheet.get("last_pray_date", "")
    if last_pray == today:
        return await msg.channel.send(embed=discord.Embed(
            description="🕯️ *The shrine is still. You've already made your offering today.*\nThe Silent Ones do not answer twice.",
            color=0x888888
        ), ephemeral=True)

    # Check if already blessed
    if "blessed" in sheet.get("conditions", []):
        return await msg.channel.send(embed=discord.Embed(
            description="🕯️ *You are already carrying the blessing of the Silent Ones.*\nUse it before asking for more.",
            color=0x888888
        ), ephemeral=True)

    sheet.setdefault("conditions", []).append("blessed")
    sheet["last_pray_date"] = today
    await save(sheet)

    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=discord.Embed(
        description="🕯️ **Blessed** — *the shrine acknowledges you.*\nYour next hunt grants +2 to all attack and stat rolls.\n*The condition clears after your next combat.*",
        color=0xaaddff
    ), view=view)


async def _handle_offer(ctx, msg, send, rest, uid, uname, is_owner):
    from datetime import date

    sheet = await load(uid)
    if not sheet: return

    if sheet.get("location") != "shrine":
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at the Shrine of the Silent Ones.\n`!rpg go shrine`",
            color=0xcc4444
        ))

    today = date.today().strftime("%Y-%m-%d")
    offered_today = sheet.get("offered_today", {})
    already_offered = offered_today.get(today, 0) if isinstance(offered_today, dict) else 0

    from utils.ttrpg.calendar import get_special_day
    special = get_special_day()
    DAILY_CAP = 60 if (special and special.get("buff") == "solstice_blessing") else 20
    XP_MULT = 3 if (special and special.get("buff") == "solstice_blessing") else 1

    remaining_cap = max(0, DAILY_CAP - already_offered)
    on_hand = sheet.get("gil", 0)

    if remaining_cap == 0:
        return await msg.channel.send(embed=discord.Embed(
            description="🕯️ *The shrine is still. You've reached today's offering limit.*\nReturn tomorrow.",
            color=0x888888
        ))

    embed = discord.Embed(
        title="🕯️ Make an Offering",
        description=(
            f"**On Hand:** {on_hand}g\n"
            f"**XP remaining today:** {remaining_cap}/{DAILY_CAP}\n\n"
            f"*Each gil offered grants {XP_MULT} XP, up to {DAILY_CAP} max XP per day.*"
        ),
        color=0xaaddff
    )

    view = discord.ui.View(timeout=60)

    # Build amount options: 5, 10, 20 (max), and remaining cap
    amounts = []
    for amt in [5, 10]:
        if amt <= on_hand and amt <= remaining_cap:
            amounts.append((f"{amt}g", amt))
    # Max daily XP button
    max_amt = min(on_hand, remaining_cap)
    if max_amt > 0 and max_amt not in [5, 10]:
        amounts.append((f"Max ({max_amt}g = {max_amt} XP)", max_amt))
    elif max_amt > 0:
        amounts.append((f"Max ({max_amt}g = {max_amt} XP)", max_amt))

    if not amounts:
        return await msg.channel.send(embed=discord.Embed(
            description=f"Not enough gil to offer. You have {on_hand}g.",
            color=0xcc4444
        ))

    for label, amount in amounts:
        btn = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, row=0)

        async def _offer_cb(interaction: discord.Interaction, amt=amount):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("```\nnot yours.\n```", ephemeral=True)
                return

            s = await load(uid)
            t = date.today().strftime("%Y-%m-%d")
            od = s.get("offered_today", {})
            already = od.get(t, 0) if isinstance(od, dict) else 0
            cap_left = max(0, DAILY_CAP - already)

            eligible = min(amt, cap_left, s["gil"])
            if eligible <= 0:
                await interaction.response.send_message(
                    embed=discord.Embed(description="Nothing to offer — either capped or out of gil.", color=0xcc4444),
                    ephemeral=True
                )
                return

            s["gil"] -= eligible
            xp_earned = eligible * XP_MULT
            s["xp"] += xp_earned
            s["offered_today"] = {t: already + eligible}

            leveled_up, new_level = check_level_up(s)
            await save(s)

            xp_next = xp_to_next_level(s["level"])
            lines = [
                f"🕯️ **{eligible}g** offered. The air shifts.",
                f"+{xp_earned} XP ({s['xp']}/{xp_next})",
                f"On Hand: {s['gil']}g"
            ]
            if already + eligible >= DAILY_CAP:
                lines.append("*Daily offering limit reached.*")
            if leveled_up:
                lines.append(f"\n🎉 **Level Up! Now Lv.{new_level}!**")

            await interaction.response.send_message(
                embed=discord.Embed(description="\n".join(lines), color=0xaaddff)
            )

        btn.callback = _offer_cb
        view.add_item(btn)

    view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
    await msg.channel.send(embed=embed, view=view)


async def _handle_scout(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg scout — use the Watchtower to preview monster activity."""
    from utils.ttrpg.monster_registry import MONSTERS
    from utils.ttrpg.monster_registry import ENCOUNTER_TABLES as FULL_TABLES
    from utils.ttrpg.calendar import get_weather, get_season, SEASONAL_MONSTERS
    from datetime import date

    sheet = await load(uid)
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    from utils.ttrpg.housing import load_housing
    from utils.ttrpg.furniture import get_home_bonuses
    housing = load_housing(uid)
    bonuses = get_home_bonuses(housing) if housing else {}
    has_home_scout = sheet.get("location") == "housing_district" and bonuses.get("home_scout")

    if sheet.get("location") != "watchtower" and not has_home_scout:
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at the Watchtower to scout.\n`!rpg go watchtower`",
            color=0xcc4444
        ))

    weather = get_weather()
    effect = weather.get("effect")
    if effect and effect.get("type") == "scout_blocked":
        return await msg.channel.send(embed=discord.Embed(
            description=f"{weather['emoji']} **Scouting Blocked:** {effect['desc']}",
            color=0x888888
        ))

    today = date.today().strftime("%Y-%m-%d")
    if sheet.get("last_scout_date") == today:
        return await msg.channel.send(embed=discord.Embed(
            description="🗼 *The guards shrug. You've already had your look today.*\nCome back tomorrow.",
            color=0x888888
        ))

    sheet["last_scout_date"] = today
    await save(sheet)

    HUNTING_LOCATIONS = {
        "whisperwood_edge": "Edge of the Whisperwood",
        "whisperwood_deep": "Whisperwood Deep",
        "aeridor_ruins":    "Aeridor Ruins",
        "trade_road":       "The Trade Road",
    }

    DANGER_ICONS = {
        "trivial": "🟢", "easy": "🟡",
        "medium": "🟠", "hard": "🔴", "deadly": "💀", "boss": "☠️"
    }

    season = get_season()
    seasonal_mods = SEASONAL_MONSTERS.get(season, {})

    lines = [f"🗼 **Scout Report** — *{weather['emoji']} {weather['name']} — {today}*\n"]

    for loc_key, loc_name in HUNTING_LOCATIONS.items():
        base_table = FULL_TABLES.get(loc_key, [])
        seasonal = seasonal_mods.get(loc_key, [])
        table = base_table + seasonal

        if not table:
            continue

        total_weight = sum(w for _, w in table)

        # Roll 3 distinct random sightings, weighted
        spotted_keys = []
        attempts = 0
        while len(spotted_keys) < 3 and attempts < 20:
            attempts += 1
            r = secrets.randbelow(total_weight)
            cum = 0
            for mk, w in table:
                cum += w
                if r < cum:
                    if mk not in spotted_keys and mk in MONSTERS:
                        spotted_keys.append(mk)
                    break

        # Tier distribution
        tier_weights: dict[str, int] = {}
        for mk, w in table:
            t = MONSTERS.get(mk, {}).get("tier", "trivial")
            tier_weights[t] = tier_weights.get(t, 0) + w

        dominant_tier = max(tier_weights, key=tier_weights.get)
        dominant_pct = int(tier_weights[dominant_tier] / total_weight * 100)
        danger = DANGER_ICONS.get(dominant_tier, "⚪")

        spotted_names = [MONSTERS[k]["name"] for k in spotted_keys[:2] if k in MONSTERS]
        seasonal_note = f"  *(+ {season} spawns)*" if seasonal else ""

        # XP range hint
        xp_vals = [MONSTERS[mk]["xp"] for mk, _ in table if mk in MONSTERS]
        xp_hint = f"  ·  XP {min(xp_vals)}–{max(xp_vals)}" if xp_vals else ""

        lines.append(
            f"{danger} **{loc_name}**{seasonal_note}\n"
            f"   Mostly *{dominant_tier}* ({dominant_pct}%){xp_hint}\n"
            f"   Spotted: *{', '.join(spotted_names) if spotted_names else 'nothing visible'}*"
        )

    # Weather encounter note
    if effect and effect.get("type") == "encounter_mod":
        lines.append(f"\n⚠️ *{weather['name']} effect: {effect['desc']}*")

    # Randomized guard commentary
    GUARD_COMMENTS = [
        "*\"Whisperwood's been louder than usual. Watch yourself.\"*",
        "*\"Something came out of the ruins before sunrise again. We didn't follow it.\"*",
        "*\"Trade Road's clear as far as I can see. That's about two miles. After that, your problem.\"*",
        "*\"Don't go past the edge after dark. Not my rule. Just good sense.\"*",
        "*\"You didn't hear this from me — the deep wood's restless. More than usual.\"*",
        "*\"The canopy moved this morning. Wind was calm. Make of that what you will.\"*",
        "*\"Patrol came back short a man last week. We're not talking about it.\"*",
        "*\"Aeridor's been glowing again at dusk. Third time this month.\"*",
        "*\"I've got a theory about the ruins. But I like sleeping at night, so I keep it to myself.\"*",
        "*\"Ruins or deep woods tonight — ruins has better loot. Deep woods wants to keep it.\"*",
    ]
    lines.append(f"\n{GUARD_COMMENTS[secrets.randbelow(len(GUARD_COMMENTS))]}")

    embed = discord.Embed(
        description="\n".join(lines),
        color=0x8888aa
    )
    embed.set_footer(text=f"Scout intel refreshes daily at dawn · Today: {weather['name']}")
    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=embed, view=view)


async def _handle_bank_deposit(ctx, msg, send, rest, uid, uname, is_owner):
    sheet = await load(uid)
    if not sheet: return
    embed = discord.Embed(
        title="🏦 Deposit Gil",
        description=f"**Balance:** {sheet.get('bank_balance', 0)}g  ·  **On Hand:** {sheet.get('gil', 0)}g",
        color=0xaa88ff
    )
    view = discord.ui.View(timeout=60)
    for amt_label, amt_val in [("10g", 10), ("25g", 25), ("50g", 50), ("All", None)]:
        actual = sheet["gil"] if amt_val is None else amt_val
        btn = discord.ui.Button(
            label=f"Deposit {amt_label if amt_val else str(sheet['gil'])+'g'}",
            style=discord.ButtonStyle.secondary, row=0
        )
        async def _dep_cb(interaction: discord.Interaction, amount=actual, is_all=(amt_val is None)):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("```\nnot yours.\n```", ephemeral=True)
                return
            s = await load(uid)
            if is_all: amount = s["gil"]
            if amount > s["gil"]:
                await interaction.response.send_message(
                    embed=discord.Embed(description=f"Not enough gil. You have {s['gil']}g.", color=0xcc4444),
                    ephemeral=True
                )
                return
            s["gil"] -= amount
            s["bank_balance"] = s.get("bank_balance", 0) + amount
            await save(s)
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"Deposited **{amount}g**.\nBalance: {s['bank_balance']}g  ·  On Hand: {s['gil']}g",
                    color=0x44aa44
                )
            )
        btn.callback = _dep_cb
        view.add_item(btn)
    view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
    await msg.channel.send(embed=embed, view=view)


async def _handle_bank_withdraw(ctx, msg, send, rest, uid, uname, is_owner):
    sheet = await load(uid)
    if not sheet: return
    balance = sheet.get("bank_balance", 0)
    embed = discord.Embed(
        title="🏦 Withdraw Gil",
        description=f"**Balance:** {balance}g  ·  **On Hand:** {sheet.get('gil', 0)}g",
        color=0xaa88ff
    )
    view = discord.ui.View(timeout=60)
    for amt_label, amt_val in [("10g", 10), ("25g", 25), ("50g", 50), ("All", None)]:
        actual = balance if amt_val is None else amt_val
        btn = discord.ui.Button(
            label=f"Withdraw {amt_label if amt_val else str(balance)+'g'}",
            style=discord.ButtonStyle.secondary, row=0
        )
        async def _wth_cb(interaction: discord.Interaction, amount=actual, is_all=(amt_val is None)):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("```\nnot yours.\n```", ephemeral=True)
                return
            s = await load(uid)
            bank = s.get("bank_balance", 0)
            if is_all: amount = bank
            if amount > bank:
                await interaction.response.send_message(
                    embed=discord.Embed(description=f"Not enough in bank. Balance: {bank}g", color=0xcc4444),
                    ephemeral=True
                )
                return
            s["bank_balance"] = bank - amount
            s["gil"] += amount
            await save(s)
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"Withdrew **{amount}g**.\nBalance: {s['bank_balance']}g  ·  On Hand: {s['gil']}g",
                    color=0x44aa44
                )
            )
        btn.callback = _wth_cb
        view.add_item(btn)
    view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
    await msg.channel.send(embed=embed, view=view)


async def _handle_bank(ctx, msg, send, rest, uid, uname, is_owner):
    # Keep the legacy !rpg bank for balance checking
    sheet = await load(uid)
    if not sheet: return
    balance = sheet.get("bank_balance", 0)
    await msg.channel.send(embed=discord.Embed(
        title="🏦 OakHaven Bank",
        description=f"Your current balance is **{balance}g**.\nUse `!rpg bank_deposit` or `!rpg bank_withdraw` for transactions.",
        color=0xaa88ff
    ))


async def _handle_roll(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.dice_engine import roll
    try:
        total, breakdown = roll(rest.strip() or "d20")
        await msg.channel.send(embed=discord.Embed(
            description=f"🎲 **{uname}** rolled `{rest.strip() or 'd20'}`: {breakdown}",
            color=0x4488cc
        ))
    except:
        await msg.channel.send(embed=discord.Embed(description="Invalid syntax", color=0xcc4444))


async def _handle_bestiary(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return
    from utils.ttrpg.monster_registry import format_bestiary
    await send(msg.channel, format_bestiary(), use_code_block=False)


async def _handle_xp(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return
    await msg.channel.send(embed=discord.Embed(
        description="Developer override required to assign arbitrary XP in Aethelgard. Go hunt.",
        color=0xcc4444
    ))


async def _handle_give(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return
    from utils.ttrpg.shop import find_item
    args = rest.strip().split()
    if not args: return
    sheet = await load(str(msg.mentions[0].id) if msg.mentions else uid)
    if not sheet: return
    item = find_item(args[0])
    if item:
        sheet["inventory"].append(args[0])
        await save(sheet)
        await msg.channel.send(embed=discord.Embed(
            description=f"Admin granted `{args[0]}` to {sheet['character_name']}.",
            color=0x44aa44
        ))


async def _handle_heal(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return
    sheet = await load(str(msg.mentions[0].id) if msg.mentions else uid)
    if not sheet: return
    sheet["hp"]["current"] = sheet["hp"]["max"]
    await save(sheet)
    await msg.channel.send(embed=discord.Embed(
        description=f"Admin fully healed {sheet['character_name']}.",
        color=0x44aa44
    ))


async def _handle_leaderboard(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg leaderboard — show all characters ranked by XP."""
    from utils.ttrpg.world import LOCATION_DATA

    sheets = await load_all()
    if not sheets:
        return await msg.channel.send(embed=discord.Embed(description="No adventurers have been created yet.", color=0x888888))

    # Sort by XP descending, then by level descending, then by least deaths
    sheets.sort(key=lambda s: (s.get("xp", 0), s.get("level", 1), -s.get("deaths", 0)), reverse=True)

    MEDALS = ["🥇", "🥈", "🥉"]
    lines = []
    for i, s in enumerate(sheets[:15]):  # cap at 15 entries
        medal = MEDALS[i] if i < 3 else f"`{i+1}.`"
        cls_icon = CLASS_ICONS.get(s.get("class", ""), "⚔️")
        char_title = get_title(s)
        title_suffix = f" · *{char_title}*" if char_title != "Adventurer" else ""
        adv_class = s.get("advanced_class", "") or s.get("class", "?")
        loc_key = s.get("location", "oakhaven")
        loc_icon = LOCATION_ICONS.get(loc_key, "🗟a️")
        loc_name = LOCATION_DATA.get(loc_key, {}).get("name", loc_key.replace("_", " ").title())
        deaths = s.get("deaths", 0)
        race = s.get("race", "Unknown")

        line = (
            f"{medal} {cls_icon} **{s.get('character_name', '???')}**{title_suffix}\n"
            f"  {race} {adv_class} · Lv.{s.get('level', 1)} · {s.get('xp', 0)} XP\n"
            f"  💀 {deaths} death{'s' if deaths != 1 else ''} · {loc_icon} {loc_name}"
        )
        lines.append(line)

    embed = discord.Embed(
        title="🏆  AETHELGARD LEADERBOARD",
        description="\n\n".join(lines),
        color=0xd4a843  # gold
    )
    embed.set_footer(text=f"{len(sheets)} adventurer{'s' if len(sheets) != 1 else ''} registered")

    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=embed, view=view)


async def _handle_rpg_help(ctx, msg, send, rest, uid, uname, is_owner):

    embed = discord.Embed(
        title="📜 Aethelgard Commands",
        description="*Type any command to use it. Most require being in the right location.*",
        color=0x8b7355
    )

    embed.add_field(name="⚔️ World", value=(
        "`!rpg` — status & HUD\n"
        "`!rpg go <place>` — travel\n"
        "`!rpg look` — describe location\n"
        "`!rpg look at <thing>` — inspect\n"
        "`!rpg map` — world map\n"
        "`!rpg weather` / `calendar`"
    ), inline=True)

    embed.add_field(name="🧍 Character", value=(
        "`!rpg new <n> <Race> <Class>`\n"
        "`!rpg sheet` — full stats\n"
        "`!rpg inventory` — gear & items\n"
        "`!rpg equip <item>`\n"
        "`!rpg use <item>`\n"
        "`!rpg leaderboard`"
    ), inline=True)

    embed.add_field(name="🗡️ Combat", value=(
        "`!rpg hunt` — fight (1 hunt)\n"
        "`!rpg attack` — strike\n"
        "`!rpg flee` — escape attempt\n"
        "`!rpg dungeon` — enter dungeon (2 hunts)\n"
        "`!rpg duel @user` — PvP\n"
        "`!rpg roll <dice>` — d20, 2d6+3"
    ), inline=True)

    embed.add_field(name="🍺 Stone Hearth", value=(
        "`!rpg rest` — full heal (5g)\n"
        "`!rpg drink` — +3 temp HP (2g)\n"
        "`!rpg gamble` — dice (10g)\n"
        "`!rpg rumor` — gossip"
    ), inline=True)

    embed.add_field(name="🏪 Hemlock's Store", value=(
        "`!rpg shop` — browse stock\n"
        "`!rpg buy <item>`\n"
        "`!rpg sell <item>`"
    ), inline=True)

    embed.add_field(name="⛩️ Shrine", value=(
        "`!rpg pray` — daily blessing\n"
        "`!rpg offer <amount>` — XP\n"
        "`!rpg fountain` — heal spring"
    ), inline=True)

    embed.add_field(name="🌿 Herbalist's Hut", value=(
        "`!rpg brew` — list recipes\n"
        "`!rpg brew <recipe>` — brew\n"
        "`!rpg talk maren`"
    ), inline=True)

    embed.add_field(name="🏹 Watchtower", value=(
        "`!rpg scout` — monster intel\n"
        "`!rpg talk guard`"
    ), inline=True)

    embed.add_field(name="🏦 Oakhaven", value=(
        "`!rpg bank` — deposit/withdraw\n"
        "`!rpg notices` — notice board\n"
        "`!rpg quests` — quest log\n"
        "`!rpg mail` — moogle mail\n"
        "`!rpg talk <npc>`"
    ), inline=True)

    embed.add_field(name="🎣 Tricklebrook Pond", value=(
        "`!rpg go tricklebrook_pond`\n"
        "`!rpg fish` — open fishing HUD\n"
        "`!rpg fish_shop` — buy bait & poles\n"
        "*(Buy bait via Shop button in HUD)*"
    ), inline=True)

    embed.add_field(name="🏡 Housing District", value=(
        "`!rpg go housing_district`\n"
        "`!rpg home` — view/manage your home\n"
        "*(Farming, pets, & furniture)*"
    ), inline=True)

    embed.add_field(name="💬 NPCs", value=(
        "`elara` · `hemlock`\n"
        "`barkeep` · `guard`\n"
        "`hooded_figure` · `maren`"
    ), inline=True)

    embed.set_footer(text="!rpg go  with no argument lists exits from your current location")

    await msg.channel.send(embed=embed)
