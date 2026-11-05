"""Inventory viewing and equipment actions for Aethelgard."""
from collections import Counter

import discord

from utils.commands.stale_view import StaleSafeView
from utils.ttrpg.equipment_registry import (
    WEAPONS, ARMOR as ARMOR_REG, HEADGEAR, BOOTS, ACCESSORIES,
)
from utils.ttrpg.shop import find_item


async def _handle_inventory(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, no_character_handler, make_status_view, make_inventory_view, get_class_abbr_string, get_item_effect_string):
    from utils.ttrpg.shop import find_item
    from utils.ttrpg.equipment_registry import WEAPONS, ARMOR as ARMOR_REG, HEADGEAR, BOOTS, ACCESSORIES
    from collections import Counter

    sheet = await load_character(uid)
    if not sheet: return await no_character_handler(msg)

    # ── Equipped gear summary ────────────────────────────────────────────────
    def _eq_name(slot_val, registry):
        if not slot_val: return "—"
        if isinstance(slot_val, dict): return slot_val.get("name", "?")
        return registry.get(slot_val, {}).get("name", slot_val)

    eq = sheet.get("equipment", {})
    equipped_lines = (
        f"🗡️ {_eq_name(eq.get('weapon'), WEAPONS)}  "
        f"🛡️ {_eq_name(eq.get('armor'), ARMOR_REG)}  "
        f"🪖 {_eq_name(eq.get('head'), HEADGEAR)}\n"
        f"👢 {_eq_name(eq.get('boots'), BOOTS)}  "
        f"💍 {_eq_name(eq.get('accessory'), ACCESSORIES)}"
    )

    inventory = sheet.get("inventory", [])
    if not inventory:
        embed = discord.Embed(
            title="🎒 Inventory",
            description=f"**Equipped:**\n{equipped_lines}\n\n*Backpack is empty.*",
            color=0x888888
        )
        embed.set_footer(text="!rpg status  ·  !rpg help")
        view = make_status_view(ctx, msg, uid, uname, is_owner)
        await msg.channel.send(embed=embed, view=view)
        return

    # ── Categorize inventory ─────────────────────────────────────────────────
    GEAR_SLOTS = [
        ("weapon",    "🗡️ WEAPONS"),
        ("armor",     "🛡️ ARMOR"),
        ("head",      "🪖 HEAD"),
        ("boots",     "👢 BOOTS"),
        ("accessory", "💍 ACCESSORIES"),
    ]
    SLOT_PREFIX = {k: label for k, label in GEAR_SLOTS}

    sections: dict[str, list[str]] = {k: [] for k, _ in GEAR_SLOTS}
    consumable_lines: list[str] = []
    misc_lines: list[str] = []

    inv_counts = Counter(inventory)

    for key, count in sorted(inv_counts.items(), key=lambda kv: (find_item(kv[0]) or {}).get("name", kv[0])):
        if key == "symbol_of_the_silent_ones":
            continue

        item = find_item(key)
        count_str = f" ×{count}" if count > 1 else ""

        if item:
            cat = item["category"]

            if cat == "weapon":
                proc_str = ""
                proc_data = item.get("proc")
                if proc_data:
                    proc_str = f"  {proc_data.get('emoji','⚡')}{proc_data['name']}"
                class_tag = get_class_abbr_string(item)
                line = (
                    f"**{item['name']}**{count_str} — "
                    f"+{item['attack_bonus']} ATK, d{item['damage_die']}{proc_str}{class_tag}  "
                    f"*(sell: {item['value'] // 2}g)*"
                )
                sections["weapon"].append(line)

            elif cat == "armor":
                class_tag = get_class_abbr_string(item)
                line = f"**{item['name']}**{count_str} — +{item['defense_bonus']} DEF{class_tag}  *(sell: {item['value'] // 2}g)*"
                sections["armor"].append(line)

            elif cat == "head":
                class_tag = get_class_abbr_string(item)
                line = f"**{item['name']}**{count_str} — +{item['defense_bonus']} DEF{class_tag}  *(sell: {item['value'] // 2}g)*"
                sections["head"].append(line)

            elif cat == "boots":
                class_tag = get_class_abbr_string(item)
                line = f"**{item['name']}**{count_str} — +{item['defense_bonus']} DEF{class_tag}  *(sell: {item['value'] // 2}g)*"
                sections["boots"].append(line)

            elif cat == "accessory":
                atk = item.get("attack_bonus", 0)
                dfs = item.get("defense_bonus", 0)
                stat_parts = []
                if dfs: stat_parts.append(f"+{dfs} DEF")
                if atk: stat_parts.append(f"+{atk} ATK")
                stat_str = ", ".join(stat_parts) if stat_parts else "cosmetic"
                class_tag = get_class_abbr_string(item)
                line = f"**{item['name']}**{count_str} — {stat_str}{class_tag}  *(sell: {item['value'] // 2}g)*"
                sections["accessory"].append(line)

            elif cat == "consumable":
                val = item.get("value", 0)
                effect_str = get_item_effect_string(item)
                # Helper returns " — effect", we want to strip the " — " prefix for the log if possible or just use it consistently.
                # Actually _get_item_effect_string returns " — restores 30 HP".
                # The log format was "**name** — effect".
                effect = effect_str.lstrip(" — ")
                consumable_lines.append(f"**{item['name']}**{count_str} — {effect}  *(sell: {val // 2}g)*")
            else:
                misc_lines.append(f"**{item['name']}**{count_str}")
        else:
            display = key.replace("_", " ").title()
            misc_lines.append(f"**{display}**{count_str} — *sell to Hemlock to find out*")

    # ── Build ordered section blocks ─────────────────────────────────────────
    section_blocks: list[tuple[str, list[str]]] = []
    for slot_key, slot_label in GEAR_SLOTS:
        if sections[slot_key]:
            section_blocks.append((slot_label, sections[slot_key]))
    if consumable_lines:
        section_blocks.append(("🧪 CONSUMABLES", consumable_lines))
    if misc_lines:
        section_blocks.append(("📦 MISC", misc_lines))

    # ── Pagination (keep sections whole where possible) ───────────────────────
    header = f"**Equipped:**\n{equipped_lines}\n\n"
    MAX_DESC = 4096
    HEADER_BUDGET = len(header) + 60
    BODY_BUDGET = MAX_DESC - HEADER_BUDGET

    pages: list[list[tuple[str, list[str]]]] = []
    current_page: list[tuple[str, list[str]]] = []
    current_len = 0

    for sect_name, sect_lines in section_blocks:
        block_text = f"**{sect_name}**\n" + "\n".join(sect_lines) + "\n\n"
        cost = len(block_text)
        if current_page and current_len + cost > BODY_BUDGET:
            pages.append(current_page)
            current_page = []
            current_len = 0
        current_page.append((sect_name, sect_lines))
        current_len += cost

    if current_page:
        pages.append(current_page)
    if not pages:
        pages = [[]]

    async def _send_page(page_idx, interaction=None):
        desc = header
        if len(pages) > 1:
            desc += f"*Page {page_idx + 1}/{len(pages)}*\n\n"

        if pages[page_idx]:
            for sect_name, sect_lines in pages[page_idx]:
                desc += f"**{sect_name}**\n"
                desc += "\n".join(sect_lines)
                desc += "\n\n"
        else:
            desc += "*Backpack is empty.*"

        embed = discord.Embed(
            title="🎒 Inventory",
            description=desc.rstrip(),
            color=0x8b7355
        )
        view = make_inventory_view(
            ctx, msg, uid, uname, is_owner, inventory,
            page_idx, len(pages), _send_page
        )
        if interaction:
            await interaction.message.edit(embed=embed, view=view)
        else:
            await msg.channel.send(embed=embed, view=view)

    await _send_page(0)

async def _handle_equip(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character, no_character_handler):
    from utils.ttrpg.shop import find_item
    sheet = await load_character(uid)
    if not sheet: return await no_character_handler(msg)
    
    if not rest.strip():
        return await msg.channel.send(embed=discord.Embed(description="Equip what? `!rpg equip <item>`", color=0x888888))
        
    item_key = rest.strip().lower().replace(" ", "_")
    from utils.ttrpg.equipment_registry import ALIASES
    item_key = ALIASES.get(item_key, item_key)
    if item_key not in sheet.get("inventory", []):
        return await msg.channel.send(embed=discord.Embed(description=f"You don't have `{item_key}` in your inventory.", color=0xcc4444))
        
    item = find_item(item_key)
    if not item or item["category"] not in ["weapon", "armor", "head", "boots", "accessory"]:
        return await msg.channel.send(embed=discord.Embed(description=f"`{item_key}` cannot be equipped.", color=0xcc4444))

    # Check class restriction
    item_classes = item.get("classes")
    char_class = sheet.get("class", "")
    adv_class  = sheet.get("advanced_class", "")
    if item_classes and char_class not in item_classes and adv_class not in item_classes:
        class_str = "/".join(item_classes)
        return await msg.channel.send(embed=discord.Embed(
            description=f"**{item['name']}** can only be used by: {class_str}.",
            color=0xcc4444
        ))

    # Project the swap first: returning the old item must fit after the
    # selected item leaves the bag. Do not change HP or equipment on refusal.
    slot = item["category"]
    old_val = sheet["equipment"].get(slot)
    old_key = old_val.get("key") if isinstance(old_val, dict) else old_val
    from utils.ttrpg.inventory_capacity import grant_item
    projected = {"inventory": list(sheet.get("inventory", []))}
    projected["inventory"].remove(item_key)
    if old_key and not grant_item(projected, old_key):
        from utils.ttrpg.character_manager import INVENTORY_LIMIT
        from utils.ttrpg.inventory_capacity import unique_item_type_count
        current_unique = unique_item_type_count(sheet.get("inventory", []))
        return await msg.channel.send(embed=discord.Embed(
            description=(
                f"Your inventory is full ({current_unique}/{INVENTORY_LIMIT} unique item types). "
                "Make room before swapping this equipment."
            ),
            color=0xcc4444,
        ))
    sheet["inventory"] = projected["inventory"]

    if old_val:
        # Remove old HP bonus if it exists.
        old_hp_bonus = old_val.get("hp_bonus", 0) if isinstance(old_val, dict) else 0
        if old_hp_bonus:
            sheet["hp"]["max"] = max(1, sheet["hp"]["max"] - old_hp_bonus)
            sheet["hp"]["current"] = min(sheet["hp"]["current"], sheet["hp"]["max"])

    # Equip new and add its HP bonus if it exists.
    new_hp_bonus = item.get("hp_bonus", 0)
    if new_hp_bonus:
        sheet["hp"]["max"] += new_hp_bonus
        sheet["hp"]["current"] += new_hp_bonus

    sheet["equipment"][slot] = item
    await save_character(sheet)
    
    await msg.channel.send(embed=discord.Embed(description=f"Equipped **{item['name']}** as {slot}.", color=0x44aa44))

async def _handle_unequip(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character, no_character_handler, player_locked_decorator, interaction_msg_factory, interaction_send_factory, status_btn_factory):
    from utils.ttrpg.equipment_registry import WEAPONS, ARMOR as ARMOR_REG, HEADGEAR, BOOTS, ACCESSORIES

    sheet = await load_character(uid)
    if not sheet: return await no_character_handler(msg)

    slot_aliases = {
        "weapon": "weapon", "sword": "weapon", "bow": "weapon", "axe": "weapon",
        "staff": "weapon", "dagger": "weapon", "blade": "weapon",
        "armor": "armor", "chest": "armor", "body": "armor", "robe": "armor",
        "head": "head", "helm": "head", "helmet": "head", "hat": "head", "hood": "head",
        "boots": "boots", "feet": "boots", "greaves": "boots",
        "accessory": "accessory", "ring": "accessory", "bracer": "accessory",
        "bracelet": "accessory", "amulet": "accessory",
    }

    eq = sheet.get("equipment", {})
    arg = rest.strip().lower()

    # Try to find slot by arg — either slot name/alias or item name
    target_slot = None
    if arg in slot_aliases:
        target_slot = slot_aliases[arg]
    else:
        # Match against equipped item names
        registries = {
            "weapon": WEAPONS, "armor": ARMOR_REG,
            "head": HEADGEAR, "boots": BOOTS, "accessory": ACCESSORIES
        }
        for slot, registry in registries.items():
            val = eq.get(slot)
            if not val: continue
            item_key = val.get("key") if isinstance(val, dict) else val
            item_name = (val.get("name") if isinstance(val, dict) else registry.get(val, {}).get("name", "")).lower()
            if arg and (arg in (item_key or "").lower() or arg in item_name):
                target_slot = slot
                break

    # No arg or no match — show select menu of equipped items
    if not target_slot or not eq.get(target_slot):
        equipped = [(slot, val) for slot, val in eq.items() if val]
        if not equipped:
            return await msg.channel.send(embed=discord.Embed(description="Nothing equipped.", color=0x888888))

        if not arg:
            # Build a select menu
            registries = {
                "weapon": WEAPONS, "armor": ARMOR_REG,
                "head": HEADGEAR, "boots": BOOTS, "accessory": ACCESSORIES
            }
            options = []
            for slot, val in equipped:
                name = val.get("name") if isinstance(val, dict) else registries.get(slot, {}).get(val, {}).get("name", val)
                options.append(discord.SelectOption(label=f"{slot.title()}: {name}", value=slot))

            view = StaleSafeView(timeout=60)
            sel = discord.ui.Select(placeholder="Unequip which item?", options=options, row=0)

            @player_locked_decorator(uid)
            async def _sel_cb(interaction: discord.Interaction):
                if str(interaction.user.id) != uid:
                    await interaction.response.send_message("not yours.", ephemeral=True)
                    return
                chosen_slot = interaction.data["values"][0]
                await interaction.response.defer()
                fake_msg = interaction_msg_factory(interaction)
                send_fn = interaction_send_factory(interaction)
                from utils.ttrpg import rpg_core_handler as core
                await core._handle_unequip(ctx, fake_msg, send_fn, chosen_slot, uid, uname, is_owner)

            sel.callback = _sel_cb
            view.add_item(sel)
            view.add_item(status_btn_factory(ctx, uid, uname, is_owner))
            return await msg.channel.send(embed=discord.Embed(description="Select an item to unequip:", color=0x888888), view=view)

        return await msg.channel.send(embed=discord.Embed(
            description=f"Nothing equipped in that slot matching `{arg}`.", color=0xcc4444
        ))

    # Unequip
    val = eq[target_slot]
    item_key = val.get("key") if isinstance(val, dict) else val
    item_name = val.get("name") if isinstance(val, dict) else item_key

    if item_key:
        from utils.ttrpg.inventory_capacity import grant_item
        if not grant_item(sheet, item_key):
            from utils.ttrpg.character_manager import INVENTORY_LIMIT
            from utils.ttrpg.inventory_capacity import unique_item_type_count
            current_unique = unique_item_type_count(sheet.get("inventory", []))
            return await msg.channel.send(embed=discord.Embed(
                description=(
                    f"Your inventory is full ({current_unique}/{INVENTORY_LIMIT} unique item types). "
                    "Make room before unequipping this item."
                ),
                color=0xcc4444,
            ))

    # Remove HP bonus
    hp_bonus = val.get("hp_bonus", 0) if isinstance(val, dict) else 0
    if hp_bonus:
        sheet["hp"]["max"] = max(1, sheet["hp"]["max"] - hp_bonus)
        sheet["hp"]["current"] = min(sheet["hp"]["current"], sheet["hp"]["max"])

    sheet["equipment"][target_slot] = None
    await save_character(sheet)

    await msg.channel.send(embed=discord.Embed(
        description=f"Unequipped **{item_name}** — moved to inventory.",
        color=0x44aa44
    ))
