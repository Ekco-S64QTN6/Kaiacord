"""Crash-safe, idempotent commit protocol for combat outcomes.

The character sheet is the durable write-ahead record. It is saved with the
already-applied character result and a pending encounter-side operation before
the dungeon/session file is changed. Recovery replays only that encounter-side
operation, then clears the journal entry. Replaying a state snapshot or
removing one monster ID is idempotent.
"""


def stage_outcome(sheet: dict, outcome: dict) -> bool:
    """Add one pending outcome to the character sheet exactly once."""
    outcome_id = str(outcome.get("outcome_id") or "")
    if not outcome_id:
        raise ValueError("combat outcome requires a durable outcome_id")
    pending = sheet.setdefault("pending_combat_outcomes", {})
    if outcome_id in pending:
        return False
    pending[outcome_id] = outcome
    return True


async def commit_outcome(
    sheet: dict,
    outcome: dict,
    *,
    save_sheet,
    persist_encounter,
) -> bool:
    """Write the sheet journal, persist encounter state, then clear the journal.

    If either persistence operation raises, the pending entry remains in the
    saved character sheet and can be replayed after restart. The caller must
    have already applied all character rewards/penalties to sheet before
    calling this function.
    """
    if not stage_outcome(sheet, outcome):
        return False

    await save_sheet(sheet)
    await persist_encounter(outcome)

    pending = sheet.get("pending_combat_outcomes", {})
    pending.pop(str(outcome["outcome_id"]), None)
    if not pending:
        sheet.pop("pending_combat_outcomes", None)
    await save_sheet(sheet)
    return True


async def recover_pending_outcomes(sheet: dict, *, save_sheet, recoverers: dict) -> int:
    """Replay pending encounter-side operations and clear committed entries."""
    pending = sheet.get("pending_combat_outcomes", {})
    recovered = 0
    for outcome_id, outcome in list(pending.items()):
        kind = outcome.get("kind")
        recover = recoverers.get(kind)
        if recover is None:
            # Unknown journal versions must be preserved, never silently dropped.
            continue
        await recover(outcome)
        pending.pop(outcome_id, None)
        recovered += 1

    if recovered:
        if pending:
            sheet["pending_combat_outcomes"] = pending
        else:
            sheet.pop("pending_combat_outcomes", None)
        await save_sheet(sheet)
    return recovered
