PENDING_DUELS = {}

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

async def _dungeon_combat_round(ctx_obj, interaction, uid, uname, is_owner):
    from utils.ttrpg.dungeon import load_dungeon, save_dungeon, _key
    from utils.ttrpg.combat_engine import _resolve_combat
    from utils.ttrpg.loot_tables import get_loot
    from utils.ttrpg.shop import find_item
    from utils.ttrpg.progression import check_level_up, xp_to_next_level
    from utils.ttrpg.world_state import get_current_state

    state = await load_dungeon(uid)
    if not state or not state.get("active_combat"):
        await interaction.followup.send("No active combat.", ephemeral=True)
        return

    sheet = await load(uid)
    if not sheet:
        return

    combat = state["active_combat"]
    monster = combat["monster"]
    monster_key = combat.get("monster_key", "goblin")
    is_boss = combat.get("is_boss", False)
    boss_name = combat.get("boss_name")
    room_key = combat["room_key"]

    from utils.ttrpg.housing import load_housing_async
    from utils.ttrpg.pets import get_pet_passive
    _housing = await load_housing_async(str(sheet.get("user_id", "")))
    _pet_bonuses = get_pet_passive(_housing) if _housing else {}

    from utils.ttrpg.furniture import get_home_bonuses
    _home_bonuses = get_home_bonuses(_housing) if _housing else {}
    _furniture_atk = _home_bonuses.get("home_atk", 0)  # local_atk only applies at home location

    world_state = get_current_state()
    # Calendar day ATK buffs (spring_awakening +1, amber_sight +2)
    from utils.ttrpg.calendar import get_special_day as _get_special_day_dng
    _sp_dng = _get_special_day_dng()
    _cal_atk = 0
    if _sp_dng:
        _b = _sp_dng.get("buff")
        if _b in ("spring_awakening", "amber_sight"):
            _cal_atk = _sp_dng.get("buff_value", 0)
    res = _resolve_combat(sheet, monster,
                          atk_mod_global=world_state.get("atk_mod", 0) + _furniture_atk + _cal_atk,
                          def_mod_global=world_state.get("def_mod", 0),
                          pet_bonuses=_pet_bonuses)

    sheet = res["sheet"]
    monster = res["monster"]

    # Consume blessed condition after use (mirrors overworld combat behaviour)
    if "blessed" in sheet.get("conditions", []):
        sheet["conditions"].remove("blessed")

    # Accumulate for end-of-combat summary
    state.setdefault("dungeon_combat_log", []).append({
        "monster_name": monster.get("name", "enemy"),
        "monster_desc": monster.get("desc", monster.get("description", "")),
        "player_hit": res["player_hit"],
        "player_crit": res["player_crit"],
        "player_fumble": res["player_fumble"],
        "player_damage": res.get("player_damage", 0),
        "monster_hit": res["monster_hit"],
        "monster_damage": res["monster_damage"],
        "monster_defeated": res["monster_defeated"],
        "player_alive": res["player_alive"],
        "player_hp_after": sheet["hp"]["current"],
        "player_hp_max": sheet["hp"]["max"],
    })

    # Advanced class bonuses are already applied inside _resolve_combat()

    exchange_text = "\n".join(res["exchanges"])
    loot_text = ""
    level_text = ""
    xp_gain = 0
    gil_gain = 0

    if res["monster_defeated"]:
        for _cb in ["embered", "fortified"]:
            if _cb in sheet.get("conditions", []): sheet["conditions"].remove(_cb)
        # Clear combat, mark room cleared
        del state["active_combat"]
        state["rooms"][room_key]["cleared"] = True
        xp_gain = int(monster.get("xp", 25) * (2 if is_boss else 1))
        gil_gain = int(monster.get("gil", 5) * (2 if is_boss else 1))
        
        # ── Calendar Special Day Buffs ─────────────────────────────────────
        from utils.ttrpg.calendar import get_special_day
        _sp_dungeon = get_special_day()
        if _sp_dungeon:
            _buff = _sp_dungeon.get("buff")
            _bv = _sp_dungeon.get("buff_value", 0)
            if _buff == "long_fire":
                if res["player_alive"]:
                    sheet["hp"]["current"] = min(sheet["hp"]["max"], sheet["hp"]["current"] + _bv)
            elif _buff == "harvest_strength":
                gil_gain += _bv
            elif _buff == "remembrance":
                xp_gain = int(xp_gain * _bv)
            elif _buff == "winter_resolve":
                if not sheet.get("_winter_resolve_applied"):
                    sheet["hp"]["max"] += _bv
                    sheet["hp"]["current"] += _bv
                    sheet["_winter_resolve_applied"] = True
            elif _buff == "new_year_resolve":
                if not sheet.get("_new_year_applied"):
                    sheet["hp"]["current"] = sheet["hp"]["max"]
                    sheet["_new_year_applied"] = True
                    
        # Advanced class bonuses
        _adv = sheet.get("advanced_class", "")
        if _adv:
            from utils.ttrpg.class_advancement import ADVANCED_CLASSES
            for _opts in ADVANCED_CLASSES.values():
                if _adv in _opts:
                    _b = _opts[_adv].get("bonuses", {})
                    xp_gain  = int(xp_gain  * (1.0 + _b.get("xp_bonus_pct",  0.0)))
                    gil_gain = int(gil_gain * (1.0 + _b.get("gil_bonus_pct", 0.0)))
                    _heal = _b.get("heal_on_combat_end", 0)
                    if _heal > 0 and sheet["hp"]["current"] > 0:
                        sheet["hp"]["current"] = min(sheet["hp"]["max"], sheet["hp"]["current"] + _heal)
                    break

        # Experience Tonic bonus (+25% XP, consumed on use)
        if "xp_boosted" in sheet.get("conditions", []):
            xp_gain = int(xp_gain * 1.25)
            sheet["conditions"].remove("xp_boosted")
        
        # Pet Gil Bonus (Oakhaven Cat)
        from utils.ttrpg.housing import load_housing_async
        from utils.ttrpg.pets import get_pet_passive
        housing_rewards = await load_housing_async(uid)
        pet_rewards = get_pet_passive(housing_rewards) if housing_rewards else {}
        if pet_rewards.get("gil_bonus_pct"):
            gil_gain = int(gil_gain * (1.0 + pet_rewards["gil_bonus_pct"]))

        sheet["xp"] = sheet.get("xp", 0) + xp_gain
        sheet["gil"] = sheet.get("gil", 0) + gil_gain
        state["xp_gained"] = state.get("xp_gained", 0) + xp_gain
        state["gil_gained"] = state.get("gil_gained", 0) + gil_gain

        # Loot — split gear and consumable pools
        from utils.ttrpg.loot_tables import get_gear_loot, get_consumable_loot
        level = sheet.get("level", 1)
        if is_boss:
            _boss_tier_map = {1: "easy", 2: "easy", 3: "medium", 4: "medium",
                              5: "hard", 6: "hard", 7: "hard", 8: "deadly", 9: "boss",
                              10: "boss", 11: "boss", 12: "boss", 13: "boss",
                              14: "boss", 15: "boss"}
            tier = _boss_tier_map.get(level, "boss")
        else:
            tier = _get_dungeon_loot_tier(level, False)
        if is_boss:
            drops = []
            # First gear drop: guaranteed
            gear = get_gear_loot(tier)
            attempts = 0
            while not gear and attempts < 5:
                gear = get_gear_loot(tier)
                attempts += 1
            if gear:
                sheet.setdefault("inventory", []).append(gear)
                item = find_item(gear)
                drops.append(f"⚔️ {item['name'] if item else gear}")
                state.setdefault("loot_gained", []).append(gear)
            # Second gear drop: 40% chance
            if secrets.randbelow(10) < 4:
                gear2 = get_gear_loot(tier)
                attempts = 0
                while not gear2 and attempts < 5:
                    gear2 = get_gear_loot(tier)
                    attempts += 1
                if gear2:
                    sheet.setdefault("inventory", []).append(gear2)
                    item = find_item(gear2)
                    drops.append(f"⚔️ {item['name'] if item else gear2}")
                    state.setdefault("loot_gained", []).append(gear2)
            # Consumable drop: always
            cons = get_consumable_loot(tier)
            if cons:
                sheet.setdefault("inventory", []).append(cons)
                item = find_item(cons)
                drops.append(f"🧪 {item['name'] if item else cons}")
                state.setdefault("loot_gained", []).append(cons)
            if drops:
                loot_text = f"\n🎁 **Boss drops:**\n" + "\n".join(drops)
            else:
                # Guaranteed fallback: gil payout if loot table still produces nothing
                bonus_gil = 25
                sheet["gil"] = sheet.get("gil", 0) + bonus_gil
                state["gil_gained"] = state.get("gil_gained", 0) + bonus_gil
                loot_text = f"\n💰 No material loot, but the corpse yields **{bonus_gil} gil**."
        else:
            # Normal dungeon kill: 40% gear + always consumable
            drop_lines = []
            if secrets.randbelow(10) < 4:
                gear = get_gear_loot(tier)
                if gear:
                    sheet.setdefault("inventory", []).append(gear)
                    item = find_item(gear)
                    drop_lines.append(f"⚔️ {item['name'] if item else gear}")
                    state.setdefault("loot_gained", []).append(gear)
            cons = get_consumable_loot(tier)
            if cons:
                sheet.setdefault("inventory", []).append(cons)
                item = find_item(cons)
                drop_lines.append(f"🧪 {item['name'] if item else cons}")
                state.setdefault("loot_gained", []).append(cons)
            if drop_lines:
                loot_text = f"\n🎁 " + ", ".join(drop_lines)

        leveled, new_level = check_level_up(sheet)
        if leveled:
            level_text = f"\n\n🎉 **Level Up! Now Lv.{new_level}!**"
            await _log_world_event(f"**{sheet['character_name']}** reached Level {new_level} deep in a dungeon.")
            lv_embed = discord.Embed(
                title=f"⬆️ {sheet['character_name']} — Level {new_level}",
                description=_level_up_flavor(sheet, new_level),
                color=0xffcc00
            )
            lv_embed.set_footer(text=f"{sheet.get('advanced_class') or sheet.get('class', '?')} · Dungeon Run")
            await _broadcast_world_event(ctx_obj, lv_embed)

        xp_next = xp_to_next_level(sheet["level"])
        exchange_text += f"\n\n+{xp_gain} XP ({sheet['xp']}/{xp_next}) · +{gil_gain} Gil{loot_text}{level_text}"

        await save(sheet)
        await save_dungeon(uid, state)

        if is_boss:
            # Boss dead — fire summary narration then finalize
            combat_log = state.get("dungeon_combat_log", [])
            state["dungeon_combat_log"] = []
            if combat_log:
                asyncio.ensure_future(
                    _narrate_combat_summary(
                        ctx_obj, interaction.channel, uid, uname, sheet,
                        combat_log, player_won=True
                    )
                )
            await _dungeon_complete(ctx_obj, interaction, uid, uname, is_owner,
                                    state, sheet, leveled, new_level)
        else:
            embed = discord.Embed(title="⚔️ Victory", description=exchange_text, color=0x2D5A27)
            view = DungeonView(ctx_obj, uid, uname, is_owner, state)
            await interaction.followup.send(embed=embed, view=view)

    elif not res["player_alive"]:
        for _cb in ["embered", "fortified"]:
            if _cb in sheet.get("conditions", []): sheet["conditions"].remove(_cb)
        # Player defeated in dungeon
        del state["active_combat"]
        sheet["hp"]["current"] = 1
        sheet["location"] = "shrine"
        sheet["deaths"] = sheet.get("deaths", 0) + 1
        xp_loss = int(sheet["xp"] * 0.10)
        gil_loss = int(sheet["gil"] * 0.05)
        sheet["xp"] = max(0, sheet["xp"] - xp_loss)
        sheet["gil"] = max(0, sheet["gil"] - gil_loss)
        await save(sheet)
        from utils.ttrpg.dungeon import clear_dungeon
        await clear_dungeon(uid)
        embed = discord.Embed(
            title="💀 Defeated",
            description=f"{exchange_text}\n\n*You collapsed in the dark. Someone dragged you back to the Shrine.*\n-{xp_loss} XP · -{gil_loss} Gil",
            color=0x8B0000
        )
        view = _make_status_view(ctx_obj, None, uid, uname, is_owner)
        await interaction.followup.send(embed=embed, view=view)

        # Broadcast death
        m_name = monster.get("name", monster_key.replace("_", " ").title())
        await _log_world_event(f"💀 **{sheet['character_name']}** fell to a **{m_name}** in the {state.get('theme_name', 'dungeon')}.")
        death_embed = discord.Embed(
            title=f"💀 {sheet['character_name']} fell in the {state.get('theme_name', 'dungeon')}",
            description=f"*The darkness of the {state.get('theme_name', 'ruins')} claimed them. They were struck down by a **{m_name}**.*",
            color=0x8B0000
        )
        death_embed.set_footer(text=f"Level {sheet.get('level', 1)} {sheet.get('class', '?')}")
        await _broadcast_world_event(ctx_obj, death_embed)

        # End-of-dungeon-combat summary on player death
        combat_log = state.get("dungeon_combat_log", [])
        state["dungeon_combat_log"] = []
        if combat_log:
            asyncio.ensure_future(
                _narrate_combat_summary(
                    ctx_obj, interaction.channel, uid, uname, sheet,
                    combat_log, player_won=False
                )
            )

    else:
        # Combat continues — update monster HP in state
        combat["monster"] = monster
        state["active_combat"] = combat
        await save(sheet)
        await save_dungeon(uid, state)

        name_used = boss_name if (is_boss and boss_name) else monster.get("name", "Enemy")
        embed = discord.Embed(
            title=f"⚔️ {name_used}",
            description=exchange_text,
            color=0xFF4500
        )
        view = DungeonCombatView(ctx_obj, uid, uname, is_owner, name_used)
        await interaction.followup.send(embed=embed, view=view)


async def _handle_dungeon(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.dungeon import generate_dungeon, save_dungeon, load_dungeon, DUNGEON_THEMES

    # Resume existing run
    existing = await load_dungeon(uid)
    if existing and existing.get("active"):
        await msg.channel.send(embed=discord.Embed(
            description="*You're already in there. Picking up where you left off...*",
            color=0x7a6a9a))
        await _send_dungeon_room(ctx, msg.channel, uid, uname, is_owner, existing)
        return

    sheet = await load(uid)
    if not sheet: return

    inv = sheet.get("inventory", [])
    has_lightstone = "lightstone" in inv
    has_torch      = "torch" in inv

    if not has_lightstone and not has_torch:
        return await msg.channel.send(embed=discord.Embed(
            title="⬛ Total Darkness",
            description=(
                "*The entrance yawns open. You can't see your hand in front of your face.*\n\n"
                "You need a light source:\n"
                "• **Torch** (2g) — buy from Hemlock. Single use.\n"
                "• **Lightstone** — rare drop from wisps. Permanent."
            ),
            color=0x4a4a6a
        ))

    # Consume torch on entry (lightstone is permanent)
    if not has_lightstone and has_torch:
        sheet["inventory"].remove("torch")
        torch_line = "\n*Your torch gutters. You have one run before it burns out.*"
    else:
        torch_line = "\n*The lightstone pulses softly. The dark gives way.*"

    ENTRY_HUNTS = 2
    sheet = check_and_reset_hunts(sheet)
    if hunts_remaining(sheet) < ENTRY_HUNTS:
        return await msg.channel.send(embed=discord.Embed(
            description=(f"Entering costs **{ENTRY_HUNTS} hunts**. "
                         f"You have {hunts_remaining(sheet)}/{get_max_hunts(sheet)}."),
            color=0xcc4444))

    sheet["hunts_today"] = sheet.get("hunts_today", 0) + ENTRY_HUNTS
    await save(sheet)

    loc = sheet.get("location", "whisperwood_edge")
    from utils.ttrpg.dungeon import LOCATION_DIFFICULTY_BONUS
    loc_diff_bonus = LOCATION_DIFFICULTY_BONUS.get(loc, 0)
    difficulty = max(1, min(5, (sheet["level"] - 1) // 3 + 1 + loc_diff_bonus))
    dungeon = generate_dungeon(difficulty, player_level=sheet["level"], location=loc)
    await save_dungeon(uid, dungeon)

    theme_key  = dungeon.get("theme_key", "undead")
    theme_data = DUNGEON_THEMES.get(theme_key, {})
    t_emoji    = theme_data.get("emoji", "🏚️")
    t_name     = theme_data.get("name", "Unknown Depths")
    t_flavor   = theme_data.get("flavor", "Something waits in the dark.")

    await msg.channel.send(embed=discord.Embed(
        title=f"{t_emoji} {t_name}",
        description=(
            f"*{t_flavor}*\n\n"
            f"*Difficulty: {'🟥' * difficulty}{'⬜' * (5 - difficulty)}  ·  "
            f"Cost: {ENTRY_HUNTS} hunts*"
            f"{torch_line}"
        ),
        color=0x7a6a9a,
    ))
    await asyncio.sleep(2)
    await _send_dungeon_room(ctx, msg.channel, uid, uname, is_owner, dungeon)


async def _handle_hunts(ctx, msg, send, rest, uid, uname, is_owner):
    sheet = await load(uid)
    if not sheet: return
    view = _make_hunt_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=discord.Embed(
        description=f"**{sheet['character_name']}** has {hunts_remaining(sheet)} hunts remaining today. Reset is at midnight server time.",
        color=0x888888
    ), view=view)


async def _handle_hunt(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.world import LOCATION_DATA
    from utils.ttrpg.monster_registry import get as get_monster
    from utils.ttrpg.calendar import get_weather
    
    sheet = await load(uid)
    if not sheet: return

    # Weather Check (e.g. Blizzard level gate)
    weather = get_weather()
    effect = weather.get("effect")
    if effect and effect.get("type") == "level_gate":
        gate_val = effect["value"]
        loc = sheet.get("location", "oakhaven")
        gate_locs = effect.get("locations", [loc])
        if loc in gate_locs and sheet.get("level", 1) < gate_val:
            view = _make_map_view(ctx, msg, uid, uname, is_owner, loc)
            return await msg.channel.send(embed=discord.Embed(
                description=f"🌨️ **Blizzard Warning:** {effect['desc']}\n*You are currently level {sheet.get('level', 1)} and cannot pass.*",
                color=0x8aaac8
            ), view=view)
    
    loc = sheet.get("location", "oakhaven")
    ld = LOCATION_DATA.get(loc, {})
    if not ld.get("hunting"):
        view = _make_map_view(ctx, msg, uid, uname, is_owner, loc)
        return await msg.channel.send(embed=discord.Embed(description=f"You can't hunt in **{ld.get('name', loc)}**.\nTravel somewhere wild first.", color=0xcc4444), view=view)
        
    # Engage tracking & Resume Logic
    chan_id = str(msg.channel.id)
    s = await load_session(chan_id)
    if not s:
        s = {
            "channel_id": chan_id,
            "active": True,
            "monsters": [],
            "combat_active": False,
            "created_at": time.time(),
        }
    
    # Are we already fighting something?
    monsters = s.get("monsters", [])
    my_fights = []
    for m in monsters:
        if isinstance(m, dict) and m.get("aggro_uid") == uid:
            my_fights.append(m)

    if my_fights:
        if sheet["hp"]["current"] <= 0:
            view = _make_status_view(ctx, msg, uid, uname, is_owner)
            return await msg.channel.send(embed=discord.Embed(description=f"You are far too weak to resume your hunt right now. Go rest.", color=0xcc4444), view=view)
            
        m_data = my_fights[0]
        m_name = m_data.get("name", "Unknown Monster")
        m_key = m_data.get("key", "monster")
        
        # Resumption uses global imports now
        tier_icon = TIER_ICONS.get(m_data.get("tier", "medium"), "🟠")
        hp_obj = m_data.get("hp", {"current": 0, "max": 0})
        
        embed = discord.Embed(
            title=f"⚔️ Already in combat: {m_name} {tier_icon}",
            description=f"Picking up where you left off...\n*{m_data.get('desc', 'A dangerous creature.')}*",
            color=0xcc6622
        )
        # Show current health in resumption (monospaced bar for embeds)
        filled = int((hp_obj['current'] / max(hp_obj['max'], 1)) * 10)
        hb = "█" * filled + "░" * (10 - filled)
        embed.add_field(name="❤️ Monster HP", value=f"`{hb}` {hp_obj['current']}/{hp_obj['max']}", inline=False)
        embed.add_field(name="🗡️ ATK", value=str(m_data.get('attack', 0)), inline=True)
        embed.add_field(name="🛡️ DEF", value=str(m_data.get('defense', 0)), inline=True)
        
        embed.set_footer(text=f"Your HP: {sheet['hp']['current']}/{sheet['hp']['max']}")
        combat_view = RPGCombatView(ctx, msg, uid, uname, is_owner, m_key)
        return await msg.channel.send(embed=embed, view=combat_view)
        
    # Standard hunt stamina & HP flow
    sheet = check_and_reset_hunts(sheet)
    await save(sheet) # Avoid race condition by persisting reset before awaiting UI
    if hunts_remaining(sheet) <= 0:
        view = _make_status_view(ctx, msg, uid, uname, is_owner)
        return await msg.channel.send(embed=discord.Embed(description=f"You have exhausted your stamina for the day. (0/{get_max_hunts(sheet)} hunts remaining)", color=0xcc4444), view=view)
        
    if sheet["hp"]["current"] <= 0:
        view = _make_status_view(ctx, msg, uid, uname, is_owner)
        return await msg.channel.send(embed=discord.Embed(description=f"You are far too weak to hunt right now. Go rest.", color=0xcc4444), view=view)
    
    # Quest Task Tracking: Hunt Location
    active_id = sheet.get("active_quest")
    if active_id:
        from utils.ttrpg.quest_registry import get_quest
        q = get_quest(active_id)
        if q:
            task_id = f"hunt_{loc}"
            if task_id in q["tasks"]:
                prog = sheet.setdefault("quest_progress", {}).setdefault(active_id, [])
                if task_id not in prog:
                    prog.append(task_id)
                    await save(sheet)
                # Check if this hunt task completed the quest
                if all(t in prog for t in q["tasks"]):
                    # Complete — apply rewards inline
                    xp_reward  = q["rewards"].get("xp", 0)
                    gil_reward = q["rewards"].get("gil", 0)
                    sheet["xp"]  = sheet.get("xp",  0) + xp_reward
                    sheet["gil"] = sheet.get("gil", 0) + gil_reward
                    if "item" in q["rewards"]:
                        sheet.setdefault("inventory", []).append(q["rewards"]["item"])
                    if "recipe" in q["rewards"]:
                        rk = q["rewards"]["recipe"]
                        if rk not in sheet.setdefault("recipes", []):
                            sheet.setdefault("recipes", []).append(rk)
                    sheet["active_quest"] = None
                    sheet.setdefault("completed_quests", []).append(active_id)
                    await save(sheet)
                    leveled, new_level = check_level_up(sheet)
                    if leveled:
                        await save(sheet)
                    from utils.ttrpg.progression import xp_to_next_level
                    xp_next = xp_to_next_level(sheet["level"])
                    lines = [
                        f"**{q['name']}** — complete.",
                        f"+{xp_reward} XP ({sheet['xp']}/{xp_next})  ·  +{gil_reward} Gil",
                    ]
                    if "item" in q["rewards"]:
                        lines.append(f"🎁 Received: **{q['rewards']['item'].replace('_',' ').title()}**")
                    if leveled:
                        lines.append(f"🎉 **Level Up! Now Lv.{new_level}!**")
                    await msg.channel.send(embed=discord.Embed(
                        title="✅ Quest Complete",
                        description="\n".join(lines),
                        color=0x2ecc71
                    ))
                    await _log_world_event(
                        f"✅ **{sheet['character_name']}** completed '**{q['name']}**'."
                    )
    
    # Roll for special forest event before monster spawn
    from utils.ttrpg.encounter_tables import roll_for_event, random_event
    from utils.ttrpg.forest_events import resolve_event

    if roll_for_event(loc):
        event_key = random_event(loc)
        result = resolve_event(event_key, sheet)
        # Events are FREE — they don't consume a daily hunt.
        # The player still gets their full hunts for combat XP.
        await _apply_and_narrate_event(ctx, msg, send, sheet, result, uname)
        return  # event resolved, hunt NOT consumed

    # Pay hunt cost BEFORE spawn (crash-safe: hunt is consumed even if spawn fails)
    sheet["hunts_today"] = sheet.get("hunts_today", 0) + 1

    # BUG-C2 fix: consume "rested" condition after first hunt of the day
    if "rested" in sheet.get("conditions", []):
        sheet["conditions"].remove("rested")

    await save(sheet)

    # Spawn monsters based on density
    density = ld.get("density", 1)
    dist_mult = ld.get("dist_mult", 1.0)
    
    num_to_spawn = 1
    if density > 1:
        spawn_roll = secrets.randbelow(100) / 100.0
        if density == 2 and spawn_roll < 0.25:
            num_to_spawn = 2
        elif density == 3:
            if spawn_roll < 0.15: num_to_spawn = 3
            elif spawn_roll < 0.40: num_to_spawn = 2
            
    s.setdefault("channel_id", chan_id)
    spawned_names = []
    
    # Quest-aware encounter nudge
    active_quest = sheet.get("active_quest", "")
    quest_location_override = None
    if active_quest == "maren_herbs" and loc == "trade_road":
        quest_location_override = "trade_road_maren"
    elif active_quest == "deep_hunt" and loc == "whisperwood_deep":
        quest_location_override = "whisperwood_deep_hunt"
    elif active_quest == "aeridor_remnant" and loc == "aeridor_ruins":
        quest_location_override = "aeridor_ruins_remnant"
    elif active_quest == "shadow_incursion" and loc == "whisperwood_deep":
        quest_location_override = "whisperwood_deep_shadow"

    for _ in range(num_to_spawn):
        m_key = random_encounter(quest_location_override or loc, sheet.get("level", 1))
        m_data = get_monster(m_key)
        if not m_data: continue
        
        monster_instance = m_data.copy()
        monster_instance["key"] = m_key
        # Apply distance difficulty scaling
        scaled_hp = int(monster_instance["hp"] * dist_mult)
        monster_instance["hp"] = {"current": scaled_hp, "max": scaled_hp}
        monster_instance["attack"] = int(monster_instance.get("attack", 0) * dist_mult)
        monster_instance["id"] = f"{m_key}_{_uuid.uuid4().hex[:4]}"
        monster_instance["aggro_uid"] = uid  # personal instance
        
        s["monsters"].append(monster_instance)
        spawned_names.append(f"**{monster_instance['name']}**")

    if not spawned_names:
        return await msg.channel.send(embed=discord.Embed(description="You searched the area but found nothing this time.", color=0x888888))
        
    s["combat_active"] = True
    await save_session(s)
    
    
    rec = ld.get("recommended_level", 1)
    warn = f"⚠️ *{sheet['character_name']} is underleveled for this area.*\n" if sheet["level"] < rec - 1 else ""
    
    primary_monster = s["monsters"][-len(spawned_names)]
    monster_desc = primary_monster.get("desc", primary_monster.get("description", "A dangerous creature."))
    tier_icon = TIER_ICONS.get(primary_monster.get("tier", "medium"), "🟠")
    m_key = primary_monster.get("key", "monster")
    
    if num_to_spawn > 1:
        title = f"⚔️ Encounter: SWARM! {tier_icon}"
        description = f"{warn}You are surrounded by a group: {', '.join(spawned_names)}\n\n*{monster_desc}*"
    else:
        title = f"⚔️ Encounter: {primary_monster.get('name', 'Enemy')} {tier_icon}"
        description = f"{warn}*{monster_desc}*"

    embed = discord.Embed(
        title=title,
        description=description,
        color=0xFF4500 if num_to_spawn == 1 else 0xCC3300
    )
    
    # Show stats of the primary (first) monster
    embed.add_field(name="❤️ HP", value=str(primary_monster['hp']['max']), inline=True)
    embed.add_field(name="🗡️ ATK", value=str(primary_monster.get('attack', 0)), inline=True)
    embed.add_field(name="🛡️ DEF", value=str(primary_monster.get('defense', 0)), inline=True)
    
    embed.set_footer(text=f"Use !rpg attack  ·  1 hunt consumed")
    combat_view = RPGCombatView(ctx, msg, uid, uname, is_owner, m_key)
    await msg.channel.send(embed=embed, view=combat_view)


async def _handle_attack(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.combat_engine import _resolve_combat
    from utils.ttrpg.rpg_prompt_builder import build_combat_prompt
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    from utils.ttrpg.loot_tables import get_loot
    from utils.ttrpg.calendar import get_weather
    
    sheet = await load(uid)
    if not sheet: return
    loc = sheet.get("location", "oakhaven")
    if sheet["hp"]["current"] <= 0:
        view = _make_status_view(ctx, msg, uid, uname, is_owner)
        return await msg.channel.send(embed=discord.Embed(description="You are incapacitated.", color=0xcc4444), view=view)
        
    s = await load_session(str(msg.channel.id))
    if not s or not s.get("combat_active") or not s.get("monsters"):
        view = _make_hunt_status_view(ctx, msg, uid, uname, is_owner)
        return await msg.channel.send(embed=discord.Embed(description="No active combat. `!rpg hunt` to find something.", color=0x888888), view=view)
        
    target_key = rest.strip().lower()
    
    monster = None
    monster_idx = -1
    for i, m in enumerate(s["monsters"]):
        # Prioritize engaging enemies aggro'd onto THIS player
        m_key = m.get("key", "")
        if m.get("aggro_uid") == uid or (target_key and target_key in m_key):
            monster = m
            monster_idx = i
            break
            
    if not monster:
        return await msg.channel.send(embed=discord.Embed(description="Cannot identify monster.", color=0xcc4444))
        
    from utils.ttrpg.housing import load_housing_async
    from utils.ttrpg.pets import get_pet_passive
    _housing = await load_housing_async(uid)
    _pet_bonuses = get_pet_passive(_housing) if _housing else {}

    # Execute deterministic combat math loop with world state modifiers
    state = get_current_state()
    from utils.ttrpg.furniture import get_home_bonuses
    home_bonuses = get_home_bonuses(_housing) if _housing else {}
    # Calendar day ATK buffs (spring_awakening +1, amber_sight +2)
    from utils.ttrpg.calendar import get_special_day as _get_special_day_ow
    _sp_ow = _get_special_day_ow()
    _cal_atk_ow = 0
    if _sp_ow:
        _b_ow = _sp_ow.get("buff")
        if _b_ow in ("spring_awakening", "amber_sight"):
            _cal_atk_ow = _sp_ow.get("buff_value", 0)
    if sheet.get("location") == "housing_district":
        atk_mod_global = state.get("atk_mod", 0) + home_bonuses.get("home_atk", 0) + home_bonuses.get("local_atk", 0) + _cal_atk_ow
    else:
        atk_mod_global = state.get("atk_mod", 0) + home_bonuses.get("home_atk", 0) + _cal_atk_ow

    res = _resolve_combat(
        sheet, monster, 
        atk_mod_global=atk_mod_global, 
        def_mod_global=state.get("def_mod", 0),
        pet_bonuses=_pet_bonuses
    )
    
    sheet = res["sheet"]
    monster = res["monster"]

    # After combat resolves, consume the blessing
    if "blessed" in sheet.get("conditions", []):
        sheet["conditions"].remove("blessed")
    
    # Handle state cleanup
    if res["monster_defeated"] or not res["player_alive"]:
        for _cb in ["embered", "fortified"]:
            if _cb in sheet.get("conditions", []): sheet["conditions"].remove(_cb)
        s["monsters"].pop(monster_idx)
        if not s["monsters"]: s["combat_active"] = False
    else:
        s["monsters"][monster_idx] = monster

    # Accumulate combat log for end-of-combat summary narration
    s.setdefault("combat_log", []).append({
        "monster_name": monster.get("name", "enemy"),
        "monster_desc": monster.get("desc", monster.get("description", "")),
        "player_hit": res["player_hit"],
        "player_crit": res["player_crit"],
        "player_fumble": res["player_fumble"],
        "player_damage": res.get("player_damage", 0),
        "monster_hit": res["monster_hit"],
        "monster_damage": res["monster_damage"],
        "monster_defeated": res["monster_defeated"],
        "player_alive": res["player_alive"],
        "player_hp_after": sheet["hp"]["current"],
        "player_hp_max": sheet["hp"]["max"],
    })
        
    await save_session(s)
    
    xp_gain, gil_gain, level_up_msg, loot_msg, streak_msg = 0, 0, "", "", ""
    if res["monster_defeated"]:
        xp_gain = int(monster.get("xp", 10) * state.get("xp_mult", 1.0))
        gil_gain = int(monster.get("gil", 5) * state.get("gil_mult", 1.0))
        # Advanced class XP/Gil percentage bonuses
        _adv = sheet.get("advanced_class", "")
        if _adv:
            from utils.ttrpg.class_advancement import ADVANCED_CLASSES
            for _opts in ADVANCED_CLASSES.values():
                if _adv in _opts:
                    _b = _opts[_adv].get("bonuses", {})
                    xp_gain  = int(xp_gain  * (1.0 + _b.get("xp_bonus_pct",  0.0)))
                    gil_gain = int(gil_gain * (1.0 + _b.get("gil_bonus_pct", 0.0)))
                    _heal = _b.get("heal_on_combat_end", 0)
                    if _heal > 0 and sheet["hp"]["current"] > 0:
                        sheet["hp"]["current"] = min(sheet["hp"]["max"], sheet["hp"]["current"] + _heal)
                    break
        # Weather bonus effects (e.g. clear autumn +5 XP, winter frost +3 Gil)
        weather_effect = get_weather().get("effect") or {}
        if weather_effect.get("type") == "xp_bonus":
            xp_gain += weather_effect.get("value", 0)
        if weather_effect.get("type") == "gil_bonus":
            gil_gain += weather_effect.get("value", 0)

        # ── Calendar Special Day Buffs ─────────────────────────────────────
        from utils.ttrpg.calendar import get_special_day
        _special = get_special_day()
        if _special:
            _buff = _special.get("buff")
            _bv = _special.get("buff_value", 0)
            if _buff == "long_fire":
                # Beltane: +3 HP after every successful hunt
                if res["player_alive"]:
                    sheet["hp"]["current"] = min(sheet["hp"]["max"], sheet["hp"]["current"] + _bv)
                    streak_msg += f"  🔥 Long Fire: +{_bv} HP"
            elif _buff == "harvest_strength":
                # First Day of Autumn: +1 Gil per kill
                gil_gain += _bv
            elif _buff == "remembrance":
                # The Remembrance: +50% XP
                xp_gain = int(xp_gain * _bv)
            elif _buff == "amber_sight":
                # Amber Night: +2 ATK — wired into atk_mod_global above
                pass
            elif _buff == "winter_resolve":
                # First Day of Winter: +5 max HP today (applied once per combat)
                if not sheet.get("_winter_resolve_applied"):
                    sheet["hp"]["max"] += _bv
                    sheet["hp"]["current"] += _bv
                    sheet["_winter_resolve_applied"] = True
            elif _buff == "new_year_resolve":
                # The Turning: full HP restore once today
                if not sheet.get("_new_year_applied"):
                    sheet["hp"]["current"] = sheet["hp"]["max"]
                    sheet["_new_year_applied"] = True
                    streak_msg += "  🎆 The Turning: fully restored"

        # Experience Tonic bonus (+25% XP, consumed on use)
        if "xp_boosted" in sheet.get("conditions", []):
            xp_gain = int(xp_gain * 1.25)
            sheet["conditions"].remove("xp_boosted")
        
        # Pet Gil Bonus (Oakhaven Cat)
        from utils.ttrpg.housing import load_housing_async
        from utils.ttrpg.pets import get_pet_passive
        housing_rewards = await load_housing_async(uid)
        pet_rewards = get_pet_passive(housing_rewards) if housing_rewards else {}
        if pet_rewards.get("gil_bonus_pct"):
            gil_gain = int(gil_gain * (1.0 + pet_rewards["gil_bonus_pct"]))
        
        # Streak mechanics
        streak = sheet.get("hunt_streak", 0) + 1
        sheet["hunt_streak"] = streak
        if streak > 1:
            streak_bonus_gil = min(streak, 5) * 2
            gil_gain += streak_bonus_gil
            streak_msg = f"  🔥 Streak: {streak} (+{streak_bonus_gil}g)"
            
        # Loot mechanics — dual roll: gear + consumable
        from utils.ttrpg.loot_tables import get_gear_loot, get_consumable_loot
        loot_lines = []

        # Gear roll
        gear_drop = get_gear_loot(monster.get("tier", "medium"))
        if gear_drop:
            sheet.setdefault("inventory", []).append(gear_drop)
            from utils.ttrpg.shop import find_item as _find_loot
            gear_info = _find_loot(gear_drop)
            gear_display = gear_info["name"] if gear_info else gear_drop
            loot_lines.append(f"⚔️ {gear_display}")

        # Consumable roll
        consumable_drop = get_consumable_loot(monster.get("tier", "medium"))
        if consumable_drop:
            sheet.setdefault("inventory", []).append(consumable_drop)
            from utils.ttrpg.shop import find_item as _find_cons
            cons_info = _find_cons(consumable_drop)
            cons_display = cons_info["name"] if cons_info else consumable_drop
            loot_lines.append(f"🧪 {cons_display}")
            # Check recipe discovery (triggers on crafting ingredients)
            from utils.ttrpg.alchemy import check_and_discover_recipes
            new_recipes = check_and_discover_recipes(sheet, consumable_drop)
            for rk in new_recipes:
                from utils.ttrpg.alchemy import get_recipe
                r = get_recipe(rk)
                if r:
                    loot_lines.append(f"📖 **Recipe learned:** {r['name']}! Brew at the Herbalist's Hut.")

        if loot_lines:
            loot_msg = "\n🎁 **Looted:**\n" + "\n".join(loot_lines)
            
        sheet["xp"] += xp_gain
        sheet["gil"] += gil_gain
        
    # Emit Math block
    # Advanced class passive bonuses
    adv_mods = apply_advanced_class_to_combat(
        sheet, res.get("player_damage", 0), res["player_hit"],
        res["player_crit"], res.get("monster_damage", 0),
        monster, res["monster_defeated"],
        location=sheet.get("location", "")
    )
    if adv_mods["heal_amount"] and res["player_alive"]:
        sheet["hp"]["current"] = min(sheet["hp"]["max"], sheet["hp"]["current"] + adv_mods["heal_amount"])
    if adv_mods["extra_log"]:
        m_block = "\n".join(res["exchanges"] + adv_mods["extra_log"])
    else:
        m_block = "\n".join(res["exchanges"])

    if res["monster_defeated"]:
        # Quest Task Tracking: Kill
        active_id = sheet.get("active_quest")
        if active_id:
            from utils.ttrpg.quest_registry import get_quest
            q = get_quest(active_id)
            if q:
                monster_id = monster.get("key")
                task_id = f"kill_{monster_id}"
                if task_id in q["tasks"]:
                    prog = sheet.setdefault("quest_progress", {}).setdefault(active_id, [])
                    if task_id not in prog:
                        prog.append(task_id)
                        if all(t in prog for t in q["tasks"]):
                            xp_reward  = q["rewards"].get("xp", 0)
                            gil_reward = q["rewards"].get("gil", 0)
                            sheet["xp"]  = sheet.get("xp",  0) + xp_reward
                            sheet["gil"] = sheet.get("gil", 0) + gil_reward
                            if "item" in q["rewards"]:
                                sheet.setdefault("inventory", []).append(q["rewards"]["item"])
                            if "recipe" in q["rewards"]:
                                rk = q["rewards"]["recipe"]
                                if rk not in sheet.setdefault("recipes", []):
                                    sheet.setdefault("recipes", []).append(rk)
                            sheet["active_quest"] = None
                            sheet.setdefault("completed_quests", []).append(active_id)
                            m_block += (
                                f"\n\n✅ **Quest Complete: {q['name']}**"
                                f"\n+{xp_reward} XP · +{gil_reward} Gil"
                            )
                            await _log_world_event(f"✅ **{sheet['character_name']}** completed '**{q['name']}**'.")
                            quest_embed = discord.Embed(
                                title=f"✅ Quest Complete — {q['name']}",
                                description=f"*{sheet['character_name']} closed the book on another chapter.*",
                                color=0x2ecc71
                            )
                            quest_embed.set_footer(text=f"+{xp_reward} XP · +{gil_reward} Gil")
                            await _broadcast_world_event(ctx, quest_embed)
                        else:
                            await save(sheet)
    leveled, n_lvl = check_level_up(sheet)
    if leveled:
        level_up_msg = f"\n🎉 **LEVEL UP! {sheet['character_name']} grew to level {n_lvl}!**"
        await _log_world_event(f"**{sheet['character_name']}** reached Level {n_lvl}. Oakhaven noted it cautiously.")
        lv_embed = discord.Embed(
            title=f"⬆️ {sheet['character_name']} — Level {n_lvl}",
            description=_level_up_flavor(sheet, n_lvl),
            color=0xffcc00
        )
        lv_embed.set_footer(text=f"{sheet.get('advanced_class') or sheet.get('class', '?')} · {sheet.get('location','').replace('_',' ').title()}")
        await _broadcast_world_event(ctx, lv_embed)
        
        # Wisp-specific drop: lightstone
        WISP_KEYS = {"wisp", "ice_wisp", "moldwynd", "crew_dust"}
        if monster.get("key") in WISP_KEYS and "lightstone" not in sheet.get("inventory", []):
            if secrets.randbelow(3) == 0:  # 33%
                sheet.setdefault("inventory", []).append("lightstone")
                m_block += "\n💡 **Lightstone** — the wisp's core falls. Still glowing."

    await save(sheet)
    


    if res["monster_defeated"]:
        nx = xp_to_next_level(sheet["level"])
        m_block += f"\n+{xp_gain} XP ({sheet['xp']}/{nx})  +{gil_gain} Gil{streak_msg}{loot_msg}{level_up_msg}"
    elif not res["player_alive"]:
        sheet["hunt_streak"] = 0
        xp_loss = int(sheet["xp"] * 0.10)
        gil_loss = int(sheet["gil"] * 0.05)
        sheet["xp"] = max(0, sheet["xp"] - xp_loss)
        sheet["gil"] = max(0, sheet["gil"] - gil_loss)
        sheet["hp"]["current"] = 1
        sheet["location"] = "shrine"
        sheet["deaths"] = sheet.get("deaths", 0) + 1
        m_block += f"\n\n🚨 **You blacked out.** Townspeople dragged you back to the Shrine of the Silent Ones in Oakhaven. You dropped {xp_loss} XP and {gil_loss} Gil in the dirt."
        await _log_world_event(f"**{sheet['character_name']}** was found at the Shrine threshold. Hemlock is taking bets.")
        death_embed = discord.Embed(
            title=f"💀 {sheet['character_name']} fell",
            description=f"*{monster.get('name', 'Something')} left them at the Shrine threshold. {xp_loss} XP and {gil_loss} Gil in the dirt.*",
            color=0x8B0000
        )
        death_embed.set_footer(text=f"Death #{sheet['deaths']} · {sheet.get('location','').replace('_',' ').title()}")
        await _broadcast_world_event(ctx, death_embed)
        
    await save(sheet)
    
    embed_color = 0xFF4500 if res["monster_alive"] else 0x2D5A27
    if not res["player_alive"]:
        embed_color = 0x8B0000

        
    embed = discord.Embed(
        title="⚔️ Combat Log",
        description=m_block,
        color=embed_color
    )
    # If monster is still alive, attach Attack/Flee buttons for the next round
    if res["monster_alive"] and res["player_alive"]:
        m_key_for_btn = monster.get("key", "monster")
        combat_view = RPGCombatView(ctx, msg, uid, uname, is_owner, m_key_for_btn)
        await msg.channel.send(embed=embed, view=combat_view)
    else:
        await msg.channel.send(embed=embed)

        # End-of-combat summary narration
        combat_ended = res["monster_defeated"] or not res["player_alive"]
        if combat_ended:
            combat_log = s.get("combat_log", [])
            s["combat_log"] = []
            await save_session(s)
            await _narrate_combat_summary(
                ctx, msg.channel, uid, uname, sheet,
                combat_log, player_won=res["monster_defeated"]
            )

        if not res["player_alive"]:
            view = _make_status_view(ctx, msg, uid, uname, is_owner)
            await msg.channel.send(embed=discord.Embed(description="You are back at the Shrine.", color=0x888888), view=view)
        elif res["monster_defeated"]:
            # Check for remaining swarm members
            remaining_swarm = [m for m in s.get("monsters", []) if m.get("aggro_uid") == uid]
            if remaining_swarm:
                next_m = remaining_swarm[0]
                next_key = next_m.get("key", "monster")
                tier_icon = TIER_ICONS.get(next_m.get("tier", "medium"), "🟠")
                hp_obj = next_m.get("hp", {"current": 0, "max": 0})
                swarm_embed = discord.Embed(
                    title=f"⚔️ Swarm! {next_m.get('name', '???')} {tier_icon}",
                    description=(
                        f"*{next_m.get('desc', 'Another creature closes in.')}*\n\n"
                        f"❤️ **{hp_obj['current']}/{hp_obj['max']} HP** · "
                        f"{len(remaining_swarm)} remain"
                    ),
                    color=0xCC3300
                )
                swarm_embed.set_footer(text="No additional hunt consumed — this is the same encounter.")
                combat_view = RPGCombatView(ctx, msg, uid, uname, is_owner, next_key)
                await msg.channel.send(embed=swarm_embed, view=combat_view)
            else:
                view = _make_hunt_status_view(ctx, msg, uid, uname, is_owner)
                await msg.channel.send(view=view)


async def _handle_flee(ctx, msg, send, rest, uid, uname, is_owner):

    s = await load_session(str(msg.channel.id))
    if not s or not s.get("combat_active"): return
    
    to_flee = -1
    for i, m in enumerate(s.get("monsters", [])):
        if m.get("aggro_uid") == uid:
            to_flee = i
            break
            
    if to_flee == -1: return await msg.channel.send(embed=discord.Embed(description="You have nothing chasing you.", color=0xcc4444))
    
    # Load sheet to deduct hunt
    sheet = await load(uid)
    if sheet:
        sheet["hunts_today"] = sheet.get("hunts_today", 0) + 1
        await save(sheet)
        hunt_note = "\n*(This escape cost 1 hunt stamina)*"
    else:
        hunt_note = ""

    for _cb in ["embered", "fortified"]:
        if _cb in sheet.get("conditions", []): sheet["conditions"].remove(_cb)
    s["monsters"].pop(to_flee)
    if not s["monsters"]: s["combat_active"] = False
    await save_session(s)
    
    view = _make_hunt_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=discord.Embed(
        description=f"🏃 **{uname}** scrambled to safety!{hunt_note}", 
        color=0x44aa44
    ), view=view)


async def _handle_duel(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg duel <@user> — challenge another player to a non-lethal duel."""
    # Clean expired challenges (60s timeout)
    now = time.time()
    expired = [k for k, ts in PENDING_DUELS.items() if now - ts >= 60]
    for k in expired:
        del PENDING_DUELS[k]
        
    if not msg.mentions:
        return await send(msg.channel, "You must mention someone to duel. `!rpg duel @user`")
    
    target = msg.mentions[0]
    target_id = str(target.id)
    
    if target_id == uid:
        return await send(msg.channel, "You cannot duel yourself.")
    
    target_sheet = await load(target_id)
    if not target_sheet:
        return await send(msg.channel, f"{target.display_name} has no character in Aethelgard.")
        
    sheet = await load(uid)
    if not sheet: return
    
    if sheet.get("location") != target_sheet.get("location"):
        return await send(msg.channel, "You must be in the same location to duel.")

    PENDING_DUELS[(uid, target_id)] = time.time()
    
    embed = discord.Embed(
        title="⚔️ DUEL CHALLENGE",
        description=f"**{uname}** has challenged **{target.display_name}** to a duel!\n\n**{target.display_name}**, type `!rpg accept` to engage.\n*Duels are non-lethal (stop at 1 HP).*",
        color=0xffcc00
    )
    await msg.channel.send(target.mention, embed=embed)


async def _handle_accept(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg accept — accept a pending duel or quest."""
    # Check for duels first
    challenger_id = None
    for (c_id, t_id), ts in list(PENDING_DUELS.items()):
        if t_id == uid and time.time() - ts < 60: # 60s timeout
            challenger_id = c_id
            del PENDING_DUELS[(c_id, t_id)]
            break
            
    if challenger_id:
        from utils.ttrpg.combat_engine import _resolve_combat, _compute_player_defense
        
        c_sheet = await load(challenger_id)
        t_sheet = await load(uid)
        
        if not c_sheet or not t_sheet: return
        
        # Build "monster" data from target sheet using proper defense pipeline
        def _get_k(val): return val.get("key") if isinstance(val, dict) else val
        
        from utils.ttrpg.equipment_registry import WEAPONS, ACCESSORIES
        eq = t_sheet.get("equipment", {})
        w = WEAPONS.get(_get_k(eq.get("weapon"))) or {}
        acc = ACCESSORIES.get(_get_k(eq.get("accessory"))) or {}
        
        # Target attack (simplified — just for the counter-attack stat)
        c = t_sheet.get("class", "Warrior")
        adv_class_t = t_sheet.get("advanced_class", "")
        if adv_class_t == "Wizard": astat = "int"
        elif adv_class_t == "High Priest": astat = "wis"
        else: astat = {"Warrior":"str", "Ranger":"dex", "Mage":"int", "Rogue":"dex", "Cleric":"wis"}.get(c, "str")
        atk_val = t_sheet.get("stats", {}).get(astat, 10)
        t_atk = ((atk_val - 10) // 2) + w.get("attack_bonus", 0) + acc.get("attack_bonus", 0)

        # BUG-H1 fix: use proper defense calculation with soft-cap, global cap, etc.
        from utils.ttrpg.housing import load_housing_async
        from utils.ttrpg.pets import get_pet_passive
        t_housing = await load_housing_async(str(t_sheet.get("user_id", "")))
        t_pet_bonuses = get_pet_passive(t_housing) if t_housing else {}
        t_def = _compute_player_defense(t_sheet, pet_bonuses=t_pet_bonuses)

        # BUG-M5 fix: set tier based on target level for correct damage scaling
        t_level = t_sheet.get("level", 1)
        if t_level >= 9:    t_tier = "hard"
        elif t_level >= 7:  t_tier = "medium"
        elif t_level >= 4:  t_tier = "easy"
        else:               t_tier = "trivial"

        m_from_t = {
            "name": t_sheet["character_name"],
            "hp": t_sheet["hp"].copy(),  # BUG-H3 fix: copy to prevent reference mutation
            "attack": t_atk,
            "defense": t_def,
            "tier": t_tier,
            "id": f"player_{uid}"
        }
        
        if c_sheet["hp"]["current"] <= 1 or m_from_t["hp"]["current"] <= 1:
            return await send(msg.channel, f"One or both participants are too injured to duel.")

        round_num = 1
        all_exchanges = []
        max_rounds = 20
        
        # BUG-H2 fix: load CHALLENGER's pet bonuses (not target's)
        c_housing = await load_housing_async(str(c_sheet.get("user_id", "")))
        c_pet_bonuses = get_pet_passive(c_housing) if c_housing else {}
        
        while c_sheet["hp"]["current"] > 1 and m_from_t["hp"]["current"] > 1 and round_num <= max_rounds:
            all_exchanges.append(f"**--- Round {round_num} ---**")
            res = _resolve_combat(c_sheet, m_from_t, is_duel=True, pet_bonuses=c_pet_bonuses)
            all_exchanges.extend(res["exchanges"])
            c_sheet = res["sheet"]
            m_from_t = res["monster"]
            if c_sheet["hp"]["current"] <= 1 or m_from_t["hp"]["current"] <= 1:
                break
            round_num += 1
            
        if round_num > max_rounds:
            all_exchanges.append(f"**--- The duel ends in a draw after {max_rounds} rounds! ---**")
        
        # Apply results back
        await save(c_sheet) # challenger
        t_sheet["hp"] = m_from_t["hp"]
        await save(t_sheet) # target
        
        desc = "\n".join(all_exchanges)
        if len(desc) > 4096:
            desc = desc[:4000] + "\n...[Combat log truncated due to length]"
            
        embed = discord.Embed(
            title="⚔️ DUEL RESULTS",
            description=desc,
            color=0x4488cc
        )
        await msg.channel.send(embed=embed)
        
        await _log_world_event(f"⚔️ **DUEL:** {c_sheet['character_name']} vs {t_sheet['character_name']} in {c_sheet['location'].replace('_',' ').title()}.")
        return

    await msg.channel.send(embed=discord.Embed(
        description="No pending duel or quest acceptance. Use `!rpg duel @user` to challenge someone.",
        color=0x888888
    ))


def _get_dungeon_loot_tier(player_level: int, is_boss: bool = False) -> str:
    """Map player level to loot tier."""
    if is_boss:
        if player_level >= 9:  return "hard"
        if player_level >= 6:  return "medium"
        return "easy"  # tier 2-3 items at low level still feels good
    else:
        # Regular monsters: tier 2 base, rare tier 3
        if secrets.randbelow(6) == 0:  # ~17% tier up
            if player_level >= 6:  return "medium"
            return "easy"
        return "easy"

async def _send_dungeon_room(ctx_obj, channel, uid, uname, is_owner, dungeon,
                              extra_text=""):
    px, py = dungeon["player_pos"]
    room   = dungeon["rooms"].get(f"{px},{py}", {})
    rt     = room.get("type", "empty")

    # [RESUMPTION] Check if combat is active in this room
    ac = dungeon.get("active_combat")
    if ac and ac.get("room_key") == f"{px},{py}":
        monster = ac["monster"]
        monster_key = ac["monster_key"]
        is_boss = ac.get("is_boss", False)
        name_used = ac.get("boss_name") or monster.get("name", "Unknown")
        
        # Resumption uses global imports now
        tier_icon = TIER_ICONS.get(monster.get("tier", "medium"), "🟠")
        hp_obj = monster.get("hp", {"current": 0, "max": 0})
        
        embed = discord.Embed(
            title=f"{'💀' if is_boss else '⚔️'} {name_used} {tier_icon} (Resumed)",
            description=f"*{room.get('description','A stone room.')}*\n\n*{monster.get('desc', '')}*",
            color=0x8B0000 if is_boss else 0xFF4500,
        )
        filled = int((hp_obj['current'] / max(hp_obj['max'], 1)) * 10)
        hb = "█" * filled + "░" * (10 - filled)
        embed.add_field(name="❤️ Monster HP", value=f"`{hb}` {hp_obj['current']}/{hp_obj['max']}", inline=True)
        embed.add_field(name="🗡️ ATK", value=str(monster.get("attack", 0)), inline=True)
        embed.add_field(name="🛡️ DEF", value=str(monster.get("defense", 0)), inline=True)
        
        sheet = await load(uid)
        if sheet:
            embed.set_footer(text=f"Your HP: {sheet['hp']['current']}/{sheet['hp']['max']}")

        view = DungeonCombatView(ctx_obj, uid, uname, is_owner, name_used)
        await channel.send(embed=embed, view=view)
        return

    sheet  = await load(uid)
    hp_str = f"❤️ {sheet['hp']['current']}/{sheet['hp']['max']} HP" if sheet else ""

    ROOM_TITLE_ICONS = {
        "boss": "💀", "antechamber": "🌑", "guard": "🛡️",
        "shrine": "✨", "treasure": "💰", "trap": "⚡",
    }
    icon = ROOM_TITLE_ICONS.get(rt, "🏚️")
    embed = discord.Embed(
        title=f"{icon} {rt.title()} Chamber",
        description=f"*{room.get('description','A stone room.')}*\n\n{hp_str}{extra_text}",
        color=_dungeon_room_color(rt),
    )
    view = DungeonView(ctx_obj, uid, uname, is_owner, dungeon)
    await channel.send(embed=embed, view=view)

def _dungeon_room_color(room_type):
    return {
        "start":        0x888888,
        "empty":        0x4a4a6a,
        "guard":        0xaa6622,   # warm brown — checkpoint
        "monster":      0xFF4500,
        "treasure":     0xd4a843,
        "shrine":       0xaaddff,
        "trap":         0xcc4444,
        "boss":         0x8B0000,
        "antechamber":  0x2a0a0a,   # near-black — ominous
    }.get(room_type, 0x888888)

async def _apply_and_narrate_event(ctx, msg, send, sheet, result, uname):
    """Apply a forest event's mechanical effects and trigger Kaia narration."""

    if sheet.get("advanced_class") == "Shaman" and sheet["hp"]["current"] > 0 and sheet["hp"]["current"] < sheet["hp"]["max"]:
        from utils.ttrpg.class_advancement import ADVANCED_CLASSES
        heal_amt = ADVANCED_CLASSES["Cleric"]["Shaman"]["bonuses"].get("nature_heal_on_event", 4)
        sheet["hp"]["current"] = min(sheet["hp"]["current"] + heal_amt, sheet["hp"]["max"])

    # Apply mechanical changes
    sheet["xp"]  = sheet.get("xp", 0) + result["xp"]
    sheet["gil"] = sheet.get("gil", 0) + result["gil"]

    if result["hp_change"] != 0:
        sheet["hp"]["current"] = max(0, min(
            sheet["hp"]["current"] + result["hp_change"],
            sheet["hp"]["max"]
        ))

    if result["condition_add"]:
        sheet.setdefault("conditions", [])
        if result["condition_add"] not in sheet["conditions"]:
            sheet["conditions"].append(result["condition_add"])

    if result["condition_remove"] and result["condition_remove"] in sheet.get("conditions", []):
        sheet["conditions"].remove(result["condition_remove"])

    if result["extra_hunt"]:
        sheet["hunts_today"] = max(0, sheet.get("hunts_today", 1) - 1)  # refund 1 hunt

    if result["item_add"]:
        sheet.setdefault("inventory", []).append(result["item_add"])

    leveled_up, new_level = check_level_up(sheet)
    await save(sheet)

    # Post mechanical result as embed (matches combat log card style)
    xp_next = xp_to_next_level(sheet["level"])

    event_colors = {
        "sylvan_sprites":    0x88eea8,   # soft green
        "moogle_sighting":   0xf5c842,   # moogle yellow
        "injured_silvani":   0x7ec8e3,   # blue-grey
        "old_man_riddle":    0xb8a0d8,   # purple
        "chocobo_tracks":    0xf0d060,   # chocobo yellow
        "aeridor_fragment":  0x80d8ff,   # crystal blue
        "gilded_mushroom":   0xd4a843,   # gold
        "veiled_elder":      0xc0c0d8,   # silver-pale
        "timid_tonberry":    0x88bb88,   # muted green
        "mognet_delivery":   0xf4a460,   # sandy orange
        "crystal_resonance": 0x9988dd,   # resonance purple
    }
    color = event_colors.get(result.get("event_key", ""), 0xaaaaaa)

    body_lines = [f"*{result['outcome']}*"]
    if result["xp"]:
        body_lines.append(f"+{result['xp']} XP ({sheet['xp']}/{xp_next})")
    if result["gil"]:
        body_lines.append(f"+{result['gil']} Gil  (total: {sheet['gil']}g)")
    if result["hp_change"] > 0:
        body_lines.append(f"+{result['hp_change']} HP  ({sheet['hp']['current']}/{sheet['hp']['max']})")
    if result["hp_change"] < 0:
        body_lines.append(f"{result['hp_change']} HP  ({sheet['hp']['current']}/{sheet['hp']['max']})")
    if result["extra_hunt"]:
        body_lines.append(f"🎯 Hunts remaining: {hunts_remaining(sheet)}/{get_max_hunts(sheet)}")
    if result["item_add"]:
        body_lines.append(f"📦 Added to inventory: `{result['item_add']}`")

    embed = discord.Embed(
        title=result["title"],
        description="\n".join(body_lines),
        color=color
    )

    await msg.channel.send(embed=embed)

    if leveled_up:
        await _log_world_event(f"**{sheet['character_name']}** reached Level {new_level} during a world event.")
        lv_embed = discord.Embed(
            title=f"⬆️ {sheet['character_name']} — Level {new_level}",
            description=_level_up_flavor(sheet, new_level),
            color=0xffcc00
        )
        lv_embed.set_footer(text=f"{sheet.get('advanced_class') or sheet.get('class', '?')} · World Event")
        await _broadcast_world_event(ctx, lv_embed)

    # Kaia narrates
    if result.get("narration_hook"):
        from utils.ttrpg.rpg_prompt_builder import build_event_narration_prompt
        from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
        from utils.infrastructure.system.yaml_config import config
        import uuid as _uuid

        prompt = build_event_narration_prompt(
            sheet=sheet,
            event_title=result["title"],
            narration_hook=result["narration_hook"],
        )
        persona = await load_persona_async()
        from utils.ttrpg.rpg_prompt_builder import TTRPG_NARRATOR_OVERRIDE
        messages = [
            {"role": "system", "content": f"{persona}{TTRPG_NARRATOR_OVERRIDE}{prompt}"},
            {"role": "user",   "content": f"{uname} is in the {sheet.get('location', 'forest')}."}
        ]
        gpu_manager = OllamaGPUManager(config.chat_model)
        opts = gpu_manager.get_gpu_options(for_chat=True)
        opts["num_predict"] = 120
        opts["temperature"] = 0.9

        async with msg.channel.typing():
            try:
                resp = await gpu_memory_manager.run_with_gpu_guard(
                    model_name=config.chat_model,
                    priority=GPUTaskPriority.CHAT,
                    coro=asyncio.wait_for(
                        ctx.ollama_client.chat(
                            model=config.chat_model,
                            messages=messages,
                            options=opts,
                            keep_alive=-1
                        ),
                        timeout=45.0
                    ),
                    task_id=f"rpg_event_{_uuid.uuid4().hex[:8]}"
                )
                narration = resp["message"]["content"].strip().replace("```", "")
                if narration:
                    embed = discord.Embed(
                        description=f"*{narration}*",
                        color=0x4488cc
                    )
                    await msg.channel.send(embed=embed)
            except Exception as e:
                log_error(f"[rpg event narration] {e}")



async def _dungeon_complete(ctx_obj, interaction, uid, uname, is_owner,
                             state, sheet, leveled=False, new_level=0):
    from utils.ttrpg.dungeon import clear_dungeon
    from utils.ttrpg.shop import find_item

    difficulty = state.get("difficulty", 1)
    player_level = sheet.get("level", 1)
    
    bonus_xp  = 50 + (difficulty * 25) + (player_level * 5)
    bonus_gil = 25 + (difficulty * 15) + (player_level * 3)
    sheet["xp"]  = sheet.get("xp",  0) + bonus_xp
    sheet["gil"] = sheet.get("gil", 0) + bonus_gil

    # Quest Task Tracking: Dungeon completion
    active_id = sheet.get("active_quest")
    if active_id:
        from utils.ttrpg.quest_registry import get_quest
        q = get_quest(active_id)
        if q and "complete_dungeon" in q["tasks"]:
            prog = sheet.setdefault("quest_progress", {}).setdefault(active_id, [])
            if "complete_dungeon" not in prog:
                prog.append("complete_dungeon")

    await save(sheet)
    await clear_dungeon(uid)

    xp   = state.get("xp_gained",  0) + bonus_xp
    gil  = state.get("gil_gained", 0) + bonus_gil
    loot = state.get("loot_gained", [])

    loot_str = ""
    if loot:
        names = [(find_item(l) or {}).get("name", l) for l in loot]
        loot_str = "\n**Loot:** " + ", ".join(names)

    level_str = f"\n\n🎉 **Level Up! Now Lv.{new_level}!**" if leveled else ""

    # Find boss name for broadcast
    boss_key = state.get("boss_key", "")
    boss = state.get("rooms", {}).get(boss_key, {})
    boss_name = boss.get("boss_name") or "the dungeon boss"

    embed = discord.Embed(
        title="🏰 Dungeon Conquered — Victory",
        description=(
            f"*The {boss_name} lies broken. You emerge from the ruins in triumph as they seal behind you.*\n\n"
            f"**Earned:** +{xp} XP · +{gil} Gil"
            f"{loot_str}{level_str}"
        ),
        color=0xFFAA00,
    )
    view = discord.ui.View(timeout=60)
    view.add_item(_make_status_btn(ctx_obj, uid, uname, is_owner))
    await interaction.followup.send(embed=embed, view=view)
    
    await _log_world_event(f"🏰 **{sheet['character_name']}** conquered the {state.get('theme_name', 'dungeon')}.")
    dungeon_embed = discord.Embed(
        title=f"🏰 {sheet['character_name']} conquered the {state.get('theme_name', 'dungeon')}",
        description=f"*The **{boss_name}** has been vanquished. {sheet['character_name']} emerged from the depths in total victory.*",
        color=0xFFAA00
    )
    dungeon_embed.set_footer(text=f"+{xp} XP · +{gil} Gil · {len(loot)} item(s)")
    await _broadcast_world_event(ctx_obj, dungeon_embed)

