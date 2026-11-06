"""Shrine prayer blessings and XP offering handlers."""
import discord

from utils.commands.stale_view import StaleSafeView


async def _handle_pray(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character, status_view_factory):
    """!rpg pray — once per day blessing at the Shrine of the Silent Ones."""
    from datetime import date

    sheet = await load_character(uid)
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    from utils.ttrpg.housing import load_housing_async
    from utils.ttrpg.furniture import get_home_bonuses
    _housing = await load_housing_async(uid)
    _has_shrine_replica = (
        _housing 
        and sheet.get("location") == "housing_district"
        and "shrine_replica" in _housing.get("furniture", [])
    )
    if sheet.get("location") != "shrine" and not _has_shrine_replica:
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at the Shrine of the Silent Ones to pray.\n`!rpg go shrine`\n\n*Or purchase a Shrine Replica for your home.*",
            color=0xcc4444
        ))

    from utils.ttrpg.calendar import get_special_day
    special = get_special_day()
    if special and special.get("shrine_gift"):
        today = date.today().strftime("%Y-%m-%d")
        if sheet.get("shrine_gift_date") != today:
            sheet["shrine_gift_date"] = today
            from utils.ttrpg.loot_tables import get_consumable_loot
            from utils.ttrpg.inventory_capacity import grant_item_or_mail
            gift = get_consumable_loot("hard") or "elixir"
            delivery = grant_item_or_mail(sheet, gift, "Feast of the Silent Ones")
            await save_character(sheet)
            gift_line = (
                f"**You received a {gift.replace('_',' ').title()}!**"
                if delivery == "inventory"
                else f"**{gift.replace('_',' ').title()}** was sent to Moogle Mail because your inventory is full."
            )
            return await msg.channel.send(embed=discord.Embed(
                title="🎁 Feast of the Silent Ones",
                description=f"A small bundle was left at the threshold.\n{gift_line}",
                color=0xd4a843
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

    # ── Quest Task Tracking: pray_shrine ────────────────────────────────────
    active_ids = sheet.get("active_quests", [])
    if active_ids:
        from utils.ttrpg.quest_registry import get_quest
        for active_id in list(active_ids):
            q = get_quest(active_id)
            if q and "pray_shrine" in q["tasks"]:
                prog = sheet.setdefault("quest_progress", {}).setdefault(active_id, [])
                if "pray_shrine" not in prog:
                    prog.append("pray_shrine")

    # ── Calendar Special Day / Shrine Vigil / Pilgrims: Morvenna's Ward (+5 HP on prayer) ──
    import time
    from utils.ttrpg.world_state import load_world_state
    wstate = load_world_state()
    has_vigil = wstate.get("blessing_window_until", 0) > time.time()
    has_pilgrims = wstate.get("pilgrim_blessing_until", 0) > time.time()

    if (special and special.get("buff") == "morvennas_ward") or has_vigil or has_pilgrims:
        _ward_hp = 5
        sheet["hp"]["current"] = min(sheet["hp"]["max"], sheet["hp"]["current"] + _ward_hp)
        sheet.setdefault("conditions", []).append("blessed")
        sheet["last_pray_date"] = today
        await save_character(sheet)
        view = status_view_factory(ctx, msg, uid, uname, is_owner)
        if has_pilgrims:
            desc_text = f"🕯️ **Blessed (Pilgrim's Blessing)** — *the Shrine is filled with incense and quiet chants.*\n+2 to next attack rolls · **+{_ward_hp} HP restored**\n*The Silent Ones watch over Oakhaven's travelers.*"
        elif has_vigil:
            desc_text = f"🕯️ **Blessed (Shrine Vigil)** — *the flame burns with intense blue resonance.*\n+2 to next attack rolls · **+{_ward_hp} HP restored**\n*The Silent Ones have answered Oakhaven's prayers. You are protected.*"
        else:
            desc_text = f"🕯️ **Blessed** — *Morvenna's ward shelters you on this dark night.*\n+2 to next attack rolls · **+{_ward_hp} HP restored**\n*The veil is thin. The dead are restless. But you are protected.*"
        return await msg.channel.send(embed=discord.Embed(
            description=desc_text,
            color=0xaaddff
        ), view=view)

    sheet.setdefault("conditions", []).append("blessed")
    sheet["last_pray_date"] = today
    await save_character(sheet)

    view = status_view_factory(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=discord.Embed(
        description="🕯️ **Blessed** — *the shrine acknowledges you.*\nYour next hunt grants +2 to all attack and stat rolls.\n*The condition clears after your next combat.*",
        color=0xaaddff
    ), view=view)


async def _handle_offer(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character, no_character_handler, player_locked_decorator, check_level_up_fn, xp_to_next_level_fn, status_btn_factory):
    from datetime import date

    sheet = await load_character(uid)
    if not sheet: return await no_character_handler(msg)

    if sheet.get("location") != "shrine":
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at the Shrine of the Silent Ones.\n`!rpg go shrine`",
            color=0xcc4444
        ))

    today = date.today().strftime("%Y-%m-%d")
    offered_today = sheet.get("offered_today", {})
    already_offered = offered_today.get(today, 0) if isinstance(offered_today, dict) else 0

    from utils.ttrpg.calendar import get_special_day
    special = get_special_day()
    DAILY_CAP = 60 if (special and special.get("buff") == "solstice_blessing") else 20
    XP_MULT = 3 if (special and special.get("buff") == "solstice_blessing") else 1

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
            f"*Each gil offered grants {XP_MULT} XP, up to {DAILY_CAP} max XP per day.*"
        ),
        color=0xaaddff
    )

    view = StaleSafeView(timeout=60)

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

        @player_locked_decorator(uid)
        async def _offer_cb(interaction: discord.Interaction, amt=amount):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("```\nnot yours.\n```", ephemeral=True)
                return

            s = await load_character(uid)
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
            xp_earned = eligible * XP_MULT
            s["xp"] += xp_earned
            s["offered_today"] = {t: already + eligible}

            # Check world_state for temporary shrine vigil or pilgrim events
            import time
            from utils.ttrpg.world_state import load_world_state
            wstate = load_world_state()
            has_vigil = wstate.get("blessing_window_until", 0) > time.time()
            has_pilgrims = wstate.get("pilgrim_blessing_until", 0) > time.time()
            vigil_blessing_granted = False
            
            if (has_vigil or has_pilgrims) and "blessed" not in s.get("conditions", []):
                s.setdefault("conditions", []).append("blessed")
                vigil_blessing_granted = True

            leveled_up, new_level = check_level_up_fn(s)
            await save_character(s)

            xp_next = xp_to_next_level_fn(s["level"])
            lines = [
                f"🕯️ **{eligible}g** offered. The air shifts.",
                f"+{xp_earned} XP ({s['xp']}/{xp_next})",
                f"On Hand: {s['gil']}g"
            ]
            if vigil_blessing_granted:
                if has_pilgrims:
                    lines.append("✨ **Blessed (Pilgrim's Blessing)** — *incense hangs in the warm air! (+2 to next combat roll)*")
                else:
                    lines.append("✨ **Blessed** — *Morvenna's ward shelters you during this Shrine Vigil! (+2 to next combat roll)*")
            if already + eligible >= DAILY_CAP:
                lines.append("*Daily offering limit reached.*")
            if leveled_up:
                lines.append(f"\n🎉 **Level Up! Now Lv.{new_level}!**")

            await interaction.response.send_message(
                embed=discord.Embed(description="\n".join(lines), color=0xaaddff)
            )

        btn.callback = _offer_cb
        view.add_item(btn)

    view.add_item(status_btn_factory(ctx, uid, uname, is_owner))
    await msg.channel.send(embed=embed, view=view)
