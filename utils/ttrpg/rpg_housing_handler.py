import time
import discord
from utils.ttrpg import turn_buttons

from utils.commands.stale_view import StaleSafeView
from utils.ttrpg.character_manager import load, save
from utils.ttrpg.progression import hunts_remaining, check_level_up
from utils.ttrpg.class_advancement import (
    apply_advanced_class_to_combat, apply_advanced_class_to_sheet,
    get_advanced_options, get_title, ADVANCED_CLASSES
)
from utils.ttrpg.world import LOCATION_DATA
import utils.ttrpg.dice_engine as dice_engine
from utils.ttrpg.shop import find_item
from utils.ttrpg.loot_tables import get_loot
from utils.ttrpg.broadcast import (
    log_world_event as _log_world_event,
    broadcast_world_event as _broadcast_world_event,
    level_up_flavor as _level_up_flavor,
    rare_loot_flavor as _rare_loot_flavor,
    _boss_approach_flavor
)

# One shim for every button path: it carries embeds and views, and
# answers msg.content / msg.mentions for handlers that read them.
from utils.ttrpg.rpg_views import _make_interaction_send, _InteractionMsg, no_character, no_house  # noqa: E402


from utils.ttrpg.rpg_views import *
from utils.ttrpg.session_manager import player_locked, serialize_user_action

async def _handle_seed_shop(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg seed_shop — Buy seeds from Sister Maren."""
    from utils.ttrpg.farming import CROPS

    sheet = await load(uid)
    if not sheet: return await no_character(msg)

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

    view = StaleSafeView(timeout=120)
    sel = discord.ui.Select(placeholder="🌱 Select seeds to buy...", options=options, row=0)

    @player_locked(uid)
    async def _buy_seed_cb(interaction: discord.Interaction):
        if str(interaction.user.id) != uid:
            await interaction.response.send_message("not yours.", ephemeral=True)
            return
        chosen = interaction.data["values"][0]
        await interaction.response.defer()
        s = await load(uid)
        if not s:
            return
        if s.get("location") != "herbalists_hut":
            await interaction.followup.send(
                embed=discord.Embed(
                    description="This seed-shop menu is no longer valid because you are not at the Herbalist's Hut.",
                    color=0xcc4444,
                ),
                ephemeral=True,
            )
            return
        cost = CROPS[chosen]["seed_cost"]
        from utils.ttrpg.inventory_capacity import grant_item, unique_item_type_count
        if s["gil"] < cost:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"Not enough gil. **{CROPS[chosen]['name']}** costs {cost}g. You have {s['gil']}g.",
                    color=0xcc4444
                ),
                ephemeral=True
            )
            return
        if not grant_item(s, chosen):
            from utils.ttrpg.character_manager import INVENTORY_LIMIT
            current_unique = unique_item_type_count(s.get("inventory", []))
            await interaction.followup.send(
                embed=discord.Embed(
                    description=(
                        f"Your inventory has too many unique item types. Cannot purchase seeds. "
                        f"Cap: {INVENTORY_LIMIT} unique types (currently holding {current_unique})."
                    ),
                    color=0xcc4444,
                ),
                ephemeral=True,
            )
            return
        s["gil"] -= cost
        await save(s)
        await interaction.followup.send(
            embed=discord.Embed(
                description=(
                    f"*Maren wraps the seeds in cloth and hands them over.*\n\n"
                    f"✅ Purchased **{CROPS[chosen]['name']}** for {cost}g.\n"
                    f"*Plant it at your home farm.* Remaining gil: {s['gil']}g"
                ),
                color=0x44aa44
            ),
            view=await turn_buttons.buttons_for(ctx, interaction, uid, uname, is_owner),
        )

    sel.callback = _buy_seed_cb
    view.add_item(sel)
    view.add_item(_make_status_btn(ctx, uid, uname, is_owner))
    await msg.channel.send(embed=embed, view=view)
