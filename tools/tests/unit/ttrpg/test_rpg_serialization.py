"""One !rpg command per player at a time: every handler is a load-change-save
of the sheet, and two overlapping ones lost the first one's change."""
import asyncio
import types

from utils.commands import rpg_handler
import utils.ttrpg.rpg_core_handler as cor
import pytest


@pytest.fixture(autouse=True)
def fresh_locks(monkeypatch):
    """asyncio locks are bound to the loop that first waits on them; each test runs its own."""
    from utils.ttrpg import session_manager
    monkeypatch.setattr(session_manager, "_action_locks", {})


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


def test_a_button_handler_serialises_without_the_dispatcher():
    """Buttons call handlers directly: a purchase and a cast from one player still queue."""
    from utils.ttrpg.session_manager import serialize_user_action
    running, overlaps = [0], [0]

    @serialize_user_action
    async def cast(ctx, interaction, uid, uname, is_owner):
        running[0] += 1
        overlaps[0] = max(overlaps[0], running[0])
        await asyncio.sleep(0.05)
        running[0] -= 1

    inter = types.SimpleNamespace(channel=types.SimpleNamespace(id=1))

    async def go():
        await asyncio.gather(cast(None, inter, "42", "P", False), cast(None, inter, "42", "P", False),
                             cast(None, inter, "99", "Q", False))
    asyncio.run(go())
    assert overlaps[0] == 2          # 42 twice in sequence, 99 alongside


def test_two_open_mail_menus_cannot_claim_the_same_package_twice(monkeypatch):
    import copy
    from unittest.mock import AsyncMock, MagicMock
    from utils.ttrpg import rpg_views
    disk = {"42": {"user_id": "42", "character_name": "P", "gil": 0, "inventory": [],
                   "mailbox": [{"from_name": "Q", "item": "tonic", "gil": 100}]}}

    async def load(uid):
        return copy.deepcopy(disk.get(str(uid)))

    async def save(sheet):
        disk[str(sheet["user_id"])] = copy.deepcopy(sheet)
    monkeypatch.setattr(rpg_views, "load", load)
    monkeypatch.setattr(rpg_views, "save", save)
    monkeypatch.setattr(rpg_views, "_make_status_view", lambda *a, **k: None)

    def inter():
        i = MagicMock()
        i.user.id = 42
        i.response.defer = AsyncMock()
        i.response.send_message = AsyncMock()
        i.followup.send = AsyncMock()
        return i

    async def go():
        a = rpg_views.MailMenuView(None, None, "42", "P", False, copy.deepcopy(disk["42"]))
        b = rpg_views.MailMenuView(None, None, "42", "P", False, copy.deepcopy(disk["42"]))
        await a.check_mail.callback(inter())
        await b.check_mail.callback(inter())
    asyncio.run(go())
    assert disk["42"]["gil"] == 100 and disk["42"]["inventory"] == ["tonic"] and disk["42"]["mailbox"] == []
