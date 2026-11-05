"""Stone Hearth dice gambling and its locked replay button."""
import discord

from utils.commands.stale_view import StaleSafeView


async def _handle_gamble(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character, secrets_module, daily_win_cap, player_locked_decorator, interaction_msg_factory, interaction_send_factory, status_btn_factory):
    """!rpg gamble — dice game at the Stone Hearth. 10 gil buy-in."""

    sheet = await load_character(uid)
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    if sheet.get("location") != "stone_hearth":
        return await msg.channel.send(embed=discord.Embed(
            description="The dice game only happens at the Stone Hearth.", 
            color=0xcc4444
        ))

    BUY_IN = 10
    # The Trickster's two dice make the table worth +1.6 gil a roll with no
    # limit on rolls. The perk stays; what it can take in a day does not grow
    # without bound. Losses count against the day's total.
    from datetime import date as _date
    _today = _date.today().isoformat()
    if sheet.get("gamble_day") != _today:
        sheet["gamble_day"], sheet["gamble_net"] = _today, 0
    if sheet.get("gamble_net", 0) >= daily_win_cap:
        return await msg.channel.send(embed=discord.Embed(
            description=f"You're {sheet['gamble_net']} gil up tonight.\n*The weathered man sweeps the dice "
                        f"off the table. \"Come back tomorrow.\"*",
            color=0xcc4444
        ))
    if sheet.get("gil", 0) < BUY_IN:
        return await msg.channel.send(embed=discord.Embed(
            description=f"The buy-in is {BUY_IN} gil. you have {sheet.get('gil', 0)}g.\n*A weathered man across the table doesn't look up from his cards.*",
            color=0xcc4444
        ))

    # Roll d6 vs d6. Tie goes to house.
    # Trickster gamble_edge check
    has_gamble_edge = False
    adv = sheet.get("advanced_class", "")
    if adv == "Trickster":
        has_gamble_edge = True

    if has_gamble_edge:
        # Roll twice, take best
        player_roll = max(secrets_module.randbelow(6) + 1, secrets_module.randbelow(6) + 1)
    else:
        player_roll = secrets_module.randbelow(6) + 1
        
    house_roll  = secrets_module.randbelow(6) + 1

    # ── Calendar: Festival of Fools — 2x wins AND 2x losses ───────────
    from utils.ttrpg.calendar import get_special_day as _get_special_gamble
    _sp_gamble = _get_special_gamble()
    _fools_mult = 1
    if _sp_gamble and _sp_gamble.get("buff") == "fools_luck":
        _fools_mult = _sp_gamble.get("buff_value", 2)

    sheet["gil"] -= BUY_IN

    if player_roll > house_roll:
        winnings = BUY_IN * 2 * _fools_mult
        sheet["gil"] += winnings
        net = BUY_IN * _fools_mult
        sheet["gamble_net"] = sheet.get("gamble_net", 0) + net
        fools_tag = " 🎭" if _fools_mult > 1 else ""
        result_line = f"🎲 You rolled **{player_roll}**, they rolled **{house_roll}**. You win!{fools_tag}"
        gil_line = f"+{net} gil (net). Total: {sheet['gil']}g"
    elif player_roll < house_roll:
        extra_loss = BUY_IN * (_fools_mult - 1)
        sheet["gil"] = max(0, sheet["gil"] - extra_loss)
        sheet["gamble_net"] = sheet.get("gamble_net", 0) - BUY_IN * _fools_mult
        fools_tag = " 🎭" if _fools_mult > 1 else ""
        result_line = f"🎲 You rolled **{player_roll}**, they rolled **{house_roll}**. You lose.{fools_tag}"
        gil_line = f"-{BUY_IN * _fools_mult} gil. Total: {sheet['gil']}g"
    else:
        extra_loss = BUY_IN * (_fools_mult - 1)
        sheet["gil"] = max(0, sheet["gil"] - extra_loss)
        sheet["gamble_net"] = sheet.get("gamble_net", 0) - BUY_IN * _fools_mult
        fools_tag = " 🎭" if _fools_mult > 1 else ""
        result_line = f"🎲 You both rolled **{player_roll}**. House takes ties.{fools_tag}"
        gil_line = f"-{BUY_IN * _fools_mult} gil. Total: {sheet['gil']}g"

    await save_character(sheet)

    gamble_view = StaleSafeView(timeout=60)

    gamble_again_btn = discord.ui.Button(
        label="🎲 Gamble Again", style=discord.ButtonStyle.secondary, row=0
    )

    @player_locked_decorator(uid)
    async def _gamble_again_cb(interaction: discord.Interaction):
        if str(interaction.user.id) != uid:
            await interaction.response.send_message("```\nnot your table.\n```", ephemeral=True)
            return
        await interaction.response.defer()
        fake_msg = interaction_msg_factory(interaction)
        send_fn = interaction_send_factory(interaction)
        from utils.ttrpg import rpg_core_handler as core
        await core._handle_gamble(ctx, fake_msg, send_fn, "", uid, uname, is_owner)

    gamble_again_btn.callback = _gamble_again_cb
    gamble_view.add_item(gamble_again_btn)
    gamble_view.add_item(status_btn_factory(ctx, uid, uname, is_owner))

    await msg.channel.send(embed=discord.Embed(
        description=f"{result_line}\n{gil_line}",
        color=0x44aa44 if player_roll > house_roll else 0xcc4444
    ), view=gamble_view)
