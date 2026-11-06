"""Owner-only Aethelgard character administration commands."""
import re

import discord


async def _with_target_action_lock(target_uid: str, caller_uid: str, operation):
    """Serialize an admin mutation across both caller and target identities.

    The dispatcher marks these commands as self-serialized so the caller and
    target locks are always acquired together in a deterministic UID order.
    Self-targeted commands acquire the single shared lock exactly once.
    """
    target_uid = str(target_uid)
    if target_uid == str(caller_uid):
        return await operation()

    from contextlib import AsyncExitStack
    from utils.ttrpg.session_manager import get_action_lock

    # Acquire both identities in one global order. This prevents two owners
    # targeting one another from forming a caller->target lock cycle.
    lock_ids = sorted({str(target_uid), str(caller_uid)})
    locks = [await get_action_lock(f"user:{uid}") for uid in lock_ids]
    async with AsyncExitStack() as stack:
        for lock in locks:
            await stack.enter_async_context(lock)
        return await operation()


async def _handle_give(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character, no_character_handler, with_target_action_lock_fn):
    if not is_owner: return
    from utils.ttrpg.shop import find_item

    mentions = getattr(msg, "mentions", []) or []
    target_uid = str(mentions[0].id) if mentions else str(uid)
    item_query = rest.strip()
    if mentions:
        # Discord leaves the mention token in the dispatcher's remaining text.
        # Remove only the selected recipient token before resolving the item.
        item_query = re.sub(rf"<@!?{re.escape(target_uid)}>", "", item_query, count=1).strip()
    if not item_query:
        return await msg.channel.send(embed=discord.Embed(
            description="Specify an item to grant. Example: `!rpg give @player tonic`.",
            color=0x888888
        ))

    item = find_item(item_query)
    if not item:
        return await msg.channel.send(embed=discord.Embed(
            description=f"No RPG item found for `{item_query}`.",
            color=0xcc4444
        ))

    async def grant():
        sheet = await load_character(target_uid)
        if not sheet:
            return None
        from utils.ttrpg.inventory_capacity import grant_item
        from utils.ttrpg.inventory_capacity import unique_item_type_count
        from utils.ttrpg.character_manager import INVENTORY_LIMIT
        if not grant_item(sheet, item["key"]):
            return (sheet["character_name"], False, unique_item_type_count(sheet.get("inventory", [])), INVENTORY_LIMIT)
        await save_character(sheet)
        return (sheet["character_name"], True, 0, INVENTORY_LIMIT)

    grant_result = await with_target_action_lock_fn(target_uid, uid, grant)
    if not grant_result:
        return await no_character_handler(msg)
    target_name, granted, current_unique, limit = grant_result
    if not granted:
        return await msg.channel.send(embed=discord.Embed(
            description=(
                f"Could not grant `{item['key']}` to {target_name}: inventory full "
                f"({current_unique}/{limit} unique item types)."
            ),
            color=0xcc4444,
        ))
    await msg.channel.send(embed=discord.Embed(
        description=f"Admin granted `{item['key']}` to {target_name}.",
        color=0x44aa44
    ))


async def _handle_heal(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character, no_character_handler, with_target_action_lock_fn):
    if not is_owner: return
    mentions = getattr(msg, "mentions", []) or []
    target_uid = str(mentions[0].id) if mentions else str(uid)

    async def heal():
        sheet = await load_character(target_uid)
        if not sheet:
            return None
        sheet["hp"]["current"] = sheet["hp"]["max"]
        await save_character(sheet)
        return sheet["character_name"]

    target_name = await with_target_action_lock_fn(target_uid, uid, heal)
    if not target_name:
        return await no_character_handler(msg)
    await msg.channel.send(embed=discord.Embed(
        description=f"Admin fully healed {target_name}.",
        color=0x44aa44
    ))
