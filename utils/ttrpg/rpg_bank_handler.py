"""Oakhaven Bank and Ironbound Vault Chest transactions."""
import discord

from utils.commands.stale_view import StaleSafeView


async def _bank_refusal(sheet: dict, uid: str) -> str:
    """'' when the character can bank here: at the Oakhaven Bank, or at home
    with the Ironbound Vault Chest. Banking worked everywhere, which left the
    chest — owned by most players — with nothing to add."""
    loc = sheet.get("location", "")
    if loc == "oakhaven_bank":
        return ""
    if loc == "housing_district":
        from utils.ttrpg.housing import load_housing_async
        from utils.ttrpg.furniture import get_home_bonuses
        housing = await load_housing_async(str(uid))
        if housing and get_home_bonuses(housing).get("home_bank"):
            return ""
    return ("The vaults are at the **Oakhaven Bank** — or at home, if you own an Ironbound Vault Chest. "
            "`!rpg go bank`")


async def _handle_bank_deposit(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character, no_character_handler, player_locked_decorator, status_btn_factory):
    sheet = await load_character(uid)
    if not sheet: return await no_character_handler(msg)
    refusal = await _bank_refusal(sheet, uid)
    if refusal:
        return await msg.channel.send(embed=discord.Embed(description=refusal, color=0xcc4444))
    embed = discord.Embed(
        title="🏦 Deposit Gil",
        description=f"**Balance:** {sheet.get('bank_balance', 0)}g  ·  **On Hand:** {sheet.get('gil', 0)}g",
        color=0xaa88ff
    )
    view = StaleSafeView(timeout=60)
    for amt_label, amt_val in [("10g", 10), ("25g", 25), ("50g", 50), ("All", None)]:
        actual = sheet["gil"] if amt_val is None else amt_val
        btn = discord.ui.Button(
            label=f"Deposit {amt_label if amt_val else str(sheet['gil'])+'g'}",
            style=discord.ButtonStyle.secondary, row=0
        )
        @player_locked_decorator(uid)
        async def _dep_cb(interaction: discord.Interaction, amount=actual, is_all=(amt_val is None)):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("```\nnot yours.\n```", ephemeral=True)
                return
            s = await load_character(uid)
            if is_all: amount = s["gil"]
            if amount > s["gil"]:
                await interaction.response.send_message(
                    embed=discord.Embed(description=f"Not enough gil. You have {s['gil']}g.", color=0xcc4444),
                    ephemeral=True
                )
                return
            s["gil"] -= amount
            s["bank_balance"] = s.get("bank_balance", 0) + amount
            await save_character(s)
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"Deposited **{amount}g**.\nBalance: {s['bank_balance']}g  ·  On Hand: {s['gil']}g",
                    color=0x44aa44
                )
            )
        btn.callback = _dep_cb
        view.add_item(btn)
    view.add_item(status_btn_factory(ctx, uid, uname, is_owner))
    await msg.channel.send(embed=embed, view=view)


async def _handle_bank_withdraw(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character, no_character_handler, player_locked_decorator, status_btn_factory):
    sheet = await load_character(uid)
    if not sheet: return await no_character_handler(msg)
    refusal = await _bank_refusal(sheet, uid)
    if refusal:
        return await msg.channel.send(embed=discord.Embed(description=refusal, color=0xcc4444))
    balance = sheet.get("bank_balance", 0)
    embed = discord.Embed(
        title="🏦 Withdraw Gil",
        description=f"**Balance:** {balance}g  ·  **On Hand:** {sheet.get('gil', 0)}g",
        color=0xaa88ff
    )
    view = StaleSafeView(timeout=60)
    for amt_label, amt_val in [("10g", 10), ("25g", 25), ("50g", 50), ("All", None)]:
        actual = balance if amt_val is None else amt_val
        btn = discord.ui.Button(
            label=f"Withdraw {amt_label if amt_val else str(balance)+'g'}",
            style=discord.ButtonStyle.secondary, row=0
        )
        @player_locked_decorator(uid)
        async def _wth_cb(interaction: discord.Interaction, amount=actual, is_all=(amt_val is None)):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("```\nnot yours.\n```", ephemeral=True)
                return
            s = await load_character(uid)
            bank = s.get("bank_balance", 0)
            if is_all: amount = bank
            if amount > bank:
                await interaction.response.send_message(
                    embed=discord.Embed(description=f"Not enough in bank. Balance: {bank}g", color=0xcc4444),
                    ephemeral=True
                )
                return
            s["bank_balance"] = bank - amount
            s["gil"] += amount
            await save_character(s)
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"Withdrew **{amount}g**.\nBalance: {s['bank_balance']}g  ·  On Hand: {s['gil']}g",
                    color=0x44aa44
                )
            )
        btn.callback = _wth_cb
        view.add_item(btn)
    view.add_item(status_btn_factory(ctx, uid, uname, is_owner))
    await msg.channel.send(embed=embed, view=view)


async def _handle_bank(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, no_character_handler):
    # Keep the legacy !rpg bank for balance checking
    sheet = await load_character(uid)
    if not sheet: return await no_character_handler(msg)
    balance = sheet.get("bank_balance", 0)
    await msg.channel.send(embed=discord.Embed(
        title="🏦 OakHaven Bank",
        description=f"Your current balance is **{balance}g**.\nUse `!rpg bank_deposit` or `!rpg bank_withdraw` for transactions.",
        color=0xaa88ff
    ))
