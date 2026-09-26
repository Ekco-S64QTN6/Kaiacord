"""One !rpg command per player at a time: every handler is a load-change-save
of the sheet, and two overlapping ones lost the first one's change."""
import asyncio
import types

from utils.commands import rpg_handler
import utils.ttrpg.rpg_core_handler as cor


def _msg(text, uid=42):
    async def send(*a, **k):
        return None
    return types.SimpleNamespace(content=text, author=types.SimpleNamespace(id=uid, name="p", display_name="P"),
                                 channel=types.SimpleNamespace(id=7, send=send))


def _ctx():
    return types.SimpleNamespace(config=types.SimpleNamespace(is_owner=lambda *a: False))


def test_two_commands_from_one_player_do_not_overlap(monkeypatch):
    running, overlaps = [0], [0]

    async def slow(ctx, msg, send, rest, uid, uname, is_owner):
        running[0] += 1
        overlaps[0] = max(overlaps[0], running[0])
        await asyncio.sleep(0.05)
        running[0] -= 1
    monkeypatch.setattr(cor, "_handle_bank", slow)
    monkeypatch.setattr("utils.ttrpg.character_manager.mark_active", lambda uid: None)

    async def go():
        await asyncio.gather(rpg_handler.handle_rpg_command(_ctx(), _msg("!rpg bank"), None),
                             rpg_handler.handle_rpg_command(_ctx(), _msg("!rpg bank"), None))
    asyncio.run(go())
    assert overlaps[0] == 1


def test_a_combat_action_still_takes_its_own_locks(monkeypatch):
    """Holding the user lock around a handler that takes it again would deadlock."""
    from utils.ttrpg.session_manager import serialize_combat_action
    ran = []

    @serialize_combat_action
    async def use(ctx, msg, send, rest, uid, uname, is_owner):
        ran.append(uid)
    monkeypatch.setattr(cor, "_handle_use", use)
    monkeypatch.setattr("utils.ttrpg.character_manager.mark_active", lambda uid: None)
    asyncio.run(asyncio.wait_for(rpg_handler.handle_rpg_command(_ctx(), _msg("!rpg use potion"), None), 2))
    assert ran == ["42"]
