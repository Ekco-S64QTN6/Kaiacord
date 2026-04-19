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

async def _handle_shop(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.shop import get_shop_inventory
    sheet = await load(uid)
    loc = sheet.get("location", "hemlocks_store")
    weapons, armor, headgear, boots, accessories, consumables = get_shop_inventory(loc)

    def _fmt_weapon(k, v):
        return f"**{v['name']}** · +{v['attack_bonus']} ATK d{v['damage_die']} · {v['value']}g"
    def _fmt_defense(k, v):
        return f"**{v['name']}** · +{v['defense_bonus']} DEF · {v['value']}g"
    def _fmt_accessory(k, v):
        parts = []
        if v.get("defense_bonus"): parts.append(f"+{v['defense_bonus']} DEF")
        if v.get("attack_bonus"):  parts.append(f"+{v['attack_bonus']} ATK")
        return f"**{v['name']}** · {', '.join(parts)} · {v['value']}g"
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

    def _chunk_field(embed, name, arr):
        chunk = ""
        part = 1
        for item in arr:
            if len(chunk) + len(item) + 1 > 1024:
                embed.add_field(name=name if part == 1 else f"{name} (Cont.)", value=chunk, inline=False)
                chunk = item + "\n"
                part += 1
            else:
                chunk += item + "\n"
        if chunk:
            embed.add_field(name=name if part == 1 else f"{name} (Cont.)", value=chunk, inline=False)

    shop_name = "🐪 Corvus Road Trading Co." if loc == "caravan" else "🏪 Hemlock's Store"
    shop_color = LOCATION_COLORS.get(loc, 0x4488cc)
    embed = discord.Embed(title=shop_name, color=shop_color)

    if weapons:     _chunk_field(embed, "🗡️ Weapons", [_fmt_weapon(k, v) for k, v in weapons.items()])
    if armor:       _chunk_field(embed, "🛡️ Armor", [_fmt_defense(k, v) for k, v in armor.items()])
    if headgear:    _chunk_field(embed, "🪖 Headgear", [_fmt_defense(k, v) for k, v in headgear.items()])
    if boots:       _chunk_field(embed, "👢 Boots", [_fmt_defense(k, v) for k, v in boots.items()])
    if accessories: _chunk_field(embed, "💍 Accessories", [_fmt_accessory(k, v) for k, v in accessories.items()])
    if consumables: _chunk_field(embed, "🧪 Consumables", [_fmt_consumable(k, v) for k, v in consumables.items()])

    if sheet:
        embed.set_footer(text=f"💰 Your Gil: {sheet.get('gil', 0)}g  ·  !rpg buy <item>  ·  !rpg sell <item>")

    # Collect all available item keys for the shop view, capping at 75 to fit Discord UI limits.
    # Prioritize Consumables and Weapons so they are never truncated.
    shop_items = list(consumables.keys()) + list(weapons.keys()) + list(armor.keys()) + list(headgear.keys()) + list(accessories.keys()) + list(boots.keys())
    shop_items = shop_items[:75]
    
    view = await _make_shop_view(ctx, msg, uid, uname, is_owner, shop_items, sheet=sheet)
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
        can_equip = True
        
        if item and "classes" in item:
            char_class = updated_sheet.get("class", "")
            adv_class = updated_sheet.get("advanced_class", "")
            if char_class not in item["classes"] and adv_class not in item["classes"]:
                final_msg += f"\n*Note: {item['name']} can only be equipped by {'/'.join(item['classes'])}.*"
                can_equip = False
            
        if can_equip and item and item["category"] in ["weapon", "armor", "head", "boots", "accessory"] and quantity == 1:
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
        view = await _make_shop_view(ctx, msg, uid, uname, is_owner, shop_items, sheet=sheet)
        await msg.channel.send(embed=discord.Embed(description=final_msg, color=0x44aa44), view=view)
    else:
        await msg.channel.send(embed=discord.Embed(description=purchase_msg, color=0xcc4444))


async def _handle_sell(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.shop import process_sell, find_item as _find_item
    
    sheet = await load(uid)
    if not sheet: return
    if sheet.get("location") not in ("hemlocks_store", "caravan"):
        return await msg.channel.send(embed=discord.Embed(description="You must remain at a merchant location to sell items.", color=0xcc4444))
        
    if not rest.strip():
        return await msg.channel.send(embed=discord.Embed(description="Sell what? Use `!rpg inventory` for items.", color=0x888888))
        
    item_key = rest.strip().lower().replace(" ", "_")
    cha_mod = (sheet.get("stats", {}).get("cha", 10) - 10) // 2

    item_snap = _find_item(item_key)
    if item_snap:
        from utils.ttrpg.shop import get_sell_price
        sell_price = get_sell_price(item_snap["value"], sheet.get("reputation", 0), cha_mod)
    else:
        sell_price = 0

    success, resp_msg, updated_sheet = process_sell(sheet, item_key, sheet.get("reputation", 0), cha_mod=cha_mod)
    
    if success:
        if item_snap:
            buyback = updated_sheet.setdefault("buyback", [])
            buyback.insert(0, {"key": item_key, "name": item_snap["name"], "repurchase_price": sell_price})
            updated_sheet["buyback"] = buyback[:25]

        await save(updated_sheet)
        from utils.ttrpg.shop import get_shop_inventory
        loc = updated_sheet.get("location", "hemlocks_store")
        weapons, armor, headgear, boots, accessories, consumables = get_shop_inventory(loc)
        shop_items = list(weapons.keys()) + list(armor.keys()) + list(headgear.keys()) + list(boots.keys()) + list(accessories.keys()) + list(consumables.keys())
        view = await _make_shop_view(ctx, msg, uid, uname, is_owner, shop_items, sheet=sheet)
        await msg.channel.send(embed=discord.Embed(description=resp_msg, color=0x44aa44), view=view)
    else:
        await msg.channel.send(embed=discord.Embed(description=resp_msg, color=0xcc4444))


async def _handle_sell_all_gear(ctx, msg, send, rest, uid, uname, is_owner):
    """Sell all unequipped, non-consumable inventory items at once."""
    from utils.ttrpg.shop import find_item as _find_item

    sheet = await load(uid)
    if not sheet: return

    if sheet.get("location") not in ("hemlocks_store", "caravan"):
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at a merchant to sell.\n`!rpg go hemlocks_store`",
            color=0xcc4444
        ))

    eq = sheet.get("equipment", {})
    equipped_keys = set()
    for slot_val in eq.values():
        if not slot_val: continue
        k = slot_val.get("key") if isinstance(slot_val, dict) else slot_val
        if k: equipped_keys.add(k)

    PROTECTED_KEYS = {"symbol_of_the_silent_ones", "mognet_letter", "lightstone",
                      "adventurers_pack", "torch", "elaras_token"}

    inventory = sheet.get("inventory", [])
    sold_lines = []
    total_gil = 0
    buyback_entries = []
    kept = []

    cha_mod = (sheet.get("stats", {}).get("cha", 10) - 10) // 2

    for item_key in inventory:
        item = _find_item(item_key)
        if not item:
            kept.append(item_key)
            continue
        if item["category"] == "consumable" and not item.get("gem_tier"):
            kept.append(item_key)
            continue
        if item_key in equipped_keys or item_key in PROTECTED_KEYS:
            kept.append(item_key)
            continue

        from utils.ttrpg.shop import get_sell_price
        sell_price = get_sell_price(item["value"], sheet.get("reputation", 0), cha_mod)

        total_gil += sell_price
        sold_lines.append(f"• {item['name']} → {sell_price}g")
        buyback_entries.append({"key": item_key, "name": item["name"], "repurchase_price": sell_price})

    if not sold_lines:
        return await msg.channel.send(embed=discord.Embed(
            description="*Hemlock peers into your pack.*\n\"Nothing in here worth buying.\"",
            color=0x888888
        ))

    sheet["inventory"] = kept
    sheet["gil"] = sheet.get("gil", 0) + total_gil

    existing_bb = sheet.get("buyback", [])
    sheet["buyback"] = (buyback_entries + existing_bb)[:25]

    await save(sheet)

    summary = "\n".join(sold_lines[:20])
    if len(sold_lines) > 20:
        summary += f"\n*...and {len(sold_lines) - 20} more items*"

    embed = discord.Embed(
        title="💰 Bulk Sale Complete",
        description=(
            f"*Hemlock sweeps everything off the counter and into his back room.*\n\n"
            f"{summary}\n\n"
            f"**Total: +{total_gil}g** · Running total: {sheet['gil']}g"
        ),
        color=0x44aa44
    )
    embed.set_footer(text="Items can be bought back from the shop dropdown ↩️")
    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=embed, view=view)
