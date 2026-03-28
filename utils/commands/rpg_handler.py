"""
!rpg command handler — Aethelgard Persistent World System

WORLD & MOVEMENT
  !rpg                       — status and location
  !rpg go <location>         — travel (auto-paths through town)
  !rpg look                  — narrate current location
  !rpg map                   — show accessible locations and local actions
  !rpg weather               — check today's deterministic weather
  !rpg calendar              — view current season and upcoming events

CHARACTER
  !rpg new <Name> <Race> <Class>  — create character
  !rpg sheet [@user]              — view sheet
  !rpg leaderboard / lb           — adventurer rankings
  !rpg inventory             — list items
  !rpg equip <item>          — equip weapon/armor

LOCATION ACTIONS
  !rpg rest                  — Stone Hearth: sleep at inn (5 gil)
  !rpg drink                 — Stone Hearth: Buy an ale (2g, +3 temp HP)
  !rpg gamble                — Stone Hearth: Dice game (10g buy-in)
  !rpg rumor                 — Stone Hearth: hear an inn rumor
  !rpg shop                  — Hemlock: view stock
  !rpg buy <item>            — Hemlock: purchase item
  !rpg sell <item>           — Hemlock: sell item
  !rpg pray                  — Shrine: Daily blessing (+2 next hunt)
  !rpg offer <amount>        — Shrine: Donate gil for XP (cap 20/day)
  !rpg fountain              — Shrine: Sacred spring heal (every other day)
  !rpg brew                  — Sister Maren: combine alchemy ingredients
  !rpg bank                  — Oakhaven Bank: save/withdraw gil
  !rpg notices               — Notice Board: read community news
  !rpg scout                 — Watchtower: Preview monster activity
  !rpg mail                  — Moogle Mail system (Oakhaven)

COMBAT & PVP
  !rpg hunt                  — fight random monster (costs 1 hunt)
  !rpg attack <monster>      — attack current monster
  !rpg flee                  — attempt to escape
  !rpg duel <@user>          — challenge player to non-lethal duel
  !rpg accept                — accept a pending duel

UTILITY & ADMIN
  !rpg hunts                 — hunts remaining today
  !rpg use <item>            — use consumable item
  !rpg talk <npc>            — speak with NPC
  !rpg roll <dice>           — pure dice roll
  !rpg help                  — this list
  !rpg xp <amount> [@user]   — award milestone XP
  !rpg give <item> [@user]   — grant item
  !rpg heal <amount> [@user] — restore HP
  !rpg event <description>   — global narrative event
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
from utils.ttrpg.world_state import get_current_state
from utils.ttrpg.character_manager import load, save, create, format_sheet, load_all
from utils.ttrpg.session_manager import load_session, save_session, create_session, end_session
from utils.ttrpg.progression import check_and_reset_hunts, hunts_remaining, check_level_up, MAX_HUNTS_PER_DAY, get_max_hunts, xp_to_next_level, XP_THRESHOLDS
from utils.ttrpg.class_advancement import (
    apply_advanced_class_to_combat, apply_advanced_class_to_sheet,
    get_advanced_options, get_title, ADVANCED_CLASSES
)
from utils.ttrpg.dungeon import _scale_boss_to_level, load_dungeon, save_dungeon
from utils.ttrpg.rpg_ui import TIER_ICONS, colored_bar, hp_label, CLASS_ICONS, LOCATION_ICONS, ANSI_GREEN, ANSI_RESET
from utils.social.kaia_social_responder import load_persona_async
from utils.ttrpg.world import LOCATION_DATA
from utils.ttrpg.encounter_tables import random_encounter
import utils.ttrpg.dice_engine as dice_engine
from utils.ttrpg.monster_registry import get as get_monster
from utils.ttrpg.loot_tables import get_loot


# ── Interaction adapters for button/select callbacks ─────────────────────────

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
    async def _send(channel, text, use_code_block=None):
        if use_code_block is None:
            use_code_block = "```" not in str(text)
        if use_code_block:
            await interaction.followup.send(f"```\n{text.strip()}\n```")
        else:
            await interaction.followup.send(text.strip())
    return _send


# Location → list of (label, emoji, command, rest_arg, button_style, row)
_LOCATION_BUTTONS: dict[str, list] = {
    "oakhaven": [
        ("Look", "🔎", "look", "", discord.ButtonStyle.secondary, 0),
        ("Notices", "📋", "notices", "", discord.ButtonStyle.secondary, 0),
        ("Quests", "📜", "quests", "", discord.ButtonStyle.secondary, 0),
        ("Weather", "🌦️", "weather", "", discord.ButtonStyle.secondary, 0),
        ("Talk Elara", "🧙", "talk", "elara", discord.ButtonStyle.secondary, 1),
        ("Calendar", "📅", "calendar", "", discord.ButtonStyle.secondary, 1),
        ("Mail", "📬", "mail", "", discord.ButtonStyle.secondary, 1),
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
        ("Hunt", "🗡️", "hunt", "", discord.ButtonStyle.danger, 0),
        ("Look", "🔎", "look", "", discord.ButtonStyle.secondary, 0),
    ],
    "herbalists_hut": [
        ("Brew", "⚗️", "brew", "", discord.ButtonStyle.green, 0),
        ("Talk Maren","🌿","talk", "maren", discord.ButtonStyle.secondary, 0),
        ("Look", "🔎", "look", "", discord.ButtonStyle.secondary, 0),
        ("Look: Herbs","🫙","look", "at herbs", discord.ButtonStyle.secondary, 0),
    ],
    "oakhaven_bank": [
        ("Deposit", "💰", "bank_deposit", "", discord.ButtonStyle.secondary, 0),
        ("Withdraw", "💸", "bank_withdraw", "", discord.ButtonStyle.secondary, 0),
        ("Look", "🔎", "look", "", discord.ButtonStyle.secondary, 0),
    ],
}

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
        }

        # ── Location action buttons ───────────────────────────────────
        for label, emoji, cmd, rest_arg, style, row in _LOCATION_BUTTONS.get(location, []):
            self._add_btn(label, emoji, cmd, rest_arg, style, row)

        # ── Always-present row 3 (moved up from 4) ────────────────────
        self._add_btn("Status", "📊", "status_board", "", discord.ButtonStyle.secondary, 3)
        self._add_btn("Inventory", "🎒", "inventory", "", discord.ButtonStyle.secondary, 3)
        self._add_btn("Map", "🗺️", "map", "", discord.ButtonStyle.secondary, 3)

        # ── Travel select (row 4 — moved down from 3) ─────────────────
        from utils.ttrpg.world import LOCATION_DATA
        from utils.ttrpg.world_state import load_world_state
        state = load_world_state()
        active = state.get("caravan_active", False)

        all_locs = [k for k in LOCATION_DATA.keys() if k != location]
        # Filter caravan if not active
        if not active:
            all_locs = [k for k in all_locs if k != "caravan"]

        all_locs.sort(key=lambda k: 1 if LOCATION_DATA.get(k, {}).get("hunting") else 0)
        if all_locs:
            options = []
            for ex in all_locs[:25]:
                td = LOCATION_DATA.get(ex, {})
                lbl = td.get("name", ex.replace("_", " ").title())
                em = "🗡️" if td.get("hunting") else "📍"
                options.append(discord.SelectOption(label=lbl[:100], value=ex, emoji=em))

            sel = discord.ui.Select(placeholder="Travel to...", options=options, row=4)

            async def _travel_cb(interaction: discord.Interaction, _sel=sel):
                if str(interaction.user.id) != self._uid:
                    await interaction.response.send_message("```\nnot your menu.\n```", ephemeral=True)
                    return
                
                try:
                    chosen = interaction.data["values"][0]
                    await interaction.response.defer()
                    fake = _InteractionMsg(interaction)
                    sfn = _make_interaction_send(interaction)
                    await _handle_go(self._ctx, fake, sfn, chosen, self._uid, self._uname, self._is_owner)
                except Exception as e:
                    import traceback
                    log_error(f"[rpg travel] {e}\n{traceback.format_exc()}")
                    try:
                        await interaction.followup.send(f"```\nTravel failed: {e}\n```", ephemeral=True)
                    except: pass

            sel.callback = _travel_cb
            self.add_item(sel)

    def _add_btn(self, label: str, emoji: str, cmd: str, rest_arg: str,
                 style: discord.ButtonStyle, row: int):
        btn = discord.ui.Button(label=label, emoji=emoji, style=style, row=row)

        async def cb(interaction: discord.Interaction, _cmd=cmd, _rest=rest_arg):
            if str(interaction.user.id) != self._uid:
                await interaction.response.send_message(
                    "```\nthese aren't your buttons.\n```", ephemeral=True)
                return
            await interaction.response.defer()
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
                    await interaction.followup.send(
                        f"```\nerror in {_cmd}: {e}\n```", ephemeral=True)

        btn.callback = cb
        self.add_item(btn)

    async def on_timeout(self):
        pass


# Keep this alias so _make_status_view and other helpers still work
RPGLocationView = RPGFullLocationView


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
                await interaction.response.send_message(
                    "```\nthese aren't your buttons.\n```", ephemeral=True
                )
                return
            await interaction.response.defer()
            fake_msg = _InteractionMsg(interaction)
            send_fn = _make_interaction_send(interaction)
            try:
                await _handle_attack(
                    self._ctx, fake_msg, send_fn,
                    self._monster_key, self._uid, self._uname, self._is_owner
                )
            except Exception as e:
                log_error(f"[rpg button] attack failed: {e}")
                await interaction.followup.send(
                    "```\nerror running attack. check logs.\n```", ephemeral=True
                )

        atk_btn.callback = _attack_cb
        self.add_item(atk_btn)

        # ── Flee button ───────────────────────────────────────────────
        flee_btn = discord.ui.Button(
            label="🏃 Flee", style=discord.ButtonStyle.secondary, row=0
        )

        async def _flee_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != self._uid:
                await interaction.response.send_message(
                    "```\nthese aren't your buttons.\n```", ephemeral=True
                )
                return
            await interaction.response.defer()
            fake_msg = _InteractionMsg(interaction)
            send_fn = _make_interaction_send(interaction)
            try:
                await _handle_flee(
                    self._ctx, fake_msg, send_fn,
                    "", self._uid, self._uname, self._is_owner
                )
            except Exception as e:
                log_error(f"[rpg button] flee failed: {e}")
                await interaction.followup.send(
                    "```\nerror running flee. check logs.\n```", ephemeral=True
                )

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
                if hp_restore > 0 or on_use in ("cure_poison", "luck_roll_bonus"):
                    if hp_restore > 0:
                        label = f"{item['name']} (+{hp_restore} HP)"
                    elif on_use == "cure_poison":
                        label = f"{item['name']} (cures poison)"
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


def _make_status_btn(ctx, uid, uname, is_owner, row=3):
    """Helper to create a unified Status button."""
    btn = discord.ui.Button(label="📊 Status", style=discord.ButtonStyle.secondary, row=row)
    async def _cb(interaction):
        if str(interaction.user.id) != uid:
            await interaction.response.send_message("not yours", ephemeral=True)
            return
        await interaction.response.defer()
        fake = _InteractionMsg(interaction)
        await _handle_status(ctx, fake, _make_interaction_send(interaction), "", uid, uname, is_owner)
    btn.callback = _cb
    return btn


async def _make_shop_view(ctx, msg, uid, uname, is_owner, items):
    """Return a View with Buy and Sell select menus."""
    from utils.ttrpg.shop import find_item
    from collections import Counter

    view = discord.ui.View(timeout=120)

    # ── Buy menus (Rows 0 & 1) ────────────────────────────────────────
    # Discord select menus are capped at 25 options. 
    # Hemlock now has ~40 items, so we split into two menus.
    chunks = [items[i:i + 25] for i in range(0, len(items), 25)]
    
    for idx, chunk in enumerate(chunks):
        if idx >= 2: break # Max 2 buy rows (50 items total)
        options = []
        for item_key in chunk:
            item = find_item(item_key)
            if not item: continue
            label = f"{item['name']} ({item['value']}g)"
            options.append(discord.SelectOption(label=label[:100], value=item_key))

        if options:
            placeholder = "🛒 Buy an item..." if idx == 0 else "🛒 Buy (continued)..."
            buy_select = discord.ui.Select(
                placeholder=placeholder, options=options, row=idx
            )
            async def _buy_cb(interaction: discord.Interaction):
                if str(interaction.user.id) != uid:
                    await interaction.response.send_message("```\nnot your menu.\n```", ephemeral=True)
                    return
                # Get the value from the specific select that was clicked
                chosen = interaction.data["values"][0]
                await interaction.response.defer()
                fake_msg = _InteractionMsg(interaction)
                send_fn = _make_interaction_send(interaction)
                await _handle_buy(ctx, fake_msg, send_fn, chosen, uid, uname, is_owner)
            buy_select.callback = _buy_cb
            view.add_item(buy_select)

    # ── Sell menu (Row 2) — built from player's current inventory ─────
    sheet = await load(uid)
    if sheet and sheet.get("inventory"):
        inv_counts = Counter(sheet["inventory"])
        sell_options = []
        for item_key, count in inv_counts.items():
            item = find_item(item_key)
            if not item: continue
            sell_val = max(1, item["value"] // 2)
            label = f"{item['name']} x{count} ({sell_val}g ea)" if count > 1 else f"{item['name']} ({sell_val}g)"
            sell_options.append(discord.SelectOption(label=label[:100], value=item_key))

        if sell_options:
            sell_select = discord.ui.Select(
                placeholder="💰 Sell an item...",
                options=sell_options[:25],
                row=2  # Shifted to Row 2
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
            sell_select.callback = _sell_cb
            view.add_item(sell_select)

    view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
    return view


def _make_inventory_view(ctx, msg, uid, uname, is_owner, inventory):
    """Return a View with Use and Equip select menus."""
    from utils.ttrpg.shop import find_item
    view = discord.ui.View(timeout=120)
    
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
        opts = [discord.SelectOption(label=it["name"][:100], value=k) for k, it in consumables[:25]]
        sel = discord.ui.Select(placeholder="Use item...", options=opts, row=0)
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
        opts = [discord.SelectOption(label=it["name"][:100], value=k) for k, it in gear[:25]]
        sel = discord.ui.Select(placeholder="Equip gear...", options=opts, row=1)
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

    view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
    return view


def _make_status_view(ctx, msg, uid, uname, is_owner):
    """Return a View with a single 📊 Status button that re-opens the HUD."""
    view = discord.ui.View(timeout=60)
    view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
    return view

async def _get_combat_view_if_active(ctx, msg, uid, uname, is_owner):
    """Returns a RPGCombatView if the player is in active combat, else None."""
    s = await load_session(str(msg.channel.id))
    if not s or not s.get("combat_active"):
        return None
    for m in s.get("monsters", []):
        if m.get("aggro_uid") == uid:
            return RPGCombatView(ctx, msg, uid, uname, is_owner, m.get("key", "monster"))
    return None


def _make_map_view(ctx, msg, uid, uname, is_owner, loc):
    """Return a full location view — used after blizzard/no-hunt redirects."""
    return RPGFullLocationView(ctx, msg, uid, uname, is_owner, loc)


LOCATION_ACTIONS = {
    "oakhaven": [
        "👁️ Look — observe the square",
        "📜 Notice Board — read community news",
        "📦 Deliver — turn in a mognet letter",
        "💬 Talk to Elder Elara",
        "📋 Quests — view available quests",
        "🗺️ Map — view the world map",
        "📅 Calendar — current season & events",
        "🌤️ Weather — today's conditions",
    ],
    "stone_hearth": [
        "🛏️ Rest — full heal (5 gil)",
        "🍺 Drink — buy an ale, +3 temp HP (2 gil)",
        "🎲 Gamble — dice game, 10 gil buy-in",
        "💬 Rumor — hear gossip from the bar",
        "💬 Talk to Mira the barkeep",
        "💬 Talk to the hooded figure",
        "👁️ Look — observe the room",
    ],
    "hemlocks_store": [
        "🛒 Shop — browse Hemlock's inventory",
        "💰 Buy — purchase an item",
        "💸 Sell — sell something",
        "🎒 Inventory — check your gear",
        "💬 Talk to Hemlock",
        "👁️ Look — observe the shop",
    ],
    "caravan": [
        "🐪 Shop — browse the merchant's tier III wares",
        "💬 Talk — hear stories from the Trade Road",
        "🎒 Inventory — check your gear",
        "👁️ Look — observe the colorful wagon",
    ],
    "shrine": [
        "🙏 Pray — receive a daily blessing (free)",
        "🪙 Offer — donate gil for XP",
        "⛲ Fountain — sacred spring (full heal, once per day)",
        "👁️ Look — observe the ancient carvings",
    ],
    "watchtower": [
        "🔭 Scout — preview monster activity (once/day)",
        "💬 Talk to the guards",
        "👁️ Look — observe the canopy from above",
    ],
    "whisperwood_edge": [
        "⚔️ Hunt — fight a random monster (costs 1 hunt)",
        "👁️ Look — observe the treeline",
    ],
    "whisperwood_deep": [
        "⚔️ Hunt — fight a monster (lvl 4+ recommended)",
        "👁️ Look — observe the deep forest",
    ],
    "aeridor_ruins": [
        "⚔️ Hunt — fight a monster (lvl 7+ recommended)",
        "👁️ Look — observe the ruins",
    ],
    "trade_road": [
        "⚔️ Hunt — encounter a road threat (costs 1 hunt)",
        "👁️ Look — observe the road",
    ],
    "notice_board": [
        "📜 Notices — read the latest parchment and news",
        "📋 Quests — view available quests",
        "👁️ Look — observe the crowd at the square",
    ],
    "herbalists_hut": [
        "🧪 Brew — list recipes / brew a potion",
        "💬 Talk to Sister Maren",
        "👁️ Look — observe the herbs and vials",
    ],
    "oakhaven_bank": [
        "🏦 Bank — check balance, deposit, or withdraw gil",
        "👁️ Look — observe the coin-counting and ledger",
    ],
}

LOCATION_COLORS = {
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
}

# ── Dungeon ───────────────────────────────────────────────────────────────────

def _dungeon_room_color(room_type):
    return {
        "start":    0x888888, "empty":    0x4a4a6a,
        "monster":  0xFF4500, "treasure": 0xd4a843,
        "shrine":   0xaaddff, "trap":     0xcc4444,
        "boss":     0x8B0000, "exit":     0x2D5A27,
    }.get(room_type, 0x888888)


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
            state = load_dungeon(self._uid)
            if not state:
                try:
                    await interaction.followup.send("no dungeon found", ephemeral=True)
                except discord.NotFound:
                    pass
                return
            try:
                await interaction.followup.send(
                    embed=discord.Embed(title="🗺️ Dungeon Map",
                                        description=render_map(state), color=0x7a6a9a),
                    ephemeral=True)
            except discord.NotFound:
                pass
        map_btn.callback = _show_map
        self.add_item(map_btn)

        leave_btn = discord.ui.Button(label="🏃 Leave", style=discord.ButtonStyle.danger, row=3)
        async def _leave(interaction):
            if str(interaction.user.id) != self._uid:
                try:
                    await interaction.response.send_message("not yours", ephemeral=True)
                except discord.NotFound:
                    pass
                return
            try:
                await interaction.response.defer()
            except discord.NotFound:
                pass
            await _dungeon_leave(self._ctx, interaction, self._uid, self._uname, self._is_owner)
        leave_btn.callback = _leave
        self.add_item(leave_btn)

        self.add_item(_make_status_btn(ctx_obj, uid, uname, is_owner, row=3))

        # Use Item button — same pattern as DungeonCombatView
        use_btn = discord.ui.Button(label="🧪 Use Item", style=discord.ButtonStyle.secondary, row=3)
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
                if hp_restore > 0 or on_use in ("cure_poison", "luck_roll_bonus"):
                    label = f"{item['name']} (+{hp_restore} HP)" if hp_restore > 0 else f"{item['name']} (cures {on_use.replace('_', ' ')})"
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
                if hp_restore > 0 or on_use in ("cure_poison", "luck_roll_bonus"):
                    label = f"{item['name']} (+{hp_restore} HP)" if hp_restore > 0 else f"{item['name']} (cures {on_use.replace('_', ' ')})"
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


async def _dungeon_combat_round(ctx_obj, interaction, uid, uname, is_owner):
    from utils.ttrpg.dungeon import load_dungeon, save_dungeon, _key
    from utils.ttrpg.combat_engine import _resolve_combat
    from utils.ttrpg.loot_tables import get_loot
    from utils.ttrpg.shop import find_item
    from utils.ttrpg.progression import check_level_up, xp_to_next_level
    from utils.ttrpg.world_state import get_current_state

    state = load_dungeon(uid)
    if not state or not state.get("active_combat"):
        await interaction.followup.send("No active combat.", ephemeral=True)
        return

    sheet = await load(uid)
    if not sheet:
        return

    combat = state["active_combat"]
    monster = combat["monster"]
    is_boss = combat.get("is_boss", False)
    boss_name = combat.get("boss_name")
    room_key = combat["room_key"]

    world_state = get_current_state()
    res = _resolve_combat(sheet, monster,
                          atk_mod_global=world_state.get("atk_mod", 0),
                          def_mod_global=world_state.get("def_mod", 0))

    sheet = res["sheet"]
    monster = res["monster"]

    # Advanced class bonuses are already applied inside _resolve_combat()

    exchange_text = "\n".join(res["exchanges"])
    loot_text = ""
    level_text = ""
    xp_gain = 0
    gil_gain = 0

    if res["monster_defeated"]:
        # Clear combat, mark room cleared
        del state["active_combat"]
        state["rooms"][room_key]["cleared"] = True
        xp_gain = int(monster.get("xp", 25) * (2 if is_boss else 1))
        gil_gain = int(monster.get("gil", 5) * (2 if is_boss else 1))
        sheet["xp"] = sheet.get("xp", 0) + xp_gain
        sheet["gil"] = sheet.get("gil", 0) + gil_gain
        state["xp_gained"] = state.get("xp_gained", 0) + xp_gain
        state["gil_gained"] = state.get("gil_gained", 0) + gil_gain

        # Loot
        tier = "hard" if is_boss else _get_dungeon_loot_tier(sheet.get("level", 1), is_boss)
        if is_boss:
            drops = []
            for _ in range(2):
                loot = get_loot(tier)
                attempts = 0
                while not loot and attempts < 5:
                    loot = get_loot(tier)
                    attempts += 1
                if loot:
                    sheet.setdefault("inventory", []).append(loot)
                    item = find_item(loot)
                    drops.append(item["name"] if item else loot)
                    state.setdefault("loot_gained", []).append(loot)
            if drops:
                loot_text = f"\n🎁 **Boss drops:** {', '.join(drops)}"
            else:
                # Guaranteed fallback: gil payout if loot table still produces nothing
                bonus_gil = 25
                sheet["gil"] = sheet.get("gil", 0) + bonus_gil
                state["gil_gained"] = state.get("gil_gained", 0) + bonus_gil
                loot_text = f"\n💰 No material loot, but the corpse yields **{bonus_gil} gil**."
        elif secrets.randbelow(10) < 4:
            loot = get_loot(tier)
            if loot:
                sheet.setdefault("inventory", []).append(loot)
                item = find_item(loot)
                loot_text = f"\n🎁 {item['name'] if item else loot}"
                state.setdefault("loot_gained", []).append(loot)

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
        save_dungeon(uid, state)

        if is_boss:
            # Boss dead — finalize the dungeon run
            await _dungeon_complete(ctx_obj, interaction, uid, uname, is_owner,
                                    state, sheet, leveled, new_level)
        else:
            embed = discord.Embed(title="⚔️ Victory", description=exchange_text, color=0x2D5A27)
            view = DungeonView(ctx_obj, uid, uname, is_owner, state)
            await interaction.followup.send(embed=embed, view=view)

    elif not res["player_alive"]:
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
        clear_dungeon(uid)
        embed = discord.Embed(
            title="💀 Defeated",
            description=f"{exchange_text}\n\n*You collapsed in the dark. Someone dragged you back to the Shrine.*\n-{xp_loss} XP · -{gil_loss} Gil",
            color=0x8B0000
        )
        view = _make_status_view(ctx_obj, None, uid, uname, is_owner)
        await interaction.followup.send(embed=embed, view=view)

    else:
        # Combat continues — update monster HP in state
        combat["monster"] = monster
        state["active_combat"] = combat
        await save(sheet)
        save_dungeon(uid, state)

        name_used = boss_name if (is_boss and boss_name) else monster.get("name", "Enemy")
        embed = discord.Embed(
            title=f"⚔️ {name_used}",
            description=exchange_text,
            color=0xFF4500
        )
        view = DungeonCombatView(ctx_obj, uid, uname, is_owner, name_used)
        await interaction.followup.send(embed=embed, view=view)

    # Kaia narration removed from dungeon combat — too many GPU calls
    # and typing indicators cause Discord rate limits with concurrent players.


async def _dungeon_combat_flee(ctx_obj, interaction, uid, uname, is_owner):
    from utils.ttrpg.dungeon import load_dungeon, save_dungeon

    state = load_dungeon(uid)
    if not state or not state.get("active_combat"):
        await interaction.followup.send("No combat to flee from.", ephemeral=True)
        return

    # Fleeing costs 1 hunt and sends you back one step (just clear combat, stay in room)
    del state["active_combat"]
    save_dungeon(uid, state)

    sheet = await load(uid)
    if sheet:
        sheet["hunts_today"] = sheet.get("hunts_today", 0) + 1
        await save(sheet)

    embed = discord.Embed(
        description="*You scramble back into the corridor.*\n*(1 hunt consumed)*",
        color=0x888888
    )
    view = DungeonView(ctx_obj, uid, uname, is_owner, state)
    await interaction.followup.send(embed=embed, view=view)


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
        embed.add_field(name="❤️ Monster HP", value=f"{hp_obj['current']}/{hp_obj['max']}", inline=True)
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

    embed = discord.Embed(
        title=f"{'💀' if rt == 'boss' else '🏚️'} {rt.title()} Chamber",
        description=f"*{room.get('description','A stone room.')}*\n\n{hp_str}{extra_text}",
        color=_dungeon_room_color(rt),
    )
    view = DungeonView(ctx_obj, uid, uname, is_owner, dungeon)
    await channel.send(embed=embed, view=view)


async def _dungeon_move(ctx_obj, interaction, uid, uname, is_owner, direction):
    from utils.ttrpg.dungeon import (load_dungeon, save_dungeon,
                                      DIRECTIONS, DIR_OPPOSITE,
                                      R_MONSTER, R_BOSS, R_TREASURE,
                                      R_SHRINE, R_TRAP, R_EXIT, _key)
    from utils.ttrpg.loot_tables import get_loot
    from utils.ttrpg.shop import find_item
    from utils.ttrpg.progression import check_level_up, xp_to_next_level

    state = load_dungeon(uid)
    if not state or not state.get("active"):
        await interaction.followup.send("No active dungeon.", ephemeral=True)
        return

    sheet = await load(uid)
    if not sheet:
        return

    px, py = state["player_pos"]
    dx, dy = DIRECTIONS[direction]
    nx, ny = px + dx, py + dy
    nk = _key(nx, ny)

    if nk not in state["connections"]:
        await interaction.followup.send("Can't go that way.", ephemeral=True)
        return

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
        if rt in (R_MONSTER, R_BOSS):
            # [RESUMPTION] Check if we are ALREADY fighting this room
            ac = state.get("active_combat")
            if ac and ac.get("room_key") == nk:
                # Combat already initialized, just send the room (it will auto-resume in _send_dungeon_room)
                await _send_dungeon_room(ctx_obj, interaction.channel, uid, uname, is_owner, state)
                return

            # Spawn the monster and store it for interactive combat
            monster_key = room.get("monster_key", "goblin")
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
                save_dungeon(uid, state)

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
            dmg = secrets.randbelow(8) + 3
            sheet["hp"]["current"] = max(1, sheet["hp"]["current"] - dmg)
            encounter_text = f"\n\n⚡ *The floor gives way. You catch yourself.* (-{dmg} HP)"
            if secrets.randbelow(3) == 0:
                loot = get_loot("easy")
                if loot:
                    sheet.setdefault("inventory", []).append(loot)
                    item = find_item(loot)
                    loot_text = f"\nBut you find: **{item['name'] if item else loot}**"

        room["cleared"] = True
        state["rooms"][nk] = room



    hp_warning = "\n\n⚠️ *HP critically low — consider leaving.*" \
        if sheet["hp"]["current"] <= sheet["hp"]["max"] // 4 else ""

    leveled, new_level = check_level_up(sheet)
    await save(sheet)
    save_dungeon(uid, state)

    level_text = f"\n\n🎉 **Level Up! Now Lv.{new_level}!**" if leveled else ""
    hp_str = f"\n\n❤️ {sheet['hp']['current']}/{sheet['hp']['max']} HP"

    extra = f"{encounter_text}{loot_text}{hp_str}{hp_warning}{level_text}"

    embed = discord.Embed(
        title=f"{'💀' if rt == 'boss' else '🏚️'} {rt.title()} Chamber",
        description=f"*{room.get('description','A stone room.')}*{extra}",
        color=_dungeon_room_color(rt),
    )
    view = DungeonView(ctx_obj, uid, uname, is_owner, state)
    await interaction.followup.send(embed=embed, view=view)


async def _dungeon_complete(ctx_obj, interaction, uid, uname, is_owner,
                             state, sheet, leveled=False, new_level=0):
    from utils.ttrpg.dungeon import clear_dungeon
    from utils.ttrpg.shop import find_item

    bonus_xp  = 75
    bonus_gil = 40
    sheet["xp"]  = sheet.get("xp",  0) + bonus_xp
    sheet["gil"] = sheet.get("gil", 0) + bonus_gil
    await save(sheet)
    clear_dungeon(uid)

    xp   = state.get("xp_gained",  0) + bonus_xp
    gil  = state.get("gil_gained", 0) + bonus_gil
    loot = state.get("loot_gained", [])

    loot_str = ""
    if loot:
        names = [(find_item(l) or {}).get("name", l) for l in loot]
        loot_str = "\n**Loot:** " + ", ".join(names)

    level_str = f"\n\n🎉 **Level Up! Now Lv.{new_level}!**" if leveled else ""

    embed = discord.Embed(
        title="🚪 Dungeon Complete — You Escaped",
        description=(
            f"*You drag yourself into daylight. The ruins seal behind you.*\n\n"
            f"**Earned:** +{xp} XP · +{gil} Gil"
            f"{loot_str}{level_str}"
        ),
        color=0x2D5A27,
    )
    view = discord.ui.View(timeout=60)
    view.add_item(_make_status_btn(ctx_obj, uid, uname, is_owner))
    await interaction.followup.send(embed=embed, view=view)
    await _log_world_event(f"🏚️ **{sheet['character_name']}** completed a dungeon run.")
    dungeon_embed = discord.Embed(
        title=f"🏚️ {sheet['character_name']} escaped the {state.get('theme_name', 'dungeon')}",
        description=f"*They found a crack in the stone and squeezed out. Whatever was in there is still in there.*",
        color=0x7a6a9a
    )
    dungeon_embed.set_footer(text=f"+{xp} XP · +{gil} Gil · {len(loot)} item(s)")
    await _broadcast_world_event(ctx_obj, dungeon_embed)


async def _dungeon_leave(ctx_obj, interaction, uid, uname, is_owner):
    from utils.ttrpg.dungeon import load_dungeon, clear_dungeon
    from utils.ttrpg.shop import find_item

    state = load_dungeon(uid)
    if not state:
        await interaction.followup.send("No active dungeon.", ephemeral=True)
        return

    xp   = state.get("xp_gained",  0)
    gil  = state.get("gil_gained", 0)
    loot = state.get("loot_gained", [])
    cleared = sum(1 for r in state["rooms"].values()
                  if r.get("cleared") and r.get("type") not in ("start", "empty"))
    clear_dungeon(uid)

    loot_str = ""
    if loot:
        names = [(find_item(l) or {}).get("name", l) for l in loot]
        loot_str = "\n**Kept:** " + ", ".join(names)

    embed = discord.Embed(
        title="🏃 Left the Dungeon",
        description=(
            f"*You find a crack in the stone and squeeze out.*\n\n"
            f"**This run:** +{xp} XP · +{gil} Gil\n"
            f"Rooms cleared: {cleared}{loot_str}"
        ),
        color=0x888888,
    )
    view = discord.ui.View(timeout=60)
    view.add_item(_make_status_btn(ctx_obj, uid, uname, is_owner))
    await interaction.followup.send(embed=embed, view=view)


async def _handle_dungeon(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.dungeon import generate_dungeon, save_dungeon, load_dungeon, DUNGEON_THEMES

    # Resume existing run
    existing = load_dungeon(uid)
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
                         f"You have {hunts_remaining(sheet)}/{MAX_HUNTS_PER_DAY}."),
            color=0xcc4444))

    sheet["hunts_today"] = sheet.get("hunts_today", 0) + ENTRY_HUNTS
    await save(sheet)

    loc = sheet.get("location", "whisperwood_edge")
    from utils.ttrpg.dungeon import LOCATION_DIFFICULTY_BONUS
    loc_diff_bonus = LOCATION_DIFFICULTY_BONUS.get(loc, 0)
    difficulty = max(1, min(3, (sheet["level"] - 1) // 3 + 1 + loc_diff_bonus))
    dungeon = generate_dungeon(difficulty, player_level=sheet["level"], location=loc)
    save_dungeon(uid, dungeon)

    theme_key  = dungeon.get("theme_key", "undead")
    theme_data = DUNGEON_THEMES.get(theme_key, {})
    t_emoji    = theme_data.get("emoji", "🏚️")
    t_name     = theme_data.get("name", "Unknown Depths")
    t_flavor   = theme_data.get("flavor", "Something waits in the dark.")

    await msg.channel.send(embed=discord.Embed(
        title=f"{t_emoji} {t_name}",
        description=(
            f"*{t_flavor}*\n\n"
            f"*Difficulty: {'⬛' * difficulty}{'░' * (3 - difficulty)}  ·  "
            f"Cost: {ENTRY_HUNTS} hunts*"
            f"{torch_line}"
        ),
        color=0x7a6a9a,
    ))
    await asyncio.sleep(2)
    await _send_dungeon_room(ctx, msg.channel, uid, uname, is_owner, dungeon)


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
        "status_board": _handle_status,
        "new":       _handle_new,
        "go":        _handle_go,
        "look":      _handle_look,
        "map":       _handle_map,
        "rest":      _handle_rest,
        "rumor":     _handle_rumor,
        "buy":       _handle_buy,
        "sell":      _handle_sell,
        "shop":      _handle_shop,
        "use":       _handle_use,
        "talk":      _handle_talk,
        "calendar":  _handle_calendar,
        "hunt":      _handle_hunt,
        "attack":    _handle_attack,
        "flee":      _handle_flee,
        "hunts":     _handle_hunts,
        "inventory": _handle_inventory,
        "equip":     _handle_equip,
        "roll":      _handle_roll,
        "bestiary":  _handle_bestiary,
        "help":      _handle_rpg_help,
        "xp":        _handle_xp,
        "give":      _handle_give,
        "heal":      _handle_heal,
        "event":     _handle_event,
        "drink":     _handle_drink,
        "gamble":    _handle_gamble,
        "pray":      _handle_pray,
        "offer":     _handle_offer,
        "scout":     _handle_scout,
        "mail":      _handle_mail,
        "fountain":  _handle_fountain,
        "leaderboard": _handle_leaderboard,
        "lb":        _handle_leaderboard,
        "notices":   _handle_notices,
        "quests":    _handle_quests,
        "quest":     _handle_quest_detail,
        "accept":    _handle_accept,
        "abandon":   _handle_abandon,
        "brew":      _handle_brew,
        "bank_deposit": _handle_bank_deposit,
        "bank_withdraw": _handle_bank_withdraw,
        "bank":      _handle_bank,
        "duel":      _handle_duel,
        "weather":   _handle_weather,
        "dungeon":   _handle_dungeon,
        "unequip":   _handle_unequip,
        "advance":   _handle_advance,
        "bard_song": _handle_bard_song,
    }
    async def _auto_send(channel, text, use_code_block=None):
        if use_code_block is None:
            use_code_block = "```" not in str(text)
        return await send_kaia_response(channel, text, use_code_block=use_code_block)

    handler = handlers.get(sub, _handle_rpg_help)
    try:
        await handler(ctx, msg, _auto_send, rest, author_id, author_name, is_owner)
    except Exception as e:
        log_error(f"[rpg] Handler error in '{sub}': {e}")
        await _auto_send(msg.channel, f"system fault in `{sub}`. check logs.")


# ── HUD / Status ─────────────────────────────────────────────────────────────

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
    if dungeon and dungeon.get("active"):
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
    
    exits = loc_data.get("exits", [])
    nearby = []
    for e in exits:
        ld = LOCATION_DATA.get(e, {})
        n = ld.get("name", e)
        if ld.get("hunting"): n += " *(hunting)*"
        nearby.append(n)
    nearby_str = " · ".join(nearby) if nearby else "None"
    
    s = await load_session(str(msg.channel.id))
    in_combat = False
    if s and s.get("combat_active"):
        for m in s.get("monsters", []):
            if m.get("aggro_uid") == uid:
                in_combat = True
                break
                
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
    
    embed.add_field(name="🗺️ Nearby", value=nearby_str, inline=False)
    
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


# ── Character Management ─────────────────────────────────────────────────────

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
    # For button presses (no @mention), show own sheet as the rich status HUD
    target_id = str(msg.mentions[0].id) if msg.mentions else uid
    
    # If viewing someone else's sheet, fall back to text format
    if target_id != uid:
        sheet = await load(target_id)
        if not sheet:
            return await msg.channel.send(embed=discord.Embed(description="Character not found.", color=0xcc4444))
        embed = discord.Embed(
            title=f"📄 {sheet['character_name']}",
            description=f"```\n{format_sheet(sheet)}\n```",
            color=0x888888
        )
        return await msg.channel.send(embed=embed)
    
    # Own sheet — just show the full rich status HUD
    await _handle_status(ctx, msg, send, rest, uid, uname, is_owner)

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

async def _handle_bard_song(ctx, msg, send, rest, uid, uname, is_owner):
    """Request a song from the Bard — generates a ballad about recent Oakhaven events."""
    import os, json
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority

    sheet = await load(uid)
    if sheet and sheet.get("location") != "stone_hearth":
        return await msg.channel.send(embed=discord.Embed(
            description="The Bard isn't here. Head to the Stone Hearth. (`!rpg go stone_hearth`)",
            color=0xcc4444
        ))

    events_path = os.path.join("memory", "ttrpg", "world_events.json")
    recent_events = []
    if os.path.exists(events_path):
        try:
            with open(events_path, 'r', encoding='utf-8') as f:
                recent_events = json.load(f)[-6:]
        except Exception:
            pass

    all_sheets = await load_all()
    top_adventurers = sorted(all_sheets, key=lambda s: s.get("xp", 0), reverse=True)[:4]
    names = [s["character_name"] for s in top_adventurers]

    events_str = "\n".join([f"- {e}" for e in recent_events]) if recent_events else "- A quiet season. The forest waits."
    names_str = ", ".join(names) if names else uname

    persona = await load_persona_async()
    prompt = (
        f"You are Caelindra the Bard performing at the Stone Hearth Inn in Oakhaven.\n"
        f"Recent events:\n{events_str}\n\n"
        f"Notable adventurers: {names_str}\n\n"
        f"Write a ballad (4-10 lines) about these deeds. "
        f"Voice: dry, specific, sardonic — like a journalist who found melody. "
        f"It MUST name at least one adventurer. Reference a specific event. "
        f"Output only the ballad, no preamble."
    )

    async with msg.channel.typing():
        song_text = "*The Bard strikes a chord... then shrugs. Nothing comes.*"
        try:
            gpu_manager = OllamaGPUManager(config.chat_model)
            opts = gpu_manager.get_gpu_options(for_chat=True)
            opts["num_predict"] = 180
            opts["temperature"] = 0.95

            resp = await gpu_memory_manager.run_with_gpu_guard(
                model_name=config.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(
                    ctx.ollama_client.chat(
                        model=config.chat_model,
                        messages=[
                            {"role": "system", "content": persona + "\n\n" + prompt},
                            {"role": "user", "content": "Perform the song."}
                        ],
                        options=opts,
                        keep_alive=-1
                    ),
                    timeout=45.0
                ),
                task_id=f"bard_song_{_uuid.uuid4().hex[:8]}"
            )
            raw = resp["message"]["content"].strip().replace("```", "")
            if raw:
                song_text = raw
        except Exception as e:
            log_error(f"[bard song] {e}")

    embed = discord.Embed(
        title="🎵 Caelindra Performs",
        description=f"*{song_text}*",
        color=0x9b59b6
    )
    embed.set_footer(text="The Stone Hearth goes quiet for a moment. Then Mira refills something.")
    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=embed, view=view)


# ── World & Movement ─────────────────────────────────────────────────────────

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
    actions = LOCATION_ACTIONS.get(target, ["`!rpg look` — observe the surroundings"])
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


# ── Economy / NPCs / World Iterations ───────────────────────────────────────

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

async def _handle_shop(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.shop import get_shop_inventory
    sheet = await load(uid)
    loc = sheet.get("location", "hemlocks_store")
    weapons, armor, headgear, boots, accessories, consumables = get_shop_inventory(loc)

    def _fmt_weapon(k, v):
        return f"**{v['name']}** · +{v['attack_bonus']} ATK d{v['damage_die']} · {v['value']}g"
    def _fmt_defense(k, v):
        cls = f" *({'/'.join(v['classes'])})*" if v.get("classes") else ""
        return f"**{v['name']}** · +{v['defense_bonus']} DEF{cls} · {v['value']}g"
    def _fmt_accessory(k, v):
        parts = []
        if v.get("defense_bonus"): parts.append(f"+{v['defense_bonus']} DEF")
        if v.get("attack_bonus"):  parts.append(f"+{v['attack_bonus']} ATK")
        cls = f" *({'/'.join(v['classes'])})*" if v.get("classes") else ""
        return f"**{v['name']}** · {', '.join(parts)}{cls} · {v['value']}g"
    def _fmt_consumable(k, v):
        hp = v.get("hp_restore", 0)
        if hp:
            stat = f"+{hp} HP"
        elif v.get("on_use"):
            labels = {"cure_poison": "cures poison", "luck_roll_bonus": "+1 next hit", "starter_kit": "open for items"}
            stat = labels.get(v["on_use"], v["on_use"])
        elif v.get("description"):
            stat = v["description"].split(".")[0].strip() # Clean up description
        else:
            stat = "misc"
        return f"**{v['name']}** · {stat} · {v['value']}g"

    shop_name = "🐪 Corvus Road Trading Co." if loc == "caravan" else "🏪 Hemlock's Store"
    shop_color = LOCATION_COLORS.get(loc, 0x4488cc)
    embed = discord.Embed(title=shop_name, color=shop_color)

    embed.add_field(
        name="🗡️ Weapons",
        value="\n".join(_fmt_weapon(k, v) for k, v in weapons.items()),
        inline=False
    )
    embed.add_field(
        name="🛡️ Armor",
        value="\n".join(_fmt_defense(k, v) for k, v in armor.items()),
        inline=False
    )
    if headgear:
        embed.add_field(
            name="🪖 Headgear",
            value="\n".join(_fmt_defense(k, v) for k, v in headgear.items()),
            inline=False
        )
    if boots:
        embed.add_field(
            name="👢 Boots",
            value="\n".join(_fmt_defense(k, v) for k, v in boots.items()),
            inline=False
        )
    if accessories:
        embed.add_field(
            name="💍 Accessories",
            value="\n".join(_fmt_accessory(k, v) for k, v in accessories.items()),
            inline=False
        )
    embed.add_field(
        name="🧪 Consumables",
        value="\n".join(_fmt_consumable(k, v) for k, v in consumables.items()),
        inline=False
    )

    if sheet:
        embed.set_footer(text=f"💰 Your Gil: {sheet.get('gil', 0)}g  ·  !rpg buy <item>  ·  !rpg sell <item>")

    # Collect all available item keys for the shop view
    shop_items = list(weapons.keys()) + list(armor.keys()) + list(headgear.keys()) + list(boots.keys()) + list(accessories.keys()) + list(consumables.keys())
    view = await _make_shop_view(ctx, msg, uid, uname, is_owner, shop_items)
    await msg.channel.send(embed=embed, view=view)

async def _handle_buy(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.shop import process_purchase
    
    sheet = await load(uid)
    if not sheet: return
    if sheet.get("location") not in ("hemlocks_store", "caravan"):
        return await msg.channel.send(embed=discord.Embed(description="You must be at a merchant location to buy items.", color=0xcc4444))
        
    if not rest.strip():
        return await msg.channel.send(embed=discord.Embed(description="Buy what? Use `!rpg shop` for items.", color=0x888888))
        
    args = rest.strip().split()
    if len(args) > 1 and args[-1].isdigit() and int(args[-1]) > 0:
        quantity = int(args[-1])
        item_key = " ".join(args[:-1]).lower()
    else:
        quantity = 1
        item_key = rest.strip().lower()
        
    cha_mod = (sheet.get("stats", {}).get("cha", 10) - 10) // 2
    success, purchase_msg, updated_sheet = process_purchase(sheet, item_key, quantity, sheet.get("reputation", 0), cha_mod=cha_mod)
    
    if success:
        from utils.ttrpg.shop import find_item
        item = find_item(item_key)
        
        # Determine specific response with optional soft warnings
        final_msg = purchase_msg
        if item and "classes" in item and updated_sheet["class"] not in item["classes"]:
            final_msg += f"\n*Note: this is typically used by {'/'.join(item['classes'])} — you can equip it but it may feel awkward.*"
            
        if item and item["category"] in ["weapon", "armor", "head", "boots", "accessory"] and quantity == 1:
            slot = item["category"]
            if not updated_sheet["equipment"].get(slot):
                updated_sheet["inventory"].remove(item["key"])
                updated_sheet["equipment"][slot] = item
                final_msg += f"\nAuto-equipped **{item['name']}**."
        
        await save(updated_sheet)
        from utils.ttrpg.shop import get_shop_inventory
        loc = updated_sheet.get("location", "hemlocks_store")
        weapons, armor, headgear, boots, accessories, consumables = get_shop_inventory(loc)
        shop_items = list(weapons.keys()) + list(armor.keys()) + list(headgear.keys()) + list(boots.keys()) + list(accessories.keys()) + list(consumables.keys())
        view = await _make_shop_view(ctx, msg, uid, uname, is_owner, shop_items)
        await msg.channel.send(embed=discord.Embed(description=final_msg, color=0x44aa44), view=view)
    else:
        await msg.channel.send(embed=discord.Embed(description=purchase_msg, color=0xcc4444))

async def _handle_sell(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.shop import process_sell
    
    sheet = await load(uid)
    if not sheet: return
    if sheet.get("location") not in ("hemlocks_store", "caravan"):
        return await msg.channel.send(embed=discord.Embed(description="You must remain at a merchant location to sell items.", color=0xcc4444))
        
    if not rest.strip():
        return await msg.channel.send(embed=discord.Embed(description="Sell what? Use `!rpg inventory` for items.", color=0x888888))
        
    item_key = rest.strip().lower().replace(" ", "_")
    cha_mod = (sheet.get("stats", {}).get("cha", 10) - 10) // 2
    success, resp_msg, updated_sheet = process_sell(sheet, item_key, sheet.get("reputation", 0), cha_mod=cha_mod)
    
    if success:
        await save(updated_sheet)
        from utils.ttrpg.shop import get_shop_inventory
        loc = updated_sheet.get("location", "hemlocks_store")
        weapons, armor, headgear, boots, accessories, consumables = get_shop_inventory(loc)
        shop_items = list(weapons.keys()) + list(armor.keys()) + list(headgear.keys()) + list(boots.keys()) + list(accessories.keys()) + list(consumables.keys())
        view = await _make_shop_view(ctx, msg, uid, uname, is_owner, shop_items)
        await msg.channel.send(embed=discord.Embed(description=resp_msg, color=0x44aa44), view=view)
    else:
        await msg.channel.send(embed=discord.Embed(description=resp_msg, color=0xcc4444))

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

async def _handle_talk(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.npc_registry import get_npc, NPCS
    from utils.ttrpg.rpg_prompt_builder import build_npc_prompt
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    
    sheet = await load(uid)
    
    args = rest.strip().split(maxsplit=1)
    if not args:
        return await msg.channel.send(embed=discord.Embed(description=f"Talk to who? Known NPCs: {', '.join(NPCS.keys())}", color=0x888888))
        
    npc_key = args[0].lower()
    npc = get_npc(npc_key)
    if not npc:
        return await msg.channel.send(embed=discord.Embed(description=f"Nobody by that name. Known NPCs: {', '.join(NPCS.keys())}", color=0xcc4444))
        
    loc = sheet.get("location", "oakhaven") if sheet else "oakhaven"
    if npc["location"] != "any" and npc["location"] != loc:
        from utils.ttrpg.world import LOCATION_DATA
        target = LOCATION_DATA.get(npc['location'], {}).get('name', npc['location'])
        return await msg.channel.send(embed=discord.Embed(description=f"**{npc['name']}** isn't here. They're usually at **{target}**.", color=0xcc4444))
        
    player_msg = args[1] if len(args) > 1 else "(Approach silently)"
    
    # Dynamic Context Calculation
    from utils.ttrpg.calendar import get_today_summary
    cal_summary = get_today_summary()
    season = cal_summary["season_name"]
    special_day = cal_summary["special_day"]["name"] if cal_summary["special_day"] else ""
    from datetime import datetime
    time_of_day_hour = datetime.now().hour
    
    if 5 <= time_of_day_hour < 12:
        time_of_day = "morning"
    elif 12 <= time_of_day_hour < 17:
        time_of_day = "afternoon"
    elif 17 <= time_of_day_hour < 21:
        time_of_day = "evening"
    else:
        time_of_day = "night"
        
    blacked_out = False
    if sheet:
        if sheet.get("location") == "shrine" and sheet.get("hp", {}).get("current") == 1:
            blacked_out = True
            
    topic = ""
    if npc_key == "bard" or npc.get("role") == "bard":
        import os, json
        path = os.path.join("memory", "ttrpg", "world_events.json")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                events = json.load(f)
            recent = events[-5:] if events else ["The world has been quiet lately."]
            topic = "Recent Events: " + " | ".join(recent)
        except Exception:
            topic = "An ancient tale of Aeridor's fall."
    elif "topics" in npc and npc["topics"]:
        import hashlib
        from datetime import date
        seed = int(hashlib.md5(f"{npc_key}_{uid}_{date.today().isoformat()}".encode()).hexdigest(), 16)
        topic = npc["topics"][seed % len(npc["topics"])]
        
    # Quest Integration
    from utils.ttrpg.quest_registry import get_npc_quests, get_quest
    available_quests = []
    active_quest_info = None
    quest_progress_msg = ""
    
    if sheet:
        # 1. Available Quests
        all_npc_quests = get_npc_quests(npc_key)
        completed = sheet.get("completed_quests", [])
        for q in all_npc_quests:
            if q["id"] not in completed and q["id"] != sheet.get("active_quest"):
                if sheet["level"] >= q["requirements"].get("level", 1):
                    available_quests.append(q)
                    
        # 2. Active Quest Progress & Completion
        active_id = sheet.get("active_quest")
        if active_id:
            q = get_quest(active_id)
            if q and q["npc"] == npc_key:
                active_quest_info = q
                
                # Update progress if this is a talk task
                task_id = f"talk_{npc_key}"
                prog = sheet.setdefault("quest_progress", {}).setdefault(active_id, [])
                if task_id in q["tasks"]:
                    if task_id not in prog:
                        prog.append(task_id)

                # Check for completion (even if talk task was already done)
                if all(t in prog for t in q["tasks"]):
                    # Complete — apply rewards
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
                    completion_lines = [
                        f"**{q['name']}** — complete.",
                        f"+{xp_reward} XP ({sheet['xp']}/{xp_next})  ·  +{gil_reward} Gil",
                    ]
                    if "item" in q["rewards"]:
                        completion_lines.append(f"🎁 Received: **{q['rewards']['item'].replace('_',' ').title()}**")
                    if leveled:
                        completion_lines.append(f"🎉 **Level Up! Now Lv.{new_level}!**")

                    await msg.channel.send(embed=discord.Embed(
                        title="✅ Quest Complete",
                        description="\n".join(completion_lines),
                        color=0x2ecc71
                    ))
                    await _log_world_event(
                        f"✅ **{sheet['character_name']}** completed '**{q['name']}**'."
                    )
                    quest_embed = discord.Embed(
                        title=f"✅ Quest Complete — {q['name']}",
                        description=f"*{sheet['character_name']} closed the book on another chapter.*",
                        color=0x2ecc71
                    )
                    quest_embed.set_footer(text=f"+{xp_reward} XP · +{gil_reward} Gil")
                    await _broadcast_world_event(ctx, quest_embed)
                    quest_progress_msg = "COMPLETED"
                else:
                    # Not complete, show current progress
                    total = len(q["tasks"])
                    quest_progress_msg = f"{len(prog)}/{total} tasks done: {', '.join(prog)}"
                    await save(sheet)

            
        # Generic turn-in check is covered by the talk task tracking above.
        # If an NPC has a specific inventory turn-in (like Maren), we can add it here.
        if npc_key == "maren" and active_id == "maren_herbs":
            # This is optional if we only want kill_road_bandit + talk_maren.
            # But we could check for an item here if we wanted.
            pass

    cha_mod = (sheet.get("stats", {}).get("cha", 10) - 10) // 2 if sheet else 0
    context = {
        "season": season,
        "special_day": special_day,
        "time_of_day": time_of_day,
        "blacked_out": blacked_out,
        "topic": topic,
        "available_quests": available_quests,
        "active_quest_info": active_quest_info,
        "quest_progress_msg": quest_progress_msg,
        "cha_mod": cha_mod,
    }
    
    prompt = build_npc_prompt(sheet, npc, player_msg, context)
    persona = await load_persona_async()
    messages = [
        {"role": "system", "content": f"{persona}\n\n{prompt}"},
        {"role": "user", "content": f"The player says: {player_msg}"}
    ]
    
    gpu_manager = OllamaGPUManager(config.chat_model)
    opts = gpu_manager.get_gpu_options(for_chat=True)
    opts["num_predict"] = 300
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
                task_id=f"rpg_talk_{_uuid.uuid4().hex[:8]}"
            )
            dialogue = resp["message"]["content"].strip().replace("```", "")
            if dialogue: 
                embed = discord.Embed(
                    title=f"🗣️ {npc['name']}",
                    description=f"*{dialogue}*",
                    color=0x4488cc
                )
                view = discord.ui.View(timeout=180)

                # Quest accept buttons
                if available_quests:
                    for i, q in enumerate(available_quests[:2]):
                        btn = discord.ui.Button(
                            label=f"✅ Accept: {q['name'][:28]}",
                            style=discord.ButtonStyle.primary,
                            row=0
                        )
                        async def _accept(interaction: discord.Interaction, quest=q):
                            if str(interaction.user.id) != uid:
                                await interaction.response.send_message("not yours.", ephemeral=True)
                                return
                            await interaction.response.defer()
                            s = await load(uid)
                            if s.get("active_quest"):
                                await interaction.followup.send(embed=discord.Embed(
                                    description=f"Already on quest: **{s['active_quest']}**.",
                                    color=0xcc4444), ephemeral=True)
                                return
                            s["active_quest"] = quest["id"]
                            await save(s)
                            await interaction.followup.send(embed=discord.Embed(
                                title="📜 Quest Accepted",
                                description=f"**{quest['name']}**\n\n*{quest['description']}*\n\n"
                                            f"**Reward:** {quest['rewards'].get('xp',0)} XP · "
                                            f"{quest['rewards'].get('gil',0)} Gil",
                                color=0x2ecc71))
                        btn.callback = _accept
                        view.add_item(btn)

                # Active quest turn-in hint
                if active_quest_info and quest_progress_msg == "COMPLETED":
                    view.add_item(discord.ui.Button(
                        label="Quest Complete ✓", style=discord.ButtonStyle.success,
                        row=0, disabled=True))

                view.add_item(_make_status_btn(ctx, uid, uname, is_owner))

                await msg.channel.send(embed=embed, view=view)
        except Exception as e:
            log_error(f"[rpg talk] {e}")


async def _log_world_event(event_text):
    path = os.path.join("memory", "ttrpg", "world_events.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    events = []
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                events = json.load(f)
        except:
            events = []
            
    if not isinstance(events, list):
        events = []
    events.append(event_text)
    if len(events) > 10:
        events = list(events)[-10:]
        
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=2)

async def _broadcast_world_event(ctx, embed: discord.Embed):
    """Post a notable event embed to the main #aethelgard broadcast channel."""
    try:
        channel_name = config.get('discord.rpg_channel', 'aethelgard').lower()
        channel = discord.utils.get(ctx.bot.get_all_channels(), name=channel_name)
        if channel:
            await channel.send(embed=embed)
    except Exception as e:
        log_error(f"[rpg broadcast] {e}")


def _level_up_flavor(sheet: dict, level: int) -> str:
    """Short lore-flavored level-up announcement."""
    name = sheet["character_name"]
    cls = sheet.get("advanced_class") or sheet.get("class", "Adventurer")
    loc = sheet.get("location", "oakhaven").replace("_", " ")

    FLAVOR = {
        2:  f"*The first real fight is behind them. {name} is starting to understand the difference.*",
        3:  f"*{name} stopped flinching at the sound of something moving in the dark.*",
        4:  f"*Something about the way {name} moves has changed. The forest notices.*",
        5:  f"*{name} reached level 5. A crossroads approaches — the path ahead splits.*",
        6:  f"*{cls} {name} has survived long enough to become something the Whisperwood remembers.*",
        7:  f"*Seven levels in. The monsters that gave {name} trouble at the start no longer look up.*",
        8:  f"*The Aeridorian constructs track {name} now. That is not a comfortable thing to know.*",
        9:  f"*Nine levels. {name} has outlived three scouts and a guard who had twenty years of experience.*",
        10: f"*{name} reached the cap. Whatever comes next, Oakhaven won't be the same for it.*",
    }
    return FLAVOR.get(level, f"*{name} grows stronger. The {loc} feels it.*")


def _rare_loot_flavor(monster_name: str, item_name: str, location: str) -> str:
    loc_name = location.replace("_", " ").title()
    FLAVOR = [
        f"*Something worth keeping fell from the {monster_name} in the {loc_name}.*",
        f"*The {monster_name} had no use for it anymore. Now someone does.*",
        f"*It wasn't supposed to survive the fight. Neither was the {monster_name}.*",
        f"*The {loc_name} gives up something old.*",
    ]
    return FLAVOR[secrets.randbelow(len(FLAVOR))]

async def _handle_brew(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.world import LOCATION_DATA
    from utils.ttrpg.alchemy import brew, get_recipe, ALCHEMY_RECIPES
    
    sheet = await load(uid)
    if not sheet: return
    
    loc = sheet.get("location", "oakhaven")
    if not LOCATION_DATA.get(loc, {}).get("brewing_allowed"):
        return await send(msg.channel, "You need a proper station to brew. Try the Herbalist's Hut.")
        
    recipe_id = rest.strip().lower()
    if not recipe_id:
        known = sheet.get("recipes", [])

        from utils.ttrpg.alchemy import check_and_discover_recipes
        for ing in sheet.get("inventory", []):
            check_and_discover_recipes(sheet, ing)
        await save(sheet)
        known = sheet.get("recipes", [])

        if not known:
            return await send(msg.channel,
                "No recipes known yet. Pick up ingredients like blood thistle, "
                "silver moss, dire root, or honey sap.")

        embed = discord.Embed(title="📜 Known Recipes", color=0x2ecc71)
        view = discord.ui.View(timeout=120)

        for i, r_key in enumerate(known):
            r = get_recipe(r_key)
            if not r: continue
            ingredients = ", ".join(r["ingredients"])
            embed.add_field(
                name=r["name"],
                value=f"*{ingredients}*",
                inline=True
            )
            btn = discord.ui.Button(
                label=f"Brew {r['name']}",
                style=discord.ButtonStyle.secondary,
                row=i % 4
            )
            async def _brew_cb(interaction: discord.Interaction, key=r_key):
                if str(interaction.user.id) != uid:
                    await interaction.response.send_message("```\nnot yours.\n```", ephemeral=True)
                    return
                await interaction.response.defer()
                fake_msg = _InteractionMsg(interaction)
                send_fn = _make_interaction_send(interaction)
                await _handle_brew(ctx, fake_msg, send_fn, key, uid, uname, is_owner)
            btn.callback = _brew_cb
            view.add_item(btn)

        view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
        return await msg.channel.send(embed=embed, view=view)
        
    success, result_msg = brew(sheet, recipe_id)
    if success:
        await save(sheet)
        await msg.channel.send(embed=discord.Embed(description=result_msg, color=0x2ecc71))
    else:
        await msg.channel.send(embed=discord.Embed(description=result_msg, color=0xcc4444))

async def _handle_notices(ctx, msg, send, rest, uid, uname, is_owner):
    import os
    path = os.path.join("memory", "ttrpg", "world_events.json")
    events = []
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                events = json.load(f)
        except:
            pass
            
    if not events:
        desc = "*The board is currently empty. Oakhaven is quiet.*"
    else:
        desc = "\n".join([f"• {e}" for e in reversed(events)])
        
    embed = discord.Embed(
        title="📝 Oakhaven Notice Board",
        description=desc,
        color=0x8b7355
    )
    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=embed, view=view)


async def _handle_quests(ctx, msg, send, rest, uid, uname, is_owner):
    sheet = await load(uid)
    if not sheet: return
    
    active = sheet.get("active_quest")
    completed = sheet.get("completed_quests", [])
    
    desc = ""
    if active:
        from utils.ttrpg.quest_registry import get_quest
        q = get_quest(active)
        if q:
            prog = sheet.get("quest_progress", {}).get(active, [])
            done = len(prog)
            total = len(q["tasks"])
            bar = "█" * done + "░" * (total - done)
            desc += f"📜 **Active Quest:** {q['name']}\n> {q['description']}\n> Progress: `{bar}` {done}/{total} tasks\n\n"
        else:
            desc += f"📜 **Active Quest:** {active} (invalid ID)\n\n"
            
    if completed:
        desc += "✅ **Completed Quests:**\n"
        desc += "\n".join([f"• {q_id.replace('_', ' ').title()}" for q_id in completed])
    else:
        desc += "❌ **No completed quests.**"
        
    embed = discord.Embed(
        title=f"Quest Log — {sheet['character_name']}",
        description=desc,
        color=0x4a90e2
    )
    view = discord.ui.View(timeout=120)
    if active:
        abandon_btn = discord.ui.Button(label="🗑️ Abandon Quest", style=discord.ButtonStyle.danger, row=0)
        async def _abandon_cb(interaction: discord.Interaction):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("```\nnot your quest log.\n```", ephemeral=True)
                return
            await interaction.response.defer()
            fake_msg = _InteractionMsg(interaction)
            send_fn = _make_interaction_send(interaction)
            await _handle_abandon(ctx, fake_msg, send_fn, "", uid, uname, is_owner)
            
        abandon_btn.callback = _abandon_cb
        view.add_item(abandon_btn)
        
    view.add_item(_make_status_btn(ctx, uid, uname, is_owner, row=1))
    await msg.channel.send(embed=embed, view=view)

async def _handle_abandon(ctx, msg, send, rest, uid, uname, is_owner):
    sheet = await load(uid)
    if not sheet or not sheet.get("active_quest"):
        return await msg.channel.send(embed=discord.Embed(description="No active quest to abandon.", color=0x888888))
    quest_id = sheet["active_quest"]
    sheet["active_quest"] = None
    sheet["quest_progress"] = {k: v for k, v in sheet.get("quest_progress", {}).items() if k != quest_id}
    await save(sheet)
    await msg.channel.send(embed=discord.Embed(
        description=f"Quest **{quest_id.replace('_', ' ').title()}** abandoned. No rewards. The notice board doesn't care.",
        color=0x888888
    ))

async def _handle_quest_detail(ctx, msg, send, rest, uid, uname, is_owner):
    # !rpg quest <quest_id> or just !rpg quest for current
    sheet = await load(uid)
    if not sheet: return
    
    quest_id = rest.strip().lower() or sheet.get("active_quest")
    if not quest_id:
        return await send(msg.channel, "You have no active quest. Speak with NPCs in Oakhaven for tasks.")
        
    from utils.ttrpg.quest_registry import get_quest
    q = get_quest(quest_id)
    if not q:
        return await send(msg.channel, f"Quest `{quest_id}` not found.")
        
    embed = discord.Embed(
        title=f"📜 {q['name']}",
        description=q['description'],
        color=0x4a90e2
    )
    embed.add_field(name="Rewards", value=f"• {q['rewards'].get('xp', 0)} XP\n• {q['rewards'].get('gil', 0)} Gil")
    if "item" in q['rewards']: embed.add_field(name="Bonus", value=f"🎁 {q['rewards']['item'].replace('_', ' ').title()}")
    
    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=embed, view=view)

# ── Items and Equipment ──────────────────────────────────────────────────────

async def _handle_inventory(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.shop import find_item
    from utils.ttrpg.equipment_registry import WEAPONS, ARMOR as ARMOR_REG, HEADGEAR, BOOTS, ACCESSORIES

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

    # ── Inventory items ──────────────────────────────────────────────────────
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

    lines = []
    
    from collections import Counter
    inv_counts = Counter(inventory)
    
    for key, count in inv_counts.items():
        if key == "symbol_of_the_silent_ones":
            continue
            
        item = find_item(key)
        count_str = f" x{count}" if count > 1 else ""
        if item:
            category = item["category"]
            if category == "consumable":
                if item.get("on_use") == "starter_kit":
                    lines.append(f"**{item['name']}**{count_str} — {item.get('description', 'starter pack type !rpg use pack to open')}")
                else:
                    val = item.get("value", 0)
                    hp = item.get("hp_restore", 0)
                    if item.get("on_use") == "cure_poison":
                        effect = "Cures poison"
                    elif item.get("on_use") == "cure_blind":
                        effect = "Cures blindness"
                    elif item.get("on_use") == "luck_roll_bonus":
                        effect = "Grants luck"
                    elif "description" in item and hp == 0:
                        effect = item["description"]
                    else:
                        effect = f"Restores {hp} HP"
                        
                    lines.append(f"**{item['name']}**{count_str} — {effect} *(sell: {val // 2}g)*")
            elif category == "weapon":
                lines.append(f"**{item['name']}**{count_str} — +{item['attack_bonus']} ATK, d{item['damage_die']}  *(sell: {item['value'] // 2}g)*")
            elif category in ("armor", "head", "boots"):
                lines.append(f"**{item['name']}**{count_str} — +{item['defense_bonus']} DEF  *(sell: {item['value'] // 2}g)*")
            elif category == "accessory":
                atk = item.get("attack_bonus", 0)
                dfs = item.get("defense_bonus", 0)
                stat_parts = []
                if dfs: stat_parts.append(f"+{dfs} DEF")
                if atk: stat_parts.append(f"+{atk} ATK")
                stat_str = ", ".join(stat_parts) if stat_parts else "cosmetic"
                lines.append(f"**{item['name']}**{count_str} — {stat_str}  *(sell: {item['value'] // 2}g)*")
            else:
                lines.append(f"**{item['name']}**{count_str}")
        else:
            # Unknown/lore item — show raw with note
            display = key.replace("_", " ").title()
            lines.append(f"**{display}**{count_str} — *sell to Hemlock to find out*")

    embed = discord.Embed(
        title="🎒 Inventory",
        description=f"**Equipped:**\n{equipped_lines}\n\n**Backpack:**\n" + "\n".join(lines),
        color=0x8b7355
    )
    view = _make_inventory_view(ctx, msg, uid, uname, is_owner, inventory)
    await msg.channel.send(embed=embed, view=view)

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
    if item_classes and sheet.get("class") not in item_classes:
        class_str = "/".join(item_classes)
        return await msg.channel.send(embed=discord.Embed(
            description=f"**{item['name']}** can only be used by: {class_str}.", color=0xcc4444
        ))

    # Unequip existing if slot filled
    slot = item["category"]
    old_val = sheet["equipment"].get(slot)
    if old_val:
        # Handle both string keys and dict values
        old_key = old_val.get("key") if isinstance(old_val, dict) else old_val
        if old_key:
            sheet["inventory"].append(old_key)
        
    # Equip new
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
        sheet["hp"]["current"] = min(sheet["hp"]["current"] + item["hp_restore"], sheet["hp"]["max"])
        healed = sheet["hp"]["current"] - before
        sheet["inventory"].remove(item_key)
        await save(sheet)
        combat_view = await _get_combat_view_if_active(ctx, msg, uid, uname, is_owner)
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
            combat_view = await _get_combat_view_if_active(ctx, msg, uid, uname, is_owner)
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
            combat_view = await _get_combat_view_if_active(ctx, msg, uid, uname, is_owner)
            view = combat_view if combat_view else _make_status_view(ctx, msg, uid, uname, is_owner)
            await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. You feel a sudden surge of confidence. (+1 to next hit roll)", color=0x44aa44), view=view)
        else:
            await msg.channel.send(embed=discord.Embed(description=f"You are already feeling pretty lucky.", color=0xcc4444))
    else:
        await msg.channel.send(embed=discord.Embed(description=f"**{item['name']}** can't be used. Try selling it: `!rpg sell {item_key}`", color=0xcc4444))


# ── Combat ───────────────────────────────────────────────────────────────────

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
        
    sheet = check_and_reset_hunts(sheet)
    if hunts_remaining(sheet) <= 0:
        view = _make_status_view(ctx, msg, uid, uname, is_owner)
        return await msg.channel.send(embed=discord.Embed(description=f"You have exhausted your stamina for the day. (0/{get_max_hunts(sheet)} hunts remaining)", color=0xcc4444), view=view)
        
    if sheet["hp"]["current"] <= 0:
        view = _make_status_view(ctx, msg, uid, uname, is_owner)
        return await msg.channel.send(embed=discord.Embed(description=f"You are far too weak to hunt right now. Go rest.", color=0xcc4444), view=view)
        
    # Engage tracking
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

    # Are we already fighting something?
    monsters = s.get("monsters", [])
    my_fights = []
    for m in monsters:
        if isinstance(m, dict) and m.get("aggro_uid") == uid:
            my_fights.append(m)

    if my_fights:
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
        # Show current health in resumption
        hp_bar = colored_bar(hp_obj['current'], hp_obj['max'], 10)
        embed.add_field(name="❤️ Monster HP", value=f"{hp_bar} {hp_obj['current']}/{hp_obj['max']}", inline=False)
        embed.add_field(name="🗡️ ATK", value=str(m_data.get('attack', 0)), inline=True)
        embed.add_field(name="🛡️ DEF", value=str(m_data.get('defense', 0)), inline=True)
        
        embed.set_footer(text=f"Your HP: {sheet['hp']['current']}/{sheet['hp']['max']}")
        combat_view = RPGCombatView(ctx, msg, uid, uname, is_owner, m_key)
        return await msg.channel.send(embed=embed, view=combat_view)
    
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
    
    for _ in range(num_to_spawn):
        m_key = random_encounter(loc, player_level=sheet.get("level", 1))
        m_data = get_monster(m_key)
        if not m_data: continue
        
        m_temp = m_data.copy()
        m_temp["key"] = m_key
        # Apply distance difficulty scaling
        scaled_hp = int(m_temp["hp"] * dist_mult)
        m_temp["hp"] = {"current": scaled_hp, "max": scaled_hp}
        m_temp["attack"] = int(m_temp.get("attack", 0) * dist_mult)
        m_temp["id"] = f"{m_key}_{_uuid.uuid4().hex[:4]}"
        m_temp["aggro_uid"] = uid  # personal instance
        
        s["monsters"].append(m_temp)
        spawned_names.append(f"**{m_temp['name']}**")

    s["combat_active"] = True
    await save_session(s)
    
    
    rec = ld.get("recommended_level", 1)
    warn = f"⚠️ *{sheet['character_name']} is underleveled for this area.*\n" if sheet["level"] < rec - 1 else ""
    
    monster_desc = m_data.get("desc", m_data.get("description", "A dangerous creature."))
    tier_icon = TIER_ICONS.get(m_data.get("tier", "medium"), "🟠")
    
    if num_to_spawn > 1:
        title = f"⚔️ Encounter: SWARM! {tier_icon}"
        description = f"{warn}You are surrounded by a group: {', '.join(spawned_names)}\n\n*{monster_desc}*"
    else:
        title = f"⚔️ Encounter: {m_data['name']} {tier_icon}"
        description = f"{warn}*{monster_desc}*"

    embed = discord.Embed(
        title=title,
        description=description,
        color=0xFF4500 if num_to_spawn == 1 else 0xCC3300
    )
    
    # Show stats of the primary (first) monster
    embed.add_field(name="❤️ HP", value=str(m_temp['hp']['max']), inline=True)
    embed.add_field(name="🗡️ ATK", value=str(m_data.get('attack', 0)), inline=True)
    embed.add_field(name="🛡️ DEF", value=str(m_data.get('defense', 0)), inline=True)
    
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
        
    # Execute deterministic combat math loop with world state modifiers
    state = get_current_state()
    res = _resolve_combat(
        sheet, monster, 
        atk_mod_global=state.get("atk_mod", 0), 
        def_mod_global=state.get("def_mod", 0)
    )
    
    sheet = res["sheet"]
    monster = res["monster"]

    # After combat resolves, consume the blessing
    if "blessed" in sheet.get("conditions", []):
        sheet["conditions"].remove("blessed")
    
    # Handle state cleanup
    if res["monster_defeated"] or not res["player_alive"]:
        s["monsters"].pop(monster_idx)
        if not s["monsters"]: s["combat_active"] = False
    else:
        s["monsters"][monster_idx] = monster
        
    await save_session(s)
    
    xp_gain, gil_gain, level_up_msg, loot_msg, streak_msg = 0, 0, "", "", ""
    if res["monster_defeated"]:
        xp_gain = int(monster.get("xp", 10) * state.get("xp_mult", 1.0))
        gil_gain = int(monster.get("gil", 5) * state.get("gil_mult", 1.0))
        # Weather bonus effects (e.g. clear autumn +5 XP, winter frost +3 Gil)
        weather_effect = get_weather().get("effect") or {}
        if weather_effect.get("type") == "xp_bonus":
            xp_gain += weather_effect.get("value", 0)
        if weather_effect.get("type") == "gil_bonus":
            gil_gain += weather_effect.get("value", 0)
        
        # Streak mechanics
        streak = sheet.get("hunt_streak", 0) + 1
        sheet["hunt_streak"] = streak
        if streak > 1:
            streak_bonus_gil = streak * 2
            gil_gain += streak_bonus_gil
            streak_msg = f"  🔥 Streak: {streak} (+{streak_bonus_gil}g)"
            
        # Loot mechanics
        loot = get_loot(monster.get("tier", "medium"))
        if loot:
            sheet.setdefault("inventory", []).append(loot)
            from utils.ttrpg.shop import find_item as _find_loot
            loot_info = _find_loot(loot)
            loot_display = loot_info["name"] if loot_info else loot
            loot_msg = f"\n🎁 **Looted:** {loot_display}"
            # Check recipe discovery (triggers on crafting ingredients)
            from utils.ttrpg.alchemy import check_and_discover_recipes
            new_recipes = check_and_discover_recipes(sheet, loot)
            for rk in new_recipes:
                from utils.ttrpg.alchemy import get_recipe
                r = get_recipe(rk)
                if r:
                    loot_msg += f"\n📖 **Recipe learned:** {r['name']}! Brew at the Herbalist's Hut."
            
            # Log rare drop if it's high tier or specific items
            tier = monster.get("tier", "medium")
            if tier in ["hard", "deadly", "boss"]:
                loc_name = LOCATION_DATA.get(loc, {}).get('name', loc)
                await _log_world_event(f"A **{loot_display}** was recovered from the {loc_name}. Oakhaven listens carefully.")
                loot_embed = discord.Embed(
                    title=f"🎁 Rare drop — {loot_display}",
                    description=_rare_loot_flavor(monster.get('name', 'something'), loot_display, loc),
                    color=0xd4a843
                )
                loot_embed.set_footer(text=f"{sheet['character_name']} · {loc_name}")
                await _broadcast_world_event(ctx, loot_embed)
            
        sheet["xp"] += xp_gain
        sheet["gil"] += gil_gain
        
    # Emit Math block
    # Advanced class passive bonuses
    adv_mods = apply_advanced_class_to_combat(
        sheet, res.get("player_damage", 0), res["player_hit"],
        res["player_crit"], res.get("monster_damage", 0),
        monster, res["monster_defeated"]
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
        # Victory or Death — show Hunt Again or Status
        if not res["player_alive"]:
            view = _make_status_view(ctx, msg, uid, uname, is_owner)
        else:
            view = _make_hunt_status_view(ctx, msg, uid, uname, is_owner)
        await msg.channel.send(embed=embed, view=view)
    
    # Kaia Narration Generation
    monster_desc = monster.get("desc", monster.get("description", "A dangerous creature."))
    truth = build_combat_prompt(
        sheet, monster["name"], monster_desc,
        res["player_hit"], res["player_crit"], res["player_fumble"], res.get("player_damage", 0),
        res["monster_alive"], res["monster_hit"], res["monster_damage"],
        res["player_alive"], sheet["hp"]["current"], sheet["hp"]["max"],
        sheet["hp"]["current"] / max(1, sheet["hp"]["max"])
    )
    
    persona = await load_persona_async()
    messages = [
        {"role": "system", "content": f"{persona}\n\n{truth}"},
        {"role": "user", "content": f"{uname} engages."}
    ]
    gpu_manager = OllamaGPUManager(config.chat_model)
    opts = gpu_manager.get_gpu_options(for_chat=True)
    opts["num_predict"] = 150
    opts["temperature"] = 0.85
    
    async with msg.channel.typing():
        try:
            nar = await gpu_memory_manager.run_with_gpu_guard(
                model_name=config.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(
                    ctx.ollama_client.chat(model=config.chat_model, messages=messages, options=opts, keep_alive=-1),
                    timeout=45.0
                ),
                task_id=f"rpg_fight_{_uuid.uuid4().hex[:8]}"
            )
            narr = nar["message"]["content"].strip().replace("```", "")
            if narr: await send(msg.channel, f"```\n{narr}\n```")
        except Exception:
            pass

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

    s["monsters"].pop(to_flee)
    if not s["monsters"]: s["combat_active"] = False
    await save_session(s)
    
    view = _make_hunt_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=discord.Embed(
        description=f"🏃 **{uname}** scrambled to safety!{hunt_note}", 
        color=0x44aa44
    ), view=view)


async def _apply_and_narrate_event(ctx, msg, send, sheet, result, uname):
    """Apply a forest event's mechanical effects and trigger Kaia narration."""

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
        messages = [
            {"role": "system", "content": f"{persona}\n\n{prompt}"},
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
            f"*+1 hunt cap until next rest.* ({hunts_remaining(sheet)}/{MAX_HUNTS_PER_DAY + 1} available)\n"
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
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    if sheet.get("location") != "shrine":
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at the Shrine of the Silent Ones to pray.\n`!rpg go shrine`",
            color=0xcc4444
        ))

    # Once per day check
    today = date.today().strftime("%Y-%m-%d")
    last_pray = sheet.get("last_pray_date", "")
    if last_pray == today:
        return await msg.channel.send(embed=discord.Embed(
            description="🕯️ *The shrine is still. You've already made your offering today.*\nThe Silent Ones do not answer twice.",
            color=0x888888
        ))

    # Check if already blessed
    if "blessed" in sheet.get("conditions", []):
        return await msg.channel.send(embed=discord.Embed(
            description="🕯️ *You are already carrying the blessing of the Silent Ones.*\nUse it before asking for more.",
            color=0x888888
        ))

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
    DAILY_CAP = 20
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
            f"*Each gil offered grants 1 XP, up to {DAILY_CAP} XP per day.*"
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
            s["xp"] += eligible
            s["offered_today"] = {t: already + eligible}

            leveled_up, new_level = check_level_up(s)
            await save(s)

            xp_next = xp_to_next_level(s["level"])
            lines = [
                f"🕯️ **{eligible}g** offered. The air shifts.",
                f"+{eligible} XP ({s['xp']}/{xp_next})",
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

    if sheet.get("location") != "watchtower":
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
        async def _dep_cb(interaction: discord.Interaction, amount=actual):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("```\nnot yours.\n```", ephemeral=True)
                return
            s = await load(uid)
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
        async def _wth_cb(interaction: discord.Interaction, amount=actual):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("```\nnot yours.\n```", ephemeral=True)
                return
            s = await load(uid)
            bank = s.get("bank_balance", 0)
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


async def _handle_mail(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg mail — Moogle Mail system in Oakhaven."""
    sheet = await load(uid)
    if not sheet: return

    if sheet.get("location") not in ("oakhaven", "stone_hearth"):
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be in Oakhaven (or at the Inn) to access the Moogle Mail post.",
            color=0xcc4444
        ))

    # 1. Existing Quest Delivery logic (Silent but rewarding)
    if "mognet_letter" in sheet.get("inventory", []):
        reward_gil = 25
        reward_xp  = 20
        sheet["inventory"].remove("mognet_letter")
        if "mognet_pending" in sheet.get("conditions", []):
            sheet["conditions"].remove("mognet_pending")
        sheet["gil"] += reward_gil
        sheet["xp"]  += reward_xp
        leveled_up, new_level = check_level_up(sheet)
        await save(sheet)
        
        xp_next = xp_to_next_level(sheet["level"])
        quest_msg = f"📬 **Mognet letter delivered.**\n*A moogle materialises briefly, takes the letter, says 'kupo' with visible relief, and vanishes.*\n+{reward_xp} XP ({sheet['xp']}/{xp_next})  +{reward_gil} Gil"
        await msg.channel.send(embed=discord.Embed(description=quest_msg, color=0xf4a460))
        if leveled_up:
            await msg.channel.send(embed=discord.Embed(description=f"🎉 **{sheet['character_name']} reached Level {new_level}!**", color=0xffcc00))

    # 2. Main Mail Interface
    mailbox = sheet.get("mailbox", [])
    mail_count = len(mailbox)
    status_text = f"You have **{mail_count}** package(s) waiting." if mail_count > 0 else "Your mailbox is empty."
    
    embed = discord.Embed(
        title="📬 Moogle Mail Post",
        description=f"\"Kupo! Welcome to the mail post! Do you have something to send, or are you checking for a delivery?\"\n\n{status_text}",
        color=0xf4a460
    )
    embed.set_thumbnail(url="https://i.imgur.com/w2YxYmB.png") # Optional Moogle icon if available, or just omit
    
    view = MailMenuView(ctx, msg, uid, uname, is_owner, sheet)
    await msg.channel.send(embed=embed, view=view)


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
        
        items_gained = []
        total_gil = 0
        for entry in mailbox:
            if entry.get("item"):
                self.sheet["inventory"].append(entry["item"])
                items_gained.append(entry["item"].replace("_", " ").title())
            total_gil += entry.get("gil", 0)
        
        self.sheet["gil"] += total_gil
        self.sheet["mailbox"] = []
        await save(self.sheet)
        
        res = "kupo! You received:\n"
        if items_gained: res += f"📦 **Items:** {', '.join(items_gained)}\n"
        if total_gil: res += f"💰 **Gil:** {total_gil}g\n"
        
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



# ── Administration & Overrides ───────────────────────────────────────────────


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

    # Sort by XP descending, then by level descending
    sheets.sort(key=lambda s: (s.get("xp", 0), s.get("level", 1)), reverse=True)

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

async def _handle_event(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return

    from utils.core.background_tasks import (
        run_village_raid, run_oracle_speaks, run_moogle_festival,
        run_aeridorian_tremor, run_tonberry_procession, run_spine_storm,
        run_caravan_arrival, run_bard_performance
    )

    EVENTS = {
        "raid":       run_village_raid,
        "invasion":   run_village_raid,
        "oracle":     run_oracle_speaks,
        "moogle":     run_moogle_festival,
        "mail":       run_moogle_festival,
        "tremor":     run_aeridorian_tremor,
        "aeridor":    run_aeridorian_tremor,
        "tonberry":   run_tonberry_procession,
        "procession": run_tonberry_procession,
        "storm":      run_spine_storm,
        "caravan":    run_caravan_arrival,
        "bard":       run_bard_performance,
        "random":     None,
    }

    key = rest.strip().lower()

    if key in EVENTS:
        import secrets as _sec
        fn = EVENTS[key]
        if fn is None:  # random
            fn = _sec.choice([f for k, f in EVENTS.items() if f is not None])
        await send(msg.channel, f"triggering: **{key}**...")
        await fn(ctx, msg.channel)
        return

    if not key:
        # Show available events
        available = ", ".join(f"`{k}`" for k in EVENTS)
        await msg.channel.send(embed=discord.Embed(
            description=f"**Available events:**\n{available}\n\nUsage: `!rpg event raid`",
            color=0x888888
        ))
        return

    # Legacy: free-form narrative event
    description = rest.strip()
    from utils.ttrpg.rpg_prompt_builder import build_event_prompt
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    await _log_world_event(f"📣 **WORLD EVENT:** {description}")
    prompt = build_event_prompt(description)
    persona = await load_persona_async()
    messages = [
        {"role": "system", "content": f"{persona}\n\n{prompt}"},
        {"role": "user", "content": "Narrate the event."}
    ]
    gpu_manager = OllamaGPUManager(config.chat_model)
    opts = gpu_manager.get_gpu_options(for_chat=True)
    opts["num_predict"] = 250
    opts["temperature"] = 0.85
    async with msg.channel.typing():
        try:
            resp = await gpu_memory_manager.run_with_gpu_guard(
                model_name=config.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(
                    ctx.ollama_client.chat(model=config.chat_model, messages=messages, options=opts, keep_alive=-1),
                    timeout=60.0
                ),
                task_id=f"rpg_event_{_uuid.uuid4().hex[:8]}"
            )
            narr = resp["message"]["content"].strip().replace("```", "")
            if narr: await send(msg.channel, f"🌍 **WORLD EVENT**\n*{narr}*")
        except Exception as e:
            log_error(f"[rpg event] {e}")

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
        "`!rpg deliver` — mognet mail\n"
        "`!rpg talk <npc>`"
    ), inline=True)

    embed.add_field(name="💬 NPCs", value=(
        "`elara` · `hemlock`\n"
        "`barkeep` · `guard`\n"
        "`hooded_figure` · `maren`"
    ), inline=True)

    embed.set_footer(text="!rpg go  with no argument lists exits from your current location")

    await msg.channel.send(embed=embed)

# ── PvP Duels ───────────────────────────────────────────────────────────────

PENDING_DUELS = {} # (challenger_id, target_id) -> timestamp

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
        from utils.ttrpg.combat_engine import _resolve_combat
        
        c_sheet = await load(challenger_id)
        t_sheet = await load(uid)
        
        if not c_sheet or not t_sheet: return
        
        # Duel is just a special combat resolution
        # We'll treat the challenger as the "player" and the target as the "monster" for math purposes
        # but swapped so it feels mutual. 
        # Actually, let's just do one exchange for now or a loop.
        
        # Setup "monster" data from target sheet
        m_from_t = {
            "name": t_sheet["character_name"],
            "hp": t_sheet["hp"],
            "attack": t_sheet["stats"]["str"] + 5, # basic attack proxy
            "defense": 10 + (t_sheet["stats"]["dex"]-10)//2,
            "id": f"player_{uid}"
        }
        
        res = _resolve_combat(c_sheet, m_from_t, is_duel=True)
        
        # Apply results back
        await save(res["sheet"]) # challenger
        t_sheet["hp"] = res["monster"]["hp"]
        await save(t_sheet) # target
        
        embed = discord.Embed(
            title="⚔️ DUEL RESULTS",
            description="\n".join(res["exchanges"]),
            color=0x4488cc
        )
        await msg.channel.send(embed=embed)
        
        await _log_world_event(f"⚔️ **DUEL:** {c_sheet['character_name']} vs {t_sheet['character_name']} in {c_sheet['location'].replace('_',' ').title()}.")
        return

    # If no duel, try quest accept
    sheet = await load(uid)
    if not sheet: return

    quest_id = rest.strip().lower()
    if not quest_id:
        return await send(msg.channel, "Usage: `!rpg accept <quest_id>`")

    if sheet.get("active_quest"):
        return await send(msg.channel, f"You are already on a quest: `{sheet['active_quest']}`. Complete or abandon it first.")

    from utils.ttrpg.quest_registry import get_quest
    q = get_quest(quest_id)
    if not q:
        return await send(msg.channel, f"Quest `{quest_id}` not found.")

    if quest_id in sheet.get("completed_quests", []):
        return await send(msg.channel, "You have already completed this quest.")

    # Check level requirement
    if sheet['level'] < q['requirements'].get('level', 1):
        return await send(msg.channel, f"You must be at least Level {q['requirements']['level']} to accept this quest.")

    sheet["active_quest"] = quest_id
    await save(sheet)

    embed = discord.Embed(
        title="Quest Accepted!",
        description=f"You have taken up the task: **{q['name']}**.\n\n*{q['description']}*",
        color=0x2ecc71
    )
    await msg.channel.send(embed=embed)
