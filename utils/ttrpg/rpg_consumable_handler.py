"""Player consumable effects, including safe overworld smoke-bomb escape."""
import discord


async def _handle_use(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character, no_character_handler, load_session_fn, active_view_factory, status_view_factory, hunt_status_view_factory, secrets_module, uuid_module):
    from utils.ttrpg.shop import find_item
    sheet = await load_character(uid)
    if not sheet: return await no_character_handler(msg)
    from utils.ttrpg.rpg_combat_handler import _recover_pending_combat_outcomes
    await _recover_pending_combat_outcomes(uid, sheet)

    item_key = rest.strip().lower().replace(" ", "_")
    from utils.ttrpg.equipment_registry import ALIASES
    item_key = ALIASES.get(item_key, item_key)
        
    if item_key not in sheet.get("inventory", []):
        return await msg.channel.send(embed=discord.Embed(description=f"You don't have `{item_key}`.", color=0xcc4444))
        
    item = find_item(item_key)
    if not item or item["category"] != "consumable":
        return await msg.channel.send(embed=discord.Embed(description=f"You can't use `{item_key}`.", color=0xcc4444))
    if item.get("deprecated"):
        return await msg.channel.send(embed=discord.Embed(
            description=(
                f"**{item['name']}** has been retired because its effect is not supported. "
                "The item was not consumed; you can still sell it to a merchant."
            ),
            color=0xcc4444,
        ))
    had = sheet["inventory"].count(item_key)
        
    if "hp_restore" in item and item["hp_restore"] > 0:
        before = sheet["hp"]["current"]
        # Cleric/High Priest heal_mult bonus
        heal_mult = 1.0
        char_class = sheet.get("class", "")
        adv_class  = sheet.get("advanced_class", "")
        if adv_class == "High Priest":
            heal_mult = 1.5
        elif adv_class in ("Cleric", "") and char_class == "Cleric":
            heal_mult = 1.25
        actual_restore = int(item["hp_restore"] * heal_mult)
        sheet["hp"]["current"] = min(sheet["hp"]["current"] + actual_restore, sheet["hp"]["max"])
        healed = sheet["hp"]["current"] - before
        sheet["inventory"].remove(item_key)
        await save_character(sheet)
        combat_view = await active_view_factory(ctx, msg, uid, uname, is_owner)
        view = combat_view if combat_view else status_view_factory(ctx, msg, uid, uname, is_owner)
        await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. Restored {healed} HP ({before} → {sheet['hp']['current']})", color=0x44aa44), view=view)
    elif item.get("on_use") == "starter_kit":
        from utils.ttrpg.inventory_capacity import grant_items, unique_item_type_count
        from utils.ttrpg.character_manager import INVENTORY_LIMIT
        projected = {"inventory": list(sheet.get("inventory", []))}
        projected["inventory"].remove(item_key)
        contents = ["bandage", "healing_herb", "torch"]
        if not grant_items(projected, contents):
            current_unique = unique_item_type_count(sheet.get("inventory", []))
            return await msg.channel.send(embed=discord.Embed(
                description=(
                    f"Your inventory is too full to open the {item['name']} "
                    f"({current_unique}/{INVENTORY_LIMIT} unique item types). "
                    "Make room first. The kit was not consumed."
                ),
                color=0xcc4444,
            ))
        sheet["inventory"] = projected["inventory"]
        await save_character(sheet)
        await msg.channel.send(embed=discord.Embed(description=f"You open the **{item['name']}**.\n\nObtained:\n• Bandage\n• Healing Herb\n• Torch (lore item)", color=0x44aa44))
    elif item.get("on_use") == "smoke_bomb":
        # Smoke Bombs are an overworld escape only. Dungeon combat uses a
        # separate persisted dungeon state and retains its normal flee action.
        location = sheet.get("location", "oakhaven")
        from utils.ttrpg.dungeon import load_dungeon
        active_dungeon = await load_dungeon(uid)
        active_spine = None
        if location == "aeridor_ruins":
            from utils.ttrpg.spine_dungeon import load_spine_dungeon
            active_spine = await load_spine_dungeon(uid)
        if (active_dungeon and active_dungeon.get("active")) or (
            active_spine and active_spine.get("active")
        ):
            return await msg.channel.send(embed=discord.Embed(
                description=(
                    "Smoke Bombs only clear overworld encounters. Use the dungeon "
                    "Flee action for dungeon combat. Nothing was consumed."
                ),
                color=0xcc4444,
            ))

        session = await load_session_fn(str(msg.channel.id))
        own_encounters = [
            monster for monster in (session or {}).get("monsters", [])
            if isinstance(monster, dict)
            and str(monster.get("aggro_uid")) == str(uid)
            and monster.get("origin_location") == location
        ]
        if not session or not session.get("combat_active") or not own_encounters:
            return await msg.channel.send(embed=discord.Embed(
                description=(
                    "A Smoke Bomb can only clear your own overworld encounter "
                    "at your current location. Nothing was consumed."
                ),
                color=0xcc4444,
            ))

        # Escape the whole personal swarm without touching another player's
        # monsters in this shared channel session.
        escaped_names = [m.get("name", "a monster") for m in own_encounters]
        monster_ids = [str(m.get("id") or "") for m in own_encounters]
        if any(not monster_id for monster_id in monster_ids):
            return await msg.channel.send(embed=discord.Embed(
                description=(
                    "This encounter needs to be refreshed before a Smoke Bomb can "
                    "safely escape. Nothing was consumed."
                ),
                color=0xcc4444,
            ))

        for condition in ("embered", "fortified"):
            if condition in sheet.get("conditions", []):
                sheet["conditions"].remove(condition)
        sheet["inventory"].remove(item_key)

        from utils.ttrpg.combat_outcomes import commit_outcome
        from utils.ttrpg.session_manager import apply_overworld_combat_update

        escape_id = (
            f"overworld-escape:{uid}:{msg.channel.id}:"
            f"{getattr(msg, 'id', None) or uuid_module.uuid4().hex}"
        )
        outcome = {
            "outcome_id": escape_id,
            "kind": "overworld_escape",
            "channel_id": str(msg.channel.id),
            "owner_id": str(uid),
            "monster_ids": monster_ids,
        }

        async def _persist_escape(pending):
            await apply_overworld_combat_update(pending, remove_monster=True)

        await commit_outcome(
            sheet,
            outcome,
            save_sheet=save_character,
            persist_encounter=_persist_escape,
        )

        from utils.ttrpg import outing
        await outing.note(uid, "fled", f"smoke bomb: {', '.join(escaped_names)}")
        view = hunt_status_view_factory(ctx, msg, uid, uname, is_owner)
        await msg.channel.send(embed=discord.Embed(
            title="💨 Smoke Bomb",
            description=(
                f"You vanish behind a wall of smoke and escape **{', '.join(escaped_names)}**.\n"
                "No hunt stamina, XP, or Gil was lost."
            ),
            color=0x44aa44,
        ), view=view)
    elif item.get("on_use") == "cure_poison":
        if "poisoned" in sheet.get("conditions", []):
            sheet["conditions"].remove("poisoned")
            sheet["inventory"].remove(item_key)
            await save_character(sheet)
            combat_view = await active_view_factory(ctx, msg, uid, uname, is_owner)
            view = combat_view if combat_view else status_view_factory(ctx, msg, uid, uname, is_owner)
            await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. The venom fades from your veins.", color=0x44aa44), view=view)
        else:
            await msg.channel.send(embed=discord.Embed(description=f"You aren't poisoned.", color=0xcc4444))
    elif item.get("on_use") == "luck_roll_bonus":
        if "lucky" not in sheet.get("conditions", []):
            if "conditions" not in sheet: sheet["conditions"] = []
            sheet["conditions"].append("lucky")
            sheet["inventory"].remove(item_key)
            await save_character(sheet)
            combat_view = await active_view_factory(ctx, msg, uid, uname, is_owner)
            view = combat_view if combat_view else status_view_factory(ctx, msg, uid, uname, is_owner)
            await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. You feel a sudden surge of confidence. (+1 to next hit roll)", color=0x44aa44), view=view)
        else:
            await msg.channel.send(embed=discord.Embed(description=f"You are already feeling pretty lucky.", color=0xcc4444))
    elif item.get("on_use") == "xp_boost":
        if "xp_boosted" not in sheet.get("conditions", []):
            if "conditions" not in sheet: sheet["conditions"] = []
            sheet["conditions"].append("xp_boosted")
            sheet["inventory"].remove(item_key)
            await save_character(sheet)
            combat_view = await active_view_factory(ctx, msg, uid, uname, is_owner)
            view = combat_view if combat_view else status_view_factory(ctx, msg, uid, uname, is_owner)
            await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. 🧪 Your mind sharpens. (+25% XP on next hunt)", color=0x44aa44), view=view)
        else:
            await msg.channel.send(embed=discord.Embed(description=f"You're already buzzing with experience tonic.", color=0xcc4444))
    elif item.get("on_use") == "hunt_bonus":
        sheet["inventory"].remove(item_key)
        # Grant a bonus hunt condition instead of decrementing to respect the hard ceiling
        sheet.setdefault("conditions", []).append("hunt_bonus")
        await save_character(sheet)
        from utils.ttrpg.progression import hunts_remaining as _hr, get_max_hunts as _gmh
        combat_view = await active_view_factory(ctx, msg, uid, uname, is_owner)
        view = combat_view if combat_view else status_view_factory(ctx, msg, uid, uname, is_owner)
        await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. 🏹 Your senses sharpen. (+1 bonus hunt today — {_hr(sheet)}/{_gmh(sheet)} remaining)", color=0x44aa44), view=view)
    elif item.get("on_use") == "atk_boost":
        if "embered" not in sheet.get("conditions", []):
            if "conditions" not in sheet: sheet["conditions"] = []
            sheet["conditions"].append("embered")
            sheet["inventory"].remove(item_key)
            await save_character(sheet)
            combat_view = await active_view_factory(ctx, msg, uid, uname, is_owner)
            view = combat_view if combat_view else status_view_factory(ctx, msg, uid, uname, is_owner)
            await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. 🔥 Fire courses through your arms. (+2 ATK until next combat)", color=0x44aa44), view=view)
        else:
            await msg.channel.send(embed=discord.Embed(description=f"You're already burning with firebrew.", color=0xcc4444))
    elif item.get("on_use") == "def_boost":
        if "fortified" not in sheet.get("conditions", []):
            if "conditions" not in sheet: sheet["conditions"] = []
            sheet["conditions"].append("fortified")
            sheet["inventory"].remove(item_key)
            await save_character(sheet)
            combat_view = await active_view_factory(ctx, msg, uid, uname, is_owner)
            view = combat_view if combat_view else status_view_factory(ctx, msg, uid, uname, is_owner)
            await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. 🛡️ Your skin hardens like bark. (+2 DEF until next combat)", color=0x44aa44), view=view)
        else:
            await msg.channel.send(embed=discord.Embed(description=f"You're already toughened by ironbark.", color=0xcc4444))
    elif item_key == "stolen_trade_crate":
        sheet["inventory"].remove(item_key)
        crate_gil = secrets_module.randbelow(101) + 50  # 50-150 gil
        sheet["gil"] = sheet.get("gil", 0) + crate_gil
        extra_items = ["bandage", "healing_herb", "lucky_charm", "aeridor_shard", "ironbark_tonic"]
        bonus_item = secrets_module.choice(extra_items)
        from utils.ttrpg.inventory_capacity import grant_item_or_mail
        bonus_delivery = grant_item_or_mail(sheet, bonus_item, "Stolen Trade Crate")
        item_data = find_item(bonus_item)
        bonus_name = item_data.get("name", bonus_item.replace("_", " ").title()) if item_data else bonus_item.replace("_", " ").title()
        await save_character(sheet)
        bonus_line = (
            f"🎁 **Bonus Item:** **{bonus_name}**"
            if bonus_delivery == "inventory"
            else f"📬 **{bonus_name}** was sent to Moogle Mail because your inventory is full."
        )
        await msg.channel.send(embed=discord.Embed(
            title="📦 Stolen Trade Crate Opened",
            description=(
                f"You pry open the iron-banded trade crate!\n\n"
                f"💰 **Found:** +{crate_gil} Gil\n"
                f"{bonus_line}"
            ),
            color=0x27ae60
        ))
    else:
        await msg.channel.send(embed=discord.Embed(description=f"**{item['name']}** can't be used. Try selling it: `!rpg sell {item_key}`", color=0xcc4444))
    if sheet.get("inventory", []).count(item_key) < had:
        from utils.ttrpg import outing                     # drunk on a trip: part of its story
        await outing.note(uid, "used", item["name"])
