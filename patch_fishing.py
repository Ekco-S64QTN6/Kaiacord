import re

with open("utils/commands/fishing_handler.py", "r", encoding="utf-8") as f:
    content = f.read()

# Chunk 1
content = content.replace(
    '''        bait = stats.get("bait", "earthworm")
        bait_count = stats.get("bait_count", 0)
        pole_name = POLES.get(pole, {}).get("name", "None") if pole else "None"''',
    '''        bait = stats.get("bait", "earthworm")
        if "bait_count" in stats:
            stats.setdefault("bait_stock", {})[bait] = stats.pop("bait_count", 0)
        bait_count = stats.get("bait_stock", {}).get(bait, 0)
        pole_name = POLES.get(pole, {}).get("name", "None") if pole else "None"'''
)

# Chunk 2
content = content.replace(
    '''        bait_count = fishing_stats.get("bait_count", 0)
        if bait_count > 0:
            fishing_stats["bait_count"] = bait_count - 1''',
    '''        if "bait_count" in fishing_stats:
            old_bait = fishing_stats.get("bait", "earthworm")
            fishing_stats.setdefault("bait_stock", {})[old_bait] = fishing_stats.pop("bait_count", 0)
        bait_stock = fishing_stats.get("bait_stock", {})
        if bait_stock.get(self._bait_key, 0) > 0:
            bait_stock[self._bait_key] -= 1
        fishing_stats["bait_stock"] = bait_stock'''
)

# Chunk 4
content = content.replace(
    '''    bait_key = stats.get("bait", "earthworm")
    pole_key = stats.get("pole")
    bait_count = stats.get("bait_count", 0)''',
    '''    if "bait_count" in stats:
        old_bt = stats.get("bait", "earthworm")
        stats.setdefault("bait_stock", {})[old_bt] = stats.pop("bait_count", 0)
    
    bait_key = stats.get("bait", "earthworm")
    pole_key = stats.get("pole")
    bait_count = stats.get("bait_stock", {}).get(bait_key, 0)'''
)

# Chunk 5
content = content.replace(
    '''            bait_count = fishing_stats.get("bait_count", 0)
            if bait_count > 0:
                fishing_stats["bait_count"] = bait_count - 1''',
    '''            if "bait_count" in fishing_stats:
                old_bait = fishing_stats.get("bait", "earthworm")
                fishing_stats.setdefault("bait_stock", {})[old_bait] = fishing_stats.pop("bait_count", 0)
            bait_stock = fishing_stats.get("bait_stock", {})
            if bait_stock.get(bait_key, 0) > 0:
                bait_stock[bait_key] -= 1
            fishing_stats["bait_stock"] = bait_stock'''
)

# Chunk 6
content = content.replace(
    '''    current_bait = stats.get("bait", "earthworm")
    current_pole = stats.get("pole")
    bait_count = stats.get("bait_count", 0)
    current_bait_name = BAIT.get(current_bait, {}).get("name", "Earthworm")''',
    '''    current_bait = stats.get("bait", "earthworm")
    current_pole = stats.get("pole")
    if "bait_count" in stats:
        old_bt = stats.get("bait", "earthworm")
        stats.setdefault("bait_stock", {})[old_bt] = stats.pop("bait_count", 0)
    bait_count = stats.get("bait_stock", {}).get(current_bait, 0)
    current_bait_name = BAIT.get(current_bait, {}).get("name", "Earthworm")'''
)

# Chunk 7
content = content.replace(
    '''            fs["bait"] = chosen_bait
            fs["bait_count"] = fs.get("bait_count", 0) + 10
            await save(s)
            await interaction.followup.send(
                embed=discord.Embed(
                    description=(
                        f"*Gregor hands over a pack of {bait_data['name']}.*\\n\\n"
                        f"✅ **{bait_data['name']} ×10** purchased for **{cost}g**.\\n"
                        f"Bait count: {fs['bait_count']}. Gil: {s['gil']}g"
                    ),''',
    '''            if "bait_count" in fs:
                old_bait = fs.get("bait", "earthworm")
                fs.setdefault("bait_stock", {})[old_bait] = fs.pop("bait_count", 0)
            fs["bait"] = chosen_bait
            bait_stock = fs.setdefault("bait_stock", {})
            bait_stock[chosen_bait] = bait_stock.get(chosen_bait, 0) + 10
            await save(s)
            total_active_bait = fs["bait_stock"][chosen_bait]
            await interaction.followup.send(
                embed=discord.Embed(
                    description=(
                        f"*Gregor hands over a pack of {bait_data['name']}.*\\n\\n"
                        f"✅ **{bait_data['name']} ×10** purchased for **{cost}g**.\\n"
                        f"Bait count: {total_active_bait}. Gil: {s['gil']}g"
                    ),'''
)

# Chunk 8
content = content.replace(
    '''        stats["bait"] = "earthworm"
        stats["bait_count"] = 5  # small starter gift
        stats["bag"] = "woven_sack"''',
    '''        stats["bait"] = "earthworm"
        stats.setdefault("bait_stock", {})["earthworm"] = 5  # small starter gift
        stats["bag"] = "woven_sack"'''
)

# Chunk 9
content = content.replace(
    '''    bait_name = BAIT.get(stats.get("bait", "earthworm"), {}).get("name", "Earthworm")
    bait_count = stats.get("bait_count", 0)''',
    '''    cur_bt = stats.get("bait", "earthworm")
    if "bait_count" in stats:
        stats.setdefault("bait_stock", {})[cur_bt] = stats.pop("bait_count", 0)
    bait_name = BAIT.get(cur_bt, {}).get("name", "Earthworm")
    bait_count = stats.get("bait_stock", {}).get(cur_bt, 0)'''
)

with open("utils/commands/fishing_handler.py", "w", encoding="utf-8") as f:
    f.write(content)

