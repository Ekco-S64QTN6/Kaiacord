with open("utils/ttrpg/loot_tables.py", "r") as f:
    lines = f.readlines()

new_hard_generics = '            ("miners_rebellion_pick", 2), ("soot_stained_cleaver", 2), ("bone_woven_bow", 2), ("echo_chime_focus", 2),\n            ("rusted_ironclad_plate", 2), ("ash_woven_robes", 2), ("cowl_of_the_blind_leech", 2), ("pendant_of_the_lost_scout", 2),\n'
new_deadly_generics = '            ("void_touched_scalpel", 2), ("marrow_bite_spear", 2), ("forge_masters_hammer", 2), ("aeridorian_spine_staff", 2),\n            ("flesh_forged_cuirass", 2), ("slag_crusted_helm", 2), ("striders_of_the_abyss", 2), ("resonance_warped_ring", 2),\n'
new_boss_generics = '            ("heart_forged_greatsword", 3), ("elaras_betrayal_dagger", 3), ("the_vessels_mantle", 3), ("tithe_collectors_signet", 3),\n'

# Find insertion points
for i, line in enumerate(lines):
    if "# Tier 4 generics" in line and '"hard"' in "".join(lines[max(0, i-30):i]):
        # We are in hard tier
        lines.insert(i+1, new_hard_generics)
        break

for i, line in enumerate(lines):
    if "# Tier 5 generics" in line and '"deadly"' in "".join(lines[max(0, i-30):i]):
        lines.insert(i+1, new_deadly_generics)
        break

for i, line in enumerate(lines):
    if "# Tier 6" in line and '"boss"' in "".join(lines[max(0, i-40):i]):
        lines.insert(i+1, new_boss_generics)
        break

with open("utils/ttrpg/loot_tables.py", "w") as f:
    f.writelines(lines)
print("Added items to loot_tables.py")
