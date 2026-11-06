"""Aethelgard character creation and starting ability-score rolls."""
import discord


async def _handle_new(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, create_character, roll_fn, class_registry):
    

    existing = await load_character(uid)
    if existing:
        return await msg.channel.send(embed=discord.Embed(
            description=f"You already have a character: **{existing['character_name']}**.\nSheets are permanent.",
            color=0x888888
        ))
    
    args = rest.split()
    if len(args) < 3:
        class_list = ", ".join(class_registry.keys())
        return await msg.channel.send(embed=discord.Embed(
            description=f"Usage: `!rpg new <Name> <Race> <Class>`\nClasses: {class_list}",
            color=0x888888
        ))
    
    char_name = args[0]
    race = args[1].title()
    class_name = args[2].title()
    
    VALID_RACES = {"Human", "Elf", "Silvani", "Dwarf", "Glimmerkin", "Veiled"}
    if race not in VALID_RACES:
        return await msg.channel.send(embed=discord.Embed(
            description=f"Unknown race: **{race}**\nValid races: {', '.join(sorted(VALID_RACES))}",
            color=0xcc4444
        ))
    
    if class_name not in class_registry:
        class_list = ", ".join(class_registry.keys())
        return await msg.channel.send(embed=discord.Embed(
            description=f"Unknown class. Options: {class_list}",
            color=0xcc4444
        ))
    
    RACE_BONUSES = {
        "Human":    {"str": 1, "dex": 1, "con": 1, "int": 1, "wis": 1, "cha": 1},
        "Elf":      {"dex": 2, "int": 1, "wis": 1},
        "Silvani":  {"dex": 2, "wis": 2},
        "Dwarf":    {"con": 2, "str": 1},
        "Glimmerkin": {"cha": 2, "int": 1, "dex": 1},
        "Veiled":   {"int": 2, "cha": 2},
    }
    bonus_dict = RACE_BONUSES.get(race, {})
    
    stats_order = ["str", "dex", "con", "int", "wis", "cha"]
    rolled_stats = {}
    roll_log = []
    for stat in stats_order:
        dice = [roll_fn("d6")[0] for _ in range(4)]
        base = sum(sorted(dice)[1:])  # drop lowest
        bonus = bonus_dict.get(stat, 0)
        rolled_stats[stat] = base + bonus
        bonus_str = f" (+{bonus} race)" if bonus else ""
        roll_log.append(f"{stat.upper()}: {sorted(dice)[1:]} = {base}{bonus_str} -> {rolled_stats[stat]}")
    
    sheet = await create_character(uid, uname, char_name, race, class_name, rolled_stats)
    
    embed = discord.Embed(
        title="✨ New Adventurer Registered",
        description=f"**{char_name}**, the {race} {class_name}, has entered Aethelgard.\n\n**Stat rolls (4d6 drop lowest + Race):**\n```\n" + "\n".join(roll_log) + "\n```\n\nYou awaken in Oakhaven Town Square. Type `!rpg` to view your HUD.",
        color=0xddcc88
    )
    await msg.channel.send(embed=embed)
