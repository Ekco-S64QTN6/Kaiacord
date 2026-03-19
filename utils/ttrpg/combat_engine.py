import secrets

def _resolve_combat(sheet: dict, monster: dict, atk_mod_global: int = 0, def_mod_global: int = 0, is_duel: bool = False) -> dict:
    """
    Resolve one round of combat between a player and a monster (or another player).
    Returns a dict with the results.
    """
    class_name = sheet.get("class", "Warrior")
    CLASS_ATTACK_STAT = {
        "Warrior": "str",
        "Ranger":  "dex",
        "Mage":    "int",
        "Rogue":   "dex",
        "Cleric":  "wis",
    }
    atk_stat = CLASS_ATTACK_STAT.get(class_name, "str")
    atk_val = sheet.get("stats", {}).get(atk_stat, 10)
    atk_mod = (atk_val - 10) // 2

    dex_val = sheet.get("stats", {}).get("dex", 10)
    dex_mod = (dex_val - 10) // 2

    from utils.ttrpg.equipment_registry import WEAPONS, ARMOR as ARMOR_DATA, HEADGEAR, BOOTS, ACCESSORIES

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
    armor_def      = armor["defense_bonus"]    if armor     else 0
    head_def       = head["defense_bonus"]     if head      else 0
    boots_def      = boots_eq["defense_bonus"] if boots_eq  else 0
    acc_def        = accessory["defense_bonus"]if accessory else 0
    acc_atk        = accessory.get("attack_bonus", 0) if accessory else 0
    
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

    attack_mod = atk_mod + weapon_atk + acc_atk + bless_bonus + streak_bonus + luck_bonus + atk_mod_global
    
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
    
        crit_threshold = 19 if class_name == "Rogue" else 20
        player_crit = raw_hit >= crit_threshold
        player_hit = total_hit >= monster["defense"] or player_crit
        player_fumble = raw_hit == 1
    
        if player_hit and not player_fumble:
            dice_count = 2 if player_crit else 1
            dmg_rolls = [secrets.randbelow(weapon_dmg_die) + 1 for _ in range(dice_count)]
            
            warrior_dmg_bonus = ((sheet.get("level", 1) + 1) // 2) if class_name == "Warrior" else 0
            total_dmg_bonus = atk_mod + warrior_dmg_bonus
            
            player_damage = max(1, sum(dmg_rolls) + total_dmg_bonus)
            
            # Non-lethal duel check
            if is_duel:
                if monster["hp"]["current"] - player_damage < 1:
                    player_damage = max(0, monster["hp"]["current"] - 1)
                    status_logs.append(f"⚔️ **{sheet['character_name']}** pulls back their strike, dealing non-lethal damage.")
            
            die_str = f"{'2' if player_crit else '1'}d{weapon_dmg_die}"
            bonus_str = f"{'+' if total_dmg_bonus >= 0 else ''}{total_dmg_bonus}" if total_dmg_bonus != 0 else ""
            player_dmg_breakdown = (
                f"{die_str}[{','.join(str(r) for r in dmg_rolls)}]"
                f"{bonus_str}=**{player_damage}**"
            )
            monster["hp"]["current"] = max(0, monster["hp"]["current"] - player_damage)


    monster_alive = monster["hp"]["current"] > 0

    monster_hit = False
    monster_damage = 0
    monster_dmg_breakdown = "—"
    monster_raw_hit = 0
    monster_total_hit = 0

    if monster_alive:
        player_defense = 10 + dex_mod + armor_def + head_def + boots_def + acc_def + def_mod_global
        monster_attack_mod = monster["attack"] // 3
        monster_raw_hit = secrets.randbelow(20) + 1
        monster_total_hit = monster_raw_hit + monster_attack_mod
        monster_hit = monster_total_hit >= player_defense or monster_raw_hit == 20
        
        # In duels, if the opponent was brought to 1 HP this round, they shouldn't counter-attack immediately.
        if is_duel and monster["hp"]["current"] <= 1:
            monster_hit = False
            status_logs.append(f"⚔️ **{monster['name']}** is winded and cannot counter.")

        if monster_hit:
            base = secrets.randbelow(6) + 1
            # Apply global defense mod to monster's damage or hit? Usually hit. 
            # But let's apply a slight damage reduction if def_mod_global is positive (e.g. cover/rain)
            monster_damage = max(1, base + (monster["attack"] // 2))
            
            # Non-lethal duel check
            if is_duel:
                if sheet["hp"]["current"] - monster_damage < 1:
                    monster_damage = max(0, sheet["hp"]["current"] - 1)
            
            monster_dmg_breakdown = f"1d6({base})+{monster['attack']//2}=**{monster_damage}**"
            sheet["hp"]["current"] = max(0, sheet["hp"]["current"] - monster_damage)

    player_alive = sheet["hp"]["current"] > 0

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
        from utils.ttrpg.rpg_ui import colored_bar
        hp = monster["hp"]
        bar = colored_bar(hp["current"], hp["max"], 10)
        exchanges.append(f"   {monster['name']} HP: {hp['current']}/{hp['max']}\n```ansi\n{bar}\n```")
        
        if is_duel and hp["current"] == 1:
            exchanges.append(f"⚔️ **{sheet['character_name']}** stops their blade at **{monster['name']}**'s throat. Yield!")

        counter_result = "HIT" if monster_hit else "MISS"
        exchanges.append(f"🔴 Counter-attack: d20({monster_raw_hit})+{monster['attack']//3}=**{monster_total_hit}** → **{counter_result}**")
        if monster_hit:
            exchanges.append(f"   → {monster_dmg_breakdown}")
            exchanges.append(f"   Your HP: {sheet['hp']['current'] + monster_damage} → **{sheet['hp']['current']}/{sheet['hp']['max']}**")
        else:
            exchanges.append(f"   Your HP: **{sheet['hp']['current']}/{sheet['hp']['max']}** (untouched)")
    else:
        exchanges.append(f"   {monster['name']} HP: **0** 💀")
        if is_duel:
            exchanges.append(f"⚔️ **{sheet['character_name']}** stops their blade at **{monster['name']}**'s throat. Yield!")

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
