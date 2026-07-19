import sys
sys.path.append('.')
from utils.ttrpg.monster_registry import MONSTERS

# Get all deadly and boss monsters
deadlies = [(k, v) for k, v in MONSTERS.items() if v.get('tier') in ('deadly', 'boss')]

# Remove foreman_kregg since he must be first
deadlies = [m for m in deadlies if m[0] != 'foreman_kregg']

# Sort remaining by HP
deadlies.sort(key=lambda x: x[1]['hp'])

# Take the first 76
selected = deadlies[:76]

# Ensure the_mountain_heart is at floor 77 if it's not already
if selected[-1][0] != 'the_mountain_heart':
    # Swap it to the end if it's in the list
    for i, m in enumerate(selected):
        if m[0] == 'the_mountain_heart':
            selected.pop(i)
            break
    else:
        # If not in list, find it from original and add
        for m in deadlies:
            if m[0] == 'the_mountain_heart':
                selected.pop()
                break
    
    # Actually just force it to the end
    mh = [m for k, m in MONSTERS.items() if k == 'the_mountain_heart'][0]
    selected.append(('the_mountain_heart', mh))

print("STAIR_GUARDIANS = {")
print("    1: \"foreman_kregg\",")
for i, (k, v) in enumerate(selected):
    print(f"    {i+2}: \"{k}\",  # HP: {v['hp']}")
print("}")
