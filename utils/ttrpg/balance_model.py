"""
Aethelgard TTRPG Balance Model Tool

Standalone script to compute expected hit rates, damage, and TTK for any class/level/equipment vs. monster tier.
Not imported by the game. Run manually for balance checks.
"""

# Example usage: python balance_model.py

# --- CONFIGURABLE PARAMETERS ---
# Define your classes, weapons, monsters, and tiers here for analysis

CLASSES = {
    "Warrior": {"atk_mod": 3, "weapon_bonus": 2},
    "Rogue": {"atk_mod": 4, "weapon_bonus": 1},
    "Mage": {"atk_mod": 2, "weapon_bonus": 3},
}

WEAPONS = {
    "Sword": {"die": 8, "atk_bonus": 1, "dmg_bonus": 2},
    "Dagger": {"die": 4, "atk_bonus": 2, "dmg_bonus": 1},
    "Staff": {"die": 6, "atk_bonus": 0, "dmg_bonus": 3},
}

MONSTERS = {
    "Trivial": {"hp": 15, "ac": 10},
    "Easy": {"hp": 25, "ac": 12},
    "Medium": {"hp": 40, "ac": 14},
    "Hard": {"hp": 60, "ac": 16},
    "Deadly": {"hp": 90, "ac": 18},
    "Boss": {"hp": 150, "ac": 20},
}

# --- FORMULAS ---
def expected_hit_rate(atk_mod, weapon_atk_bonus, monster_ac):
    # Simplified: (10 + mods) vs AC 20 scale
    hit_chance = (10 + atk_mod + weapon_atk_bonus) / (monster_ac + 10)
    return min(max(hit_chance, 0), 1)

def expected_damage_per_hit(weapon_die, class_atk_mod, weapon_dmg_bonus):
    # Average die roll + bonuses
    return (weapon_die / 2) + class_atk_mod + weapon_dmg_bonus

def expected_dps(hit_rate, dmg_per_hit):
    return hit_rate * dmg_per_hit

def time_to_kill(monster_hp, dps):
    if dps == 0:
        return float('inf')
    return monster_hp / dps

def run_balance_model():
    print("Aethelgard Balance Model Results:\n")
    for cname, cstats in CLASSES.items():
        for wname, wstats in WEAPONS.items():
            print(f"Class: {cname}, Weapon: {wname}")
            for mname, mstats in MONSTERS.items():
                hit_rate = expected_hit_rate(cstats["atk_mod"], wstats["atk_bonus"], mstats["ac"])
                dmg_per_hit = expected_damage_per_hit(wstats["die"], cstats["atk_mod"], wstats["dmg_bonus"])
                dps = expected_dps(hit_rate, dmg_per_hit)
                ttk = time_to_kill(mstats["hp"], dps)
                print(f"  vs {mname}: Hit%={hit_rate*100:.1f}  Dmg/Hit={dmg_per_hit:.1f}  DPS={dps:.1f}  TTK={ttk:.1f} rounds")
            print()

if __name__ == "__main__":
    run_balance_model()
