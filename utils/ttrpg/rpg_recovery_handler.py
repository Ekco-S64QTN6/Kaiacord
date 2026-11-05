"""Pond purification and tavern/Shrine recovery actions for Aethelgard."""
import discord

async def _handle_purify(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, no_character_handler):
    """Purify Tricklebrook Pond as one global, recoverable player/world action."""
    sheet = await load_character(uid)
    if not sheet:
        return await no_character_handler(msg)

    loc = sheet.get("location", "oakhaven")
    if loc != "tricklebrook_pond":
        return await msg.channel.send(embed=discord.Embed(
            description="You must be at **Tricklebrook Pond** to purify the waters.\n`!rpg go tricklebrook_pond`",
            color=0xcc4444
        ))

    def _purify(current_sheet, wstate):
        if not wstate.get("fishing_water_tainted", False):
            return False, {"ok": False, "reason": "clear"}
        inventory = current_sheet.get("inventory", [])
        used_item = next(
            (candidate for candidate in ("aeridor_shard", "tonic", "healing_herb")
             if candidate in inventory),
            None,
        )
        if not used_item:
            return False, {"ok": False, "reason": "reagent"}

        inventory.remove(used_item)
        wstate["fishing_water_tainted"] = False
        wstate["fishing_water_tainted_expiry"] = 0
        current_sheet["xp"] = current_sheet.get("xp", 0) + 50
        current_sheet["reputation"] = current_sheet.get("reputation", 0) + 15
        from utils.ttrpg.progression import check_level_up
        leveled, new_level = check_level_up(current_sheet)
        return True, {
            "ok": True,
            "item": used_item,
            "leveled": leveled,
            "new_level": new_level,
        }

    from utils.ttrpg.world_state import mutate_world_state
    result = await mutate_world_state(_purify, sheet)
    if not result["ok"]:
        if result["reason"] == "clear":
            return await msg.channel.send(embed=discord.Embed(
                description="🌊 *The waters of Tricklebrook Pond are already clear and peaceful.*",
                color=0x3a8fc1
            ))
        return await msg.channel.send(embed=discord.Embed(
            title="🧪 Purification Reagent Needed",
            description=(
                "You need a cleansing reagent to neutralize the dark sludge.\n\n"
                "**Accepted items:**\n"
                "• `aeridor_shard` (Aeridor Crystal Shard)\n"
                "• `tonic` (Tonic)\n"
                "• `healing_herb` (Healing Herb)"
            ),
            color=0xcc4444
        ))

    used_item = result["item"]
    item_data = find_item(used_item)
    item_name = item_data.get("name", used_item.replace("_", " ").title()) if item_data else used_item
    desc = (
        f"**{sheet['character_name']}** crushed a **{item_name}** into the pond headwaters!\n\n"
        "A shimmering wave of resonance washes through the reeds. The oily black sludge dissolves, "
        "and the Silverstream runs pure again!\n\n"
        "✨ **Rewards:** +50 XP, +15 Town Reputation"
    )
    if result["leveled"]:
        desc += f"\n🎉 **Level Up!** You reached **Level {result['new_level']}!**"

    await msg.channel.send(embed=discord.Embed(
        title="🌊 Tricklebrook Pond Purified!",
        description=desc,
        color=0x2ecc71
    ))

    from utils.ttrpg.broadcast import log_world_event as _log_world_event, broadcast_world_event
    await _log_world_event(
        f"🌊 **Pond Purified:** {sheet['character_name']} cleansed Tricklebrook Pond using {item_name}."
    )
    await broadcast_world_event(ctx, discord.Embed(
        title="🌊 Waters Cleansed — Tricklebrook Pond",
        description=f"*{sheet['character_name']} neutralized the dark sludge at Tricklebrook Pond! Fishing waters are restored.*",
        color=0x2ecc71
    ))


async def _handle_drink(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character, make_status_view, hunts_remaining_fn, get_max_hunts_fn):
    """!rpg drink — buy an ale at the Stone Hearth. Costs 2 gil, +3 temporary HP."""

    sheet = await load_character(uid)
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    loc = sheet.get("location")
    if loc != "stone_hearth":
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at a tavern to drink.\n`!rpg go stone_hearth`", 
            color=0xcc4444
        ))
        
    DRINK_COST = 2
    drink_name = "an ale"
    barkeeper = "Mira"

    if sheet.get("gil", 0) < DRINK_COST:
        return await msg.channel.send(embed=discord.Embed(
            description=f"{barkeeper} glances at your coin purse and shakes her head.\n{drink_name.capitalize()} costs {DRINK_COST} gil. You have {sheet.get('gil', 0)}g.",
            color=0xcc4444
        ))

    # Grant temp HP by raising max temporarily (tracked via condition)
    TEMP_HP = 3
    already_drinking = any("ale" in c.lower() for c in sheet.get("conditions", []))
    if already_drinking:
        return await msg.channel.send(embed=discord.Embed(
            description=f"*{barkeeper} pours another without comment.*\nYou're already feeling the first one. Another won't stack.",
            color=0x888888
        ))

    sheet["gil"] -= DRINK_COST
    sheet["hp"]["max"] += TEMP_HP
    sheet["hp"]["current"] = min(sheet["hp"]["current"] + TEMP_HP, sheet["hp"]["max"])
    sheet.setdefault("conditions", []).append("ale_warmth")
    await save_character(sheet)

    view = make_status_view(ctx, msg, uid, uname, is_owner)
    icon = "🍺"
    await msg.channel.send(embed=discord.Embed(
        description=(
            f"{icon} {barkeeper} slides {drink_name} across. (-{DRINK_COST} gil)\n"
            f"Temp HP: +{TEMP_HP} ({sheet['hp']['current']}/{sheet['hp']['max']})\n"
            f"*+1 hunt cap until next rest.* ({hunts_remaining_fn(sheet)}/{get_max_hunts_fn(sheet)} available)\n"
            f"*Clears on rest.*"
        ), color=0x44aa44), view=view)


async def _handle_fountain(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character, make_status_view):
    """!rpg fountain — drink from the healing spring at the Shrine. Once per day, full heal."""
    from datetime import date

    sheet = await load_character(uid)
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
    await save_character(sheet)

    view = make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=discord.Embed(
        description=f"💧 **{sheet['character_name']} drinks from the spring.**\nYour wounds stitch closed. You are fully recovered. (HP: {sheet['hp']['current']}/{sheet['hp']['max']})\n*Clears when you next rest.*",
        color=0x44aa44
    ), view=view)


GAMBLE_DAILY_WIN_CAP = 100
