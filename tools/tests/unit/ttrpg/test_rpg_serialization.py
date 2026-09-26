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


def test_a_view_callback_holds_the_players_lock():
    from utils.ttrpg.session_manager import player_locked
    running, overlaps = [0], [0]

    @player_locked("42")
    async def cb(interaction, amount=5):
        running[0] += 1
        overlaps[0] = max(overlaps[0], running[0])
        await asyncio.sleep(0.02)
        running[0] -= 1
        return amount

    async def go():
        return await asyncio.gather(cb(None), cb(None))
    assert asyncio.run(go()) == [5, 5]        # the callback's own defaults survive
    assert overlaps[0] == 1


def test_only_the_first_advancement_button_counts(monkeypatch):
    """Every path was a live button on the same message and none checked that
    the choice was still open: two clicks, two HP bonuses."""
    import copy
    from unittest.mock import AsyncMock, MagicMock
    from utils.ttrpg.class_advancement import get_advanced_options

    base = next(c for c in ("Warrior", "Knight", "Mage", "Rogue", "Cleric")
                if any("hp_bonus" in o.get("bonuses", {}) for o in get_advanced_options(c).values()))
    store = {"42": {"user_id": "42", "character_name": "P", "class": base, "level": 5,
                    "hp": {"current": 50, "max": 50}, "_advancement_pending": True}}
    monkeypatch.setattr(cor, "load", AsyncMock(side_effect=lambda uid: copy.deepcopy(store.get(uid))))
    monkeypatch.setattr(cor, "save", AsyncMock(side_effect=lambda s: store.__setitem__(s["user_id"], copy.deepcopy(s))))
    monkeypatch.setattr(cor, "_log_world_event", AsyncMock())
    monkeypatch.setattr(cor, "_broadcast_world_event", AsyncMock())

    sent = {}
    async def channel_send(embed=None, view=None, **k):
        sent["view"] = view

    async def go():
        msg = types.SimpleNamespace(channel=types.SimpleNamespace(send=channel_send))
        await cor._handle_advance(_ctx(), msg, None, "", "42", "p", False)
        buttons = [b for b in sent["view"].children if isinstance(b, cor.discord.ui.Button)]
        for b in buttons:
            inter = MagicMock()
            inter.user.id = "42"
            inter.response.send_message = AsyncMock()
            await b.callback(inter)
    asyncio.run(go())

    chosen = store["42"]["advanced_class"]
    bonus = get_advanced_options(base)[chosen].get("bonuses", {}).get("hp_bonus", 0)
    assert store["42"]["hp"]["max"] == 50 + bonus
    assert cor.save.await_count == 1


def test_the_estate_upgrade_confirms_once_against_the_current_estate(monkeypatch):
    """The confirm button saved the housing dict captured when the dialog
    opened, wiping anything placed since, and a second click paid again."""
    import copy
    from unittest.mock import AsyncMock, MagicMock
    import utils.ttrpg.housing as H
    import utils.ttrpg.rpg_housing_handler as hh

    tiers = list(H.HOUSING_TIERS)
    sheets = {"9": {"user_id": "9", "character_name": "P", "level": 99, "gil": 10**7}}
    homes = {"9": {"user_id": "9", "tier": tiers[0], "furniture": ["old"]}}
    monkeypatch.setattr(hh, "load", AsyncMock(side_effect=lambda uid: copy.deepcopy(sheets[uid])))
    monkeypatch.setattr(hh, "save", AsyncMock(side_effect=lambda s: sheets.__setitem__(s["user_id"], copy.deepcopy(s))))
    monkeypatch.setattr(H, "load_housing", lambda uid: copy.deepcopy(homes[uid]))
    monkeypatch.setattr(H, "_write_housing", lambda uid, data: homes.__setitem__(uid, data))
    monkeypatch.setattr(H, "_serialise_housing", copy.deepcopy)
    monkeypatch.setattr(hh, "_log_world_event", AsyncMock())
    monkeypatch.setattr(hh, "_handle_my_home", AsyncMock())

    async def go():
        send = AsyncMock()
        await hh._handle_upgrade_house.__wrapped__(None, types.SimpleNamespace(channel=None), send, "", "9", "p", False)
        homes["9"]["furniture"].append("placed after the dialog opened")
        confirm = next(b for b in send.call_args.kwargs["view"].children if "Confirm" in (b.label or ""))
        for _ in range(2):
            inter = MagicMock()
            inter.user.id = "9"
            inter.response.send_message = AsyncMock()
            await confirm.callback(inter)
    asyncio.run(go())

    assert homes["9"]["tier"] == tiers[1]
    assert 10**7 - sheets["9"]["gil"] == H.HOUSING_TIERS[tiers[1]]["cost"]
    assert "placed after the dialog opened" in homes["9"]["furniture"]


def test_leaving_from_an_old_room_message_keeps_the_floor_as_it_is(monkeypatch, tmp_path):
    """Leave saved the dungeon captured when its room was posted, undoing every
    room cleared since; the stairs resume that floor."""
    import copy
    from unittest.mock import AsyncMock, MagicMock
    import utils.ttrpg.spine_dungeon as sd
    import utils.ttrpg.rpg_views as rv
    monkeypatch.setattr(sd, "SPINE_DIR", str(tmp_path))

    async def go():
        floor = sd.generate_spine_floor(1, 5)
        await sd.save_spine_dungeon("42", floor)
        old_view = rv.DungeonView(None, "42", "p", False, copy.deepcopy(floor))
        uncleared = next(k for k, r in floor["rooms"].items() if not r.get("cleared"))
        now = await sd.load_spine_dungeon("42")
        now["rooms"][uncleared]["cleared"] = True
        await sd.save_spine_dungeon("42", now)

        leave = next(b for b in old_view.children if "Leave" in (b.label or ""))
        inter = MagicMock()
        inter.user.id = "42"
        inter.response.defer = AsyncMock()
        inter.followup.send = AsyncMock()
        await leave.callback(inter)
        return uncleared

    uncleared = asyncio.run(go())
    saved = asyncio.run(sd.load_spine_dungeon("42", target_floor=1))
    assert saved["active"] is False
    assert saved["rooms"][uncleared]["cleared"] is True
