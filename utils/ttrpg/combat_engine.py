import secrets

from utils.ttrpg.equipment_registry import WEAPONS, ARMOR as ARMOR_DATA, HEADGEAR, BOOTS, ACCESSORIES
from utils.ttrpg.class_advancement import ADVANCED_CLASSES, apply_advanced_class_to_combat, resolve_class_proc
from utils.ttrpg.calendar import get_weather
from utils.ttrpg.rpg_ui import colored_bar

TIER_DAMAGE = {
    "trivial": (1, 4),
    "easy":    (1, 6),
    "medium":  (2, 6),
    "hard":    (3, 6),
    "boss":    (4, 6),
    "deadly":  (5, 6),
}


def _compute_player_defense(sheet: dict, def_mod_global: int = 0, pet_bonuses: dict = None) -> int:
    """
    Compute a player's effective defense using the full pipeline:
    gear soft-cap, advanced class bonuses, weather, pets, conditions, and global cap.
    Shared between _resolve_combat and duel setup.
    """
    pet_bonuses = pet_bonuses or {}

    def _eq_key(val):
        if not val:
            return None
        return val.get("key") if isinstance(val, dict) else val

    eq = sheet.get("equipment", {})
    armor     = ARMOR_DATA.get(_eq_key(eq.get("armor")))     or None
    head      = HEADGEAR.get(_eq_key(eq.get("head")))        or None
    boots_eq  = BOOTS.get(_eq_key(eq.get("boots")))          or None
    accessory = ACCESSORIES.get(_eq_key(eq.get("accessory"))) or None

    armor_def  = armor["defense_bonus"]     if armor     else 0
    head_def   = head["defense_bonus"]      if head      else 0
    boots_def  = boots_eq["defense_bonus"]  if boots_eq  else 0
    acc_def    = accessory["defense_bonus"] if accessory else 0

    dex_val = sheet.get("stats", {}).get("dex", 10)
    if armor:
        dex_val += armor.get("stat_bonus", {}).get("dex", 0)
    dex_mod = (dex_val - 10) // 2

    # Advanced class flat DEF bonus
    adv_flat_def = 0
    adv_class = sheet.get("advanced_class", "")
    if adv_class:
        for base_opts in ADVANCED_CLASSES.values():
            if adv_class in base_opts:
                b = base_opts[adv_class].get("bonuses", {})
                adv_flat_def = b.get("def_bonus", 0) + b.get("bone_shield_passive", 0)
                break

    # Gear soft-cap
    raw_gear_def = armor_def + head_def + boots_def + acc_def
    effective_gear_def = min(10, raw_gear_def) + max(0, raw_gear_def - 10) // 2

    pet_def_bonus = pet_bonuses.get("def_bonus", 0)

    # Weather modifier
    weather = get_weather()
    weather_effect = weather.get("effect") if weather else None
    weather_def_mod = weather_effect.get("value", 0) if weather_effect and weather_effect.get("type") == "armor_penalty" else 0

    raw_total_def = 10 + dex_mod + effective_gear_def + adv_flat_def + def_mod_global + pet_def_bonus + weather_def_mod

    # Conditions
    conditions = set(sheet.get("conditions", []))
    if "fortified" in conditions:
        raw_total_def += 2

    # Global DEF cap
    player_level = sheet.get("level", 1)
    global_def_cap = int(player_level * 1.5) + 12

    return min(raw_total_def, global_def_cap)


def _resolve_combat(sheet: dict, monster: dict, atk_mod_global: int = 0, def_mod_global: int = 0, is_duel: bool = False, pet_bonuses: dict = None) -> dict:
    """
    Resolve one round of combat between a player and a monster (or another player).
    Returns a dict with the results.
    """
    pet_bonuses = pet_bonuses or {}
    class_name = sheet.get("class", "Warrior")
    CLASS_ATTACK_STAT = {
        "Warrior": "str",
        "Ranger":  "dex",
        "Mage":    "int",
        "Rogue":   "dex",
        "Cleric":  "wis",
    }
    adv_class = sheet.get("advanced_class", "")
    if adv_class == "Wizard":
        atk_stat = "int"
    elif adv_class == "High Priest":
        atk_stat = "wis"
    else:
        atk_stat = CLASS_ATTACK_STAT.get(class_name, "str")
    atk_val = sheet.get("stats", {}).get(atk_stat, 10)
    atk_mod = (atk_val - 10) // 2

    dex_val = sheet.get("stats", {}).get("dex", 10)
    dex_mod = (dex_val - 10) // 2

    def _eq_key(val):
        """Extract the item key whether the slot stores a string or a dict."""
        if not val:
            return None
        return val.get("key") if isinstance(val, dict) else val

    eq = sheet.get("equipment", {})
    weapon    = WEAPONS.get(_eq_key(eq.get("weapon")))       or None
    armor     = ARMOR_DATA.get(_eq_key(eq.get("armor")))     or None
    head      = HEADGEAR.get(_eq_key(eq.get("head")))        or None
    boots_eq  = BOOTS.get(_eq_key(eq.get("boots")))          or None
    accessory = ACCESSORIES.get(_eq_key(eq.get("accessory"))) or None

    weapon_atk     = weapon["attack_bonus"]    if weapon    else 0
    weapon_dmg_die = weapon["damage_die"]      if weapon    else 4
    weapon_dmg_bonus = weapon.get("damage_bonus", 0) if weapon else 0
    armor_def      = armor["defense_bonus"]    if armor     else 0
    head_def       = head["defense_bonus"]     if head      else 0
    boots_def      = boots_eq["defense_bonus"] if boots_eq  else 0
    acc_def        = accessory["defense_bonus"]if accessory else 0
    acc_atk        = accessory.get("attack_bonus", 0) if accessory else 0

    # Apply armor stat bonuses to combat stats
    if armor:
        armor_stats = armor.get("stat_bonus", {})
        # INT/WIS/STR bonus to effective atk_val if relevant stat
        if atk_stat in armor_stats:
            atk_val += armor_stats[atk_stat]
            atk_mod = (atk_val - 10) // 2
        # DEX bonus affects DEF (computed later below)
        _armor_dex_bonus = armor_stats.get("dex", 0)
        dex_val += _armor_dex_bonus
        dex_mod = (dex_val - 10) // 2
    else:
        pass

    # --- Advanced Class Flat Bonuses ---
    adv_flat_atk = 0
    adv_flat_def = 0
    adv_class = sheet.get("advanced_class", "")
    if adv_class:
        for base_opts in ADVANCED_CLASSES.values():
            if adv_class in base_opts:
                b = base_opts[adv_class].get("bonuses", {})
                adv_flat_atk = b.get("atk_bonus", 0) + b.get("spell_atk_bonus", 0)
                adv_flat_def = b.get("def_bonus", 0) + b.get("bone_shield_passive", 0)
                break
    
    # --- Status Effects ---
    conditions = set(sheet.get("conditions", []))
    status_logs = []
    
    if "poisoned" in conditions:
        poison_dmg = 2
        sheet["hp"]["current"] = max(0, sheet["hp"]["current"] - poison_dmg)
        status_logs.append(f"🟢 *Poison saps {poison_dmg} HP.*")
        
    if sheet["hp"]["current"] <= 0:
        return {
            "sheet": sheet,
            "monster": monster,
            "player_hit": False, "player_crit": False, "player_fumble": False, "player_damage": 0,
            "monster_alive": True, "monster_hit": False, "monster_damage": 0,
            "player_alive": False,
            "exchanges": status_logs,
            "monster_defeated": False,
        }
        
    if "weakened" in conditions:
        atk_mod = atk_mod // 2
        status_logs.append(f"🦴 *Weakened state halves attack modifier.*")
        
    bless_bonus = 2 if "blessed" in conditions else 0
    if bless_bonus:
        status_logs.append(f"✨ *Blessed guides your aim (+2).*")

    # Streak bonus (+1 to hit if streak > 1)
    streak = sheet.get("hunt_streak", 0)
    streak_bonus = 1 if streak > 1 else 0
    if streak_bonus:
        status_logs.append(f"🔥 *Combat streak adds +{streak_bonus} to hit.*")

    luck_bonus = 1 if "lucky" in conditions else 0
    if luck_bonus:
        status_logs.append(f"🍀 *Luck guides your strike (+1).*")
        if "lucky" in sheet.get("conditions", []):
            sheet["conditions"].remove("lucky")

    # Pet bonus calculation
    pet_combat_bonus = pet_bonuses.get("combat_bonus", 0)

    # Potion buff: Firebrew (+2 ATK until next combat)
    embered_bonus = 2 if "embered" in conditions else 0
    if embered_bonus:
        status_logs.append(f"🔥 *Firebrew burns through your veins (+2 ATK).*")

    attack_mod = atk_mod + weapon_atk + acc_atk + adv_flat_atk + bless_bonus + streak_bonus + luck_bonus + atk_mod_global + pet_combat_bonus + embered_bonus
    
    # Cap player attack modifier relative to level to prevent near-guaranteed hits at high tiers
    global_atk_cap = int(sheet.get("level", 1) * 1.15) + 4
    attack_mod = min(attack_mod, global_atk_cap)
    
    # --- Initialize Result Variables ---
    player_hit = False
    player_crit = False
    player_fumble = False
    player_damage = 0
    hit_breakdown = "—"
    player_dmg_breakdown = "—"
    is_stunned = False

    # Stun check
    if "stunned" in conditions:
        if secrets.randbelow(2) == 0:
            is_stunned = True
            status_logs.append(f"⚡ *Stunned! You lose your attack this round.*")
    
    if not is_stunned:
        raw_hit = secrets.randbelow(20) + 1
        total_hit = raw_hit + attack_mod
        mod_str = f"{'+' if attack_mod >= 0 else ''}{attack_mod}"
        hit_breakdown = f"d20({raw_hit}){mod_str}=**{total_hit}** vs DEF {monster['defense']}"
    
        crit_threshold = 20
        if class_name == "Rogue": crit_threshold = 19
        adv = sheet.get("advanced_class", "")
        if adv:
            for base_opts in ADVANCED_CLASSES.values():
                if adv in base_opts:
                    stored = base_opts[adv].get("bonuses", {}).get("crit_threshold")
                    if stored:
                        crit_threshold = stored
                    break
        player_crit = raw_hit >= crit_threshold
        player_hit = total_hit >= monster["defense"] or player_crit
        player_fumble = raw_hit == 1
    
        if player_hit and not player_fumble:
            dice_count = 2 if player_crit else 1
            dmg_rolls = [secrets.randbelow(weapon_dmg_die) + 1 for _ in range(dice_count)]
            
            # Warrior mastery: +1 damage per 3 levels (Lv.1-3: 0, Lv.4-6: +1, Lv.7-9: +2, Lv.10: +3)
            warrior_dmg_bonus = (sheet.get("level", 1) - 1) // 3 if class_name == "Warrior" else 0
            adv_bonus_flat = 0
            if adv_class == "Wizard": adv_bonus_flat = 3
            if adv_class == "Shadowblade" and player_crit: adv_bonus_flat = 4
            
            total_dmg_bonus = atk_mod + warrior_dmg_bonus + adv_bonus_flat + weapon_dmg_bonus
            
            player_damage = max(1, sum(dmg_rolls) + total_dmg_bonus)
                    
            adv_mods = apply_advanced_class_to_combat(
                sheet, player_damage, True, player_crit, 0, monster, False
            )
            pd_bonus = adv_mods["player_damage_bonus"]
            if pd_bonus:
                player_damage += pd_bonus

            # ── Class proc (10% base / 50% on crit) ──────────────────────────
            proc_result = resolve_class_proc(sheet, weapon_dmg_die, player_crit, monster)
            proc_damage = 0
            if proc_result["proc_triggered"]:
                proc_damage = proc_result["proc_damage"]
                if proc_damage:
                    player_damage += proc_damage
                if proc_result["proc_heal"] > 0:
                    sheet["hp"]["current"] = min(
                        sheet["hp"]["max"],
                        sheet["hp"]["current"] + proc_result["proc_heal"]
                    )
            # ─────────────────────────────────────────────────────────────────

            die_str = f"{'2' if player_crit else '1'}d{weapon_dmg_die}"
            bonus_str = f"{'+' if total_dmg_bonus >= 0 else ''}{total_dmg_bonus}" if total_dmg_bonus != 0 else ""
            if pd_bonus:
                bonus_str += f"+{pd_bonus}(Class)"
            if proc_damage:
                bonus_str += f"+{proc_damage}(Proc)"
            player_dmg_breakdown = (
                f"{die_str}[{','.join(str(r) for r in dmg_rolls)}]"
                f"{bonus_str}=**{player_damage}**"
            )
            monster["hp"]["current"] = max(0, monster["hp"]["current"] - player_damage)
            
            # Apply lifesteal
            heal = adv_mods["heal_amount"]
            if heal:
                sheet["hp"]["current"] = min(sheet["hp"]["max"], sheet["hp"]["current"] + heal)
            if adv_mods["extra_log"]:
                status_logs.extend(adv_mods["extra_log"])
            # Log proc after main exchange lines
            if proc_result.get("proc_triggered") and proc_result.get("proc_log"):
                status_logs.extend(proc_result["proc_log"])

            # ── Weapon proc (independent 10% / 50% on crit) ──────────────────
            weapon_proc = weapon.get("proc") if weapon else None
            if weapon_proc:
                wp_chance = 0.50 if player_crit else 0.10
                if secrets.randbelow(100) < int(wp_chance * 100):
                    wp_die = weapon_proc["die"]
                    wp_extra = secrets.randbelow(wp_die) + 1
                    wp_emoji = weapon_proc.get("emoji", "⚡")
                    wp_name = weapon_proc["name"]
                    wp_element = weapon_proc.get("element", "")
                    player_damage += wp_extra
                    monster["hp"]["current"] = max(0, monster["hp"]["current"] - wp_extra)
                    status_logs.append(
                        f"{wp_emoji} **{wp_name}!** +{wp_extra} {wp_element} damage (1d{wp_die})"
                    )
                    # Drain element: heal player for proc damage
                    if wp_element == "drain":
                        sheet["hp"]["current"] = min(
                            sheet["hp"]["max"],
                            sheet["hp"]["current"] + wp_extra
                        )
                        status_logs.append(
                            f"🩸 *Life drained: +{wp_extra} HP*"
                        )
            # ─────────────────────────────────────────────────────────────────
            
            # Non-lethal duel check applied after all procs
            if is_duel and monster["hp"]["current"] == 0:
                monster["hp"]["current"] = 1
                status_logs.append(f"⚔️ **{sheet['character_name']}** pulls back the final blow, sparing their opponent.")


    monster_alive = monster["hp"]["current"] > 0

    monster_hit = False
    monster_damage = 0
    monster_dmg_breakdown = "—"
    monster_raw_hit = 0
    monster_total_hit = 0

    if monster_alive:
        player_defense = _compute_player_defense(sheet, def_mod_global, pet_bonuses)
        
        # Potion buff: Ironbark Tonic (+2 DEF until next combat)
        fortified_bonus = 2 if "fortified" in conditions else 0
        if fortified_bonus:
            status_logs.append(f"🛡️ *Ironbark hardens your skin (+2 DEF).*")

        # Monster to-hit uses the monster's own ATK stat directly.
        # This value is already scaled for dungeons (difficulty * 0.15) and
        # overworld distance (dist_mult) before entering combat resolution.
        _tier = monster.get("tier", "medium")
        monster_attack_mod = monster.get("attack", 0)

        monster_raw_hit = secrets.randbelow(20) + 1
        monster_total_hit = monster_raw_hit + monster_attack_mod
        monster_hit = monster_total_hit >= player_defense or monster_raw_hit == 20
        
        # In duels, if the opponent was brought to 1 HP this round, they shouldn't counter-attack immediately.
        if is_duel and monster["hp"]["current"] <= 1:
            monster_hit = False
            status_logs.append(f"⚔️ **{monster['name']}** is winded and cannot counter.")

        if monster_hit:
            num_dice, die_size = TIER_DAMAGE.get(_tier, (1, 6))
            monster_crit = (monster_raw_hit == 20)
            if monster_crit:
                # Crit: max possible damage on all dice
                dmg_rolls = [die_size] * num_dice
            else:
                dmg_rolls = [secrets.randbelow(die_size) + 1 for _ in range(num_dice)]
            monster_damage = max(1, sum(dmg_rolls) + (monster["attack"] // 2))
            

            adv_mods = apply_advanced_class_to_combat(
                sheet, 0, False, False, monster_damage, monster, False
            )
            md_reduction = adv_mods["monster_damage_reduction"]
            if md_reduction:
                monster_damage = max(0, monster_damage - md_reduction)
            if adv_mods["extra_log"]:
                status_logs.extend(adv_mods["extra_log"])
                
            # Non-lethal duel check
            if is_duel:
                if sheet["hp"]["current"] - monster_damage < 1:
                    monster_damage = max(0, sheet["hp"]["current"] - 1)
            
            crit_tag = " 💥CRIT" if monster_crit else ""
            monster_dmg_breakdown = f"{num_dice}d{die_size}({sum(dmg_rolls)})+{monster['attack']//2}=**{monster_damage}**{crit_tag}"
            sheet["hp"]["current"] = max(0, sheet["hp"]["current"] - monster_damage)

    player_alive = sheet["hp"]["current"] > 0
    
    if monster["hp"]["current"] <= 0:

        adv_mods = apply_advanced_class_to_combat(
            sheet, 0, False, False, 0, monster, True
        )
        if adv_mods["heal_amount"]:
            sheet["hp"]["current"] = min(sheet["hp"]["max"], sheet["hp"]["current"] + adv_mods["heal_amount"])
        if adv_mods["extra_log"]:
            status_logs.extend(adv_mods["extra_log"])

    # Pet post-combat heal (Sylvan Sprite)
    pet_heal = pet_bonuses.get("combat_heal", 0)
    if pet_heal > 0 and sheet["hp"]["current"] > 0 and monster["hp"]["current"] <= 0:
        hp_before = sheet["hp"]["current"]
        sheet["hp"]["current"] = min(sheet["hp"]["max"], sheet["hp"]["current"] + pet_heal)
        if sheet["hp"]["current"] > hp_before:
            status_logs.append(f"✨ **Pet Bonus:** Your sprite mends your wounds (+{pet_heal} HP).")

    # formatting exchanges
    exchanges = list(status_logs)
    
    if not is_stunned:
        player_attack_result = (
            "CRITICAL HIT" if player_crit else
            "FUMBLE" if player_fumble else
            "HIT" if player_hit else
            "MISS"
        )
        exchanges.extend([
            f"🗡️ Your attack: {hit_breakdown}",
            f"   → **{player_attack_result}**" + (f" — {player_dmg_breakdown}" if player_hit and not player_fumble else ""),
        ])

    if monster_alive:

        hp = monster["hp"]
        bar = colored_bar(hp["current"], hp["max"], 10)
        exchanges.append(f"   {monster['name']} HP: {hp['current']}/{hp['max']}\n```ansi\n{bar}\n```")
        
        if is_duel and hp["current"] == 1:
            exchanges.append(f"⚔️ **{sheet['character_name']}** stops their blade at **{monster['name']}**'s throat. Yield!")

        monster_crit_hit = (monster_raw_hit == 20)
        counter_result = "CRITICAL HIT" if monster_crit_hit else ("HIT" if monster_hit else "MISS")
        exchanges.append(f"🔴 Counter-attack: d20({monster_raw_hit})+{monster_attack_mod}=**{monster_total_hit}** → **{counter_result}** (your DEF: {player_defense})")
        if monster_hit:
            exchanges.append(f"   → {monster_dmg_breakdown}")
            exchanges.append(f"   Your HP: {sheet['hp']['current'] + monster_damage} → **{sheet['hp']['current']}/{sheet['hp']['max']}**")
        else:
            exchanges.append(f"   Your HP: **{sheet['hp']['current']}/{sheet['hp']['max']}** (untouched)")
    else:
        exchanges.append(f"   {monster['name']} HP: **0** 💀")
        if is_duel:
            exchanges.append(f"⚔️ **{sheet['character_name']}** stops their blade at **{monster['name']}**'s throat. Yield!")

    # ── Consume temporary combat buffs ────────────────────────────────────
    # Potions (embered & fortified) are now meant to last the full combat encounter
    # Therefore, they won't be cleared here during mid-round resolutions.

    return {
        "sheet": sheet,
        "monster": monster,
        "player_hit": player_hit,
        "player_crit": player_crit,
        "player_fumble": player_fumble,
        "player_damage": player_damage,
        "monster_alive": monster_alive,
        "monster_hit": monster_hit,
        "monster_damage": monster_damage,
        "player_alive": player_alive,
        "exchanges": exchanges,
        "monster_defeated": not monster_alive,
    }
