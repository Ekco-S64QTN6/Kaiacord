"""Read-only dice, bestiary, XP help, leaderboard, and command-guide handlers."""
import discord


async def _handle_roll(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.dice_engine import roll
    try:
        total, breakdown = roll(rest.strip() or "d20")
        await msg.channel.send(embed=discord.Embed(
            description=f"🎲 **{uname}** rolled `{rest.strip() or 'd20'}`: {breakdown}",
            color=0x4488cc
        ))
    except Exception:
        await msg.channel.send(embed=discord.Embed(description="Invalid syntax", color=0xcc4444))

async def _handle_lore(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg lore [n] — the Lore Codex: every page found, or one page read aloud."""
    from utils.ttrpg.character_manager import load
    from utils.ttrpg.lore import codex_text
    sheet = await load(uid)
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(
            description="No character yet. `!rpg new <name> <race> <class>`", color=0xcc4444))
    title, body = codex_text(sheet, rest)
    await msg.channel.send(embed=discord.Embed(title=title, description=body, color=0xc8a86b))


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

async def _handle_leaderboard(ctx, msg, send, rest, uid, uname, is_owner, *, location_data, class_icons, location_icons, get_title_fn, make_status_view):
    """!rpg leaderboard — show all characters ranked by XP."""
    from utils.ttrpg.character_manager import load_all_report
    scan = await load_all_report()
    sheets = scan.records
    if not sheets:
        if scan.failures:
            description = (
                f"No readable adventurers were found. {len(scan.failures)} character "
                "record(s) could not be read; administrators have been alerted."
            )
        else:
            description = "No adventurers have been created yet."
        return await msg.channel.send(embed=discord.Embed(description=description, color=0x888888))

    # Sort by XP descending, then by level descending, then by least deaths
    sheets.sort(key=lambda s: (s.get("xp", 0), s.get("level", 1), -s.get("deaths", 0)), reverse=True)

    MEDALS = ["🥇", "🥈", "🥉"]
    lines = []
    for i, s in enumerate(sheets[:15]):  # cap at 15 entries
        medal = MEDALS[i] if i < 3 else f"`{i+1}.`"
        cls_icon = class_icons.get(s.get("class", ""), "⚔️")
        char_title = get_title_fn(s)
        title_suffix = f" · *{char_title}*" if char_title != "Adventurer" else ""
        adv_class = s.get("advanced_class", "") or s.get("class", "?")
        loc_key = s.get("location", "oakhaven")
        loc_icon = location_icons.get(loc_key, "🗺️")
        loc_name = location_data.get(loc_key, {}).get("name", loc_key.replace("_", " ").title())
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
    footer = f"{len(sheets)} readable adventurer{'s' if len(sheets) != 1 else ''}"
    if scan.failures:
        footer += f" · incomplete scan: {len(scan.failures)} unreadable record(s)"
    embed.set_footer(text=footer)

    view = make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=embed, view=view)

#: `!rpg help`, section by section. Every subcommand `rpg_handler` dispatches is
#: here (test_rpg_help_lists_every_subcommand): the old card had drifted to
#: about half of them, missing class advancement, unequip, the bank, quests,
#: the blockade, the pond and all of housing.
RPG_HELP_FIELDS = (
    ("⚔️ World", (
        "`!rpg` — status & HUD\n"
        "`!rpg go <place>` — travel\n"
        "`!rpg look` · `look at <thing>`\n"
        "`!rpg map` — world map\n"
        "`!rpg weather` · `!rpg calendar`\n"
        "`!rpg lore` (`codex`) — history you've found")),
    ("🧍 Character", (
        "`!rpg new <name> <race> <class>`\n"
        "`!rpg sheet` — full stats\n"
        "`!rpg inventory` — gear & items\n"
        "`!rpg equip <item>` · `!rpg unequip <slot>`\n"
        "`!rpg use <item>` — a consumable\n"
        "`!rpg advance` — advanced class at level 5\n"
        "`!rpg leaderboard` (`lb`)")),
    ("🗡️ Combat", (
        "`!rpg hunt` — fight (1 hunt)\n"
        "`!rpg hunts` — hunts left today\n"
        "`!rpg attack` · `!rpg flee`\n"
        "`!rpg dungeon` — enter (2 hunts)\n"
        "`!rpg duel @user` · `!rpg accept`\n"
        "`!rpg roll <dice>` — d20, 2d6+3")),
    ("🏴 Bandit Blockade", (
        "on the Trade Road or Whisperwood Edge, while it's up:\n"
        "`!rpg raid` — assault the barricade\n"
        "`!rpg rob` — steal from their cache")),
    ("🍺 Stone Hearth", (
        "`!rpg rest` — full heal (5g)\n"
        "`!rpg drink` — +3 temp HP (2g)\n"
        "`!rpg gamble` — dice (10g)\n"
        "`!rpg rumor` — gossip\n"
        "`!rpg bard_song` — a ballad of recent events")),
    ("🏪 Hemlock's Store", (
        "`!rpg shop` — browse stock\n"
        "`!rpg buy <item>` · `!rpg sell <item>`\n"
        "`!rpg sell_all` (`sell_gear`) — unequipped gear\n"
        "`!rpg enhance [slot]` — rework gear, +1 to +5")),
    ("⛩️ Shrine", (
        "`!rpg pray` — daily blessing\n"
        "`!rpg offer <amount>` — XP\n"
        "`!rpg fountain` — heal spring")),
    ("🌿 Herbalist's Hut", (
        "`!rpg brew` — recipes · `!rpg brew <recipe>`\n"
        "`!rpg seed_shop` — seeds for your farm\n"
        "`!rpg talk maren`")),
    ("🏹 Watchtower", (
        "`!rpg scout` — monster intel\n"
        "`!rpg talk guard`")),
    ("🏦 Oakhaven", (
        "`!rpg bank` — balance\n"
        "`!rpg bank_deposit [gil]` · `!rpg bank_withdraw [gil]`\n"
        "`!rpg donate <gil>` — reinforce the walls\n"
        "`!rpg notices` — notice board\n"
        "`!rpg mail` (`deliver`) — moogle mail\n"
        "`!rpg talk <npc>`")),
    ("📜 Quests", (
        "`!rpg quests` — your log\n"
        "`!rpg quest <id>` — one quest\n"
        "`!rpg abandon <id>`")),
    ("🎣 Tricklebrook Pond", (
        "`!rpg go tricklebrook_pond`\n"
        "`!rpg fish` — fishing HUD\n"
        "`!rpg fish_shop` — bait & poles\n"
        "`!rpg sell_catch` — sell your bag to Gregor\n"
        "`!rpg purify` — cleanse the pond")),
    ("🏡 Home", (
        "`!rpg home` (`my_home`) — your house; buy one here\n"
        "`!rpg buy_house` · `!rpg upgrade_house`\n"
        "`!rpg rename_house <name>`\n"
        "`!rpg furniture_shop` · `!rpg buy_furniture <item>`\n"
        "`!rpg home_training` — bonus daily hunt")),
    ("🌾 Farm & pets", (
        "`!rpg farm_view` · `!rpg plant_crop <crop>`\n"
        "`!rpg water_crops` · `!rpg harvest_crops`\n"
        "`!rpg treat` (`farm_treat`) — cure blight\n"
        "`!rpg visit_plots <player>`\n"
        "`!rpg pet_shop` · `!rpg buy_pet <pet>` · `!rpg feed_pet`")),
    ("💬 NPCs", (
        "`elara` · `hemlock` · `barkeep`\n"
        "`guard` · `maren` · `gregor`\n"
        "`hooded_figure` · `pip` · `barnaby`")),
)
RPG_HELP_OWNER = ("🔧 Owner", (
    "`!rpg give @player <item>` · `!rpg heal @player`\n"
    "`!rpg event [name]` — start a world event\n"
    "`!rpg bestiary` · `!rpg xp`"))


def rpg_help_embed(is_owner: bool) -> discord.Embed:
    embed = discord.Embed(
        title="📜 Aethelgard Commands",
        description="*Type any command to use it. Most require being in the right location.*",
        color=0x8b7355
    )
    for name, value in RPG_HELP_FIELDS + ((RPG_HELP_OWNER,) if is_owner else ()):
        embed.add_field(name=name, value=value, inline=True)
    embed.set_footer(text="!rpg go  with no argument lists exits from your current location")
    return embed


async def _handle_rpg_help(ctx, msg, send, rest, uid, uname, is_owner):
    await msg.channel.send(embed=rpg_help_embed(is_owner))
