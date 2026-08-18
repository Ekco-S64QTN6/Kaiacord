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

async def _handle_seed_shop(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg seed_shop — Buy seeds from Sister Maren."""
    from utils.ttrpg.farming import CROPS
    
    sheet = await load(uid)
    if not sheet: return

    if sheet.get("location") != "herbalists_hut":
        return await msg.channel.send(embed=discord.Embed(
            description="Sister Maren's seeds are only available at the Herbalist's Hut.\n`!rpg go herbalists_hut`",
            color=0xcc4444
        ))

    embed = discord.Embed(
        title="🌱 Sister Maren's Seeds",
        description=(
            "*Maren brushes soil from her apron.*\n\n"
            "\"The earth provides, if you provide the care.\"\n\n"
            f"**Your Gil:** {sheet.get('gil', 0)}g"
        ),
        color=0x44aa44
    )

    options = []
    for k, d in CROPS.items():
        embed.add_field(
            name=f"{d['emoji']} {d['name']} ({d['seed_cost']}g)",
            value=f"{d['desc']}\n*Grows in {d['growth_days']} day(s) → {d['yield_item'].replace('_',' ')}*",
            inline=True
        )
        options.append(discord.SelectOption(
            label=f"{d['name']} ({d['seed_cost']}g)",
            value=k,
            emoji=d['emoji']
        ))

    view = discord.ui.View(timeout=120)
    sel = discord.ui.Select(placeholder="🌱 Select seeds to buy...", options=options, row=0)

    async def _buy_seed_cb(interaction: discord.Interaction):
        if str(interaction.user.id) != uid:
            await interaction.response.send_message("not yours.", ephemeral=True)
            return
        chosen = interaction.data["values"][0]
        await interaction.response.defer()
        s = await load(uid)
        if not s:
            return
        cost = CROPS[chosen]["seed_cost"]
        from utils.ttrpg.character_manager import INVENTORY_LIMIT
        current_unique = set(s.get("inventory", []))
        if len(current_unique | {chosen}) > INVENTORY_LIMIT:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"Your inventory has too many unique item types. Cannot purchase seeds. Cap: {INVENTORY_LIMIT} unique types (currently holding {len(current_unique)}).",
                    color=0xcc4444
                ),
                ephemeral=True
            )
            return
        if s["gil"] < cost:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"Not enough gil. **{CROPS[chosen]['name']}** costs {cost}g. You have {s['gil']}g.",
                    color=0xcc4444
                ),
                ephemeral=True
            )
            return
        s["gil"] -= cost
        s.setdefault("inventory", []).append(chosen)
        await save(s)
        await interaction.followup.send(
            embed=discord.Embed(
                description=(
                    f"*Maren wraps the seeds in cloth and hands them over.*\n\n"
                    f"✅ Purchased **{CROPS[chosen]['name']}** for {cost}g.\n"
                    f"*Plant it at your home farm.* Remaining gil: {s['gil']}g"
                ),
                color=0x44aa44
            )
        )

    sel.callback = _buy_seed_cb
    view.add_item(sel)
    view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
    await msg.channel.send(embed=embed, view=view)


async def _handle_brew(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.world import LOCATION_DATA
    from utils.ttrpg.alchemy import brew, get_recipe, ALCHEMY_RECIPES
    
    sheet = await load(uid)
    if not sheet: return
    
    loc = sheet.get("location", "oakhaven")
    from utils.ttrpg.housing import load_housing_async
    from utils.ttrpg.furniture import get_home_bonuses
    _housing = await load_housing_async(uid)
    _has_alchemy_table = _housing and get_home_bonuses(_housing).get("home_brewing")
    if not LOCATION_DATA.get(loc, {}).get("brewing_allowed") and not _has_alchemy_table:
        return await send(msg.channel, "You need a proper station to brew. Try the Herbalist's Hut, or purchase an Alchemy Workbench for your home.")
        
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


async def _handle_my_home(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.housing import (
        load_housing, save_housing, HOUSING_TIERS,
        get_next_tier, get_tier_data, default_housing_sheet, can_afford_upgrade
    )
    from utils.ttrpg.farming import CROPS, get_crop_stage, is_harvestable
    from utils.ttrpg.pets import PET_REGISTRY
    from utils.ttrpg.furniture import FURNITURE, get_home_bonuses

    sheet = await load(uid)
    if not sheet: return

    housing = load_housing(uid)

    # ── No house yet — offer purchase ────────────────────────────────────────
    if not housing:
        hut = HOUSING_TIERS["hut"]
        embed = discord.Embed(
            title="🏡 Oakhaven Housing District",
            description=(
                "*A vacant plot sits at the end of the lane.*\n\n"
                f"**{hut['name']}** — {hut['cost']}g\n"
                f"*{hut['desc']}*\n\n"
                f"Includes: {hut['farming_plots']} farming plot · {hut['pet_slots']} pet slot · "
                f"{hut['furniture_slots']} furniture slots"
            ),
            color=0x8b7355
        )
        view = discord.ui.View(timeout=120)
        buy_btn = discord.ui.Button(
            label=f"Purchase Hut ({hut['cost']}g)",
            style=discord.ButtonStyle.green, row=0
        )
        async def _buy_cb(interaction):
            if str(interaction.user.id) != uid: return
            s = await load(uid)
            if s["gil"] < hut["cost"]:
                await interaction.response.send_message(
                    f"Not enough gil. Need {hut['cost']}g, have {s['gil']}g.", ephemeral=True)
                return
            s["gil"] -= hut["cost"]
            await save(s)
            h = default_housing_sheet(uid, s["character_name"])
            save_housing(h)
            await _log_world_event(f"🏡 **{s['character_name']}** has settled in Oakhaven, purchasing a new {hut['name']}.")
            await interaction.response.send_message(embed=discord.Embed(
                description=f"🏡 *{hut['flavor']}*\n\nWelcome home, {s['character_name']}.",
                color=0x44aa44))
        buy_btn.callback = _buy_cb
        view.add_item(buy_btn)
        view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
        return await msg.channel.send(embed=embed, view=view)

    # ── Existing house — show home HUD ───────────────────────────────────────
    tier_data = get_tier_data(housing["tier"])
    bonuses = get_home_bonuses(housing)
    
    # Farm status
    plots = housing.get("farming", {}).get("plots", [])
    farm_lines = []
    harvestable_count = 0
    for i, plot in enumerate(plots):
        stage = get_crop_stage(plot)
        if is_harvestable(plot):
            harvestable_count += 1
        farm_lines.append(f"Plot {i+1}: {stage}")
    
    # Pet status
    pet_lines = []
    for pet in housing.get("pets", []):
        p_data = PET_REGISTRY.get(pet["key"], {})
        fed = "✅" if pet.get("fed_today") else "❌"
        pet_lines.append(f"{p_data.get('emoji','?')} {pet['name']} — Fed: {fed}")

    # Build embed
    desc_parts = [f"*{tier_data['desc']}*\n"]
    if farm_lines:
        desc_parts.append("🌾 **Farm:**\n" + "\n".join(farm_lines))
    else:
        desc_parts.append("🌾 **Farm:** No crops planted.")
    if pet_lines:
        desc_parts.append("\n🐾 **Pets:**\n" + "\n".join(pet_lines))
        
    furniture_lines = []
    bonus_labels = {
        "home_atk": "ATK",
        "local_atk": "Local ATK",
        "farm_yield": "Farm Yield",
        "talk_xp": "Talk XP",
        "dungeon_xp": "Dungeon XP",
        "bank_cap": "Bank Storage",
        "home_cha": "CHA",
        "home_scout": "Scout",
        "home_pray": "Home Pray",
        "home_brewing": "Home Brewing",
        "home_bank": "Bank Access (Home)"
    }
    for f_key in housing.get("furniture", []):
        f_data = FURNITURE.get(f_key)
        if f_data:
            bonus = f_data.get("bonus", {})
            if bonus:
                b_type = bonus.get("type", "")
                label = bonus_labels.get(b_type, b_type.replace('_', ' ').title())
                if b_type in ["home_brewing", "home_pray", "home_bank", "home_scout"]:
                    b_str = label
                else:
                    b_str = f"+{bonus.get('value', 0)} {label}"
            else:
                b_str = ""
            furniture_lines.append(f"{f_data['emoji']} **{f_data['name']}**: {b_str}")
            
    if furniture_lines:
        desc_parts.append("\n🪑 **Amenities:**\n" + "\n".join(furniture_lines))
        
    if harvestable_count:
        desc_parts.append(f"\n✅ **{harvestable_count} crop(s) ready to harvest!**")

    embed = discord.Embed(
        title=f"{tier_data['emoji']} {housing['house_name']}",
        description="\n".join(desc_parts),
        color=0x8b7355
    )

    # Build view
    view = discord.ui.View(timeout=120)

    # Row 0: Farm actions (harvest handled inside farm_view)
    farm_label = f"🌾 Farm{' ✅' if harvestable_count else ''}"
    view.add_item(_make_home_btn(ctx, uid, uname, is_owner, farm_label, "farm_view", 0,
                                  style=discord.ButtonStyle.green if harvestable_count else discord.ButtonStyle.secondary))
    view.add_item(_make_home_btn(ctx, uid, uname, is_owner, "💧 Water", "water_crops", 0))

    # Row 1: Pets + shop
    if housing.get("pets"):
        unfed_pets = [p for p in housing.get("pets", []) if not p.get("fed_today")]
        unfed_cost = sum(PET_REGISTRY.get(p["key"], {}).get("food_cost", 0) for p in unfed_pets)
        feed_label = f"🐾 Feed ({unfed_cost}g)" if unfed_cost > 0 else "🐾 Pets (fed ✅)"
        feed_style = discord.ButtonStyle.primary if unfed_cost > 0 else discord.ButtonStyle.secondary
        view.add_item(_make_home_btn(ctx, uid, uname, is_owner, feed_label, "feed_pet", 1, style=feed_style))
    else:
        view.add_item(_make_home_btn(ctx, uid, uname, is_owner, "🐾 Adopt Pet", "pet_shop", 1))

    view.add_item(_make_home_btn(ctx, uid, uname, is_owner, "🪑 Decorate", "furniture_shop", 1))

    # Row 2: Conditional actions + upgrade
    bonuses = get_home_bonuses(housing)
    if bonuses.get("home_brewing"):
        view.add_item(_make_home_btn(ctx, uid, uname, is_owner, "⚗️ Brew", "brew", 2,
                                      style=discord.ButtonStyle.blurple))
    if bonuses.get("daily_training"):
        view.add_item(_make_home_btn(ctx, uid, uname, is_owner, "🪆 Train", "home_training", 2,
                                      style=discord.ButtonStyle.blurple))
    if bonuses.get("home_pray"):
        view.add_item(_make_home_btn(ctx, uid, uname, is_owner, "🕯️ Pray", "pray", 2,
                                      style=discord.ButtonStyle.blurple))
    if bonuses.get("home_bank"):
        view.add_item(_make_home_btn(ctx, uid, uname, is_owner, "🏦 Bank", "bank", 2,
                                      style=discord.ButtonStyle.blurple))
    if get_next_tier(housing["tier"]):
        view.add_item(_make_home_btn(ctx, uid, uname, is_owner, "⬆️ Upgrade", "upgrade_house", 2))

    # Row 3: Utility
    ren_btn = discord.ui.Button(label="🏷️ Rename", style=discord.ButtonStyle.secondary, row=3)
    async def _ren_cb(interaction):
        if str(interaction.user.id) != uid: return
        await interaction.response.send_modal(RenameHouseModal(uid))
    ren_btn.callback = _ren_cb
    view.add_item(ren_btn)
    view.add_item(_make_status_btn(ctx, uid, uname, is_owner, row=3))
    await msg.channel.send(embed=embed, view=view)


async def _handle_buy_house(ctx, msg, send, rest, uid, uname, is_owner):
    """Stub — logic is mostly inside _handle_my_home for the first purchase."""
    pass


async def _handle_upgrade_house(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.housing import load_housing, save_housing, HOUSING_TIERS, get_next_tier, can_afford_upgrade
    
    sheet = await load(uid)
    housing = load_housing(uid)
    if not sheet or not housing: return

    can_up, err = can_afford_upgrade(sheet, housing)
    if not can_up:
        return await send(msg.channel, err)

    next_tier = get_next_tier(housing["tier"])
    tier_data = HOUSING_TIERS[next_tier]
    
    embed = discord.Embed(
        title="⬆️ Estate Upgrade",
        description=(
            f"Upgrade your home to a **{tier_data['name']}**?\n\n"
            f"**Cost:** {tier_data['cost']}g\n"
            f"*{tier_data['desc']}*\n\n"
            f"Includes: {tier_data['farming_plots']} farming plots · {tier_data['pet_slots']} pet slots · "
            f"{tier_data['furniture_slots']} furniture slots"
        ),
        color=0x8b7355
    )
    
    view = discord.ui.View(timeout=60)
    confirm_btn = discord.ui.Button(label=f"Confirm Upgrade ({tier_data['cost']}g)", style=discord.ButtonStyle.green)
    async def _confirm_cb(interaction):
        if str(interaction.user.id) != uid: return
        s = await load(uid)
        can_u, e = can_afford_upgrade(s, housing)
        if not can_u:
            return await interaction.response.send_message(e, ephemeral=True)
            
        s["gil"] -= tier_data["cost"]
        await save(s)
        housing["tier"] = next_tier
        save_housing(housing)
        
        await _log_world_event(f"🏰 **{s['character_name']}** has upgraded their estate to a **{tier_data['name']}**.")
        
        await interaction.response.send_message(embed=discord.Embed(
            description=f"🏠 **Estate Upgraded!** Your home is now a **{tier_data['name']}**.\n*{tier_data['flavor']}*",
            color=0x44aa44
        ))
        
        fake = _InteractionMsg(interaction)
        await _handle_my_home(ctx, fake, _make_interaction_send(interaction), rest, uid, uname, is_owner)
        
    confirm_btn.callback = _confirm_cb
    view.add_item(confirm_btn)
    view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
    
    if hasattr(msg, "edit"):
        await msg.edit(embed=embed, view=view)
    else:
        await send(msg.channel, "", embed=embed, view=view)


async def _handle_farm_view(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.housing import load_housing, get_tier_data
    from utils.ttrpg.farming import CROPS, get_crop_stage, is_harvestable
    from collections import Counter

    sheet = await load(uid)
    housing = load_housing(uid)
    if not sheet or not housing: return

    tier_data = get_tier_data(housing["tier"])
    max_plots = tier_data["farming_plots"]
    plots = housing.get("farming", {}).get("plots", [])

    harvestable_count = sum(1 for p in plots if is_harvestable(p))

    embed = discord.Embed(
        title=f"🌾 {housing['house_name']} — Garden",
        description=f"**{len(plots)}/{max_plots}** plots in use.{' ✅ **Crops ready to harvest!**' if harvestable_count else ''}",
        color=0x44aa44
    )

    for i in range(max_plots):
        if i < len(plots):
            p = plots[i]
            c_data = CROPS.get(p["crop_key"], {})
            stage = get_crop_stage(p)
            watered = "💧" if p.get("watered_today") else "🌵 needs water"
            ready = " ✅" if is_harvestable(p) else ""
            status_tag = ""
            if p.get("blighted"):
                status_tag = "\n🥀 **BLIGHTED** *(Use `!rpg farm treat`)*"
            elif p.get("blight_hardened"):
                status_tag = "\n🛡️ *Blight-Hardened (+1 Yield)*"
            embed.add_field(
                name=f"Plot {i+1}: {c_data.get('name', 'Unknown')}{ready}",
                value=f"{stage}\n{watered} ({p.get('watered_count',0)} waters){status_tag}",
                inline=True
            )
        else:
            embed.add_field(name=f"Plot {i+1}: Empty", value="Available for planting.", inline=True)

    view = discord.ui.View(timeout=120)

    # Seed planting — only show if there are open plots
    if len(plots) < max_plots:
        inv = Counter(sheet.get("inventory", []))
        seeds = [(k, CROPS[k]["name"]) for k in inv if k in CROPS]
        if seeds:
            options = [discord.SelectOption(label=name, value=key, emoji=CROPS[key].get("emoji","🌱")) for key, name in seeds[:25]]
            sel = discord.ui.Select(placeholder="🌱 Plant a seed...", options=options, row=0)
            async def _plant_cb(interaction):
                if str(interaction.user.id) != uid: return
                chosen = interaction.data["values"][0]
                await interaction.response.defer()
                fake = _InteractionMsg(interaction)
                await _handle_plant_crop(ctx, fake, _make_interaction_send(interaction), chosen, uid, uname, is_owner)
            sel.callback = _plant_cb
            view.add_item(sel)
        else:
            embed.set_footer(text="No seeds in inventory. Buy seeds from Sister Maren at the Herbalist's Hut.")

    # Action buttons
    if harvestable_count:
        harvest_btn = discord.ui.Button(label=f"🪣 Harvest ({harvestable_count} ready)", style=discord.ButtonStyle.green, row=1)
        async def _harvest_cb(interaction):
            if str(interaction.user.id) != uid: return
            await interaction.response.defer()
            fake = _InteractionMsg(interaction)
            await _handle_harvest_crops(ctx, fake, _make_interaction_send(interaction), "", uid, uname, is_owner)
        harvest_btn.callback = _harvest_cb
        view.add_item(harvest_btn)

    water_btn = discord.ui.Button(label="💧 Water All", style=discord.ButtonStyle.blurple, row=1)
    async def _water_cb(interaction):
        if str(interaction.user.id) != uid: return
        await interaction.response.defer()
        fake = _InteractionMsg(interaction)
        await _handle_water_crops(ctx, fake, _make_interaction_send(interaction), "", uid, uname, is_owner)
    water_btn.callback = _water_cb
    view.add_item(water_btn)

    # If user has blighted plots, show treat button
    if any(p.get("blighted") for p in plots):
        treat_btn = discord.ui.Button(label="🌿 Treat Blight", style=discord.ButtonStyle.green, row=1)
        async def _treat_cb(interaction):
            if str(interaction.user.id) != uid: return
            await interaction.response.defer()
            fake = _InteractionMsg(interaction)
            await _handle_farm_treat(ctx, fake, _make_interaction_send(interaction), "", uid, uname, is_owner)
        treat_btn.callback = _treat_cb
        view.add_item(treat_btn)

    view.add_item(_make_home_btn(ctx, uid, uname, is_owner, "🏠 Back", "my_home", 1))
    await msg.channel.send(embed=embed, view=view)


async def _handle_farm_treat(ctx, msg, send, rest, uid, uname, is_owner):
    """Treat blighted crop plots with herbal medicine."""
    sheet = await load(uid)
    from utils.ttrpg.housing import load_housing, save_housing
    housing = load_housing(uid)
    if not sheet or not housing: return

    plots = housing.get("farming", {}).get("plots", [])
    blighted_plots = [p for p in plots if p.get("blighted")]

    if not blighted_plots:
        return await send(msg.channel, embed=discord.Embed(
            description="🌿 *None of your farm plots are infected with blight.*",
            color=0x44aa44
        ))

    # Check for herbal medicine: healing_herb, tonic, bandage
    inv = sheet.get("inventory", [])
    used_item = None
    for candidate in ["healing_herb", "tonic", "bandage"]:
        if candidate in inv:
            used_item = candidate
            break

    if not used_item:
        return await send(msg.channel, embed=discord.Embed(
            title="🌿 Herbal Treatment Needed",
            description=(
                "You need an herbal medicine to cleanse the sward blight from your crops.\n\n"
                "**Accepted remedies:**\n"
                "• `healing_herb` (Healing Herb)\n"
                "• `tonic` (Tonic)\n"
                "• `bandage` (Bandage)"
            ),
            color=0xcc4444
        ))

    inv.remove(used_item)
    for p in blighted_plots:
        p["blighted"] = False
        p["blight_hardened"] = True

    housing["farming"]["plots"] = plots
    save_housing(housing)

    sheet["xp"] = sheet.get("xp", 0) + 25
    from utils.ttrpg.progression import check_level_up
    leveled, new_lvl = check_level_up(sheet)
    await save(sheet)

    from utils.ttrpg.shop import find_item
    item_data = find_item(used_item)
    item_name = item_data.get("name", used_item.replace("_", " ").title()) if item_data else used_item.title()

    desc = (
        f"**{sheet['character_name']}** applied a soothing salve of **{item_name}** to the blighted soil!\n\n"
        f"The yellowed mold recedes and the root systems strengthen! Your treated crops are now **Blight-Hardened** (+1 harvest yield bonus).\n\n"
        f"✨ **Cured:** {len(blighted_plots)} plot(s) · **Reward:** +25 XP"
    )
    if leveled:
        desc += f"\n🎉 **Level Up!** Reached **Level {new_lvl}!**"

    await msg.channel.send(embed=discord.Embed(
        title="🌿 Soil Blight Cleansed!",
        description=desc,
        color=0x2ecc71
    ))
    await _handle_farm_view(ctx, msg, send, rest, uid, uname, is_owner)


async def _handle_plant_crop(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.housing import load_housing, save_housing, get_tier_data
    from utils.ttrpg.farming import CROPS
    from datetime import date

    sheet = await load(uid)
    housing = load_housing(uid)
    if not sheet or not housing: return

    crop_input = rest.strip().lower().replace(" ", "_")
    SEED_ALIASES = {
        "blood_thistle": "blood_thistle_seed",
        "blood_thistle_seed": "blood_thistle_seed",
        "honey_sap": "honey_sap_seed",
        "honey_sap_seed": "honey_sap_seed",
        "honey_sap_cutting": "honey_sap_seed",
        "silver_moss": "silver_moss_spore",
        "silver_moss_spore": "silver_moss_spore",
        "silvermoss": "silver_moss_spore",
        "silvermoss_spore": "silver_moss_spore",
        "dire_root": "dire_root_bulb",
        "dire_root_bulb": "dire_root_bulb",
        "gilded_mushroom": "gilded_mushroom_spore",
        "gilded_mushroom_spore": "gilded_mushroom_spore",
        "gilded_spore": "gilded_mushroom_spore",
        "spirit_bloom": "spirit_bloom_seed",
        "spirit_bloom_seed": "spirit_bloom_seed",
    }
    crop_key = SEED_ALIASES.get(crop_input, crop_input)
    if crop_key not in CROPS or crop_key not in sheet.get("inventory", []):
        display_name = crop_input.replace('_', ' ')
        return await send(msg.channel, f"You don't have any {display_name} seeds in your inventory.")


    tier_data = get_tier_data(housing["tier"])
    max_plots = tier_data["farming_plots"]
    plots = housing.get("farming", {}).get("plots", [])
    
    if len(plots) >= max_plots:
        return await send(msg.channel, "No empty plots available.")

    # Consume seed
    sheet["inventory"].remove(crop_key)
    await save(sheet)

    # Plant
    new_plot = {
        "crop_key": crop_key,
        "planted_date": date.today().isoformat(),
        "watered_today": True,
        "watered_count": 1
    }
    plots.append(new_plot)
    housing["farming"]["plots"] = plots
    save_housing(housing)

    c_data = CROPS[crop_key]
    await send(msg.channel, f"🌱 You planted **{c_data['name']}** in Plot {len(plots)}.")
    await _handle_farm_view(ctx, msg, send, rest, uid, uname, is_owner)


async def _handle_water_crops(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.housing import load_housing, save_housing
    housing = load_housing(uid)
    if not housing: return
    
    plots = housing.get("farming", {}).get("plots", [])
    watered_count = 0
    for p in plots:
        if not p.get("watered_today"):
            p["watered_today"] = True
            p["watered_count"] = p.get("watered_count", 0) + 1
            watered_count += 1

    if watered_count == 0:
        return await send(msg.channel, embed=discord.Embed(description="All crops are already watered today.", color=0x888888))
    
    save_housing(housing)
    
    embed = discord.Embed(
        description=f"💧 You watered **{watered_count}** plot(s).",
        color=0x44aa44
    )
    await msg.channel.send(embed=embed)
    await _handle_farm_view(ctx, msg, send, rest, uid, uname, is_owner)


async def _handle_harvest_crops(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.housing import load_housing, save_housing
    from utils.ttrpg.farming import is_harvestable, harvest_crop
    from utils.ttrpg.calendar import get_season
    from utils.ttrpg.furniture import get_home_bonuses

    sheet = await load(uid)
    housing = load_housing(uid)
    if not sheet or not housing: return

    from utils.ttrpg.character_manager import INVENTORY_LIMIT
    current_unique = set(sheet.get("inventory", []))
    if len(current_unique) >= INVENTORY_LIMIT:
        return await send(msg.channel, embed=discord.Embed(
            description=f"❌ **Your inventory has too many unique item types.** Cannot harvest crops. Cap: {INVENTORY_LIMIT} unique types (currently holding {len(current_unique)}). Please sell or bank items first.",
            color=0xcc4444
        ))

    bonuses = get_home_bonuses(housing)
    yield_bonus = bonuses.get("farm_yield", 0)
    
    plots = housing.get("farming", {}).get("plots", [])
    to_keep = []
    harvested = []
    season = get_season()

    for p in plots:
        if is_harvestable(p):
            extra_hardened = 1 if p.get("blight_hardened") else 0
            item_key, qty = harvest_crop(p, season, yield_bonus + extra_hardened)
            sheet["inventory"].extend([item_key] * qty)
            harvested.append(f"{qty}x {item_key.replace('_',' ')}")
        else:
            to_keep.append(p)
    
    if not harvested:
        return await send(msg.channel, "Nothing is ready to harvest yet.")

    housing["farming"]["plots"] = to_keep
    save_housing(housing)
    await save(sheet)

    await send(msg.channel, f"🪣 **Harvest Complete!**\n\nGained: {', '.join(harvested)}.")
    await _handle_my_home(ctx, msg, send, rest, uid, uname, is_owner)


async def _handle_pet_shop(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.pets import PET_REGISTRY
    from utils.ttrpg.housing import load_housing_async

    sheet = await load(uid)
    housing = await load_housing_async(uid)
    if not sheet or not housing:
        return await send(msg.channel, "Visit `My Home` to establish a plot first.")

    embed = discord.Embed(
        title="🐾 Pip's Pets",
        description="Pip sits in the dirt, surrounded by creatures. They look at you expectantly.\n\n*Pets provide passive bonuses when fed daily.*",
        color=0x8b7355
    )
    
    options = []
    for key, data in PET_REGISTRY.items():
        embed.add_field(name=f"{data['emoji']} {data['name']} ({data['cost']}g)", value=data['desc'], inline=False)
        options.append(discord.SelectOption(label=f"{data['name']} ({data['cost']}g)", value=key, emoji=data['emoji']))

    view = discord.ui.View(timeout=120)
    sel = discord.ui.Select(placeholder="Adopt a pet...", options=options[:25], row=0)
    async def _buy_cb(interaction):
        if str(interaction.user.id) != uid: return
        chosen = interaction.data["values"][0]
        await interaction.response.defer()
        fake = _InteractionMsg(interaction)
        await _handle_buy_pet(ctx, fake, _make_interaction_send(interaction), chosen, uid, uname, is_owner)
    sel.callback = _buy_cb
    view.add_item(sel)
    view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
    
    await msg.channel.send(embed=embed, view=view)


async def _handle_buy_pet(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.pets import PET_REGISTRY
    from utils.ttrpg.housing import load_housing, save_housing, get_tier_data

    sheet = await load(uid)
    housing = load_housing(uid)
    if not sheet or not housing: return

    pet_key = rest.strip()
    pet_data = PET_REGISTRY.get(pet_key)
    if not pet_data: return

    tier_data = get_tier_data(housing["tier"])
    existing_pets = housing.get("pets", [])

    # Enforce slot limit
    if len(existing_pets) >= tier_data["pet_slots"]:
        return await send(msg.channel, "Your home cannot accommodate more pets.")

    # Enforce 1 per type
    if any(p["key"] == pet_key for p in existing_pets):
        return await msg.channel.send(embed=discord.Embed(
            description=f"You already have a **{pet_data['name']}**. Pip shakes their head. \"One of each, friend.\"",
            color=0xcc4444
        ))

    if sheet["gil"] < pet_data["cost"]:
        return await send(msg.channel, f"Not enough gil ({pet_data['cost']}g).")

    sheet["gil"] -= pet_data["cost"]
    await save(sheet)
    
    new_pet = {
        "key": pet_key,
        "name": pet_data["name"],
        "fed_today": False,   # starts unfed — owner feeds on first day
        "days_owned": 0
    }
    housing.setdefault("pets", []).append(new_pet)
    save_housing(housing)
    
    await _log_world_event(f"🐾 **{sheet['character_name']}** adopted a {pet_data['name']}.")
    await send(msg.channel, f"🐾 **{pet_data['name']} adopted!** It seems happy to follow you home.")


async def _handle_feed_pet(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.pets import PET_REGISTRY, PET_FOOD_NAMES
    from utils.ttrpg.housing import load_housing, save_housing

    sheet = await load(uid)
    housing = load_housing(uid)
    if not sheet or not housing: return

    pets = housing.get("pets", [])
    if not pets:
        return await send(msg.channel, "You have no pets to feed.")

    fed_count = 0
    gil_cost = 0
    for p in pets:
        if not p.get("fed_today"):
            p_data = PET_REGISTRY[p["key"]]
            cost = p_data["food_cost"]
            if sheet.get("gil", 0) + sheet.get("bank_balance", 0) >= cost:
                if sheet.get("gil", 0) >= cost:
                    sheet["gil"] -= cost
                else:
                    rem = cost - sheet.get("gil", 0)
                    sheet["gil"] = 0
                    sheet["bank_balance"] = sheet.get("bank_balance", 0) - rem
                p["fed_today"] = True
                fed_count += 1
                gil_cost += cost
    
    if fed_count == 0:
        return await send(msg.channel, "All pets are already fed or you can't afford food.")

    moogle_delivery_msg = ""
    for p in pets:
        if p["key"] == "moogle" and p.get("fed_today"):
            last_deliv = p.get("last_moogle_delivery", None)
            if last_deliv is None:
                # First time feeding — set the clock, don't deliver yet
                p["last_moogle_delivery"] = time.time()
            else:
                elapsed_days = (time.time() - last_deliv) / 86400.0
                if elapsed_days >= 7:
                    p["last_moogle_delivery"] = time.time()
                    loot = get_loot("easy")
                    if loot:
                        # Write to character sheet mailbox (not housing)
                        sheet.setdefault("mailbox", []).append({
                            "from_name": "House Moogle",
                            "item": loot,
                            "gil": 0,
                            "timestamp": time.time()
                        })
                        moogle_delivery_msg = "\n💌 *Your House Moogle gratefully accepts the Kupo Nut and drops a letter in your mailbox!*"

    await save(sheet)
    save_housing(housing)
    await send(msg.channel, f"🐾 You fed {fed_count} pet(s) for {gil_cost}g. They look content.{moogle_delivery_msg}")
    await _handle_my_home(ctx, msg, send, rest, uid, uname, is_owner)


async def _handle_furniture_shop(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.furniture import FURNITURE, HOUSING_TIER_TO_FURNITURE_TIER
    from utils.ttrpg.housing import load_housing_async

    sheet = await load(uid)
    housing = await load_housing_async(uid)
    if not sheet or not housing:
        return await send(msg.channel, "Visit `My Home` to establish a plot first.")

    tier_val = HOUSING_TIER_TO_FURNITURE_TIER.get(housing["tier"], 1)
    
    embed = discord.Embed(
        title="🪑 Barnaby's Furnishings",
        description="Barnaby is sanding a leg of some chair. He barely looks up.\n\n*Furniture provides passive bonuses to your home.*",
        color=0x8b7355
    )
    
    options = []
    owned = housing.get("furniture", [])
    for key, data in FURNITURE.items():
        if data["tier"] <= tier_val and key not in owned:
            embed.add_field(name=f"{data['emoji']} {data['name']} ({data['cost']}g)", value=data['desc'], inline=False)
            options.append(discord.SelectOption(label=f"{data['name']} ({data['cost']}g)", value=key, emoji=data['emoji']))

    view = discord.ui.View(timeout=120)
    if options:
        sel = discord.ui.Select(placeholder="Buy furniture...", options=options[:25], row=0)
        async def _buy_cb(interaction):
            if str(interaction.user.id) != uid: return
            chosen = interaction.data["values"][0]
            await interaction.response.defer()
            fake = _InteractionMsg(interaction)
            await _handle_buy_furniture(ctx, fake, _make_interaction_send(interaction), chosen, uid, uname, is_owner)
        sel.callback = _buy_cb
        view.add_item(sel)
    
    view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
    await msg.channel.send(embed=embed, view=view)


async def _handle_buy_furniture(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.furniture import FURNITURE
    from utils.ttrpg.housing import load_housing, save_housing, get_tier_data

    sheet = await load(uid)
    housing = load_housing(uid)
    if not sheet or not housing: return

    furn_key = rest.strip()
    f_data = FURNITURE.get(furn_key)
    if not f_data: return

    tier_data = get_tier_data(housing["tier"])
    if len(housing.get("furniture", [])) >= tier_data["furniture_slots"]:
        return await send(msg.channel, "Your home has no room for more furniture.")

    if sheet["gil"] < f_data["cost"]:
        return await send(msg.channel, f"Not enough gil ({f_data['cost']}g).")

    sheet["gil"] -= f_data["cost"]
    await save(sheet)
    
    housing.setdefault("furniture", []).append(furn_key)
    save_housing(housing)
    
    await send(msg.channel, f"🪑 **{f_data['name']} purchased!** Barnaby promises to deliver it 'soon'. It's already there.")


async def _handle_visit_plots(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.housing import load_housing, HOUSING_TIERS
    from utils.ttrpg.farming import CROPS, get_crop_stage, is_harvestable
    from utils.ttrpg.pets import PET_REGISTRY
    from utils.ttrpg.furniture import FURNITURE

    target_uid = rest.strip()
    if not target_uid:
        return await msg.channel.send(embed=discord.Embed(
            description="No plot selected.", color=0x888888))

    housing = load_housing(target_uid)
    if not housing:
        return await msg.channel.send(embed=discord.Embed(
            description="*That plot is empty — no one has settled here yet.*", color=0x888888))

    tier_data = HOUSING_TIERS.get(housing["tier"], {})

    embed = discord.Embed(
        title=f"{tier_data.get('emoji','🏡')} {housing['house_name']}",
        description=(
            f"*{tier_data.get('desc', '')}*\n"
            f"Owned by **{housing.get('character_name', 'Unknown')}**"
        ),
        color=0x8b7355
    )

    # ── Pets ──────────────────────────────────────────────────────────────────
    pets = housing.get("pets", [])
    if pets:
        pet_lines = []
        for p in pets:
            p_data = PET_REGISTRY.get(p["key"], {})
            emoji = p_data.get("emoji", "🐾")
            days = p.get("days_owned", 0)
            fed = "✅" if p.get("fed_today") else "❌"
            pet_lines.append(f"{emoji} **{p['name']}** — {days}d old · Fed: {fed}\n*{p_data.get('desc','')[:60]}*")
        embed.add_field(name="🐾 Pets", value="\n".join(pet_lines), inline=False)

    # ── Farm ──────────────────────────────────────────────────────────────────
    plots = housing.get("farming", {}).get("plots", [])
    if plots:
        farm_lines = []
        for i, p in enumerate(plots):
            c_data = CROPS.get(p["crop_key"], {})
            stage = get_crop_stage(p)
            ready = " ✅" if is_harvestable(p) else ""
            farm_lines.append(f"Plot {i+1}: **{c_data.get('name','?')}**{ready} — {stage}")
        embed.add_field(name="🌾 Garden", value="\n".join(farm_lines), inline=False)
    else:
        embed.add_field(name="🌾 Garden", value="*No crops planted.*", inline=False)

    # ── Furniture ─────────────────────────────────────────────────────────────
    furniture_keys = housing.get("furniture", [])
    if furniture_keys:
        furn_lines = []
        for f_key in furniture_keys:
            f_data = FURNITURE.get(f_key)
            if not f_data: continue
            bonus = f_data.get("bonus")
            bonus_str = f" (+{bonus['value']} {bonus['type'].replace('_',' ')})" if bonus else ""
            furn_lines.append(f"{f_data['emoji']} **{f_data['name']}**{bonus_str}")
        if furn_lines:
            embed.add_field(name="🪑 Furnishings", value="\n".join(furn_lines), inline=False)

    embed.set_footer(text=f"{tier_data.get('name','Home')} · {len(plots)} crop(s) · {len(pets)} pet(s) · {len(furniture_keys)} furnishing(s)")

    view = discord.ui.View(timeout=60)
    view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
    await msg.channel.send(embed=embed, view=view)


async def _handle_rename_house(ctx, msg, send, rest, uid, uname, is_owner):
    # Left intact as a fallback for text command "!rpg rename_house <name>"
    from utils.ttrpg.housing import load_housing, save_housing
    new_name = rest.strip()
    if not new_name:
        return await send(msg.channel, "Usage: `!rpg rename_house <New Name>`")
    
    housing = load_housing(uid)
    if not housing: return
    
    housing["house_name"] = new_name[:50]
    save_housing(housing)
    await send(msg.channel, f"🏡 House renamed to **{housing['house_name']}**.")


async def _handle_home_training(ctx, msg, send, rest, uid, uname, is_owner):
    """Bonus daily hunt from training dummy."""
    from utils.ttrpg.housing import load_housing, save_housing
    from utils.ttrpg.furniture import get_home_bonuses
    from datetime import date

    sheet = await load(uid)
    housing = load_housing(uid)
    if not sheet or not housing: return

    bonuses = get_home_bonuses(housing)
    if not bonuses.get("daily_training"):
        return await send(msg.channel, "You don't have a training dummy.")

    today = date.today().isoformat()
    if housing.get("last_training") == today:
        return await send(msg.channel, embed=discord.Embed(description="You've already trained today.", color=0x888888))

    housing["last_training"] = today
    save_housing(housing)

    # Grant a bonus hunt condition to respect the hard ceiling
    sheet.setdefault("conditions", []).append("hunt_bonus")
    await save(sheet)

    from utils.ttrpg.progression import hunts_remaining
    remaining = hunts_remaining(sheet)
    await send(msg.channel, f"🪆 You beat the dummy for an hour. You feel ready for one more hunt. ({remaining} hunts remaining)")
