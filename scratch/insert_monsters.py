with open("utils/ttrpg/monster_registry.py", "r") as f:
    lines = f.readlines()

with open("scratch/new_monsters.py", "r") as f:
    new_monsters_text = f.read()

insert_idx = -1
for i, line in enumerate(lines):
    if "CHROMATIC DRAGONS" in line:
        # Go up a couple lines to find the comment block
        insert_idx = i - 1
        break

if insert_idx != -1:
    lines.insert(insert_idx, new_monsters_text)
    with open("utils/ttrpg/monster_registry.py", "w") as f:
        f.writelines(lines)
    print("Inserted successfully.")
else:
    print("Could not find insertion point.")
