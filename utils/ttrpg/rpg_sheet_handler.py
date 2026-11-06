"""Detailed Aethelgard character sheet rendering and computed combat stats."""
import discord


async def _handle_sheet(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, location_icons, location_view_factory, stale_view_factory, status_btn_factory, hunts_remaining_fn, max_hunts_fn, xp_to_next_level_fn):
    """!rpg sheet — detailed character sheet with computed combat stats."""
    from utils.ttrpg.equipment_registry import WEAPONS, ARMOR as ARMOR_REG, HEADGEAR, BOOTS, ACCESSORIES
    from utils.ttrpg.class_advancement import ADVANCED_CLASSES, get_title
    from utils.ttrpg.housing import load_housing_async
    from utils.ttrpg.pets import get_pet_passive
    from utils.ttrpg.dice_engine import STAT_MODIFIER, CLASSES

    # Support viewing another player's sheet
    target_id = str(msg.mentions[0].id) if getattr(msg, 'mentions', None) and msg.mentions else uid
    sheet = await load_character(target_id)
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="Character not found.", color=0xcc4444))

    # ── Basics ────────────────────────────────────────────────────────
    char_title = get_title(sheet)
    base_class = sheet.get("class", "Warrior")
    adv_class = sheet.get("advanced_class", "")
    display_class = adv_class if (adv_class and adv_class != base_class) else base_class
    title_suffix = f" · *({char_title})*" if char_title != "Adventurer" else ""
    loc = sheet.get("location", "oakhaven")
    from utils.ttrpg.world import LOCATION_DATA
    loc_name = LOCATION_DATA.get(loc, {}).get("name", loc.replace("_", " ").title())

    # ── Stat Modifiers ────────────────────────────────────────────────
    stats = sheet.get("stats", {})
    stat_order = ["str", "dex", "con", "int", "wis", "cha"]
    stat_lines = []
    for s in stat_order:
        val = stats.get(s, 10)
        mod = STAT_MODIFIER(val)
        mod_str = f"+{mod}" if mod >= 0 else str(mod)
        stat_lines.append(f"{s.upper()} {val:2d} ({mod_str})")
    # Format as two rows of three for compact display
    stats_block = f"{stat_lines[0]}  {stat_lines[1]}  {stat_lines[2]}\n{stat_lines[3]}  {stat_lines[4]}  {stat_lines[5]}"

    # ── Combat Stats (mirror combat_engine.py logic) ──────────────────
    CLASS_ATTACK_STAT = {
        "Warrior": "str", "Ranger": "dex", "Mage": "int",
        "Rogue": "dex", "Cleric": "wis",
    }
    if adv_class == "Wizard":
        atk_stat = "int"
    elif adv_class == "High Priest":
        atk_stat = "wis"
    else:
        atk_stat = CLASS_ATTACK_STAT.get(base_class, "str")
    atk_val = stats.get(atk_stat, 10)
    atk_mod = STAT_MODIFIER(atk_val)
    dex_mod = STAT_MODIFIER(stats.get("dex", 10))

    def _eq_key(val):
        if not val: return None
        return val.get("key") if isinstance(val, dict) else val

    eq = sheet.get("equipment", {})
    weapon    = WEAPONS.get(_eq_key(eq.get("weapon")))       or {}
    armor     = ARMOR_REG.get(_eq_key(eq.get("armor")))      or {}
    head      = HEADGEAR.get(_eq_key(eq.get("head")))        or {}
    boots_eq  = BOOTS.get(_eq_key(eq.get("boots")))          or {}
    accessory = ACCESSORIES.get(_eq_key(eq.get("accessory"))) or {}

    weapon_atk = weapon.get("attack_bonus", 0)
    weapon_dmg_die = weapon.get("damage_die", 4)
    weapon_dmg_bonus = weapon.get("damage_bonus", 0)
    acc_atk = accessory.get("attack_bonus", 0)
    armor_def = armor.get("defense_bonus", 0)
    head_def = head.get("defense_bonus", 0)
    boots_def = boots_eq.get("defense_bonus", 0)
    acc_def = accessory.get("defense_bonus", 0)
    # Hemlock's rework, as combat_engine applies it.
    from utils.ttrpg import enhancement as _enh
    if weapon:
        _e_atk, _e_dmg = _enh.weapon_bonus(sheet, _eq_key(eq.get("weapon")))
        weapon_atk += _e_atk
        weapon_dmg_bonus += _e_dmg
    armor_def += _enh.defence_bonus(sheet, _eq_key(eq.get("armor"))) if armor else 0
    head_def += _enh.defence_bonus(sheet, _eq_key(eq.get("head"))) if head else 0
    boots_def += _enh.defence_bonus(sheet, _eq_key(eq.get("boots"))) if boots_eq else 0
    acc_def += _enh.defence_bonus(sheet, _eq_key(eq.get("accessory"))) if accessory else 0

    # Advanced class bonuses
    adv_flat_atk = 0
    adv_flat_def = 0
    adv_bonus_info = []
    if adv_class:
        for base_opts in ADVANCED_CLASSES.values():
            if adv_class in base_opts:
                b = base_opts[adv_class].get("bonuses", {})
                adv_flat_atk = b.get("atk_bonus", 0) + b.get("spell_atk_bonus", 0)
                adv_flat_def = b.get("def_bonus", 0)
                if b.get("crit_threshold"):
                    adv_bonus_info.append(f"Crit on {b['crit_threshold']}+")
                if b.get("lifesteal_pct"):
                    adv_bonus_info.append(f"{int(b['lifesteal_pct']*100)}% Lifesteal")
                if b.get("heal_on_kill"):
                    adv_bonus_info.append(f"+{b['heal_on_kill']} HP on kill")
                if b.get("atk_vs_undead"):
                    adv_bonus_info.append(f"+{b['atk_vs_undead']} vs Undead")
                if b.get("death_resist"):
                    adv_bonus_info.append("Death Resist")
                if b.get("gil_bonus_pct"):
                    adv_bonus_info.append(f"+{int(b['gil_bonus_pct']*100)}% Gil")
                if b.get("xp_bonus_pct"):
                    adv_bonus_info.append(f"+{int(b['xp_bonus_pct']*100)}% XP")
                break

    # Pet bonuses
    housing = await load_housing_async(str(sheet.get("user_id", target_id)))
    pet_bonuses = get_pet_passive(housing) if housing else {}
    pet_combat = pet_bonuses.get("combat_bonus", 0)
    pet_def = pet_bonuses.get("def_bonus", 0)

    total_atk = atk_mod + weapon_atk + acc_atk + adv_flat_atk + pet_combat
    raw_gear_def = armor_def + head_def + boots_def + acc_def
    effective_gear_def = min(10, raw_gear_def) + max(0, raw_gear_def - 10) // 2
    total_def = 10 + dex_mod + effective_gear_def + adv_flat_def + pet_def

    # Apply the same global cap used in combat_engine so the sheet is truthful
    player_level = sheet.get("level", 1)
    global_def_cap = int(player_level * 1.5) + 12
    effective_def = min(total_def, global_def_cap)

    # Damage string
    warrior_dmg_bonus = (sheet.get("level", 1) - 1) // 3 if base_class == "Warrior" else 0
    adv_dmg_flat = 3 if adv_class == "Wizard" else 0
    total_dmg_bonus = atk_mod + warrior_dmg_bonus + adv_dmg_flat + weapon_dmg_bonus
    dmg_sign = "+" if total_dmg_bonus >= 0 else ""
    dmg_str = f"1d{weapon_dmg_die}{dmg_sign}{total_dmg_bonus}" if total_dmg_bonus != 0 else f"1d{weapon_dmg_die}"

    # Crit threshold
    crit_thresh = 20
    if base_class == "Rogue": crit_thresh = 19
    if adv_class:
        for base_opts in ADVANCED_CLASSES.values():
            if adv_class in base_opts:
                stored = base_opts[adv_class].get("bonuses", {}).get("crit_threshold")
                if stored:
                    crit_thresh = stored
                break

    # ── Equipment Display ─────────────────────────────────────────────
    def _eq_name(slot_val, registry, default="—"):
        if not slot_val: return default
        name = slot_val.get("name", default) if isinstance(slot_val, dict) \
            else registry.get(slot_val, {}).get("name", default)
        n = _enh.level(sheet, _eq_key(slot_val))
        return f"{name} +{n}" if n else name

    equip_lines = [
        f"🗡️ {_eq_name(eq.get('weapon'), WEAPONS, 'Unarmed')}",
        f"🛡️ {_eq_name(eq.get('armor'), ARMOR_REG, 'Unarmored')}",
        f"🪖 {_eq_name(eq.get('head'), HEADGEAR)} 👢 {_eq_name(eq.get('boots'), BOOTS)}",
        f"💍 {_eq_name(eq.get('accessory'), ACCESSORIES)}",
    ]

    # ── Life Stats ────────────────────────────────────────────────────
    hp_cur = sheet["hp"].get("current", 1)
    hp_max = sheet["hp"].get("max", 1)
    xp_cur = sheet.get("xp", 0)
    xp_next = xp_to_next_level_fn(sheet["level"])
    gil = sheet.get("gil", 0)
    bank = sheet.get("bank_balance", 0)
    deaths = sheet.get("deaths", 0)
    streak = sheet.get("hunt_streak", 0)
    completed_quests = len(sheet.get("completed_quests", []))
    active_quests = sheet.get("active_quests", [])
    known_recipes = len(sheet.get("recipes", []))
    secrets_found = len(sheet.get("secrets", []))
    conditions = sheet.get("conditions", [])
    hunts = hunts_remaining_fn(sheet)
    max_hunts = max_hunts_fn(sheet)

    # Reputation
    rep = sheet.get("reputation", 0)
    if rep >= 100: rep_rank = "Hero"
    elif rep >= 50: rep_rank = "Trusted"
    elif rep >= 20: rep_rank = "Known"
    elif rep < -50: rep_rank = "Outlaw"
    elif rep < -20: rep_rank = "Unwelcome"
    else: rep_rank = "Neutral"

    # Fishing stats
    fish_stats = sheet.get("fishing_stats", {})
    total_caught = fish_stats.get("total_caught", 0)
    species_count = len(fish_stats.get("species_caught", {}))

    # ── Build Embed ───────────────────────────────────────────────────
    embed = discord.Embed(
        title=f"📄  {sheet['character_name'].upper()}{title_suffix}",
        description=(
            f"*{sheet.get('race', '?')} {display_class} Lv.{sheet['level']}*\n"
            f"*{location_icons.get(loc, '🗺️')} {loc_name}*"
        ),
        color=0x4a6741
    )

    # Stats block
    embed.add_field(
        name="📊 Attributes",
        value=f"```\n{stats_block}\n```",
        inline=False
    )

    combat_lines = [
        f"⚔️ **ATK:** +{total_atk} to hit",
        f"🗡️ **DMG:** {dmg_str}",
        f"🛡️ **DEF:** **{effective_def}**" + (f" *(raw {total_def}, capped)*" if effective_def < total_def else ""),
        f"💥 **Crit:** {crit_thresh}+",
    ]
    embed.add_field(
        name="⚔️ Combat",
        value="\n".join(combat_lines),
        inline=True
    )

    # ATK/DEF breakdown
    atk_parts = [f"{atk_stat.upper()} mod +{atk_mod}"]
    if weapon_atk: atk_parts.append(f"Weapon +{weapon_atk}")
    if acc_atk: atk_parts.append(f"Acc +{acc_atk}")
    if adv_flat_atk: atk_parts.append(f"Class +{adv_flat_atk}")
    if pet_combat: atk_parts.append(f"Pet +{pet_combat}")

    def_parts = [f"Base 10", f"DEX mod +{dex_mod}"]
    if effective_gear_def: def_parts.append(f"Gear +{effective_gear_def}")
    if adv_flat_def: def_parts.append(f"Class +{adv_flat_def}")
    if pet_def: def_parts.append(f"Pet +{pet_def}")

    breakdown_lines = [
        f"ATK: {' + '.join(atk_parts)}",
        f"DEF: {' + '.join(def_parts)}" + (f" = {total_def} → cap {global_def_cap}" if effective_def < total_def else ""),
    ]
    if effective_def < total_def:
        breakdown_lines.append(f"*Level {player_level} cap: Lv×1.5+12 = {global_def_cap} effective DEF*")
    embed.add_field(
        name="🔬 Breakdown",
        value="\n".join(breakdown_lines),
        inline=True
    )

    # Equipment
    embed.add_field(
        name="🎽 Equipment",
        value="\n".join(equip_lines),
        inline=False
    )

    # Class passives
    if adv_bonus_info:
        embed.add_field(
            name=f"✨ {adv_class} Passives",
            value=" · ".join(adv_bonus_info),
            inline=False
        )

    # Vitals
    vitals = (
        f"❤️ HP: **{hp_cur}/{hp_max}**\n"
        f"✨ XP: **{xp_cur}/{xp_next or 'MAX'}**\n"
        f"💰 Gil: **{gil}g** (Bank: {bank}g)"
    )
    embed.add_field(name="💖 Vitals", value=vitals, inline=True)

    # Career stats
    career = (
        f"🎯 Hunts: **{hunts}/{max_hunts}** today\n"
        f"🔥 Streak: **{streak}** kills\n"
        f"💀 Deaths: **{deaths}**\n"
        f"📜 Quests: **{completed_quests}** done"
    )
    embed.add_field(name="📈 Career", value=career, inline=True)

    # Knowledge / Misc
    misc = (
        f"⚗️ Recipes: **{known_recipes}**\n"
        f"🔍 Secrets: **{secrets_found}**\n"
        f"🎣 Fish caught: **{total_caught}** ({species_count} sp.)\n"
        f"🎭 Rep: **{rep_rank}** ({rep})"
    )
    embed.add_field(name="📚 Knowledge", value=misc, inline=True)

    # Active quests
    if active_quests:
        from utils.ttrpg.quest_registry import get_quest
        quest_lines = []
        for aq in active_quests:
            q = get_quest(aq)
            q_name = q["name"] if q else aq.replace("_", " ").title()
            prog = sheet.get("quest_progress", {}).get(aq, [])
            total_tasks = len(q["tasks"]) if q else "?"
            quest_lines.append(f"**{q_name}** — {len(prog)}/{total_tasks} tasks")
            
        embed.add_field(
            name=f"📜 Active Quests ({len(active_quests)})",
            value="\n".join(quest_lines),
            inline=False
        )

    # Conditions
    if conditions:
        cond_str = ", ".join(c.replace("_", " ").title() for c in conditions)
        embed.add_field(name="⚠️ Status Effects", value=cond_str, inline=False)

    embed.set_footer(text=f"!rpg sheet · {sheet.get('race', '?')} {display_class} · Created {__import__('datetime').datetime.fromtimestamp(sheet.get('created_at', 0)).strftime('%b %d, %Y')}")

    # ── View with navigation buttons ──────────────────────────────────
    loc = sheet.get("location", "oakhaven")
    if target_id == uid:
        view = location_view_factory(ctx, msg, uid, uname, is_owner, loc)
    else:
        view = stale_view_factory(timeout=120)
        view.add_item(status_btn_factory(ctx, uid, uname, is_owner))

    await msg.channel.send(embed=embed, view=view)
