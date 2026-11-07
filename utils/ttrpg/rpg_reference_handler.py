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
        "`!rpg use <item>` — use a supported consumable\n"
        "Retired Eye Drops / Trap Kit cannot be used; sell existing copies.\n"
        "`!rpg lore` — pages of history you've found\n"
        "`!rpg leaderboard`"
    ), inline=True)

    embed.add_field(name="🗡️ Combat", value=(
        "`!rpg hunt` — fight (1 hunt)\n"
        "`!rpg attack` — strike\n"
        "`!rpg flee` — escape attempt\n"
        "`!rpg dungeon` — enter dungeon (2 hunts)\n"
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
        "`!rpg sell <item>`\n"
        "`!rpg enhance [slot]` — rework gear, +1 to +5"
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
        "`!rpg bank` — balance; deposit/withdraw at the bank\n"
        "`!rpg donate <gil>` — reinforce the walls\n"
        "`!rpg notices` — notice board\n"
        "`!rpg quests` — quest log\n"
        "`!rpg mail` — moogle mail\n"
        "`!rpg talk <npc>`"
    ), inline=True)

    embed.add_field(name="🎣 Tricklebrook Pond", value=(
        "`!rpg go tricklebrook_pond`\n"
        "`!rpg fish` — open fishing HUD\n"
        "`!rpg fish_shop` — buy bait & poles\n"
        "*(Buy bait via Shop button in HUD)*"
    ), inline=True)

    embed.add_field(name="🏡 Housing District", value=(
        "`!rpg go housing_district`\n"
        "`!rpg home` — view/manage your home\n"
        "*(Farming, pets, & furniture)*"
    ), inline=True)

    embed.add_field(name="💬 NPCs", value=(
        "`elara` · `hemlock` · `barkeep`\n"
        "`guard` · `maren` · `gregor`\n"
        "`hooded_figure` · `pip` · `barnaby`"
    ), inline=True)

    embed.set_footer(text="!rpg go  with no argument lists exits from your current location")

    await msg.channel.send(embed=embed)
