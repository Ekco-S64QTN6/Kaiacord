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

__all__ = [
    '_LOCATION_BUTTONS',
    '_make_inventory_view',
    'RPGLocationView',
    '_show_stat_choice',
    '_make_hunt_status_view',
    '_narrate_combat_summary',
    '_InteractionChannel', '_InteractionMsg', '_make_interaction_send', 
    'StatChoiceView', 'RPGFullLocationView', 'RPGCombatView', 'BossApproachView', 'SpineLiftView',
    'DungeonView', 'DungeonCombatView', 'MailMenuView', 'MailSendView', 'GilModal', 
    'ConsumableQuantityView', 'ConsumablePurchaseModal', 'RenameHouseModal', 
    '_get_active_view', '_make_status_btn', '_make_home_btn', '_make_status_view', 
    '_make_map_view', '_make_shop_view', 'LOCATION_COLORS', '_get_class_abbr_string',
    '_get_item_effect_string'
]



# Lazy Load Dispatchers to cleanly handle UI callbacks without circular imports

async def _handle_abandon(*args, **kwargs):
    from utils.ttrpg.rpg_social_handler import _handle_abandon as _f
    return await _f(*args, **kwargs)

async def _handle_bard_song(*args, **kwargs):
    from utils.ttrpg.rpg_social_handler import _handle_bard_song as _f
    return await _f(*args, **kwargs)

async def _handle_event(*args, **kwargs):
    from utils.ttrpg.rpg_social_handler import _handle_event as _f
    return await _f(*args, **kwargs)

async def _handle_mail(*args, **kwargs):
    from utils.ttrpg.rpg_social_handler import _handle_mail as _f
    return await _f(*args, **kwargs)

async def _handle_notices(*args, **kwargs):
    from utils.ttrpg.rpg_social_handler import _handle_notices as _f
    return await _f(*args, **kwargs)

async def _handle_quest_detail(*args, **kwargs):
    from utils.ttrpg.rpg_social_handler import _handle_quest_detail as _f
    return await _f(*args, **kwargs)

async def _handle_quests(*args, **kwargs):
    from utils.ttrpg.rpg_social_handler import _handle_quests as _f
    return await _f(*args, **kwargs)

async def _handle_talk(*args, **kwargs):
    from utils.ttrpg.rpg_social_handler import _handle_talk as _f
    return await _f(*args, **kwargs)

async def _handle_accept(*args, **kwargs):
    from utils.ttrpg.rpg_combat_handler import _handle_accept as _f
    return await _f(*args, **kwargs)

async def _handle_attack(*args, **kwargs):
    from utils.ttrpg.rpg_combat_handler import _handle_attack as _f
    return await _f(*args, **kwargs)

async def _handle_duel(*args, **kwargs):
    from utils.ttrpg.rpg_combat_handler import _handle_duel as _f
    return await _f(*args, **kwargs)

async def _handle_dungeon(*args, **kwargs):
    from utils.ttrpg.rpg_combat_handler import _handle_dungeon as _f
    return await _f(*args, **kwargs)

async def _handle_flee(*args, **kwargs):
    from utils.ttrpg.rpg_combat_handler import _handle_flee as _f
    return await _f(*args, **kwargs)

async def _handle_hunt(*args, **kwargs):
    from utils.ttrpg.rpg_combat_handler import _handle_hunt as _f
    return await _f(*args, **kwargs)

async def _handle_hunts(*args, **kwargs):
    from utils.ttrpg.rpg_combat_handler import _handle_hunts as _f
    return await _f(*args, **kwargs)

async def _dungeon_combat_flee(*args, **kwargs):
    from utils.ttrpg.rpg_combat_handler import _dungeon_combat_flee as _f
    return await _f(*args, **kwargs)

async def _dungeon_move(*args, **kwargs):
    from utils.ttrpg.rpg_combat_handler import _dungeon_move as _f
    return await _f(*args, **kwargs)

async def _dungeon_combat_round(*args, **kwargs):
    from utils.ttrpg.rpg_combat_handler import _dungeon_combat_round as _f
    return await _f(*args, **kwargs)

async def _send_dungeon_room(*args, **kwargs):
    from utils.ttrpg.rpg_combat_handler import _send_dungeon_room as _f
    return await _f(*args, **kwargs)

def _dungeon_room_color(*args, **kwargs):
    from utils.ttrpg.rpg_combat_handler import _dungeon_room_color as _f
    return _f(*args, **kwargs)

def _get_class_abbr_string(item):
    """Return an explicit class requirement string, e.g. [WAR/PAL/SHD]."""
    classes = item.get("classes")
    if not classes:
        return ""
    MAP = {
        "Warrior": "WAR", "Paladin": "PAL", "Shadowknight": "SHD",
        "Ranger": "RGR", "Hunter": "HTR", "Warden": "WRD",
        "Mage": "MAG", "Wizard": "WIZ", "Necromancer": "NEC",
        "Rogue": "ROG", "Shadowblade": "SHB", "Trickster": "TRK",
        "Cleric": "CLR", "High Priest": "HPR", "Shaman": "SHM"
    }
    abbrs = [MAP.get(c, c[:3].upper()) for c in classes]
    if not abbrs: return ""
    return f" [{'/'.join(abbrs)}]"

def _get_item_effect_string(item):
    """Return a short description of what a consumable or item does."""
    if item.get("category") != "consumable":
        return ""
    hp = item.get("hp_restore", 0)
    on_use = item.get("on_use", "")
    USE_LABELS = {
        "starter_kit":     "open for items",
        "cure_poison":     "cures poison",
        "cure_blind":      "cures blindness",
        "luck_roll_bonus": "+1 next hit",
        "xp_boost":        "+25% XP next hunt",
        "hunt_bonus":      "+1 bonus hunt",
        "atk_boost":       "+2 ATK (1 combat)",
        "def_boost":       "+2 DEF (1 combat)",
    }
    if on_use in USE_LABELS:
        effect = USE_LABELS[on_use]
    elif "description" in item and hp == 0:
        effect = item["description"]
    else:
        effect = f"restores {hp} HP"
    return f" — {effect}"


async def _handle_rumor(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_rumor as _f
    return await _f(*args, **kwargs)

async def _handle_buy(*args, **kwargs):
    from utils.ttrpg.rpg_shop_handler import _handle_buy as _f
    return await _f(*args, **kwargs)

async def _handle_sell(*args, **kwargs):
    from utils.ttrpg.rpg_shop_handler import _handle_sell as _f
    return await _f(*args, **kwargs)

async def _handle_sell_all_gear(*args, **kwargs):
    from utils.ttrpg.rpg_shop_handler import _handle_sell_all_gear as _f
    return await _f(*args, **kwargs)

async def _handle_shop(*args, **kwargs):
    from utils.ttrpg.rpg_shop_handler import _handle_shop as _f
    return await _f(*args, **kwargs)

async def _handle_brew(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_brew as _f
    return await _f(*args, **kwargs)

async def _handle_buy_furniture(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_buy_furniture as _f
    return await _f(*args, **kwargs)

async def _handle_buy_house(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_buy_house as _f
    return await _f(*args, **kwargs)

async def _handle_buy_pet(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_buy_pet as _f
    return await _f(*args, **kwargs)

async def _handle_farm_view(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_farm_view as _f
    return await _f(*args, **kwargs)

async def _handle_feed_pet(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_feed_pet as _f
    return await _f(*args, **kwargs)

async def _handle_furniture_shop(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_furniture_shop as _f
    return await _f(*args, **kwargs)

async def _handle_harvest_crops(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_harvest_crops as _f
    return await _f(*args, **kwargs)

async def _handle_home_training(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_home_training as _f
    return await _f(*args, **kwargs)

async def _handle_my_home(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_my_home as _f
    return await _f(*args, **kwargs)

async def _handle_pet_shop(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_pet_shop as _f
    return await _f(*args, **kwargs)

async def _handle_plant_crop(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_plant_crop as _f
    return await _f(*args, **kwargs)

async def _handle_rename_house(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_rename_house as _f
    return await _f(*args, **kwargs)

async def _handle_seed_shop(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_seed_shop as _f
    return await _f(*args, **kwargs)

async def _handle_upgrade_house(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_upgrade_house as _f
    return await _f(*args, **kwargs)

async def _handle_visit_plots(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_visit_plots as _f
    return await _f(*args, **kwargs)

async def _handle_water_crops(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_water_crops as _f
    return await _f(*args, **kwargs)

async def _handle_bank(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_bank as _f
    return await _f(*args, **kwargs)

async def _handle_status(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_status as _f
    return await _f(*args, **kwargs)

async def _handle_sheet(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_sheet as _f
    return await _f(*args, **kwargs)

async def _handle_go(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_go as _f
    return await _f(*args, **kwargs)

async def _handle_look(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_look as _f
    return await _f(*args, **kwargs)

async def _handle_map(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_map as _f
    return await _f(*args, **kwargs)

async def _handle_rest(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_rest as _f
    return await _f(*args, **kwargs)

async def _handle_drink(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_drink as _f
    return await _f(*args, **kwargs)

async def _handle_pray(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_pray as _f
    return await _f(*args, **kwargs)

async def _handle_fountain(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_fountain as _f
    return await _f(*args, **kwargs)

async def _handle_offer(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_offer as _f
    return await _f(*args, **kwargs)

async def _handle_scout(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_scout as _f
    return await _f(*args, **kwargs)

async def _handle_use(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_use as _f
    return await _f(*args, **kwargs)

async def _handle_inventory(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_inventory as _f
    return await _f(*args, **kwargs)

async def _handle_equip(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_equip as _f
    return await _f(*args, **kwargs)

async def _handle_unequip(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_unequip as _f
    return await _f(*args, **kwargs)

async def _handle_roll(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_roll as _f
    return await _f(*args, **kwargs)

async def _handle_bestiary(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_bestiary as _f
    return await _f(*args, **kwargs)

async def _handle_rpg_help(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_rpg_help as _f
    return await _f(*args, **kwargs)

async def _handle_xp(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_xp as _f
    return await _f(*args, **kwargs)

async def _handle_give(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_give as _f
    return await _f(*args, **kwargs)

async def _handle_heal(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_heal as _f
    return await _f(*args, **kwargs)

async def _handle_gamble(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_gamble as _f
    return await _f(*args, **kwargs)

async def _handle_leaderboard(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_leaderboard as _f
    return await _f(*args, **kwargs)

async def _handle_bank_deposit(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_bank_deposit as _f
    return await _f(*args, **kwargs)

async def _handle_bank_withdraw(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_bank_withdraw as _f
    return await _f(*args, **kwargs)

async def _handle_bank(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_bank as _f
    return await _f(*args, **kwargs)

async def _handle_weather(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_weather as _f
    return await _f(*args, **kwargs)

async def _handle_calendar(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_calendar as _f
    return await _f(*args, **kwargs)

async def _handle_advance(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_advance as _f
    return await _f(*args, **kwargs)

async def handle_fish_command(*args, **kwargs):
    from utils.commands.fishing_handler import handle_fish_command as _f
    return await _f(*args, **kwargs)

async def handle_fish_shop_command(*args, **kwargs):
    from utils.commands.fishing_handler import handle_fish_shop_command as _f
    return await _f(*args, **kwargs)

async def _handle_purify(*args, **kwargs):
    from utils.ttrpg.rpg_core_handler import _handle_purify as _f
    return await _f(*args, **kwargs)

async def _handle_raid_blockade(*args, **kwargs):
    from utils.ttrpg.rpg_combat_handler import _handle_raid_blockade as _f
    return await _f(*args, **kwargs)

async def _handle_rob_bandits(*args, **kwargs):
    from utils.ttrpg.rpg_combat_handler import _handle_rob_bandits as _f
    return await _f(*args, **kwargs)

async def _handle_farm_treat(*args, **kwargs):
    from utils.ttrpg.rpg_housing_handler import _handle_farm_treat as _f
    return await _f(*args, **kwargs)

LOCATION_COLORS = {
    "housing_district":  0x8b7355,   # warm earthy brown — home soil
    "tricklebrook_pond": 0x3a8fc1,   # deep pond blue
    "oakhaven":          0x8b7355,   # muddy brown — the square
    "stone_hearth":      0xc0622f,   # warm ember orange — the fire
    "hemlocks_store":    0x6b8e6b,   # muted green — herbs and iron
    "caravan":           0xc8a45c,   # desert gold — the traveling merchant
    "shrine":            0x9b9bc8,   # pale violet — the Silent Ones
    "watchtower":        0x8aacbf,   # steel blue — sky and wood
    # ... removed notice_board ...
    "herbalists_hut":    0x556b2f,   # dark olive green — herbs
    "oakhaven_bank":     0xb8860b,   # dark goldenrod — coins and gil
    "whisperwood_edge":  0x4a7c4e,   # forest green
    "whisperwood_deep":  0x2d5a35,   # deep dark green
    "aeridor_ruins":     0x7a6a9a,   # resonance purple
    "trade_road":        0xa08050,   # dust and dirt
    # grimstone locations removed
}


class _InteractionChannel:
    """Routes .send() through interaction.followup after a defer()."""
    def __init__(self, interaction: discord.Interaction):
        self._interaction = interaction
        self._real = interaction.channel
        self.id   = self._real.id
        self.name = getattr(self._real, 'name', '')

    async def send(self, content=None, **kwargs):
        return await self._interaction.followup.send(content, **kwargs)

    @property
    def typing(self):
        return self._real.typing


class _InteractionMsg:
    """Make a discord.Interaction quack like a message for handler reuse."""
    def __init__(self, interaction: discord.Interaction):
        self.channel  = _InteractionChannel(interaction)
        self.author   = interaction.user
        self.guild    = interaction.guild
        self.content  = ""
        self.mentions = []


def _make_interaction_send(interaction: discord.Interaction):
    """Return a send callable that routes through interaction.followup.

    Used as the `send` parameter for handlers that occasionally call
    send(channel, text) instead of msg.channel.send(embed=...).
    """
    async def _send(channel, text=None, use_code_block=None, **kwargs):
        if text is not None:
            if use_code_block is None:
                use_code_block = "```" not in str(text)
            if use_code_block:
                await interaction.followup.send(f"```\n{str(text).strip()}\n```", **kwargs)
            else:
                await interaction.followup.send(str(text).strip(), **kwargs)
        else:
            await interaction.followup.send(**kwargs)
    return _send


class StatChoiceView(discord.ui.View):
    def __init__(self, ctx, uid, uname, is_owner, primary_stat):
        super().__init__(timeout=60)
        self._ctx = ctx
        self._uid = uid
        self._uname = uname
        self._is_owner = is_owner
        self._primary = primary_stat
        
    @discord.ui.button(label="Growth A (+2 Primary)", style=discord.ButtonStyle.green)
    async def choice_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._process_choice(interaction, {self._primary: 2})
        
    @discord.ui.button(label="Growth B (+1 Pri, +1 CON)", style=discord.ButtonStyle.blurple)
    async def choice_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._process_choice(interaction, {self._primary: 1, "con": 1})
        
    @discord.ui.button(label="Growth C (+2 CON)", style=discord.ButtonStyle.grey)
    async def choice_c(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._process_choice(interaction, {"con": 2})
        
    async def _process_choice(self, interaction, gains):
        if str(interaction.user.id) != self._uid:
            return await interaction.response.send_message("This is not your choice to make.", ephemeral=True)
            
        sheet = await load(self._uid)
        if not sheet or not sheet.get("_stat_choice_pending"):
            return await interaction.response.send_message("No stat choice is currently pending for your character.", ephemeral=True)
            
        if "stats" not in sheet:
            sheet["stats"] = {"str": 10, "dex": 10, "int": 10, "wis": 10, "con": 10, "cha": 10}
            
        for stat, val in gains.items():
            sheet["stats"][stat] = sheet["stats"].get(stat, 10) + val
            
        # Retrospective HP boost if CON increased
        if "con" in gains:
            # Simple logic: increase max HP by (current_con_mod - previous_con_mod) * level, OR per rules:
            # In D&D/TTRPGs, increasing CON retroactively grants HP for all levels.
            con_gain = gains["con"]
            hp_gain = max(1, (con_gain + 1) // 2) * sheet["level"]
            sheet["hp"]["max"] += hp_gain
            sheet["hp"]["current"] += hp_gain
            
        del sheet["_stat_choice_pending"]
        await save(sheet)
        
        gains_str = ", ".join([f"+{v} {s.upper()}" for s, v in gains.items()])
        embed = discord.Embed(
            title="✨ Growth Confirmed",
            description=f"Your character has grown stronger! Applied bonuses: **{gains_str}**",
            color=0x2ECC71
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class RPGFullLocationView(discord.ui.View):
    """
    All-in-one location view.
    Row 0-2: location-specific action buttons (from _LOCATION_BUTTONS)
    Row 3: 📊 Status · 🎒 Inventory · 🗺️ Map · 📄 Sheet (always present)
    Row 4: travel select dropdown
    """

    def __init__(self, ctx_app, msg, uid: str, uname: str, is_owner: bool, location: str):
        super().__init__(timeout=120)
        self._ctx = ctx_app
        self._msg = msg
        self._uid = uid
        self._uname = uname
        self._is_owner = is_owner
        self._location = location
        
        # Build the handler dispatch map inside __init__ to avoid NameErrors
        self._handler_map = {
            "status_board": _handle_status,
            "sheet": _handle_sheet,
            "hunt": _handle_hunt,
            "rest": _handle_rest,
            "drink": _handle_drink,
            "gamble": _handle_gamble,
            "rumor": _handle_rumor,
            "shop": _handle_shop,
            "inventory": _handle_inventory,
            "pray": _handle_pray,
            "fountain": _handle_fountain,
            "offer": _handle_offer,
            "scout": _handle_scout,
            "notices": _handle_notices,
            "quests": _handle_quests,
            "brew": _handle_brew,
            "bank_deposit": _handle_bank_deposit,
            "bank_withdraw": _handle_bank_withdraw,
            "map": _handle_map,
            "look": _handle_look,
            "talk": _handle_talk,
            "calendar": _handle_calendar,
            "weather": _handle_weather,
            "mail":    _handle_mail,
            "hunts": _handle_hunts,
            "leaderboard": _handle_leaderboard,
            "dungeon": _handle_dungeon,
            "unequip": _handle_unequip,
            "advance": _handle_advance,
            "bard_song": _handle_bard_song,
            "go": _handle_go,
            "my_home":        _handle_my_home,
            "buy_house":      _handle_buy_house,
            "upgrade_house":  _handle_upgrade_house,
            "furniture_shop": _handle_furniture_shop,
            "buy_furniture":  _handle_buy_furniture,
            "pet_shop":       _handle_pet_shop,
            "buy_pet":        _handle_buy_pet,
            "feed_pet":       _handle_feed_pet,
            "farm_view":      _handle_farm_view,
            "plant_crop":     _handle_plant_crop,
            "water_crops":    _handle_water_crops,
            "harvest_crops":  _handle_harvest_crops,
            "visit_plots":    _handle_visit_plots,
            "rename_house":   _handle_rename_house,
            "home_training":  _handle_home_training,
            "seed_shop":      _handle_seed_shop,
            "fish":           handle_fish_command,
            "fish_shop":      handle_fish_shop_command,
            "sell_all_gear":  _handle_sell_all_gear,
            "purify":         _handle_purify,
            "raid":           _handle_raid_blockade,
            "rob":            _handle_rob_bandits,
            "farm_treat":     _handle_farm_treat,
        }

        # ── Location action buttons ───────────────────────────────────
        for label, emoji, cmd, rest_arg, style, row in _LOCATION_BUTTONS.get(location, []):
            self._add_btn(label, emoji, cmd, rest_arg, style, row)

        # ── Dynamic Active Noon Event Buttons (Row 2) ─────────────────
        from utils.ttrpg.world_state import load_world_state
        wstate = load_world_state()

        # 1. Tricklebrook Pond: Purify Waters (ONLY if fishing_water_tainted is active!)
        if location == "tricklebrook_pond" and wstate.get("fishing_water_tainted", False):
            self._add_btn("Purify Waters", "🧪", "purify", "", discord.ButtonStyle.success, 2)

        # 2. Trade Road & Whisperwood Edge: Raid Blockade & Rob Bandits (ONLY if blockade_active is active!)
        if location in ("trade_road", "whisperwood_edge") and wstate.get("blockade_active", False):
            self._add_btn("Raid Blockade", "⚔️", "raid", "blockade", discord.ButtonStyle.danger, 2)
            self._add_btn("Rob Bandits", "🗡️", "rob", "bandits", discord.ButtonStyle.primary, 2)

        # ── Always-present row 3 (moved up from 4) ────────────────────
        self._add_btn("Status", "📊", "status_board", "", discord.ButtonStyle.secondary, 3)
        self._add_btn("Sheet", "📄", "sheet", "", discord.ButtonStyle.secondary, 3)
        self._add_btn("Inventory", "🎒", "inventory", "", discord.ButtonStyle.secondary, 3)
        self._add_btn("Map", "🗺️", "map", "", discord.ButtonStyle.secondary, 3)

        # ── Travel select (row 4 — moved down from 3) ─────────────────
        from utils.ttrpg.world import LOCATION_DATA
        from utils.ttrpg.world_state import load_world_state
        state = load_world_state()
        active = state.get("caravan_active", False)

        if location == "housing_district":
            # Housing district special dropdown — only Oakhaven + player plots
            from utils.ttrpg.housing import load_all_housing, HOUSING_TIERS
            all_housing = load_all_housing()
            
            options = [discord.SelectOption(
                label="Oakhaven Town Square",
                value="oakhaven",
                emoji="🏘️"
            )]
            for h in sorted(all_housing, key=lambda x: x.get("last_updated", 0), reverse=True)[:20]:
                tier_data = HOUSING_TIERS.get(h.get("tier", "hut"), {})
                options.append(discord.SelectOption(
                    label=h.get("house_name", f"{h['character_name']}'s Home")[:100],
                    value=f"visit_{h['user_id']}",
                    emoji=tier_data.get("emoji", "🏡"),
                    description=f"{tier_data.get('name', 'Home')} · {h['character_name']}"
                ))
            
            sel = discord.ui.Select(placeholder="Visit a plot...", options=options[:25], row=4)
        else:
            all_locs = []
            for k in LOCATION_DATA.keys():
                if k == location:
                    continue
                all_locs.append(k)

            all_locs.sort(key=lambda k: 1 if LOCATION_DATA.get(k, {}).get("hunting") else 0)
            if all_locs:
                options = []
                for ex in all_locs[:25]:
                    td = LOCATION_DATA.get(ex, {})
                    lbl = td.get("name", ex.replace("_", " ").title())
                    em = "🗡️" if td.get("hunting") else "📍"
                    options.append(discord.SelectOption(label=lbl[:100], value=ex, emoji=em))

                sel = discord.ui.Select(placeholder="Travel to...", options=options, row=4)
            else:
                sel = None

        if sel:
            async def _travel_cb(interaction: discord.Interaction, _sel=sel):
                if str(interaction.user.id) != self._uid:
                    await interaction.response.send_message("```\nnot your menu.\n```", ephemeral=True)
                    return
                
                try:
                    chosen = interaction.data["values"][0]
                    await interaction.response.defer()
                    fake = _InteractionMsg(interaction)
                    sfn = _make_interaction_send(interaction)
                    
                    if chosen.startswith("visit_"):
                        target_uid = chosen.replace("visit_", "")
                        await _handle_visit_plots(self._ctx, fake, sfn, target_uid, self._uid, self._uname, self._is_owner)
                    else:
                        await _handle_go(self._ctx, fake, sfn, chosen, self._uid, self._uname, self._is_owner)
                except Exception as e:
                    import traceback
                    log_error(f"[rpg travel] {e}\n{traceback.format_exc()}")
                    try:
                        await interaction.followup.send(f"```\nTravel failed: {e}\n```", ephemeral=True)
                    except Exception: pass

            sel.callback = _travel_cb
            self.add_item(sel)

    def _add_btn(self, label: str, emoji: str, cmd: str, rest_arg: str,
                 style: discord.ButtonStyle, row: int):
        btn = discord.ui.Button(label=label, emoji=emoji, style=style, row=row)

        async def cb(interaction: discord.Interaction, _cmd=cmd, _rest=rest_arg):
            if str(interaction.user.id) != self._uid:
                try:
                    await interaction.response.send_message(
                        "```\nthese aren't your buttons.\n```", ephemeral=True)
                except discord.NotFound:
                    pass
                return
            try:
                await interaction.response.defer()
            except discord.NotFound:
                log_error(f"[rpg btn] {_cmd}: interaction expired (NotFound on defer)")
                return
            fake = _InteractionMsg(interaction)
            sfn = _make_interaction_send(interaction)
            handler = self._handler_map.get(_cmd)
            if handler:
                try:
                    await handler(self._ctx, fake, sfn, _rest,
                                  self._uid, self._uname, self._is_owner)
                except Exception as e:
                    import traceback
                    log_error(f"[rpg btn] {_cmd} failed: {e}\n{traceback.format_exc()}")
                    try:
                        await interaction.followup.send(
                            f"```\nerror in {_cmd}: {e}\n```", ephemeral=True)
                    except discord.NotFound:
                        pass

        btn.callback = cb
        self.add_item(btn)

    async def on_timeout(self):
        pass


class RPGCombatView(discord.ui.View):
    """Attack / Flee buttons shown during active combat.

    Attached to the hunt encounter embed and to combat-log embeds when the
    monster is still alive so players can keep clicking instead of typing.
    """

    def __init__(self, ctx_app, msg, uid: str, uname: str, is_owner: bool, monster_key: str):
        super().__init__(timeout=120)
        self._ctx = ctx_app
        self._msg = msg
        self._uid = uid
        self._uname = uname
        self._is_owner = is_owner
        self._monster_key = monster_key

        # ── Attack button ─────────────────────────────────────────────
        atk_btn = discord.ui.Button(
            label="⚔️ Attack", style=discord.ButtonStyle.danger, row=0
        )

        async def _attack_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != self._uid:
                try:
                    await interaction.response.send_message(
                        "```\nthese aren't your buttons.\n```", ephemeral=True
                    )
                except discord.NotFound:
                    pass
                return
            try:
                await interaction.response.defer()
            except discord.NotFound:
                log_error("[rpg button] attack: interaction expired (NotFound on defer)")
                return
            fake_msg = _InteractionMsg(interaction)
            send_fn = _make_interaction_send(interaction)
            try:
                await _handle_attack(
                    self._ctx, fake_msg, send_fn,
                    self._monster_key, self._uid, self._uname, self._is_owner
                )
            except Exception as e:
                log_error(f"[rpg button] attack failed: {e}")
                try:
                    await interaction.followup.send(
                        "```\nerror running attack. check logs.\n```", ephemeral=True
                    )
                except discord.NotFound:
                    pass

        atk_btn.callback = _attack_cb
        self.add_item(atk_btn)

        # ── Flee button ───────────────────────────────────────────────
        flee_btn = discord.ui.Button(
            label="🏃 Flee", style=discord.ButtonStyle.secondary, row=0
        )

        async def _flee_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != self._uid:
                try:
                    await interaction.response.send_message(
                        "```\nthese aren't your buttons.\n```", ephemeral=True
                    )
                except discord.NotFound:
                    pass
                return
            try:
                await interaction.response.defer()
            except discord.NotFound:
                log_error("[rpg button] flee: interaction expired (NotFound on defer)")
                return
            fake_msg = _InteractionMsg(interaction)
            send_fn = _make_interaction_send(interaction)
            try:
                await _handle_flee(
                    self._ctx, fake_msg, send_fn,
                    "", self._uid, self._uname, self._is_owner
                )
            except Exception as e:
                log_error(f"[rpg button] flee failed: {e}")
                try:
                    await interaction.followup.send(
                        "```\nerror running flee. check logs.\n```", ephemeral=True
                    )
                except discord.NotFound:
                    pass

        flee_btn.callback = _flee_cb
        self.add_item(flee_btn)

        # ── Use Item button ───────────────────────────────────────────────
        use_btn = discord.ui.Button(
            label="🧪 Use Item", style=discord.ButtonStyle.secondary, row=0
        )

        async def _use_item_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != self._uid:
                await interaction.response.send_message(
                    "```\nnot your buttons.\n```", ephemeral=True
                )
                return

            sheet = await load(self._uid)
            if not sheet:
                await interaction.response.send_message(
                    "```\nno character found.\n```", ephemeral=True
                )
                return

            from utils.ttrpg.shop import find_item as _find_item
            from collections import Counter

            inventory = sheet.get("inventory", [])
            inv_counts = Counter(inventory)

            # Only show usable consumables (healing, cure, buff)
            usable = []
            for item_key, count in inv_counts.items():
                item = _find_item(item_key)
                if not item or item["category"] != "consumable":
                    continue
                hp_restore = item.get("hp_restore", 0)
                on_use = item.get("on_use", "")
                if hp_restore > 0 or on_use in ("cure_poison", "luck_roll_bonus", "atk_boost", "def_boost", "hunt_bonus", "xp_bonus"):
                    if hp_restore > 0:
                        label = f"{item['name']} (+{hp_restore} HP)"
                    elif on_use == "cure_poison":
                        label = f"{item['name']} (cures poison)"
                    elif on_use == "atk_boost":
                        label = f"{item['name']} (+2 ATK)"
                    elif on_use == "def_boost":
                        label = f"{item['name']} (+2 DEF)"
                    else:
                        label = f"{item['name']} (+1 next hit)"
                    if count > 1:
                        label += f"  x{count}"
                    usable.append((item_key, label[:100]))

            if not usable:
                await interaction.response.send_message(
                    "```\nno usable items in your pack.\n```", ephemeral=True
                )
                return

            options = [
                discord.SelectOption(label=label, value=key)
                for key, label in usable[:25]
            ]

            select_view = discord.ui.View(timeout=30)
            item_select = discord.ui.Select(
                placeholder="Choose an item to use...",
                options=options,
                row=0
            )

            async def _item_selected(sel_interaction: discord.Interaction):
                if str(sel_interaction.user.id) != self._uid:
                    await sel_interaction.response.send_message("not yours", ephemeral=True)
                    return
                chosen = sel_interaction.data["values"][0]
                await sel_interaction.response.defer()
                fake_msg = _InteractionMsg(sel_interaction)
                send_fn = _make_interaction_send(sel_interaction)
                await _handle_use(
                    self._ctx, fake_msg, send_fn,
                    chosen, self._uid, self._uname, self._is_owner
                )

            item_select.callback = _item_selected
            select_view.add_item(item_select)

            hp = sheet["hp"]
            await interaction.response.send_message(
                f"```\nHP: {hp['current']}/{hp['max']}\n```",
                view=select_view,
                ephemeral=True
            )

        use_btn.callback = _use_item_cb
        self.add_item(use_btn)

    async def on_timeout(self):
        pass


def _make_status_btn(ctx, uid, uname, is_owner, row=None):
    """Helper to create a unified Status button."""
    btn = discord.ui.Button(label="📊 Status", style=discord.ButtonStyle.secondary) if row is None else discord.ui.Button(label="📊 Status", style=discord.ButtonStyle.secondary, row=row)
    async def _cb(interaction):
        if str(interaction.user.id) != uid:
            try:
                await interaction.response.send_message("not yours", ephemeral=True)
            except discord.NotFound:
                pass
            return
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return
        fake = _InteractionMsg(interaction)
        await _handle_status(ctx, fake, _make_interaction_send(interaction), "", uid, uname, is_owner)
    btn.callback = _cb
    return btn


async def _make_shop_view(ctx, msg, uid, uname, is_owner, items, sheet=None):
    """Return a View with categorized Buy (gear / consumable) and Sell select menus."""
    from utils.ttrpg.shop import find_item
    from collections import Counter
    from utils.ttrpg.calendar import get_special_day

    view = discord.ui.View(timeout=120)

    SLOT_PREFIX = {
        "weapon":    "[Weapon]",
        "armor":     "[Armor]",
        "head":      "[Head]",
        "boots":     "[Boots]",
        "accessory": "[Accessory]",
    }

    special = get_special_day()
    sheet = sheet or await load(uid)
    loc = sheet.get("location", "hemlocks_store") if sheet else "hemlocks_store"

    from utils.ttrpg.world_state import load_world_state
    _wstate = load_world_state()
    _special_sale = _wstate.get("special_item_sale")

    def _ui_price(item_key, base_value):
        if special and "shop_special" in special and loc == "hemlocks_store":
            if special["shop_special"].get("item") == item_key:
                return special["shop_special"].get("price", base_value)
        # Noon event special_item_sale override
        if _special_sale and isinstance(_special_sale, dict) and loc == "hemlocks_store":
            if _special_sale.get("item") == item_key:
                return _special_sale.get("price", base_value)
        return base_value

    # ── Separate items into gear vs consumables ───────────────────────────────
    items_sorted = sorted(items, key=lambda k: (find_item(k) or {}).get("name", k))
    gear_items = []
    consumable_items = []
    for item_key in items_sorted:
        item = find_item(item_key)
        if not item:
            continue
        if item["category"] == "consumable":
            consumable_items.append(item_key)
        elif item["category"] in ("weapon", "armor", "head", "boots", "accessory"):
            gear_items.append(item_key)

    current_row = 0

    # ── Gear buy selects (rows 0–1, max 50 items) ─────────────────────────────
    gear_chunks = [gear_items[i:i + 25] for i in range(0, len(gear_items), 25)]
    for chunk in gear_chunks:
        if current_row >= 2:
            break
        options = []
        for item_key in chunk:
            item = find_item(item_key)
            if not item:
                continue
            price = _ui_price(item_key, item["value"])
            prefix = SLOT_PREFIX.get(item["category"], "")
            class_tag = _get_class_abbr_string(item)
            label = f"{prefix} {item['name']} ({price}g){class_tag}"
            options.append(discord.SelectOption(label=label[:100], value=item_key))

        if options:
            placeholder = "⚔️ Buy gear..." if current_row == 0 else "⚔️ Buy gear (more)..."
            buy_gear_sel = discord.ui.Select(
                placeholder=placeholder, options=options[:25], row=current_row
            )
            async def _buy_gear_cb(interaction: discord.Interaction):
                if str(interaction.user.id) != uid:
                    await interaction.response.send_message("```\nnot your menu.\n```", ephemeral=True)
                    return
                chosen = interaction.data["values"][0]
                await interaction.response.defer()
                fake_msg = _InteractionMsg(interaction)
                send_fn = _make_interaction_send(interaction)
                await _handle_buy(ctx, fake_msg, send_fn, chosen, uid, uname, is_owner)
            buy_gear_sel.callback = _buy_gear_cb
            view.add_item(buy_gear_sel)
            current_row += 1

    # ── Consumable buy select (one row, quantity picker) ──────────────────────
    if consumable_items and current_row < 3:
        cons_options = []
        for item_key in consumable_items[:25]:
            item = find_item(item_key)
            if not item:
                continue
            price = _ui_price(item_key, item["value"])
            label = f"🧪 {item['name']} ({price}g){_get_item_effect_string(item)}"
            cons_options.append(discord.SelectOption(label=label[:100], value=item_key))

        if cons_options:
            buy_cons_sel = discord.ui.Select(
                placeholder="🧪 Buy consumables...", options=cons_options, row=current_row
            )
            async def _buy_cons_cb(interaction: discord.Interaction):
                if str(interaction.user.id) != uid:
                    await interaction.response.send_message("```\nnot your menu.\n```", ephemeral=True)
                    return
                chosen = interaction.data["values"][0]
                item = find_item(chosen)
                if item and item.get("category") == "consumable":
                    s = await load(uid)
                    on_hand = s.get("gil", 0) if s else 0
                    ui_value = _ui_price(chosen, item["value"])
                    embed_desc = (
                        f"**{ui_value}g each**\n"
                        f"You have **{on_hand}g** on hand.\n\n"
                        f"*{item.get('description', '')}*"
                        if item.get("description") else
                        f"**{ui_value}g each** — You have **{on_hand}g** on hand."
                    )
                    embed = discord.Embed(
                        title=f"🧪 {item['name']}",
                        description=embed_desc,
                        color=0x44aa44
                    )
                    qty_view = ConsumableQuantityView(ctx, msg, uid, uname, is_owner, chosen, item)
                    await interaction.response.send_message(embed=embed, view=qty_view, ephemeral=True)
                    return
                await interaction.response.defer()
                fake_msg = _InteractionMsg(interaction)
                send_fn = _make_interaction_send(interaction)
                await _handle_buy(ctx, fake_msg, send_fn, chosen, uid, uname, is_owner)
            buy_cons_sel.callback = _buy_cons_cb
            view.add_item(buy_cons_sel)
            current_row += 1

    # ── Sell select — gear first (slot-prefixed), then consumables ────────────
    if sheet and sheet.get("inventory"):
        inv_counts = Counter(sheet["inventory"])
        gear_sell_opts = []
        cons_sell_opts = []

        for item_key, count in sorted(
            inv_counts.items(),
            key=lambda kv: (find_item(kv[0]) or {}).get("name", kv[0])
        ):
            item = find_item(item_key)
            if not item:
                continue
            from utils.ttrpg.shop import get_sell_price
            cha_mod = (sheet.get("stats", {}).get("cha", 10) - 10) // 2 if sheet else 0
            reputation = sheet.get("reputation", 0) if sheet else 0
            sell_val = get_sell_price(item["value"], reputation, cha_mod)
            count_tag = f" ×{count}" if count > 1 else ""
            base_label = f"{item['name']}{count_tag} ({sell_val}g ea)" if count > 1 else f"{item['name']} ({sell_val}g)"

            if item["category"] in ("weapon", "armor", "head", "boots", "accessory"):
                prefix = SLOT_PREFIX.get(item["category"], "")
                class_tag = _get_class_abbr_string(item)
                gear_sell_opts.append(
                    discord.SelectOption(label=f"{prefix} {base_label}{class_tag}"[:100], value=item_key)
                )
            elif item["category"] == "consumable":
                cons_sell_opts.append(
                    discord.SelectOption(label=base_label[:100], value=item_key)
                )

        all_sell_opts = gear_sell_opts + cons_sell_opts
        if all_sell_opts and current_row < 4:
            sell_sel = discord.ui.Select(
                placeholder="💰 Sell an item...",
                options=all_sell_opts[:25],
                row=current_row
            )
            async def _sell_cb(interaction: discord.Interaction):
                if str(interaction.user.id) != uid:
                    await interaction.response.send_message("```\nnot your menu.\n```", ephemeral=True)
                    return
                chosen = interaction.data["values"][0]
                await interaction.response.defer()
                fake_msg = _InteractionMsg(interaction)
                send_fn = _make_interaction_send(interaction)
                await _handle_sell(ctx, fake_msg, send_fn, chosen, uid, uname, is_owner)
            sell_sel.callback = _sell_cb
            view.add_item(sell_sel)
            current_row += 1

    # ── Buyback ───────────────────────────────────────────────────────────────
    buyback_items = (sheet.get("buyback", []) if sheet else [])
    
    # ── Button row ────────────────────────────────────────────────────────────
    btn_row = min(current_row, 4)

    if buyback_items:
        bb_btn = discord.ui.Button(
            label="↩️ Buyback", style=discord.ButtonStyle.secondary, row=btn_row
        )
        async def _open_buyback_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("not yours.", ephemeral=True)
                return
            s = await load(uid)
            if not s:
                return
            buyback_list = s.get("buyback", [])
            if not buyback_list:
                await interaction.response.send_message("No items available for buyback.", ephemeral=True)
                return

            bb_options = [
                discord.SelectOption(
                    label=f"{entry['name']} ({entry['repurchase_price']}g)"[:100],
                    value=f"{i}|{entry.get('key', str(i))}",
                    description="Buyback at original sell price"
                )
                for i, entry in enumerate(buyback_list[:25])
            ]
            
            bb_sel = discord.ui.Select(
                placeholder="↩️ Choose item to buyback...",
                options=bb_options,
                row=0
            )

            async def _buyback_sel_cb(sel_interaction: discord.Interaction):
                if str(sel_interaction.user.id) != uid:
                    await sel_interaction.response.send_message("not yours.", ephemeral=True)
                    return
                await sel_interaction.response.defer()
                raw_val = sel_interaction.data["values"][0]
                expected_key = raw_val.split("|", 1)[1] if "|" in raw_val else None
                fresh_s = await load(uid)
                curr_buyback = fresh_s.get("buyback", [])
                entry = None
                actual_idx = None
                if expected_key:
                    for i, b in enumerate(curr_buyback):
                        if b.get("key") == expected_key:
                            entry, actual_idx = b, i
                            break
                if entry is None:
                    fallback = int(raw_val.split("|")[0]) if "|" in raw_val else int(raw_val)
                    if fallback < len(curr_buyback):
                        entry, actual_idx = curr_buyback[fallback], fallback
                if entry is None or actual_idx is None:
                    await sel_interaction.followup.send(
                        embed=discord.Embed(description="That item is no longer available for buyback.", color=0xcc4444),
                        ephemeral=True
                    )
                    return
                cost = entry["repurchase_price"]
                if fresh_s.get("gil", 0) < cost:
                    await sel_interaction.followup.send(
                        embed=discord.Embed(description=f"Not enough gil. Buyback costs {cost}g. You have {fresh_s['gil']}g.", color=0xcc4444),
                        ephemeral=True
                    )
                    return
                fresh_s["gil"] -= cost
                fresh_s.setdefault("inventory", []).append(entry["key"])
                fresh_s["buyback"].pop(actual_idx)
                await save(fresh_s)
                await sel_interaction.followup.send(embed=discord.Embed(
                    description=f"↩️ **{entry['name']}** returned to your inventory for {cost}g.\nRemaining gil: {fresh_s['gil']}g",
                    color=0x44aa44
                ), ephemeral=True)
                
            bb_sel.callback = _buyback_sel_cb
            bb_view = discord.ui.View(timeout=60)
            bb_view.add_item(bb_sel)
            await interaction.response.send_message("Select an item to buy back:", view=bb_view, ephemeral=True)

        bb_btn.callback = _open_buyback_cb
        view.add_item(bb_btn)

    if sheet and sheet.get("inventory"):
        sell_all_btn = discord.ui.Button(
            label="💰 Sell All Loot", style=discord.ButtonStyle.danger, row=btn_row
        )
        async def _sell_all_shop_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("not yours.", ephemeral=True)
                return
            await interaction.response.defer()
            fake_msg = _InteractionMsg(interaction)
            send_fn = _make_interaction_send(interaction)
            await _handle_sell_all_gear(ctx, fake_msg, send_fn, "", uid, uname, is_owner)
        sell_all_btn.callback = _sell_all_shop_cb
        view.add_item(sell_all_btn)

    view.add_item(_make_status_btn(ctx, uid, uname, is_owner, row=btn_row))
    return view


def _make_status_view(ctx, msg, uid, uname, is_owner):
    """Return a View with a single 📊 Status button that re-opens the HUD."""
    view = discord.ui.View(timeout=60)
    view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
    return view


async def _get_active_view(ctx, msg, uid, uname, is_owner):
    """Returns the correct view context: overworld combat, dungeon combat, dungeon map, or None."""
    s = await load_session(str(msg.channel.id))
    if s and s.get("combat_active"):
        for m in s.get("monsters", []):
            if m.get("aggro_uid") == uid:
                return RPGCombatView(ctx, msg, uid, uname, is_owner, m.get("key", "monster"))

    from utils.ttrpg.dungeon import load_dungeon
    d_state = await load_dungeon(uid)
    if d_state and d_state.get("active"):
        ac = d_state.get("active_combat")
        if ac:
            monster = ac.get("monster", {})
            m_name = ac.get("boss_name") or monster.get("name", "monster")
            return DungeonCombatView(ctx, uid, uname, is_owner, m_name)
        else:
            return DungeonView(ctx, uid, uname, is_owner, d_state)

    from utils.ttrpg.spine_dungeon import load_spine_dungeon
    s_state = await load_spine_dungeon(uid)
    if s_state and s_state.get("active"):
        ac = s_state.get("active_combat")
        if ac:
            monster = ac.get("monster", {})
            m_name = ac.get("boss_name") or monster.get("name", "monster")
            return DungeonCombatView(ctx, uid, uname, is_owner, m_name)
        else:
            return DungeonView(ctx, uid, uname, is_owner, s_state)

    return None


def _make_map_view(ctx, msg, uid, uname, is_owner, loc):
    """Return a full location view — used after blizzard/no-hunt redirects."""
    return RPGFullLocationView(ctx, msg, uid, uname, is_owner, loc)


class BossApproachView(discord.ui.View):
    """
    Warning view shown when the player is about to enter an uncleared boss room.
    Gives them the chance to turn back and clear the rest of the dungeon first.
    """

    def __init__(self, ctx_obj, uid: str, uname: str, is_owner: bool, direction: str, is_spine: bool = False):
        super().__init__(timeout=120)
        self._ctx      = ctx_obj
        self._uid      = uid
        self._uname    = uname
        self._is_owner = is_owner
        self._direction = direction
        self._is_spine = is_spine

    @discord.ui.button(label="⚔️ Press Forward", style=discord.ButtonStyle.danger, row=0)
    async def press_forward(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self._uid:
            try:
                await interaction.response.send_message("not your dungeon.", ephemeral=True)
            except discord.NotFound:
                pass
            return
        try:
            await interaction.response.defer()
        except discord.NotFound:
            pass
        # boss_warned flag is already set — _dungeon_move will skip the warning and proceed
        await _dungeon_move(
            self._ctx, interaction, self._uid,
            self._uname, self._is_owner, self._direction
        )

    @discord.ui.button(label="↩️ Retreat", style=discord.ButtonStyle.secondary, row=0)
    async def retreat(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self._uid:
            try:
                await interaction.response.send_message("not your dungeon.", ephemeral=True)
            except discord.NotFound:
                pass
            return
        try:
            await interaction.response.defer()
        except discord.NotFound:
            pass
        
        if self._is_spine:
            from utils.ttrpg.spine_dungeon import load_spine_dungeon
            state = await load_spine_dungeon(self._uid)
        else:
            from utils.ttrpg.dungeon import load_dungeon
            state = await load_dungeon(self._uid)
            
        if not state:
            try:
                await interaction.followup.send("Dungeon state lost.", ephemeral=True)
            except discord.NotFound:
                pass
            return
        embed = discord.Embed(
            description="*You pull back into the corridor. Whatever waits ahead is still there. So is everything you haven't cleared yet.*",
            color=0x888888
        )
        view = DungeonView(self._ctx, self._uid, self._uname, self._is_owner, state)
        await interaction.followup.send(embed=embed, view=view)

    async def on_timeout(self):
        pass

class SpineLiftView(discord.ui.View):
    def __init__(self, ctx_obj, uid, uname, is_owner, sheet, max_floor_defeated, has_lightstone=True):
        super().__init__(timeout=120)
        self._ctx = ctx_obj
        self._uid = uid
        self._uname = uname
        self._is_owner = is_owner
        self._sheet = sheet
        self._has_lightstone = has_lightstone
        
        # Build options for floors: 1, 5, 10, 15... up to highest multiple of 5 <= max_floor_defeated
        options = [discord.SelectOption(label="Floor 1", description="The Working Tunnels", value="1")]
        for f in range(5, max_floor_defeated + 1, 5):
            options.append(discord.SelectOption(label=f"Floor {f}", description="Start from checkpoint", value=str(f)))
            
        lift_sel = discord.ui.Select(
            placeholder="🔽 Select a floor to descend to...",
            options=options,
            row=0
        )
        
        async def _lift_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != self._uid:
                try: await interaction.response.send_message("Not your lift.", ephemeral=True)
                except discord.NotFound: pass
                return
            await interaction.response.defer()
            
            target_floor = int(interaction.data["values"][0])
            
            from utils.ttrpg.progression import check_and_reset_hunts, hunts_remaining, get_max_hunts
            from utils.ttrpg.character_manager import load, save
            
            fresh_sheet = await load(self._uid)
            fresh_sheet = check_and_reset_hunts(fresh_sheet)
            ENTRY_HUNTS = 2
            
            if hunts_remaining(fresh_sheet) < ENTRY_HUNTS:
                try:
                    await interaction.followup.send(embed=discord.Embed(
                        description=f"Entering costs **{ENTRY_HUNTS} hunts**. You have {hunts_remaining(fresh_sheet)}/{get_max_hunts(fresh_sheet)}.",
                        color=0xcc4444), ephemeral=True)
                except discord.NotFound: pass
                return
            
            # Consume torch on actual entry (lightstone is permanent)
            if not self._has_lightstone and "torch" in fresh_sheet.get("inventory", []):
                fresh_sheet["inventory"].remove("torch")
                
            fresh_sheet["hunts_today"] = fresh_sheet.get("hunts_today", 0) + ENTRY_HUNTS
            await save(fresh_sheet)
            
            from utils.ttrpg.spine_dungeon import generate_spine_floor, save_spine_dungeon
            dungeon = generate_spine_floor(target_floor, fresh_sheet["level"])
            dungeon["active"] = True
            await save_spine_dungeon(self._uid, dungeon)
            
            from utils.ttrpg.rpg_combat_handler import _send_dungeon_room
            await _send_dungeon_room(self._ctx, interaction.channel, self._uid, self._uname, self._is_owner, dungeon)
            
        lift_sel.callback = _lift_cb
        self.add_item(lift_sel)

class DungeonView(discord.ui.View):
    def __init__(self, ctx_obj, uid, uname, is_owner, dungeon):
        super().__init__(timeout=300)
        self._ctx      = ctx_obj
        self._uid      = uid
        self._uname    = uname
        self._is_owner = is_owner

        px, py = dungeon["player_pos"]
        valid  = dungeon["connections"].get(f"{px},{py}", [])

        # Direction layout: N row 0, W+E row 1, S row 2
        dir_cfg = [("N","⬆️",0), ("W","⬅️",1), ("E","➡️",1), ("S","⬇️",2)]
        for d, emoji, row in dir_cfg:
            btn = discord.ui.Button(
                label=emoji, row=row,
                style=discord.ButtonStyle.primary if d in valid else discord.ButtonStyle.secondary,
                disabled=d not in valid,
            )
            if d in valid:
                async def _move(interaction, direction=d):
                    if str(interaction.user.id) != self._uid:
                        try:
                            await interaction.response.send_message("not your dungeon.", ephemeral=True)
                        except discord.NotFound:
                            pass
                        return
                    try:
                        await interaction.response.defer()
                    except discord.NotFound:
                        pass
                    await _dungeon_move(self._ctx, interaction, self._uid,
                                        self._uname, self._is_owner, direction)
                btn.callback = _move
            self.add_item(btn)

        # Row 3: map + leave + status
        map_btn = discord.ui.Button(label="🗺️ Map", style=discord.ButtonStyle.secondary, row=3)
        async def _show_map(interaction):
            if str(interaction.user.id) != self._uid:
                try:
                    await interaction.response.send_message("not yours", ephemeral=True)
                except discord.NotFound:
                    pass
                return
            try:
                await interaction.response.defer(ephemeral=True)
            except discord.NotFound:
                pass
            from utils.ttrpg.dungeon import load_dungeon, render_map
            from utils.ttrpg.spine_dungeon import load_spine_dungeon, render_spine_map
            
            is_spine = dungeon.get("is_spine", False)
            if is_spine:
                state = await load_spine_dungeon(self._uid)
                map_str = render_spine_map(state) if state else "no dungeon found"
            else:
                state = await load_dungeon(self._uid)
                map_str = render_map(state) if state else "no dungeon found"
                
            if not state:
                try:
                    await interaction.followup.send("no dungeon found", ephemeral=True)
                except discord.NotFound:
                    pass
                return
            try:
                await interaction.followup.send(
                    embed=discord.Embed(title="🗺️ Dungeon Map",
                                        description=map_str, color=0x7a6a9a),
                    ephemeral=True)
            except discord.NotFound:
                pass
        map_btn.callback = _show_map
        self.add_item(map_btn)

        leave_btn = discord.ui.Button(label="🏃 Leave", style=discord.ButtonStyle.danger, row=3)
        async def _leave_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != self._uid:
                try: await interaction.response.send_message("Not your dungeon.", ephemeral=True)
                except discord.NotFound: pass
                return
            await interaction.response.defer()
            if dungeon.get("is_spine"):
                from utils.ttrpg.spine_dungeon import save_spine_dungeon
                dungeon["active"] = False
                await save_spine_dungeon(self._uid, dungeon)
            else:
                from utils.ttrpg.dungeon import clear_dungeon
                await clear_dungeon(self._uid)
            await interaction.followup.send("You have left the dungeon and returned to the entrance.")
        leave_btn.callback = _leave_cb
        self.add_item(leave_btn)

        status_btn = discord.ui.Button(label="📊 Status", style=discord.ButtonStyle.secondary, row=3)
        async def _status_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != self._uid:
                try: await interaction.response.send_message("Not yours.", ephemeral=True)
                except discord.NotFound: pass
                return
            try: await interaction.response.defer()
            except discord.NotFound: pass
            fake = _InteractionMsg(interaction)
            await _handle_status(self._ctx, fake, _make_interaction_send(interaction), "", self._uid, self._uname, self._is_owner)
        status_btn.callback = _status_cb
        self.add_item(status_btn)

        if dungeon.get("is_spine"):
            rt = dungeon["rooms"].get(f"{px},{py}", {}).get("type", "empty")
            if rt == "stairs_down":
                descend_btn = discord.ui.Button(label="🔽 Descend", style=discord.ButtonStyle.success, row=4)
                async def _descend_cb(interaction: discord.Interaction):
                    if str(interaction.user.id) != self._uid: return
                    await interaction.response.defer()
                    from utils.ttrpg.spine_dungeon import generate_spine_floor, save_spine_dungeon, load_spine_dungeon, MAX_FLOOR, STAIR_GUARDIANS, _xy
                    current_floor = dungeon.get("floor_num", 1)
                    if current_floor >= MAX_FLOOR:
                        await interaction.followup.send("You have reached the bottom. There is no deeper.", ephemeral=True)
                        return
                    
                    # Stair Guardian Check
                    guardian_key = STAIR_GUARDIANS.get(current_floor)
                    sheet = await load(self._uid)
                    defeated_guards = sheet.get("spine_defeated_guards", []) if sheet else []
                    
                    if guardian_key and current_floor not in defeated_guards:
                        # Force into combat with the guardian
                        g_monster = get_monster(guardian_key)
                        if not g_monster:
                            g_monster = get_monster("behemoth") # fallback
                        
                        raw_hp = g_monster["hp"]
                        g_monster["hp"] = {"current": raw_hp, "max": raw_hp}
                        
                        dungeon["active_combat"] = {
                            "monster": g_monster,
                            "monster_key": guardian_key,
                            "is_boss": g_monster.get("tier") == "boss",
                            "room_key": f"{px},{py}"
                        }
                        await save_spine_dungeon(self._uid, dungeon)
                        await interaction.followup.send(f"**A massive presence blocks the stairs.**", ephemeral=True)
                        await _send_dungeon_room(self._ctx, interaction.channel, self._uid, self._uname, self._is_owner, dungeon)
                        return

                    # Deactivate current floor before leaving
                    dungeon["active"] = False
                    await save_spine_dungeon(self._uid, dungeon)

                    new_state = await load_spine_dungeon(self._uid, target_floor=current_floor + 1)
                    if not new_state:
                        new_state = generate_spine_floor(current_floor + 1, dungeon.get("player_level", 1))
                    
                    new_state["player_pos"] = list(_xy(new_state["stairs_up_key"]))
                    new_state["active"] = True
                    await save_spine_dungeon(self._uid, new_state)
                    await _send_dungeon_room(self._ctx, interaction.channel, self._uid, self._uname, self._is_owner, new_state, extra_text="\n\n*You descend into the dark.*")
                descend_btn.callback = _descend_cb
                self.add_item(descend_btn)
            elif rt == "stairs_up" and dungeon.get("floor_num", 1) > 1:
                ascend_btn = discord.ui.Button(label="🔼 Ascend", style=discord.ButtonStyle.success, row=4)
                async def _ascend_cb(interaction: discord.Interaction):
                    if str(interaction.user.id) != self._uid: return
                    await interaction.response.defer()
                    from utils.ttrpg.spine_dungeon import generate_spine_floor, save_spine_dungeon, load_spine_dungeon, _xy
                    
                    # Deactivate current floor before leaving
                    dungeon["active"] = False
                    await save_spine_dungeon(self._uid, dungeon)
                    
                    current_floor = dungeon.get("floor_num", 1)
                    new_state = await load_spine_dungeon(self._uid, target_floor=current_floor - 1)
                    if not new_state:
                        new_state = generate_spine_floor(current_floor - 1, dungeon.get("player_level", 1))
                    
                    new_state["player_pos"] = list(_xy(new_state["stairs_down_key"]))
                    new_state["active"] = True
                    await save_spine_dungeon(self._uid, new_state)
                    await _send_dungeon_room(self._ctx, interaction.channel, self._uid, self._uname, self._is_owner, new_state, extra_text="\n\n*You ascend the stairs.*")
                ascend_btn.callback = _ascend_cb
                self.add_item(ascend_btn)


class DungeonCombatView(discord.ui.View):
    """Turn-based combat view for dungeon encounters."""

    def __init__(self, ctx_obj, uid, uname, is_owner, monster_name):
        super().__init__(timeout=300)
        self._ctx = ctx_obj
        self._uid = uid
        self._uname = uname
        self._is_owner = is_owner

        atk_btn = discord.ui.Button(label="⚔️ Attack", style=discord.ButtonStyle.danger, row=0)
        async def _atk_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != self._uid:
                try:
                    await interaction.response.send_message("not your fight.", ephemeral=True)
                except discord.NotFound:
                    pass
                return
            try:
                await interaction.response.defer()
            except discord.NotFound:
                pass
            await _dungeon_combat_round(self._ctx, interaction, self._uid, self._uname, self._is_owner)
        atk_btn.callback = _atk_cb
        self.add_item(atk_btn)

        flee_btn = discord.ui.Button(label="🏃 Flee", style=discord.ButtonStyle.secondary, row=0)
        async def _flee_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != self._uid:
                try:
                    await interaction.response.send_message("not your fight.", ephemeral=True)
                except discord.NotFound:
                    pass
                return
            try:
                await interaction.response.defer()
            except discord.NotFound:
                pass
            await _dungeon_combat_flee(self._ctx, interaction, self._uid, self._uname, self._is_owner)
        flee_btn.callback = _flee_cb
        self.add_item(flee_btn)

        use_btn = discord.ui.Button(label="🧪 Use Item", style=discord.ButtonStyle.secondary, row=0)
        async def _use_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != self._uid:
                try:
                    await interaction.response.send_message("not yours.", ephemeral=True)
                except discord.NotFound:
                    pass
                return
            sheet = await load(self._uid)
            if not sheet:
                try:
                    await interaction.response.send_message("no character found.", ephemeral=True)
                except discord.NotFound:
                    pass
                return
            from utils.ttrpg.shop import find_item as _fi
            from collections import Counter
            inv_counts = Counter(sheet.get("inventory", []))
            usable = []
            for item_key, count in inv_counts.items():
                item = _fi(item_key)
                if not item or item["category"] != "consumable": continue
                hp_restore = item.get("hp_restore", 0)
                on_use = item.get("on_use", "")
                if hp_restore > 0 or on_use in ("cure_poison", "luck_roll_bonus", "atk_boost", "def_boost", "hunt_bonus", "xp_bonus"):
                    if hp_restore > 0:
                        label = f"{item['name']} (+{hp_restore} HP)"
                    elif on_use == "cure_poison":
                        label = f"{item['name']} (Cure Poison)"
                    elif on_use == "luck_roll_bonus":
                        label = f"{item['name']} (Lucky)"
                    elif on_use == "atk_boost":
                        label = f"{item['name']} (+2 ATK Encounter)"
                    elif on_use == "def_boost":
                        label = f"{item['name']} (+2 DEF Encounter)"
                    elif on_use == "hunt_bonus":
                        label = f"{item['name']} (+1 Hunt)"
                    elif on_use == "xp_bonus":
                        label = f"{item['name']} (+25% XP)"
                    else:
                        label = item["name"]
                    if count > 1: label += f"  x{count}"
                    usable.append((item_key, label[:100]))
            if not usable:
                try:
                    await interaction.response.send_message("```\nno usable items.\n```", ephemeral=True)
                except discord.NotFound:
                    pass
                return
            options = [discord.SelectOption(label=label, value=key) for key, label in usable[:25]]
            sel_view = discord.ui.View(timeout=30)
            sel = discord.ui.Select(placeholder="Use item...", options=options, row=0)
            async def _selected(sel_interaction: discord.Interaction):
                if str(sel_interaction.user.id) != self._uid:
                    try:
                        await sel_interaction.response.send_message("not yours.", ephemeral=True)
                    except discord.NotFound:
                        pass
                    return
                chosen = sel_interaction.data["values"][0]
                try:
                    await sel_interaction.response.defer()
                except discord.NotFound:
                    pass
                fake_msg = _InteractionMsg(sel_interaction)
                send_fn = _make_interaction_send(sel_interaction)
                await _handle_use(self._ctx, fake_msg, send_fn, chosen, self._uid, self._uname, self._is_owner)
            sel.callback = _selected
            sel_view.add_item(sel)
            hp = sheet["hp"]
            try:
                await interaction.response.send_message(f"```\nHP: {hp['current']}/{hp['max']}\n```", view=sel_view, ephemeral=True)
            except discord.NotFound:
                pass
        use_btn.callback = _use_cb
        self.add_item(use_btn)

    async def on_timeout(self):
        pass


class MailMenuView(discord.ui.View):
    def __init__(self, ctx, msg, uid, uname, is_owner, sheet):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.msg = msg
        self.uid = uid
        self.uname = uname
        self.is_owner = is_owner
        self.sheet = sheet

    @discord.ui.button(label="Check Mail", emoji="📬", style=discord.ButtonStyle.primary)
    async def check_mail(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.uid: return
        
        mailbox = self.sheet.get("mailbox", [])
        if not mailbox:
            return await interaction.response.send_message("Kupo! Nothing here but dust bunnies.", ephemeral=True)
        
        await interaction.response.defer()
        
        total_gil = 0
        mail_lines = []
        for entry in mailbox:
            sender = entry.get("from_name", "Unknown")
            parts = []
            if entry.get("item"):
                self.sheet["inventory"].append(entry["item"])
                item_name = entry["item"].replace("_", " ").title()
                parts.append(f"📦 **{item_name}**")
            if entry.get("gil", 0) > 0:
                parts.append(f"💰 **{entry['gil']}g**")
                total_gil += entry["gil"]
            if parts:
                mail_lines.append(f"From **{sender}**: {', '.join(parts)}")
            else:
                mail_lines.append(f"From **{sender}**: *(empty letter — it's the thought that counts)*")
        
        self.sheet["gil"] += total_gil
        self.sheet["mailbox"] = []
        await save(self.sheet)
        
        res = "Kupo! You received:\n" + "\n".join(mail_lines)
        
        embed = discord.Embed(description=res, color=0x44aa44)
        view = _make_status_view(self.ctx, self.msg, self.uid, self.uname, self.is_owner)
        await interaction.followup.send(embed=embed, view=view)

    @discord.ui.button(label="Send Mail", emoji="📩", style=discord.ButtonStyle.secondary)
    async def send_mail_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.uid: return
        
        all_sheets = await load_all()
        # Filter out self and limit to 25 recent-ish players
        others = [s for s in all_sheets if str(s["user_id"]) != self.uid]
        others.sort(key=lambda s: s.get("last_updated", 0), reverse=True)
        recipients = others[:25]
        
        if not recipients:
            return await interaction.response.send_message("Kupo? There's no one else in Aethelgard to write to!", ephemeral=True)

        view = MailSendView(self.ctx, self.msg, self.uid, self.uname, self.is_owner, self.sheet, recipients)
        embed = discord.Embed(
            title="📨 Prepare Dispatch",
            description="\"Kupo! Who are we sending this to? And don't forget the delivery fee is included!\"",
            color=0xf4a460
        )
        await interaction.response.edit_message(embed=embed, view=view)


class MailSendView(discord.ui.View):
    def __init__(self, ctx, msg, uid, uname, is_owner, sheet, recipients):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.msg = msg
        self.uid = uid
        self.uname = uname
        self.is_owner = is_owner
        self.sheet = sheet
        self.recipients = recipients
        
        self.selected_recipient_id = None
        self.selected_item = None
        self.gil_to_send = 0

        # Recipient Select
        options = [discord.SelectOption(label=s["character_name"], description=f"Lv.{s['level']} {s['class']}", value=str(s["user_id"])) for s in recipients]
        self.user_select = discord.ui.Select(placeholder="👤 Select Recipient...", options=options, row=0)
        self.user_select.callback = self.user_callback
        self.add_item(self.user_select)

        # Item Select
        from utils.ttrpg.shop import find_item
        from collections import Counter
        inv = self.sheet.get("inventory", [])
        if inv:
            counts = Counter(inv)
            item_options = []
            for k, v in counts.items():
                it = find_item(k)
                name = it["name"] if it else k
                item_options.append(discord.SelectOption(label=f"{name} (x{v})", value=k))
            
            self.item_select = discord.ui.Select(placeholder="📦 Attach Item (Optional)...", options=item_options[:25], row=1)
            self.item_select.callback = self.item_callback
            self.add_item(self.item_select)
        
        # Dispatch Button (Disabled until recipient picked)
        self.dispatch_btn = discord.ui.Button(label="Dispatch 📨", style=discord.ButtonStyle.green, row=2, disabled=True)
        self.dispatch_btn.callback = self.dispatch_callback
        self.add_item(self.dispatch_btn)

    async def user_callback(self, interaction: discord.Interaction):
        self.selected_recipient_id = self.user_select.values[0]
        self.dispatch_btn.disabled = False
        await interaction.response.edit_message(view=self)

    async def item_callback(self, interaction: discord.Interaction):
        self.selected_item = self.item_select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Add Gil 💰", style=discord.ButtonStyle.secondary, row=2)
    async def add_gil_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.uid: return
        modal = GilModal(self)
        await interaction.response.send_modal(modal)

    async def dispatch_callback(self, interaction: discord.Interaction):
        if not self.selected_recipient_id: return
        
        # Final validation
        if self.gil_to_send > self.sheet.get("gil", 0):
            return await interaction.response.send_message("Kupo! You don't have enough gil!", ephemeral=True)
        if self.selected_item and self.selected_item not in self.sheet.get("inventory", []):
            return await interaction.response.send_message("Kupo? That item seems to have vanished from your bag! Dispatch cancelled.", ephemeral=True)

        await interaction.response.defer()
        
        # Deduct from sender
        if self.selected_item: self.sheet["inventory"].remove(self.selected_item)
        self.sheet["gil"] -= self.gil_to_send
        await save(self.sheet)
        
        # Add to recipient
        target_sheet = await load(self.selected_recipient_id)
        if target_sheet:
            if "mailbox" not in target_sheet: target_sheet["mailbox"] = []
            target_sheet["mailbox"].append({
                "from_name": self.sheet["character_name"],
                "item": self.selected_item,
                "gil": self.gil_to_send,
                "timestamp": time.time()
            })
            await save(target_sheet)
            
        success_msg = f"📩 **Mail Dispatched!**\n*The moogle takes your package with a sharp salute and flies off toward {target_sheet['character_name'] if target_sheet else 'the horizon'}.*\n"
        if self.selected_item: 
            item_display = self.selected_item.replace('_', ' ').title()
            success_msg += f"- Attached **{item_display}**\n"
        if self.gil_to_send: success_msg += f"- Enclosed **{self.gil_to_send}g**"
        
        embed = discord.Embed(description=success_msg, color=0x44aa44)
        view = _make_status_view(self.ctx, self.msg, self.uid, self.uname, self.is_owner)
        await interaction.followup.send(embed=embed, view=view)


class GilModal(discord.ui.Modal, title="Enclose Gil"):
    gil_input = discord.ui.TextInput(label="Amount of Gil", placeholder="Enter amount...", min_length=1, max_length=6)

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        val = self.gil_input.value
        if not val.isdigit():
            return await interaction.response.send_message("Kupo! That's not a number!", ephemeral=True)
        
        amount = int(val)
        if amount < 0:
            return await interaction.response.send_message("Kupo! You can't steal gil via mail!", ephemeral=True)
            
        self.parent_view.gil_to_send = amount
        await interaction.response.send_message(f"💰 **{amount}g** noted for dispatch, kupo!", ephemeral=True)


class ConsumableQuantityView(discord.ui.View):
    """
    Shown when a player selects a consumable in the shop.
    Offers quick-buy amounts and a custom quantity modal.
    """

    def __init__(self, ctx, msg, uid: str, uname: str, is_owner: bool, item_key: str, item_data: dict):
        super().__init__(timeout=60)
        self._ctx       = ctx
        self._msg       = msg
        self._uid       = uid
        self._uname     = uname
        self._is_owner  = is_owner
        self._item_key  = item_key
        self._item_data = item_data

        price = item_data.get("value", 0)

        for label, qty in [("×1", 1), ("×5", 5), ("×10", 10), ("×20", 20)]:
            cost = price * qty
            btn = discord.ui.Button(
                label=f"{label}  ({cost}g)",
                style=discord.ButtonStyle.primary if qty == 1 else discord.ButtonStyle.secondary,
                row=0
            )
            async def _qty_cb(interaction: discord.Interaction, q=qty):
                if str(interaction.user.id) != self._uid:
                    await interaction.response.send_message("not yours.", ephemeral=True)
                    return
                await interaction.response.defer()
                fake_msg = _InteractionMsg(interaction)
                send_fn  = _make_interaction_send(interaction)
                await _handle_buy(
                    self._ctx, fake_msg, send_fn,
                    f"{self._item_key} {q}",
                    self._uid, self._uname, self._is_owner
                )
            btn.callback = _qty_cb
            self.add_item(btn)

        custom_btn = discord.ui.Button(label="📝 Custom Amount", style=discord.ButtonStyle.secondary, row=1)
        async def _custom_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != self._uid:
                await interaction.response.send_message("not yours.", ephemeral=True)
                return
            await interaction.response.send_modal(
                ConsumablePurchaseModal(
                    self._ctx, self._msg, self._uid,
                    self._uname, self._is_owner,
                    self._item_key, self._item_data
                )
            )
        custom_btn.callback = _custom_cb
        self.add_item(custom_btn)

    async def on_timeout(self):
        pass


class ConsumablePurchaseModal(discord.ui.Modal):
    quantity_input = discord.ui.TextInput(
        label="Quantity",
        placeholder="Enter a number (e.g. 15)...",
        min_length=1,
        max_length=4,
    )

    def __init__(self, ctx, msg, uid: str, uname: str, is_owner: bool, item_key: str, item_data: dict):
        super().__init__(title=f"Buy {item_data.get('name', item_key)[:40]}")
        self._ctx       = ctx
        self._msg       = msg
        self._uid       = uid
        self._uname     = uname
        self._is_owner  = is_owner
        self._item_key  = item_key
        self._item_data = item_data

    async def on_submit(self, interaction: discord.Interaction):
        val = self.quantity_input.value.strip()
        if not val.isdigit() or int(val) < 1:
            await interaction.response.send_message(
                "```\nEnter a positive whole number.\n```", ephemeral=True
            )
            return
        qty = int(val)
        await interaction.response.defer()
        fake_msg = _InteractionMsg(interaction)
        send_fn  = _make_interaction_send(interaction)
        await _handle_buy(
            self._ctx, fake_msg, send_fn,
            f"{self._item_key} {qty}",
            self._uid, self._uname, self._is_owner
        )


def _make_home_btn(ctx, uid, uname, is_owner, label, cmd, row, style=discord.ButtonStyle.secondary):
    """Helper to create a button that invokes a housing handler."""
    btn = discord.ui.Button(label=label, style=style, row=row)
    async def _cb(interaction):
        if str(interaction.user.id) != uid:
            await interaction.response.send_message("not yours", ephemeral=True)
            return
        await interaction.response.defer()
        fake = _InteractionMsg(interaction)
        handler_map = {
            "my_home": _handle_my_home,
            "buy_house": _handle_buy_house,
            "upgrade_house": _handle_upgrade_house,
            "furniture_shop": _handle_furniture_shop,
            "buy_furniture": _handle_buy_furniture,
            "pet_shop": _handle_pet_shop,
            "buy_pet": _handle_buy_pet,
            "feed_pet": _handle_feed_pet,
            "farm_view": _handle_farm_view,
            "plant_crop": _handle_plant_crop,
            "water_crops": _handle_water_crops,
            "harvest_crops": _handle_harvest_crops,
            "visit_plots": _handle_visit_plots,
            "rename_house": _handle_rename_house,
            "home_training": _handle_home_training,
            "brew": _handle_brew,
            "pray": _handle_pray,
            "bank": _handle_bank,
            "scout": _handle_scout,
        }
        handler = handler_map.get(cmd)
        if handler:
            await handler(ctx, fake, _make_interaction_send(interaction), "", uid, uname, is_owner)
    btn.callback = _cb
    return btn


class RenameHouseModal(discord.ui.Modal, title="Rename Your Home"):
    new_name = discord.ui.TextInput(
        label="New Name", 
        placeholder="Enter a name (max 50 chars)...",
        max_length=50
    )
    def __init__(self, uid):
        super().__init__()
        self.uid = uid
    async def on_submit(self, interaction):
        from utils.ttrpg.housing import load_housing_async, save_housing_async
        h = await load_housing_async(self.uid)
        if not h: return
        h["house_name"] = self.new_name.value.strip()[:50]
        await save_housing_async(h)
        await interaction.response.send_message(
            f"🏡 Your home is now named **{h['house_name']}**.", ephemeral=True
        )


RPGLocationView = RPGFullLocationView

async def _show_stat_choice(ctx, msg, send, sheet, uid, uname, is_owner):
    base_class = sheet.get("class", "Warrior")
    primary = {
        "Warrior": "str", "Ranger": "dex", "Mage": "int",
        "Rogue": "dex", "Cleric": "wis"
    }.get(base_class, "str")
    
    primary_label = primary.upper()
    
    embed = discord.Embed(
        title="✨ Level Up: Choose Your Growth",
        description=(
            f"You have reached Level {sheet['level']}! "
            "How have your recent travels shaped you? Choose a focus for your development:\n\n"
            f"• **Growth A**: +2 {primary_label} (Focus on your primary discipline)\n"
            f"• **Growth B**: +1 {primary_label}, +1 CON (A balanced approach to power and endurance)\n"
            f"• **Growth C**: +2 CON (Focus on survival and hardiness)"
        ),
        color=0xF1C40F
    )
    
    view = StatChoiceView(ctx, uid, uname, is_owner, primary)
    await msg.channel.send(embed=embed, view=view)

def _make_inventory_view(ctx, msg, uid, uname, is_owner, inventory, page_idx=0, total_pages=1, page_cb=None):
    """Return a View with Use and Equip select menus."""
    from utils.ttrpg.shop import find_item
    view = discord.ui.View(timeout=120)

    SLOT_PREFIX = {
        "weapon":    "[Weapon]",
        "armor":     "[Armor]",
        "head":      "[Head]",
        "boots":     "[Boots]",
        "accessory": "[Accessory]",
    }

    consumables = []
    gear = []

    unique_items = sorted(list(set(inventory)))
    for k in unique_items:
        it = find_item(k)
        if not it: continue
        if it["category"] == "consumable":
            consumables.append((k, it))
        elif it["category"] in ("weapon", "armor", "head", "boots", "accessory"):
            gear.append((k, it))

    if consumables:
        opts = [
            discord.SelectOption(label=f"{it['name']}{_get_item_effect_string(it)}"[:100], value=k) 
            for k, it in consumables[:25]
        ]
        sel = discord.ui.Select(placeholder="🧪 Use consumable...", options=opts, row=0)
        async def _use_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("```\nnot your menu.\n```", ephemeral=True)
                return
            chosen = interaction.data["values"][0]
            await interaction.response.defer()
            fake_msg = _InteractionMsg(interaction)
            send_fn = _make_interaction_send(interaction)
            await _handle_use(ctx, fake_msg, send_fn, chosen, uid, uname, is_owner)
        sel.callback = _use_cb
        view.add_item(sel)

    if gear:
        opts = [
            discord.SelectOption(
                label=f"{SLOT_PREFIX.get(it['category'], '')} {it['name']}{_get_class_abbr_string(it)}"[:100],
                value=k
            )
            for k, it in gear[:25]
        ]
        sel = discord.ui.Select(placeholder="⚔️ Equip gear...", options=opts, row=1)
        async def _equip_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("```\nnot your menu.\n```", ephemeral=True)
                return
            chosen = interaction.data["values"][0]
            await interaction.response.defer()
            fake_msg = _InteractionMsg(interaction)
            send_fn = _make_interaction_send(interaction)
            await _handle_equip(ctx, fake_msg, send_fn, chosen, uid, uname, is_owner)
        sel.callback = _equip_cb
        view.add_item(sel)

    if gear:
        sell_all_btn = discord.ui.Button(
            label="💰 Sell All Gear", style=discord.ButtonStyle.danger, row=2
        )
        async def _sell_all_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("not yours.", ephemeral=True)
                return
            await interaction.response.defer()
            fake_msg = _InteractionMsg(interaction)
            send_fn = _make_interaction_send(interaction)
            await _handle_sell_all_gear(ctx, fake_msg, send_fn, "", uid, uname, is_owner)
        sell_all_btn.callback = _sell_all_cb
        view.add_item(sell_all_btn)

    if total_pages > 1 and page_cb:
        prev_btn = discord.ui.Button(
            label="◀ Prev", style=discord.ButtonStyle.secondary, row=4, disabled=(page_idx == 0)
        )
        async def _prev_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != uid:
                return await interaction.response.send_message("not yours.", ephemeral=True)
            await interaction.response.defer()
            await page_cb(page_idx - 1, interaction)
        prev_btn.callback = _prev_cb
        view.add_item(prev_btn)

        next_btn = discord.ui.Button(
            label="Next ▶", style=discord.ButtonStyle.secondary, row=4, disabled=(page_idx >= total_pages - 1)
        )
        async def _next_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != uid:
                return await interaction.response.send_message("not yours.", ephemeral=True)
            await interaction.response.defer()
            await page_cb(page_idx + 1, interaction)
        next_btn.callback = _next_cb
        view.add_item(next_btn)

        view.add_item(_make_status_btn(ctx, uid, uname, is_owner, row=4))
    else:
        view.add_item(_make_status_btn(ctx, uid, uname, is_owner, row=2))

    return view

async def _narrate_combat_summary(ctx, channel, uid, uname, sheet, combat_log: list, player_won: bool):
    """Generate a single end-of-combat summary narration from the accumulated combat log."""
    from utils.ttrpg.rpg_prompt_builder import build_combat_summary_prompt
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    import uuid as _uuid

    if not combat_log:
        return

    persona = await load_persona_async()
    prompt = build_combat_summary_prompt(sheet, combat_log, player_won)
    from utils.ttrpg.rpg_prompt_builder import TTRPG_NARRATOR_OVERRIDE
    messages = [
        {"role": "system", "content": f"{persona}{TTRPG_NARRATOR_OVERRIDE}{prompt}"},
        {"role": "user",   "content": f"{uname} finished the fight."}
    ]
    gpu_manager = OllamaGPUManager(config.chat_model)
    opts = gpu_manager.get_gpu_options(for_chat=True)
    opts["num_predict"] = 200
    opts["temperature"] = 0.85

    async with channel.typing():
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
                task_id=f"rpg_combat_summary_{_uuid.uuid4().hex[:8]}"
            )
            narration = resp["message"]["content"].strip().replace("```", "")
            if narration:
                embed = discord.Embed(
                    description=f"*{narration}*",
                    color=0x2D5A27 if player_won else 0x8B0000
                )
                await channel.send(embed=embed)
        except Exception as e:
            log_error(f"[rpg combat summary] {e}")

def _make_hunt_status_view(ctx, msg, uid, uname, is_owner):
    """Return a View with 🗡️ Hunt Again + 📊 Status buttons (post-combat/event)."""
    view = discord.ui.View(timeout=60)

    hunt_btn = discord.ui.Button(label="🗡️ Hunt Again", style=discord.ButtonStyle.secondary, row=3)

    async def _hunt_cb(interaction: discord.Interaction):
        if str(interaction.user.id) != uid:
            await interaction.response.send_message("```\nnot your button.\n```", ephemeral=True)
            return
        await interaction.response.defer()
        fake_msg = _InteractionMsg(interaction)
        send_fn = _make_interaction_send(interaction)
        await _handle_hunt(ctx, fake_msg, send_fn, "", uid, uname, is_owner)

    hunt_btn.callback = _hunt_cb
    view.add_item(hunt_btn)

    view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
    return view

async def _dungeon_move(ctx_obj, interaction, uid, uname, is_owner, direction):
    from utils.ttrpg.dungeon import (DIRECTIONS, DIR_OPPOSITE,
                                      R_MONSTER, R_BOSS, R_GUARD,
                                      R_TREASURE, R_SHRINE, R_TRAP,
                                      R_ANTECHAMBER, _key)
    from utils.ttrpg.loot_tables import get_loot
    from utils.ttrpg.shop import find_item
    from utils.ttrpg.progression import check_level_up, xp_to_next_level

    sheet = await load(uid)
    if not sheet:
        return

    loc = sheet.get("location", "whisperwood_edge")
    if loc == "aeridor_ruins":
        from utils.ttrpg.spine_dungeon import load_spine_dungeon, save_spine_dungeon
        state = await load_spine_dungeon(uid)
        save_func = save_spine_dungeon
    else:
        from utils.ttrpg.dungeon import load_dungeon, save_dungeon
        state = await load_dungeon(uid)
        save_func = save_dungeon

    if not state or not state.get("active"):
        await interaction.followup.send("No active dungeon.", ephemeral=True)
        return

    is_spine = state.get("is_spine", False)

    px, py = state["player_pos"]
    dx, dy = DIRECTIONS[direction]
    nx, ny = px + dx, py + dy
    nk = _key(nx, ny)

    if nk not in state["connections"]:
        await interaction.followup.send("Can't go that way.", ephemeral=True)
        return

    # ── BOSS WARNING — intercept before moving ────────────────────────
    preview_room = state["rooms"].get(nk, {})
    preview_rt   = preview_room.get("type", "empty")
    warn_key     = f"boss_warned_{nk}"

    if preview_rt == R_BOSS and not preview_room.get("cleared", False) and not state.get(warn_key):
        state[warn_key] = True          # set flag so second approach skips the warning
        await save_func(uid, state)        # persist flag — player hasn't moved yet

        theme_key = state.get("theme_key", "undead")
        boss_name = preview_room.get("boss_name", "the Ancient Horror")

        embed = discord.Embed(
            title="🔴 Something Stirs Ahead",
            description=_boss_approach_flavor(theme_key, boss_name),
            color=0x4a0000
        )
        embed.set_footer(text="Entering will trigger the boss encounter. The dungeon ends when the boss falls or you fall.")

        view = BossApproachView(ctx_obj, uid, uname, is_owner, direction, is_spine=is_spine)
        await interaction.followup.send(embed=embed, view=view)
        return   # player stays in current room until they choose
    # ─────────────────────────────────────────────────────────────────

    state["player_pos"] = [nx, ny]
    if nk not in state["visited"]:
        state["visited"].append(nk)

    room = state["rooms"].get(nk, {})
    rt   = room.get("type", "empty")

    # For boss rooms, override description with generated name
    if rt == "boss" and not room.get("cleared"):
        boss_name = room.get("boss_name", "Ancient Horror")
        room["description"] = (
            f"The chamber opens wide. In the center — **{boss_name}**.\n"
            f"It has been here a very long time. It knows you're here."
        )
        state["rooms"][nk] = room

    encounter_text = ""
    loot_text      = ""

    if not room.get("cleared", False):
        if rt in (R_MONSTER, R_BOSS, R_GUARD):
            # [RESUMPTION] Check if we are ALREADY fighting this room
            ac = state.get("active_combat")
            if ac and ac.get("room_key") == nk:
                # Combat already initialized, just send the room (it will auto-resume in _send_dungeon_room)
                await _send_dungeon_room(ctx_obj, interaction.channel, uid, uname, is_owner, state)
                return

            # Spawn the monster and store it for interactive combat
            monster_key = room.get("monster_key") or "goblin"
            monster = get_monster(monster_key)
            if monster:
                is_boss = (rt == R_BOSS)
                if is_boss:
                    monster = _scale_boss_to_level(monster, state.get("player_level", sheet.get("level", 1)))
                else:
                    # Scale regular mobs slightly by difficulty
                    diff = state.get("difficulty", 1)
                    scale = 1.0 + (diff - 1) * 0.15
                    monster["hp"] = max(5, int(monster["hp"] * scale))
                    monster["attack"] = max(1, int(monster["attack"] * scale))
                    monster["defense"] = max(1, int(monster["defense"] * scale))
                    # Cap non-boss monsters to prevent absurd stats.
                    # Targets ~50-55% hit rate against a well-geared player at
                    # the recommended level for that difficulty tier.
                    if is_spine:
                        # Spine: progressive floor-based caps so deeper floors
                        # feel meaningfully harder than early floors.
                        floor_num = state.get("floor_num", 1)
                        mob_hp_cap = 80 + (floor_num * 3)     # F1: 83, F40: 200, F77: 311
                        mob_atk_cap = 12 + (floor_num // 5)   # F1: 12, F40: 20, F77: 27
                    else:
                        MOB_HP_CAPS = {1: 35, 2: 60, 3: 90, 4: 130, 5: 180}
                        MOB_ATK_CAPS = {1: 10, 2: 14, 3: 18, 4: 20, 5: 22}
                        mob_hp_cap = MOB_HP_CAPS.get(diff, 180)
                        mob_atk_cap = MOB_ATK_CAPS.get(diff, 22)
                    # Also enforce a level-based ATK hard cap
                    # (same formula as overworld: DEF_cap - 10)
                    _plvl = state.get("player_level", sheet.get("level", 1))
                    _level_atk_cap = int(_plvl * 1.5 + 2)
                    mob_atk_cap = min(mob_atk_cap, _level_atk_cap)
                    monster["hp"] = min(monster["hp"], mob_hp_cap)
                    monster["attack"] = min(monster["attack"], mob_atk_cap)
                scaled_hp = monster["hp"] if isinstance(monster["hp"], int) else monster["hp"]
                monster["hp"] = {"current": scaled_hp, "max": scaled_hp}
                monster["key"] = monster_key
                state["active_combat"] = {
                    "monster": monster,
                    "monster_key": monster_key,
                    "is_boss": is_boss,
                    "boss_name": room.get("boss_name"),
                    "room_key": nk,
                }
                await save(sheet)
                await save_func(uid, state)

                tier_icon = TIER_ICONS.get(monster.get("tier", "medium"), "🟠")
                name_used = room.get("boss_name") if is_boss else monster.get("name", "Unknown")
                desc = room.get("description", "Something is here.")
                hp_str = f"\n\n❤️ {sheet['hp']['current']}/{sheet['hp']['max']} HP"
                embed = discord.Embed(
                    title=f"{'💀' if is_boss else '⚔️'} {name_used} {tier_icon}",
                    description=f"*{desc}*\n\n*{monster.get('desc', '')}*{hp_str}",
                    color=0x8B0000 if is_boss else 0xFF4500,
                )
                embed.add_field(name="❤️ HP", value=str(scaled_hp), inline=True)
                embed.add_field(name="🗡️ ATK", value=str(monster.get("attack", 0)), inline=True)
                embed.add_field(name="🛡️ DEF", value=str(monster.get("defense", 0)), inline=True)
                view = DungeonCombatView(ctx_obj, uid, uname, is_owner, name_used)
                await interaction.followup.send(embed=embed, view=view)
                return  # Don't fall through to the normal room send
            # monster lookup failed, treat as empty
        elif rt == R_TREASURE:
            loot = get_loot("medium")
            if loot:
                sheet.setdefault("inventory", []).append(loot)
                item = find_item(loot)
                loot_text = f"\n\n💰 Found: **{item['name'] if item else loot}**"
                state.setdefault("loot_gained", []).append(loot)
            else:
                gil = secrets.randbelow(25) + 10
                sheet["gil"] = sheet.get("gil", 0) + gil
                loot_text = f"\n\n💰 Found **{gil} gil** in a cracked chest."
                state["gil_gained"] = state.get("gil_gained", 0) + gil

        elif rt == R_SHRINE:
            if room.get("secret_shrine"):
                if "symbol_of_the_silent_ones" in sheet.get("inventory", []):
                    from utils.ttrpg.dungeon import SHRINE_ROOM_UNLOCKED
                    room["description"] = SHRINE_ROOM_UNLOCKED
                    
                    sheet.setdefault("conditions", [])
                    if "blessed" not in sheet["conditions"]:
                        sheet["conditions"].append("blessed")
                        
                    bonus_xp = 150
                    sheet["xp"] = sheet.get("xp", 0) + bonus_xp
                    encounter_text = f"\n\n✨ *The seal opens. You are deeply Blessed.* (+{bonus_xp} XP)"
                else:
                    from utils.ttrpg.dungeon import SHRINE_ROOM_SEALED
                    room["description"] = SHRINE_ROOM_SEALED
                    encounter_text = f"\n\n✨ *The flame flickers, but the seal remains shut.*"
            else:
                heal = min(15, sheet["hp"]["max"] - sheet["hp"]["current"])
                sheet["hp"]["current"] = min(sheet["hp"]["current"] + heal, sheet["hp"]["max"])
                encounter_text = f"\n\n✨ *The candle. Something old and gentle.* (+{heal} HP)"

        elif rt == R_TRAP:
            # Stat-based trap resolution — DEX save with scaling DC
            dex_val  = sheet.get("stats", {}).get("dex", 10)
            dex_mod  = (dex_val - 10) // 2
            char_class = sheet.get("class", "")
            difficulty = state.get("difficulty", 1)

            # DC scales with dungeon difficulty: 10 / 13 / 16
            trap_dc = 9 + (difficulty * 3)

            # Bonuses
            class_bonus = 4 if char_class == "Rogue" else 0
            luck_bonus  = 2 if "lucky" in sheet.get("conditions", []) else 0
            total_bonus = dex_mod + class_bonus + luck_bonus

            raw_roll  = secrets.randbelow(20) + 1
            total_roll = raw_roll + total_bonus

            if total_roll >= trap_dc:
                # Avoided
                if char_class == "Rogue":
                    encounter_text = (
                        f"\n\n⚡ *Pressure plate. You feel it flex under your boot and go still.*\n"
                        f"*You find the release pin and disarm it cleanly.*\n"
                        f"*(d20({raw_roll})+{total_bonus} = {total_roll} vs DC {trap_dc} — disarmed)*"
                    )
                else:
                    encounter_text = (
                        f"\n\n⚡ *The floor shifts. You lurch sideways and catch the wall.*\n"
                        f"*The mechanism fires into empty air.*\n"
                        f"*(d20({raw_roll})+{total_bonus} = {total_roll} vs DC {trap_dc} — evaded)*"
                    )
            else:
                # Triggered — damage scales with difficulty
                base_dmg = secrets.randbelow(4) + 2          # 2–5
                diff_dmg = secrets.randbelow(difficulty * 3) + 1  # 1–3 / 1–6 / 1–9
                dmg = base_dmg + diff_dmg
                sheet["hp"]["current"] = max(1, sheet["hp"]["current"] - dmg)

                if char_class == "Rogue":
                    encounter_text = (
                        f"\n\n⚡ *You spotted it too late. The blade catches your side.*\n"
                        f"*(-{dmg} HP)*\n"
                        f"*(d20({raw_roll})+{total_bonus} = {total_roll} vs DC {trap_dc} — triggered)*"
                    )
                else:
                    encounter_text = (
                        f"\n\n⚡ *The floor gives. You go down with it.*\n"
                        f"*(-{dmg} HP)*\n"
                        f"*(d20({raw_roll})+{total_bonus} = {total_roll} vs DC {trap_dc} — triggered)*"
                    )

            # Small loot chance on triggered traps (unchanged from original)
            if total_roll < trap_dc and secrets.randbelow(3) == 0:
                loot = get_loot("easy")
                if loot:
                    sheet.setdefault("inventory", []).append(loot)
                    item = find_item(loot)
                    loot_text = f"\nBut you find: **{item['name'] if item else loot}**"

        room["cleared"] = True
        state["rooms"][nk] = room

        # Furniture dungeon XP bonus (Aeridorian Tapestry)
        from utils.ttrpg.housing import load_housing_async
        from utils.ttrpg.furniture import get_home_bonuses
        _housing = await load_housing_async(uid)
        if _housing:
            _furniture_bonuses = get_home_bonuses(_housing)
            _tapestry_xp = _furniture_bonuses.get("dungeon_xp", 0)
            if _tapestry_xp:
                sheet["xp"] = sheet.get("xp", 0) + _tapestry_xp
                state["xp_gained"] = state.get("xp_gained", 0) + _tapestry_xp

    hp_warning = "\n\n⚠️ *HP critically low — consider leaving.*" \
        if sheet["hp"]["current"] <= sheet["hp"]["max"] // 4 else ""

    leveled, new_level = check_level_up(sheet)
    await save(sheet)
    await save_func(uid, state)

    level_text = f"\n\n🎉 **Level Up! Now Lv.{new_level}!**" if leveled else ""
    hp_str = f"\n\n❤️ {sheet['hp']['current']}/{sheet['hp']['max']} HP"

    extra = f"{encounter_text}{loot_text}{hp_str}{hp_warning}{level_text}"

    ROOM_TITLE_ICONS = {
        "boss": "💀", "antechamber": "🌑", "guard": "🛡️",
        "shrine": "✨", "treasure": "💰", "trap": "⚡",
    }
    icon = ROOM_TITLE_ICONS.get(rt, "🏚️")
    embed = discord.Embed(
        title=f"{icon} {rt.title()} Chamber",
        description=f"*{room.get('description','A stone room.')}*{extra}",
        color=_dungeon_room_color(rt),
    )
    view = DungeonView(ctx_obj, uid, uname, is_owner, state)
    await interaction.followup.send(embed=embed, view=view)

async def _dungeon_combat_flee(ctx_obj, interaction, uid, uname, is_owner):
    sheet = await load(uid)
    if not sheet: return

    loc = sheet.get("location", "whisperwood_edge")
    if loc == "aeridor_ruins":
        from utils.ttrpg.spine_dungeon import load_spine_dungeon, save_spine_dungeon
        state = await load_spine_dungeon(uid)
        save_func = save_spine_dungeon
    else:
        from utils.ttrpg.dungeon import load_dungeon, save_dungeon
        state = await load_dungeon(uid)
        save_func = save_dungeon

    if not state or not state.get("active_combat"):
        await interaction.followup.send("No combat to flee from.", ephemeral=True)
        return

    # Fleeing costs 1 hunt and sends you back one step (just clear combat, stay in room)
    del state["active_combat"]
    await save_func(uid, state)

    sheet = await load(uid)
    if sheet:
        for _cb in ["embered", "fortified"]:
            if _cb in sheet.get("conditions", []): sheet["conditions"].remove(_cb)
        sheet["hunts_today"] = sheet.get("hunts_today", 0) + 1
        await save(sheet)

    embed = discord.Embed(
        description="*You scramble back into the corridor.*\n*(1 hunt consumed)*",
        color=0x888888
    )
    view = DungeonView(ctx_obj, uid, uname, is_owner, state)
    await interaction.followup.send(embed=embed, view=view)

_LOCATION_BUTTONS: dict[str, list] = {
    "oakhaven": [
        ("Look", "🔎", "look", "", discord.ButtonStyle.secondary, 0),
        ("Notices", "📋", "notices", "", discord.ButtonStyle.secondary, 0),
        ("Quests", "📜", "quests", "", discord.ButtonStyle.secondary, 0),
        ("Weather", "🌦️", "weather", "", discord.ButtonStyle.secondary, 0),
        ("Talk Elara", "🧙", "talk", "elara", discord.ButtonStyle.secondary, 1),
        ("Calendar", "📅", "calendar", "", discord.ButtonStyle.secondary, 1),
        ("Mail", "📬", "mail", "", discord.ButtonStyle.secondary, 1),
        ("Housing", "🏡", "go", "housing_district", discord.ButtonStyle.secondary, 1),
    ],
    "stone_hearth": [
        ("Rest", "🛏️", "rest", "", discord.ButtonStyle.green, 0),
        ("Drink", "🍺", "drink", "", discord.ButtonStyle.blurple, 0),
        ("Gamble", "🎲", "gamble", "", discord.ButtonStyle.secondary, 0),
        ("Rumor", "🗣️", "rumor", "", discord.ButtonStyle.secondary, 0),
        ("Talk Mira","🍻", "talk", "barkeep", discord.ButtonStyle.secondary, 1),
        ("Talk Stranger","👤","talk", "hooded_figure",discord.ButtonStyle.secondary, 1),
        ("Talk Bard","🎵", "talk", "bard", discord.ButtonStyle.secondary, 1),
        ("🎶 Song","🎶", "bard_song", "", discord.ButtonStyle.primary, 1),
        ("Look", "🔎", "look", "", discord.ButtonStyle.secondary, 2),
    ],
    "hemlocks_store": [
        ("Shop", "🏪", "shop", "", discord.ButtonStyle.blurple, 0),
        ("Talk Hemlock","🧓","talk", "hemlock", discord.ButtonStyle.secondary, 0),
        ("Look", "🔎", "look", "", discord.ButtonStyle.secondary, 0),
    ],
    "caravan": [
        ("Shop", "🐪", "shop", "", discord.ButtonStyle.blurple, 0),
        ("Talk Merchant", "👤", "talk", "merchant", discord.ButtonStyle.secondary, 0),
        ("Look", "🔎", "look", "", discord.ButtonStyle.secondary, 0),
    ],
    "shrine": [
        ("Pray", "🕯️", "pray", "", discord.ButtonStyle.secondary, 0),
        ("Fountain", "💧", "fountain", "", discord.ButtonStyle.secondary, 0),
        ("Offer", "🪙", "offer", "", discord.ButtonStyle.secondary, 0),
        ("Look", "🔎", "look", "", discord.ButtonStyle.secondary, 0),
        ("Look: Flame","🔥", "look", "at flame", discord.ButtonStyle.secondary, 1),
        ("Look: Altar","⛩️", "look", "at altar", discord.ButtonStyle.secondary, 1),
    ],
    "watchtower": [
        ("Scout", "🗼", "scout", "", discord.ButtonStyle.blurple, 0),
        ("Talk Guard","⚔️","talk", "guard", discord.ButtonStyle.secondary, 0),
        ("Look", "🔎", "look", "", discord.ButtonStyle.secondary, 0),
    ],
    "whisperwood_edge": [
        ("Hunt",    "⚔️",  "hunt",    "", discord.ButtonStyle.danger,     0),
        ("Dungeon", "🏚️", "dungeon", "", discord.ButtonStyle.primary,    0),
        ("Look",    "🔎",  "look",    "", discord.ButtonStyle.secondary,  0),
        ("Look: Tracks","🐾","look", "at tracks", discord.ButtonStyle.secondary, 0),
    ],
    "whisperwood_deep": [
        ("Hunt",    "⚔️",  "hunt",    "", discord.ButtonStyle.danger,     0),
        ("Dungeon", "🏚️", "dungeon", "", discord.ButtonStyle.primary,    0),
        ("Look",    "🔎",  "look",    "", discord.ButtonStyle.secondary,  0),
    ],
    "aeridor_ruins": [
        ("Hunt",    "⚔️",  "hunt",    "", discord.ButtonStyle.danger,     0),
        ("Dungeon", "🏚️", "dungeon", "", discord.ButtonStyle.primary,    0),
        ("Look",    "🔎",  "look",    "", discord.ButtonStyle.secondary,  0),
        ("Look: Crystals","💎","look","at crystals", discord.ButtonStyle.secondary, 0),
    ],
    "trade_road": [
        ("Caravan", "🐪", "go", "caravan", discord.ButtonStyle.blurple, 0),
        ("Hunt", "🗡️", "hunt", "", discord.ButtonStyle.danger, 0),
        ("South (Oakhaven)", "🏘️", "go", "oakhaven", discord.ButtonStyle.secondary, 1),
        ("Look", "🔎", "look", "", discord.ButtonStyle.secondary, 1),
    ],
    "herbalists_hut": [
        ("Brew", "⚗️", "brew", "", discord.ButtonStyle.green, 0),
        ("Seeds", "🌱", "seed_shop", "", discord.ButtonStyle.blurple, 0),
        ("Talk Maren","🌿","talk", "maren", discord.ButtonStyle.secondary, 0),
        ("Look", "🔎", "look", "", discord.ButtonStyle.secondary, 0),
        ("Look: Herbs","🫙","look", "at herbs", discord.ButtonStyle.secondary, 1),
    ],
    "oakhaven_bank": [
        ("Deposit", "💰", "bank_deposit", "", discord.ButtonStyle.secondary, 0),
        ("Withdraw", "💸", "bank_withdraw", "", discord.ButtonStyle.secondary, 0),
        ("Look", "🔎", "look", "", discord.ButtonStyle.secondary, 0),
    ],
    "housing_district": [
        ("My Home", "🏡", "my_home", "", discord.ButtonStyle.green, 0),
        ("Barnaby's", "🪑", "furniture_shop", "", discord.ButtonStyle.secondary, 0),
        ("Pip's Pets", "🐾", "pet_shop", "", discord.ButtonStyle.secondary, 0),

        ("Pond", "🎣", "go", "tricklebrook_pond", discord.ButtonStyle.secondary, 1),
        ("Town Square", "⛲", "go", "oakhaven", discord.ButtonStyle.secondary, 1),
        ("Look", "🔎", "look", "", discord.ButtonStyle.secondary, 1),
    ],
    "tricklebrook_pond": [
        ("Fish", "🎣", "fish", "", discord.ButtonStyle.primary, 0),
        ("Shop", "🛒", "fish_shop", "", discord.ButtonStyle.secondary, 0),
        ("Look", "🔎", "look", "", discord.ButtonStyle.secondary, 0),
        ("Housing", "🏘️", "go", "housing_district", discord.ButtonStyle.secondary, 1),
        ("Town Square", "⛲", "go", "oakhaven", discord.ButtonStyle.secondary, 1),
    ],
}

RPGLocationView = RPGFullLocationView

