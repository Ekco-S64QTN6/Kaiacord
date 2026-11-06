from utils.ttrpg.session_manager import serialize_combat_action
from utils.ttrpg.narration import finish_cleanly
import asyncio
import re
import time
import uuid as _uuid
import discord

from utils.commands.stale_view import StaleSafeView
import secrets
from utils.infrastructure.logging.kaia_logger import log_error
from utils.infrastructure.system.yaml_config import config
from utils.ttrpg.world_state import get_current_state
from utils.ttrpg.character_manager import load, save, create, load_all
from utils.ttrpg.session_manager import load_session
from utils.ttrpg.rpg_recovery_handler import GAMBLE_DAILY_WIN_CAP
from utils.ttrpg.progression import (
    hunts_remaining, check_level_up, get_max_hunts, xp_to_next_level, XP_THRESHOLDS,
)
from utils.ttrpg.class_advancement import (
    apply_advanced_class_to_combat, apply_advanced_class_to_sheet,
    get_advanced_options, get_title, ADVANCED_CLASSES
)
from utils.ttrpg.dungeon import load_dungeon
from utils.ttrpg.rpg_ui import (
    colored_bar, hp_label, CLASS_ICONS, LOCATION_ICONS, ANSI_GREEN, ANSI_RESET,
)
from utils.social.kaia_social_responder import load_persona_async
from utils.ttrpg.world import LOCATION_DATA
import utils.ttrpg.dice_engine as dice_engine
from utils.ttrpg.shop import find_item
from utils.ttrpg.broadcast import (
    log_world_event as _log_world_event,
    broadcast_world_event as _broadcast_world_event,
    level_up_flavor as _level_up_flavor,
    rare_loot_flavor as _rare_loot_flavor,
    _boss_approach_flavor
)

# One shim for every button path: it carries embeds and views, and
# answers msg.content / msg.mentions for handlers that read them.
from utils.ttrpg.rpg_views import _make_interaction_send, _InteractionMsg, no_character  # noqa: E402


from utils.ttrpg.rpg_views import *
from utils.ttrpg.session_manager import player_locked, serialize_user_action

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
        mine = [m for m in session.get("monsters", []) if isinstance(m, dict) and str(m.get("aggro_uid")) == str(uid) and m.get("origin_location") == sheet.get("location", "oakhaven")]
        if mine:
            resume_desc = f"\n\n⚔️ **You are currently in combat here!**\nUse `!rpg hunt` to re-open the interface."
    
    # Resumption logic
    dungeon = await load_dungeon(uid)
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
            if isinstance(m, dict) and str(m.get("aggro_uid")) == str(uid) and m.get("origin_location") == sheet.get("location", "oakhaven"):
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
            view = StaleSafeView(timeout=120)
            sel = discord.ui.Select(placeholder="Choose your path...", options=sel_options, row=0)
            
            @player_locked(uid)
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
    from utils.ttrpg.rpg_character_creation_handler import _handle_new as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        create_character=create,
        roll_fn=dice_engine.roll,
        class_registry=dice_engine.CLASSES,
    )

async def _handle_sheet(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_sheet_handler import _handle_sheet as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        location_icons=LOCATION_ICONS,
        location_view_factory=RPGLocationView,
        stale_view_factory=StaleSafeView,
        status_btn_factory=_make_status_btn,
        hunts_remaining_fn=hunts_remaining,
        max_hunts_fn=get_max_hunts,
        xp_to_next_level_fn=xp_to_next_level,
    )

async def _handle_advance(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_advancement_handler import _handle_advance as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        save_character=save,
        advanced_options_fn=get_advanced_options,
        apply_advanced_class_fn=apply_advanced_class_to_sheet,
        get_title_fn=get_title,
        player_locked_decorator=player_locked,
        log_world_event_fn=_log_world_event,
        broadcast_world_event_fn=_broadcast_world_event,
    )

@serialize_user_action
async def _handle_go(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_navigation_handler import _handle_go as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load, save_character=save,
    )


def _names(phrase: str, text: str) -> bool:
    """`phrase` appears in `text` as whole words."""
    return bool(re.search(rf"\b{re.escape(phrase)}\b", text))


async def _handle_look(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_navigation_handler import _handle_look as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load, save_character=save,
    )

async def _handle_map(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_navigation_handler import _handle_map as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner, load_character=load,
    )

async def _handle_rest(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_recovery_handler import _handle_rest as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        save_character=save,
        no_character_handler=no_character,
        status_view_factory=_make_status_view,
    )

# Stable entry points retained for rpg_handler and rpg_views; implementations
# live together in rpg_world_handler.py.
async def _handle_rumor(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_world_handler import _handle_rumor as handle
    return await handle(ctx, msg, send, rest, uid, uname, is_owner)


async def _handle_calendar(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_world_handler import _handle_calendar as handle
    return await handle(ctx, msg, send, rest, uid, uname, is_owner)


async def _handle_weather(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_world_handler import _handle_weather as handle
    return await handle(ctx, msg, send, rest, uid, uname, is_owner)

async def _handle_inventory(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_inventory_handler import _handle_inventory as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        no_character_handler=no_character,
        make_status_view=_make_status_view,
        make_inventory_view=_make_inventory_view,
        get_class_abbr_string=_get_class_abbr_string,
        get_item_effect_string=_get_item_effect_string,
    )


@serialize_user_action
async def _handle_equip(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_inventory_handler import _handle_equip as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load, save_character=save,
        no_character_handler=no_character,
    )


async def _handle_unequip(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_inventory_handler import _handle_unequip as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load, save_character=save,
        no_character_handler=no_character,
        player_locked_decorator=player_locked,
        interaction_msg_factory=_InteractionMsg,
        interaction_send_factory=_make_interaction_send,
        status_btn_factory=_make_status_btn,
    )


# Drinking a potion is a combat action; keep the serializer at the public
# command/view boundary and pass the core module's patchable dependencies through.
# The extracted handler retains the Cleric/High Priest heal_mult consumable rule.
@serialize_combat_action
async def _handle_use(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_consumable_handler import _handle_use as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        save_character=save,
        no_character_handler=no_character,
        load_session_fn=load_session,
        active_view_factory=_get_active_view,
        status_view_factory=_make_status_view,
        hunt_status_view_factory=_make_hunt_status_view,
        secrets_module=secrets,
        uuid_module=_uuid,
    )

async def _handle_purify(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_recovery_handler import _handle_purify as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        no_character_handler=no_character,
    )


async def _handle_drink(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_recovery_handler import _handle_drink as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        save_character=save,
        make_status_view=_make_status_view,
        hunts_remaining_fn=hunts_remaining,
        get_max_hunts_fn=get_max_hunts,
    )


async def _handle_fountain(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_recovery_handler import _handle_fountain as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        save_character=save,
        make_status_view=_make_status_view,
    )


# The extracted handler preserves the Trickster has_gamble_edge advantage.
async def _handle_gamble(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_gamble_handler import _handle_gamble as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        save_character=save,
        secrets_module=secrets,
        daily_win_cap=GAMBLE_DAILY_WIN_CAP,
        player_locked_decorator=player_locked,
        interaction_msg_factory=_InteractionMsg,
        interaction_send_factory=_make_interaction_send,
        status_btn_factory=_make_status_btn,
    )

# The extracted Shrine gift path still uses inventory_capacity.grant_item_or_mail.
async def _handle_pray(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_shrine_handler import _handle_pray as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        save_character=save,
        status_view_factory=_make_status_view,
    )


async def _handle_offer(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_shrine_handler import _handle_offer as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        save_character=save,
        no_character_handler=no_character,
        player_locked_decorator=player_locked,
        check_level_up_fn=check_level_up,
        xp_to_next_level_fn=xp_to_next_level,
        status_btn_factory=_make_status_btn,
    )


async def _handle_scout(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_scout_handler import _handle_scout as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        save_character=save,
        status_view_factory=_make_status_view,
        secrets_module=secrets,
    )

async def _bank_refusal(sheet: dict, uid: str) -> str:
    from utils.ttrpg.rpg_bank_handler import _bank_refusal as refuse
    return await refuse(sheet, uid)


async def _handle_bank_deposit(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_bank_handler import _handle_bank_deposit as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        save_character=save,
        no_character_handler=no_character,
        player_locked_decorator=player_locked,
        status_btn_factory=_make_status_btn,
    )


async def _handle_bank_withdraw(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_bank_handler import _handle_bank_withdraw as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        save_character=save,
        no_character_handler=no_character,
        player_locked_decorator=player_locked,
        status_btn_factory=_make_status_btn,
    )


async def _handle_bank(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_bank_handler import _handle_bank as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        no_character_handler=no_character,
    )


async def _handle_roll(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_reference_handler import _handle_roll as handle
    return await handle(ctx, msg, send, rest, uid, uname, is_owner)


async def _handle_bestiary(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_reference_handler import _handle_bestiary as handle
    return await handle(ctx, msg, send, rest, uid, uname, is_owner)


async def _handle_xp(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_reference_handler import _handle_xp as handle
    return await handle(ctx, msg, send, rest, uid, uname, is_owner)


async def _with_target_action_lock(target_uid: str, caller_uid: str, operation):
    """Serialize an admin mutation with the target player, not just the admin.

    The dispatcher already holds the caller's lock. Skip reacquiring it for
    self-targeted admin commands because the action locks are not re-entrant.
    """
    target_uid = str(target_uid)
    if target_uid == str(caller_uid):
        return await operation()

    from utils.ttrpg.session_manager import get_action_lock
    async with await get_action_lock(f"user:{target_uid}"):
        return await operation()


async def _handle_give(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return
    from utils.ttrpg.shop import find_item

    mentions = getattr(msg, "mentions", []) or []
    target_uid = str(mentions[0].id) if mentions else str(uid)
    item_query = rest.strip()
    if mentions:
        # Discord leaves the mention token in the dispatcher's remaining text.
        # Remove only the selected recipient token before resolving the item.
        item_query = re.sub(rf"<@!?{re.escape(target_uid)}>", "", item_query, count=1).strip()
    if not item_query:
        return await msg.channel.send(embed=discord.Embed(
            description="Specify an item to grant. Example: `!rpg give @player tonic`.",
            color=0x888888
        ))

    item = find_item(item_query)
    if not item:
        return await msg.channel.send(embed=discord.Embed(
            description=f"No RPG item found for `{item_query}`.",
            color=0xcc4444
        ))

    async def grant():
        sheet = await load(target_uid)
        if not sheet:
            return None
        from utils.ttrpg.inventory_capacity import grant_item
        from utils.ttrpg.inventory_capacity import unique_item_type_count
        from utils.ttrpg.character_manager import INVENTORY_LIMIT
        if not grant_item(sheet, item["key"]):
            return (sheet["character_name"], False, unique_item_type_count(sheet.get("inventory", [])), INVENTORY_LIMIT)
        await save(sheet)
        return (sheet["character_name"], True, 0, INVENTORY_LIMIT)

    grant_result = await _with_target_action_lock(target_uid, uid, grant)
    if not grant_result:
        return await no_character(msg)
    target_name, granted, current_unique, limit = grant_result
    if not granted:
        return await msg.channel.send(embed=discord.Embed(
            description=(
                f"Could not grant `{item['key']}` to {target_name}: inventory full "
                f"({current_unique}/{limit} unique item types)."
            ),
            color=0xcc4444,
        ))
    await msg.channel.send(embed=discord.Embed(
        description=f"Admin granted `{item['key']}` to {target_name}.",
        color=0x44aa44
    ))


async def _handle_heal(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return
    mentions = getattr(msg, "mentions", []) or []
    target_uid = str(mentions[0].id) if mentions else str(uid)

    async def heal():
        sheet = await load(target_uid)
        if not sheet:
            return None
        sheet["hp"]["current"] = sheet["hp"]["max"]
        await save(sheet)
        return sheet["character_name"]

    target_name = await _with_target_action_lock(target_uid, uid, heal)
    if not target_name:
        return await no_character(msg)
    await msg.channel.send(embed=discord.Embed(
        description=f"Admin fully healed {target_name}.",
        color=0x44aa44
    ))


async def _handle_leaderboard(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_reference_handler import _handle_leaderboard as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        location_data=LOCATION_DATA,
        class_icons=CLASS_ICONS,
        location_icons=LOCATION_ICONS,
        get_title_fn=get_title,
        make_status_view=_make_status_view,
    )


async def _handle_rpg_help(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_reference_handler import _handle_rpg_help as handle
    return await handle(ctx, msg, send, rest, uid, uname, is_owner)
