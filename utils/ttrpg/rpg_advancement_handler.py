"""Level-five specialization selection and its one-shot choice callbacks."""
import discord

from utils.commands.stale_view import StaleSafeView


async def _handle_advance(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character, advanced_options_fn, apply_advanced_class_fn, get_title_fn, player_locked_decorator, log_world_event_fn, broadcast_world_event_fn):
    """!rpg advance — choose an advanced class at level 5."""
    sheet = await load_character(uid)
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
    options = advanced_options_fn(base)
    if not options:
        sheet.pop("_advancement_pending", None)
        await save_character(sheet)
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

    view = StaleSafeView(timeout=120)
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
        @player_locked_decorator(uid)
        async def _choose(interaction: discord.Interaction, chosen=adv_name, data=adv_data):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("not your choice.", ephemeral=True)
                return
            s = await load_character(uid)
            # Every path is a button on the same message; only the first counts.
            if not s or not s.get("_advancement_pending"):
                await interaction.response.send_message("your path is already chosen.", ephemeral=True)
                return
            s = apply_advanced_class_fn(s, chosen)
            s.pop("_advancement_pending", None)
            await save_character(s)
            await interaction.response.send_message(embed=discord.Embed(
                title=f"✨ {s['character_name']} → {chosen}",
                description=f"*{data['flavor']}*\n\nYour path is set. The title *{get_title_fn(s)}* is yours.",
                color=0xffcc00
            ))
            await log_world_event_fn(
                f"⚔️ **{s['character_name']}** advanced to **{chosen}**. Oakhaven noticed."
            )
            adv_embed = discord.Embed(
                title=f"⚔️ {s['character_name']} → {chosen}",
                description=f"*{data['flavor']}*",
                color=0xffcc00
            )
            adv_embed.set_footer(text=f"Now: {get_title_fn(s)}")
            await broadcast_world_event_fn(ctx, adv_embed)
        btn.callback = _choose
        view.add_item(btn)

    await msg.channel.send(embed=embed, view=view)
