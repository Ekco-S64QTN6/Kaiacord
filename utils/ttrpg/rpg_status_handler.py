"""Aethelgard status HUD rendering and inline level-up choice handling."""
import discord


async def _handle_status(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character, show_stat_choice_handler, load_session_fn, load_dungeon_fn, get_current_state_fn, xp_to_next_level_fn, xp_thresholds, colored_bar_fn, ansi_green, ansi_reset, hp_label_fn, hunts_remaining_fn, get_max_hunts_fn, get_title_fn, class_icons, location_icons, player_locked_decorator, location_view_factory, stale_view_factory):
    from utils.ttrpg.world import LOCATION_DATA
    # Resumption uses global imports now
    
    sheet = await load_character(uid)
    if not sheet:
        await msg.channel.send(embed=discord.Embed(
            description="You do not exist in Aethelgard. Type `!rpg new <Name> <Race> <Class>` to begin.",
            color=0xcc4444
        ))
        return
        
    # [LEVEL UP] Stat choice
    if sheet.get("_stat_choice_pending"):
        await show_stat_choice_handler(ctx, msg, send, sheet, uid, uname, is_owner)
        return
        
    loc = sheet.get("location", "oakhaven")
    loc_data = LOCATION_DATA.get(loc, {})
    loc_name = loc_data.get("name", loc.replace("_", " ").title())
    
    hp_cur = sheet["hp"].get("current", 1)
    hp_max = sheet["hp"].get("max", 1)
    
    xp_cur = sheet["xp"]
    xp_next = xp_to_next_level_fn(sheet["level"])
    if xp_next:
        floor = xp_thresholds.get(sheet["level"], 0)
        progress = xp_cur - floor
        req = xp_next - floor
        xp_bar_str = colored_bar_fn(progress, req, 14) + f" → Lv.{sheet['level'] + 1}"
    else:
        xp_bar_str = f"{ansi_green}██████████████{ansi_reset} (MAX)"
        
    gil = sheet.get("gil", 0)
    
    from utils.ttrpg.equipment_registry import WEAPONS, ARMOR as ARMOR_REG, HEADGEAR, BOOTS, ACCESSORIES
    
    # [RESUMPTION] Detect if we should add a "Resume Encounter" nudge
    resume_desc = ""
    chan_id = str(msg.channel.id)
    session = await load_session_fn(chan_id)
    if session and session.get("combat_active"):
        # Check if author is in this fight
        mine = [m for m in session.get("monsters", []) if isinstance(m, dict) and str(m.get("aggro_uid")) == str(uid) and m.get("origin_location") == sheet.get("location", "oakhaven")]
        if mine:
            resume_desc = f"\n\n⚔️ **You are currently in combat here!**\nUse `!rpg hunt` to re-open the interface."
    
    # Resumption logic
    dungeon = await load_dungeon_fn(uid)
    dungeon_in_combat = False
    if dungeon and dungeon.get("active"):
        if dungeon.get("active_combat"):
            dungeon_in_combat = True
            resume_desc += f"\n\n⚔️ **You are currently in a dungeon combat!**\nUse `!rpg dungeon` to resume the fight."
        else:
            resume_desc += f"\n\n🏚️ **You are currently in a dungeon!**\nUse `!rpg dungeon` to resume exploring."

    def _eq_display(slot_val, registry, atk=False):
        if not slot_val: return "Unarmed" if atk else "Unarmored"
        if isinstance(slot_val, dict):
            data = slot_val
        else:
            data = registry.get(slot_val)
        if not data: return slot_val
        if atk:
            return f"{data['name']} (+{data.get('attack_bonus',0)} ATK, d{data.get('damage_die',4)})"
        return f"{data['name']} (+{data.get('defense_bonus',0)} DEF)"

    eq = sheet.get("equipment", {})
    w_str  = _eq_display(eq.get("weapon"), WEAPONS, atk=True)
    a_str  = _eq_display(eq.get("armor"),  ARMOR_REG)

    def _sub_eq_display(slot_val, registry):
        if not slot_val: return "—"
        if isinstance(slot_val, dict):
            data = slot_val
        else:
            data = registry.get(slot_val)
        if not data: return slot_val
        
        name = data.get('name', slot_val)
        atk = data.get('attack_bonus', 0)
        dfs = data.get('defense_bonus', 0)
        
        stats = []
        if atk: stats.append(f"+{atk} ATK")
        if dfs: stats.append(f"+{dfs} DEF")
        
        if stats:
            return f"{name} ({', '.join(stats)})"
        return name

    h_str  = _sub_eq_display(eq.get("head"),      HEADGEAR)
    b_str  = _sub_eq_display(eq.get("boots"),     BOOTS)
    ac_str = _sub_eq_display(eq.get("accessory"), ACCESSORIES)
    
    hunts = hunts_remaining_fn(sheet)
    
    
    s = await load_session_fn(str(msg.channel.id))
    in_combat = False
    if s and s.get("combat_active"):
        for m in s.get("monsters", []):
            if isinstance(m, dict) and str(m.get("aggro_uid")) == str(uid) and m.get("origin_location") == sheet.get("location", "oakhaven"):
                in_combat = True
                break
                
    if dungeon_in_combat:
        in_combat = True
                
    # World State display
    from utils.ttrpg.calendar import get_weather
    weather = get_weather()
    state = get_current_state_fn()
    world_info = f"{weather['emoji']} **{weather['name']}** — *{weather['desc']}*"
    if state.get("event", "none") != "none":
        world_info += f"\n📣 **Event:** {state['event_desc']}"
        
    pct_hp = hp_cur / hp_max if hp_max > 0 else 0
    if hp_cur <= 0:
        color = 0x8B0000   # dark red - dead
    elif in_combat:
        color = 0xFF4500   # orange-red - fighting
    elif pct_hp <= 0.3:
        color = 0xFF6B6B   # red - critical
    else:
        color = 0x2D5A27   # deep forest green - normal
        
    char_title = get_title_fn(sheet)
    base_class = sheet.get("class", "Warrior")
    adv_class = sheet.get("advanced_class", "")
    # Format: (Title) AdvancedClass  or  (Title) BaseClass
    display_class = adv_class if (adv_class and adv_class != base_class) else base_class
    title_suffix = f" · *({char_title}) {display_class}*" if char_title != "Adventurer" else f" · *{display_class}*"
    adv_class_str = adv_class if (adv_class and adv_class != base_class) else base_class
    embed = discord.Embed(
        title=f"{class_icons.get(sheet.get('class'), '⚔️')}  {sheet['character_name'].upper()}{title_suffix}",
        description=f"*{adv_class_str} Lv.{sheet['level']}  ·  {location_icons.get(loc, '🗺️')} {loc_name}*\n\n{world_info}{resume_desc}",
        color=color
    )
    
    embed.add_field(
        name="❤️ HP",
        value=f"```ansi\n{colored_bar_fn(hp_cur, hp_max, 14)}\n``` {hp_label_fn(hp_cur, hp_max)}",
        inline=False
    )
    embed.add_field(
        name="✨ XP",
        value=f"```ansi\n{xp_bar_str}\n``` {xp_cur}/{xp_next or 'MAX'}",
        inline=True
    )
    embed.add_field(name="💰 Gil", value=f"{gil}g", inline=True)
    
    # Empty field for grid alignment if needed, or rely on Discord's 3-column layout
    
    # Replace the individual weapon/armor/head/boots/accessory/hunts/reputation fields with:
    equip_str = (
        f"🗡️ {w_str}\n"
        f"🛡️ {a_str}\n"
        f"🪖 {h_str} 👢 {b_str}\n"
        f"💍 {ac_str}"
    )
    embed.add_field(name="⚔️ Equipment", value=equip_str, inline=True)
    
    rep = sheet.get("reputation", 0)
    rep_rank = "Neutral"
    if rep >= 100: rep_rank = "Hero"
    elif rep >= 50: rep_rank = "Trusted"
    elif rep < -50: rep_rank = "Outlaw"
    elif rep < -20: rep_rank = "Unwelcome"
    
    embed.add_field(name="📊 Stats", value=f"🎯 {hunts}/{get_max_hunts_fn(sheet)} hunts\n🎭 {rep_rank} ({rep})", inline=True)
    
    
    conds = sheet.get("conditions", [])
    if conds:
        cond_str = ", ".join(c.title() for c in conds)
        embed.add_field(name="⚠️ Status Effects", value=cond_str, inline=False)
    
    if sheet.get("_advancement_pending", False) and not sheet.get("advanced_class"):
        from utils.ttrpg.class_advancement import get_advanced_options, apply_advanced_class_to_sheet
        options = get_advanced_options(sheet.get("class", ""))
        if options:
            embed.color = 0xffd700
            embed.description += "\n\n✨ **CLASS ADVANCEMENT AVAILABLE!** ✨\nYou have reached Level 5 and may choose an elite path. Your choice is permanent."
            
            sel_options = [discord.SelectOption(label=f"{adv} - {opts['description']}"[:100], value=adv) for adv, opts in options.items()]
            view = stale_view_factory(timeout=120)
            sel = discord.ui.Select(placeholder="Choose your path...", options=sel_options, row=0)
            
            @player_locked_decorator(uid)
            async def _adv_cb(interaction: discord.Interaction):
                if str(interaction.user.id) != uid:
                    return await interaction.response.send_message("Not yours.", ephemeral=True)
                chosen = interaction.data["values"][0]
                await interaction.response.defer()
                s = await load_character(uid)
                if not s or not s.get("_advancement_pending"): return
                s = apply_advanced_class_to_sheet(s, chosen)
                s["_advancement_pending"] = False
                await save_character(s)
                flavor = options[chosen].get("flavor", f"You are now a {chosen}.")
                await interaction.followup.send(f"```\n{flavor}\n```\n*You are now a {chosen}! Type `!rpg` to view your stats.*")
                
            sel.callback = _adv_cb
            view.add_item(sel)
            return await msg.channel.send(embed=embed, view=view)

    view = location_view_factory(ctx, msg, uid, uname, is_owner, loc)
    await msg.channel.send(embed=embed, view=view)
