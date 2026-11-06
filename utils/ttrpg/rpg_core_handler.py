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
    from utils.ttrpg.rpg_status_handler import _handle_status as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        save_character=save,
        show_stat_choice_handler=_show_stat_choice,
        load_session_fn=load_session,
        load_dungeon_fn=load_dungeon,
        get_current_state_fn=get_current_state,
        xp_to_next_level_fn=xp_to_next_level,
        xp_thresholds=XP_THRESHOLDS,
        colored_bar_fn=colored_bar,
        ansi_green=ANSI_GREEN,
        ansi_reset=ANSI_RESET,
        hp_label_fn=hp_label,
        hunts_remaining_fn=hunts_remaining,
        get_max_hunts_fn=get_max_hunts,
        get_title_fn=get_title,
        class_icons=CLASS_ICONS,
        location_icons=LOCATION_ICONS,
        player_locked_decorator=player_locked,
        location_view_factory=RPGLocationView,
        stale_view_factory=StaleSafeView,
    )

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
    from utils.ttrpg.rpg_admin_handler import _with_target_action_lock as handle
    return await handle(target_uid, caller_uid, operation)


async def _handle_give(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_admin_handler import _handle_give as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        save_character=save,
        no_character_handler=no_character,
        with_target_action_lock_fn=_with_target_action_lock,
    )


async def _handle_heal(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_admin_handler import _handle_heal as handle
    return await handle(
        ctx, msg, send, rest, uid, uname, is_owner,
        load_character=load,
        save_character=save,
        no_character_handler=no_character,
        with_target_action_lock_fn=_with_target_action_lock,
    )


# Both caller and target locks are acquired together by the admin helper.
# Do not let the dispatcher pre-acquire only the caller lock.
_handle_give._serialized = True
_handle_heal._serialized = True


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
