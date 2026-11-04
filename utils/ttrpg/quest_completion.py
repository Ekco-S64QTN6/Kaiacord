"""Exactly-once in-sheet settlement for completed Aethelgard quests."""


def apply_quest_completion(sheet: dict, quest: dict) -> dict | None:
    """Apply one quest's rewards and progression without persisting.

    The caller must save the returned sheet once after this function completes.
    The completion marker is written in the same save as inventory/mail rewards,
    Gil, XP, and all level-up/stat-choice milestones, so a retry cannot duplicate
    payout and a crash cannot persist the payout without its level changes.
    """
    quest_id = quest.get("id")
    if not quest_id:
        return None

    active = sheet.setdefault("active_quests", [])
    completed = sheet.setdefault("completed_quests", [])
    if not isinstance(active, list) or not isinstance(completed, list):
        return None

    if quest_id in completed:
        # Repair a stale duplicate active entry without paying the quest again.
        remaining = [active_id for active_id in active if active_id != quest_id]
        if remaining != active:
            active[:] = remaining
            return {"awarded": False}
        return None

    if quest_id not in active:
        return None

    rewards = quest.get("rewards") or {}
    xp_reward = int(rewards.get("xp", 0) or 0)
    gil_reward = int(rewards.get("gil", 0) or 0)
    sheet["xp"] = int(sheet.get("xp", 0) or 0) + xp_reward
    sheet["gil"] = int(sheet.get("gil", 0) or 0) + gil_reward

    item_delivery = None
    item_key = rewards.get("item")
    if item_key:
        from utils.ttrpg.inventory_capacity import grant_item_or_mail
        item_delivery = grant_item_or_mail(
            sheet, item_key, f"{quest.get('name', 'Quest')} quest reward"
        )

    recipe_key = rewards.get("recipe")
    if recipe_key:
        recipes = sheet.setdefault("recipes", [])
        if recipe_key not in recipes:
            recipes.append(recipe_key)

    active[:] = [active_id for active_id in active if active_id != quest_id]
    completed.append(quest_id)

    # This also queues every pending stat-choice milestone if one reward crosses
    # multiple levels. It must precede the single durable save by the caller.
    from utils.ttrpg.progression import check_level_up
    leveled, new_level = check_level_up(sheet)

    return {
        "awarded": True,
        "xp_reward": xp_reward,
        "gil_reward": gil_reward,
        "item_delivery": item_delivery,
        "leveled": leveled,
        "new_level": new_level,
    }
