"""Watchtower and Tactical War Map scouting reports."""
import discord


async def _handle_scout(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character, status_view_factory, secrets_module):
    """!rpg scout — use the Watchtower to preview monster activity."""
    from utils.ttrpg.monster_registry import MONSTERS
    from utils.ttrpg.monster_registry import ENCOUNTER_TABLES as FULL_TABLES
    from utils.ttrpg.calendar import get_weather, get_season, SEASONAL_MONSTERS
    from datetime import date

    sheet = await load_character(uid)
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    from utils.ttrpg.housing import load_housing_async
    from utils.ttrpg.furniture import get_home_bonuses
    housing = await load_housing_async(uid)
    bonuses = get_home_bonuses(housing) if housing else {}
    has_war_map = bool(bonuses.get("home_scout"))
    is_at_home = sheet.get("location") == "housing_district"
    is_at_tower = sheet.get("location") == "watchtower"

    # Allow scouting if at watchtower OR if player owns the Tactical War Map
    if not is_at_tower and not has_war_map:
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at the Watchtower to scout, or own a Tactical War Map at home.\n`!rpg go watchtower` or `!rpg go housing_district`",
            color=0xcc4444
        ))

    weather = get_weather()
    effect = weather.get("effect")
    if effect and effect.get("type") == "scout_blocked":
        return await msg.channel.send(embed=discord.Embed(
            description=f"{weather['emoji']} **Scouting Blocked:** {effect['desc']}",
            color=0x888888
        ))

    from utils.ttrpg.world_state import load_world_state
    wstate = load_world_state()
    has_watchtower_bonus = bool(wstate.get("watchtower_bonus"))

    today = date.today().strftime("%Y-%m-%d")
    # Daily reset for scout counters
    if sheet.get("scout_date") != today and sheet.get("last_scout_date") != today:
        sheet["scout_date"] = today
        sheet["last_scout_date"] = today
        sheet["tower_scouts_today"] = 0
        sheet["home_scouts_today"] = 0
        sheet["scouted_spawns"] = {}

    tower_scouts = sheet.get("tower_scouts_today", 0)
    home_scouts = sheet.get("home_scouts_today", 0)

    # Determine whether using home map or watchtower
    if is_at_home or (has_war_map and not is_at_tower):
        if home_scouts >= 2:
            return await msg.channel.send(embed=discord.Embed(
                description="📌 *You've already studied your Tactical War Map twice today.* (2/2 home checks used)\nCome back tomorrow after dawn or visit the Watchtower (`!rpg go watchtower`).",
                color=0x888888
            ))
        sheet["home_scouts_today"] = home_scouts + 1
        scout_source_type = "home"
    else:
        if tower_scouts >= 1 and not has_watchtower_bonus:
            return await msg.channel.send(embed=discord.Embed(
                description="🗼 *The sentries nod. You've already had your look from the Watchtower today.* (1/1 tower checks used)\nCome back tomorrow or consult your Tactical War Map from home.",
                color=0x888888
            ))
        sheet["tower_scouts_today"] = tower_scouts + 1
        scout_source_type = "tower"

    sheet["scout_date"] = today
    sheet["last_scout_date"] = today
    scouted_spawns = {}

    HUNTING_LOCATIONS = {
        "whisperwood_edge": "Edge of the Whisperwood",
        "whisperwood_deep": "Whisperwood Deep",
        "aeridor_ruins":    "Aeridor Ruins",
        "trade_road":       "The Trade Road",
    }

    DANGER_ICONS = {
        "trivial": "🟢", "easy": "🟡",
        "medium": "🟠", "hard": "🔴", "deadly": "💀", "boss": "☠️"
    }

    season = get_season()
    seasonal_mods = SEASONAL_MONSTERS.get(season, {})

    lines = [f"🗼 **Scout Report** — *{weather['emoji']} {weather['name']} — {today}*\n"]

    for loc_key, loc_name in HUNTING_LOCATIONS.items():
        base_table = FULL_TABLES.get(loc_key, [])
        if isinstance(base_table, dict):
            flat_table = []
            for zone_list in base_table.values():
                flat_table.extend(zone_list)
            base_table = flat_table
            
        seasonal = seasonal_mods.get(loc_key, [])
        table = base_table + seasonal

        if not table:
            continue

        total_weight = sum(w for _, w in table)

        # Roll distinct random sightings, weighted (3 if watchtower bonus, else 2)
        spotted_limit = 3 if has_watchtower_bonus else 2
        spotted_keys = []
        attempts = 0
        while len(spotted_keys) < spotted_limit and attempts < 20:
            attempts += 1
            r = secrets_module.randbelow(total_weight)
            cum = 0
            for mk, w in table:
                cum += w
                if r < cum:
                    if mk not in spotted_keys and mk in MONSTERS:
                        spotted_keys.append(mk)
                    break

        scouted_spawns[loc_key] = list(spotted_keys[:spotted_limit])

        # Tier distribution
        tier_weights: dict[str, int] = {}
        for mk, w in table:
            t = MONSTERS.get(mk, {}).get("tier", "trivial")
            tier_weights[t] = tier_weights.get(t, 0) + w

        dominant_tier = max(tier_weights, key=tier_weights.get)
        dominant_pct = int(tier_weights[dominant_tier] / total_weight * 100)
        danger = DANGER_ICONS.get(dominant_tier, "⚪")

        spotted_names = [MONSTERS[k]["name"] for k in spotted_keys[:spotted_limit] if k in MONSTERS]
        seasonal_note = f"  *(+ {season} spawns)*" if seasonal else ""

        # XP range hint
        xp_vals = [MONSTERS[mk]["xp"] for mk, _ in table if mk in MONSTERS]
        xp_hint = f"  ·  XP {min(xp_vals)}–{max(xp_vals)}" if xp_vals else ""

        lines.append(
            f"{danger} **{loc_name}**{seasonal_note}\n"
            f"   Mostly *{dominant_tier}* ({dominant_pct}%){xp_hint}\n"
            f"   Spotted: *{', '.join(spotted_names) if spotted_names else 'nothing visible'}*"
        )

    sheet["scouted_spawns"] = scouted_spawns
    await save_character(sheet)

    if has_watchtower_bonus:
        lines.append("\n🔭 **The Watchtower's Silence:** *The sentries share their precision spyglass logs. Extra monster detail revealed.*")

    # Weather encounter note
    if effect and effect.get("type") == "encounter_mod":
        lines.append(f"\n⚠️ *{weather['name']} effect: {effect['desc']}*")


    # Randomized guard commentary
    GUARD_COMMENTS = [
        "*\"Whisperwood's been louder than usual. Watch yourself.\"*",
        "*\"Something came out of the ruins before sunrise again. We didn't follow it.\"*",
        "*\"Trade Road's clear as far as I can see. That's about two miles. After that, your problem.\"*",
        "*\"Don't go past the edge after dark. Not my rule. Just good sense.\"*",
        "*\"You didn't hear this from me — the deep wood's restless. More than usual.\"*",
        "*\"The canopy moved this morning. Wind was calm. Make of that what you will.\"*",
        "*\"Patrol came back short a man last week. We're not talking about it.\"*",
        "*\"Aeridor's been glowing again at dusk. Third time this month.\"*",
        "*\"I've got a theory about the ruins. But I like sleeping at night, so I keep it to myself.\"*",
        "*\"Ruins or deep woods tonight — ruins has better loot. Deep woods wants to keep it.\"*",
    ]
    lines.append(f"\n{GUARD_COMMENTS[secrets_module.randbelow(len(GUARD_COMMENTS))]}")

    embed = discord.Embed(
        description="\n".join(lines),
        color=0x8888aa
    )
    if scout_source_type == "home":
        footer_text = f"📌 Tactical War Map ({sheet['home_scouts_today']}/2 home checks used) · Today: {weather['name']}"
    else:
        footer_text = f"🗼 Watchtower Intel ({sheet['tower_scouts_today']}/1 tower check used) · Today: {weather['name']}"
    embed.set_footer(text=footer_text)
    view = status_view_factory(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=embed, view=view)
