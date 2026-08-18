"""
!rpg command handler — Aethelgard Persistent World System
(ROUTER ONLY — Domains extracted to rpg_*_handler.py components)
"""

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

import utils.ttrpg.rpg_social_handler as soc
import utils.ttrpg.rpg_combat_handler as com
import utils.ttrpg.rpg_shop_handler as sho
import utils.ttrpg.rpg_housing_handler as hou
import utils.ttrpg.rpg_core_handler as cor
from utils.ttrpg.rpg_views import *
from utils.commands.fishing_handler import handle_fish_command, handle_fish_shop_command
from utils.commands.fishing_handler import _handle_sell_catch as _sell_catch_inner


async def _handle_sell_catch_cmd(ctx, msg, send, rest, uid, uname, is_owner):
    """Adapter: bridge the 7-arg dispatcher signature to fishing handler's 5-arg UI signature."""
    class _FakeInteraction:
        """Minimal object mimicking discord.Interaction for fishing handler's followup.send."""
        def __init__(self, channel):
            self.channel = channel
            self.followup = self
        async def send(self, *args, **kwargs):
            await self.channel.send(*args, **kwargs)

    fake = _FakeInteraction(msg.channel)
    await _sell_catch_inner(ctx, fake, uid, uname, is_owner)


async def handle_rpg_command(ctx, msg, send_kaia_response):
    """Main !rpg dispatcher."""
    parts = msg.content.strip().split(maxsplit=2)
    # !rpg with no args = status board
    sub = parts[1].lower() if len(parts) > 1 else "status_board"
    rest = parts[2] if len(parts) > 2 else ""
    
    author_id = str(msg.author.id)
    author_name = msg.author.display_name
    is_owner = ctx.config.is_owner(msg.author.name, author_name, author_id)
    
    handlers = {
        "status_board": cor._handle_status,
        "new":       cor._handle_new,
        "go":        cor._handle_go,
        "look":      cor._handle_look,
        "map":       cor._handle_map,
        "rest":      cor._handle_rest,
        "rumor":     cor._handle_rumor,
        "buy":       sho._handle_buy,
        "sell":      sho._handle_sell,
        "sell_gear": sho._handle_sell_all_gear,
        "sell_all":  sho._handle_sell_all_gear,
        "shop":      sho._handle_shop,
        "use":       cor._handle_use,
        "talk":      soc._handle_talk,
        "calendar":  cor._handle_calendar,
        "hunt":      com._handle_hunt,
        "fish":      handle_fish_command,
        "fish_shop": handle_fish_shop_command,
        "sell_catch": _handle_sell_catch_cmd,
        "attack":    com._handle_attack,
        "flee":      com._handle_flee,
        "hunts":     com._handle_hunts,
        "inventory": cor._handle_inventory,
        "equip":     cor._handle_equip,
        "roll":      cor._handle_roll,
        "bestiary":  cor._handle_bestiary,
        "help":      cor._handle_rpg_help,
        "xp":        cor._handle_xp,
        "give":      cor._handle_give,
        "heal":      cor._handle_heal,
        "event":     soc._handle_event,
        "drink":     cor._handle_drink,
        "gamble":    cor._handle_gamble,
        "pray":      cor._handle_pray,
        "offer":     cor._handle_offer,
        "scout":     cor._handle_scout,
        "mail":      soc._handle_mail,
        "deliver":   soc._handle_mail,
        "fountain":  cor._handle_fountain,
        "leaderboard": cor._handle_leaderboard,
        "lb":        cor._handle_leaderboard,
        "notices":   soc._handle_notices,
        "quests":    soc._handle_quests,
        "quest":     soc._handle_quest_detail,
        "accept":    com._handle_accept,
        "abandon":   soc._handle_abandon,
        "brew":      hou._handle_brew,
        "bank_deposit": cor._handle_bank_deposit,
        "bank_withdraw": cor._handle_bank_withdraw,
        "bank":      cor._handle_bank,
        "duel":      com._handle_duel,
        "weather":   cor._handle_weather,
        "dungeon":   com._handle_dungeon,
        "unequip":   cor._handle_unequip,
        "advance":   cor._handle_advance,
        "bard_song": soc._handle_bard_song,
        "sheet":     cor._handle_sheet,
        "my_home":        hou._handle_my_home,
        "buy_house":      hou._handle_buy_house,
        "upgrade_house":  hou._handle_upgrade_house,
        "furniture_shop": hou._handle_furniture_shop,
        "buy_furniture":  hou._handle_buy_furniture,
        "pet_shop":       hou._handle_pet_shop,
        "buy_pet":        hou._handle_buy_pet,
        "feed_pet":       hou._handle_feed_pet,
        "farm_view":      hou._handle_farm_view,
        "plant_crop":     hou._handle_plant_crop,
        "water_crops":    hou._handle_water_crops,
        "harvest_crops":  hou._handle_harvest_crops,
        "visit_plots":    hou._handle_visit_plots,
        "rename_house":   hou._handle_rename_house,
        "home_training":  hou._handle_home_training,
        "seed_shop":      hou._handle_seed_shop,
        "purify":         cor._handle_purify,
        "raid":           com._handle_raid_blockade,
        "rob":            com._handle_rob_bandits,
        "farm_treat":     hou._handle_farm_treat,
        "treat":          hou._handle_farm_treat,
    }
    async def _auto_send(channel, text, use_code_block=None):
        if use_code_block is None:
            use_code_block = "```" not in str(text)
        return await send_kaia_response(channel, text, use_code_block=use_code_block)

    handler = handlers.get(sub, cor._handle_rpg_help)
    try:
        await handler(ctx, msg, _auto_send, rest, author_id, author_name, is_owner)
    except Exception as e:
        log_error(f"[rpg] Handler error in '{sub}': {e}")
        await _auto_send(msg.channel, f"system fault in `{sub}`. check logs: {e}")
