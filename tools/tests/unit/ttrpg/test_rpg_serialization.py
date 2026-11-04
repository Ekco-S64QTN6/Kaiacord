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


def test_gamble_again_clicked_twice_charges_both_rolls(monkeypatch):
    """The Gamble Again button ran the handler outside the player's lock: two
    quick clicks both read the same purse and the second save undid the first."""
    import copy
    from unittest.mock import AsyncMock
    store = {"42": {"user_id": "42", "character_name": "P", "location": "stone_hearth", "gil": 100,
                    "hp": {"current": 10, "max": 10}}}

    async def slow_load(uid):
        sheet = copy.deepcopy(store.get(uid))
        await asyncio.sleep(0.01)
        return sheet
    monkeypatch.setattr(cor, "load", slow_load)
    monkeypatch.setattr(cor, "save", AsyncMock(side_effect=lambda s: store.__setitem__(s["user_id"], copy.deepcopy(s))))
    monkeypatch.setattr(cor.secrets, "randbelow", lambda n: 0)            # every roll a tie: the house takes 10
    monkeypatch.setattr("utils.ttrpg.calendar.get_special_day", lambda *a: None)

    views = []
    async def channel_send(*a, view=None, **k):
        views.append(view)

    def click():
        followup = types.SimpleNamespace(send=channel_send)
        return types.SimpleNamespace(user=types.SimpleNamespace(id=42), guild=None, followup=followup,
                                     channel=types.SimpleNamespace(id=7),
                                     response=types.SimpleNamespace(defer=AsyncMock()))

    async def go():
        msg = types.SimpleNamespace(channel=types.SimpleNamespace(id=7, send=channel_send))
        await cor._handle_gamble(_ctx(), msg, None, "", "42", "p", False)
        again = next(i for i in views[0].children if "Gamble Again" in (i.label or ""))
        await asyncio.gather(again.callback(click()), again.callback(click()))
    asyncio.run(go())
    assert store["42"]["gil"] == 70


def test_the_unequip_menu_holds_the_players_lock(monkeypatch):
    from unittest.mock import AsyncMock
    sheet = {"user_id": "42", "character_name": "P", "inventory": [], "hp": {"current": 10, "max": 10},
             "equipment": {"weapon": "rusty_dagger"}}
    monkeypatch.setattr(cor, "load", AsyncMock(return_value=sheet))
    views = []
    async def channel_send(*a, view=None, **k):
        views.append(view)

    async def go():
        msg = types.SimpleNamespace(channel=types.SimpleNamespace(id=7, send=channel_send))
        await cor._handle_unequip(_ctx(), msg, None, "", "42", "p", False)
        from utils.ttrpg.session_manager import get_action_lock
        lock = await get_action_lock("user:42")
        seen = []
        async def inner(*a, **k):
            seen.append(lock.locked())
        monkeypatch.setattr(cor, "_handle_unequip", inner)
        sel = next(i for i in views[0].children if hasattr(i, "options"))
        interaction = types.SimpleNamespace(user=types.SimpleNamespace(id=42), guild=None,
                                            data={"values": ["weapon"]}, channel=types.SimpleNamespace(id=7),
                                            followup=None, response=types.SimpleNamespace(defer=AsyncMock()))
        await sel.callback(interaction)
        return seen
    assert asyncio.run(go()) == [True]


def _click(uid=42):
    from unittest.mock import AsyncMock, MagicMock
    inter = MagicMock()
    inter.user.id = uid
    inter.response.defer = AsyncMock()
    inter.followup.send = AsyncMock()
    return inter


def test_a_location_button_runs_its_handler_under_the_players_lock():
    """The location view's buttons (Rest, Drink, Gamble, Pray, Dungeon...) called
    their handlers directly, outside the lock the typed command takes. A handler
    that takes the lock itself must still run, not deadlock."""
    import utils.ttrpg.rpg_views as rv
    from utils.ttrpg.session_manager import get_action_lock, serialize_user_action

    async def go():
        view = rv.RPGFullLocationView(None, None, "42", "p", False, "stone_hearth")
        lock = await get_action_lock("user:42")
        seen = []

        async def rest(*a):
            seen.append(lock.locked())

        @serialize_user_action
        async def go_somewhere(ctx, msg, send, rest, uid, uname, is_owner):
            seen.append("ran")
        view._handler_map["rest"], view._handler_map["go"] = rest, go_somewhere
        view._add_btn("Rest", "🛏️", "rest", "", discord.ButtonStyle.green, 2)
        view._add_btn("Go", "📍", "go", "oakhaven", discord.ButtonStyle.green, 2)
        buttons = [b for b in view.children if getattr(b, "label", None) in ("Rest", "Go")]
        for b in buttons[-2:]:
            await asyncio.wait_for(b.callback(_click()), 2)
        return seen
    import discord
    assert asyncio.run(go()) == [True, "ran"]


def test_the_lazy_handlers_show_whether_they_lock_for_themselves():
    import utils.ttrpg.rpg_views as rv
    assert rv._handle_go.target()._serialized is True
    assert not getattr(rv._handle_rest.target(), "_serialized", False)


def test_descending_from_an_old_room_message_keeps_the_floor_as_it_is(monkeypatch, tmp_path):
    """Descend and Ascend saved the floor captured when their room was posted,
    undoing every room cleared since, and took stairs the player had walked away from."""
    import copy
    from unittest.mock import AsyncMock
    import utils.ttrpg.spine_dungeon as sd
    import utils.ttrpg.rpg_views as rv
    monkeypatch.setattr(sd, "SPINE_DIR", str(tmp_path))
    monkeypatch.setattr(rv, "_send_dungeon_room", AsyncMock())
    monkeypatch.setattr(rv, "load", AsyncMock(return_value={"spine_defeated_guards": list(range(80))}))

    async def go():
        floor = sd.generate_spine_floor(1, 5)
        stairs = next(k for k, r in floor["rooms"].items() if r.get("type") == "stairs_down")
        floor["player_pos"] = [int(c) for c in stairs.split(",")]
        await sd.save_spine_dungeon("42", floor)
        old_view = rv.DungeonView(None, "42", "p", False, copy.deepcopy(floor))

        now = await sd.load_spine_dungeon("42")
        elsewhere = next(k for k, r in now["rooms"].items() if k != stairs and not r.get("cleared"))
        now["rooms"][elsewhere]["cleared"] = True
        now["player_pos"] = [int(c) for c in elsewhere.split(",")]
        await sd.save_spine_dungeon("42", now)

        descend = next(b for b in old_view.children if "Descend" in (b.label or ""))
        await descend.callback(_click())
        return elsewhere

    elsewhere = asyncio.run(go())
    current = asyncio.run(sd.load_spine_dungeon("42"))
    assert current and current["floor_num"] == 1
    assert current["rooms"][elsewhere]["cleared"] is True


def test_the_unequip_menu_runs_the_real_handler_without_deadlocking(monkeypatch):
    """The lock test above stubs the handler; this runs the real one under the
    menu's lock, which would hang if the handler took the player's lock too."""
    from unittest.mock import AsyncMock
    sheet = {"user_id": "42", "character_name": "P", "inventory": [], "hp": {"current": 10, "max": 10},
             "equipment": {"weapon": "rusty_dagger"}}
    saved = []
    monkeypatch.setattr(cor, "load", AsyncMock(side_effect=lambda uid: dict(sheet, equipment=dict(sheet["equipment"]))))
    monkeypatch.setattr(cor, "save", AsyncMock(side_effect=lambda s: saved.append(s)))
    views = []
    async def channel_send(*a, view=None, **k):
        views.append(view)

    async def go():
        msg = types.SimpleNamespace(channel=types.SimpleNamespace(id=7, send=channel_send))
        await cor._handle_unequip(_ctx(), msg, None, "", "42", "p", False)
        sel = next(i for i in views[0].children if hasattr(i, "options"))
        interaction = types.SimpleNamespace(user=types.SimpleNamespace(id=42), guild=None,
                                            data={"values": ["weapon"]}, channel=types.SimpleNamespace(id=7, send=channel_send),
                                            followup=types.SimpleNamespace(send=channel_send),
                                            response=types.SimpleNamespace(defer=AsyncMock()))
        await asyncio.wait_for(sel.callback(interaction), timeout=5)
    asyncio.run(go())
    assert saved and not saved[-1]["equipment"].get("weapon")



def test_stale_furniture_shop_cannot_buy_an_already_owned_bonus_again(monkeypatch):
    """An old shop menu must not let the same bonus furnishing stack twice."""
    import copy
    from unittest.mock import AsyncMock
    import utils.ttrpg.rpg_housing_handler as hh
    import utils.ttrpg.housing as H

    sheets = {"42": {"user_id": "42", "character_name": "P", "gil": 500, "inventory": []}}
    homes = {"42": {"user_id": "42", "character_name": "P", "tier": "hut",
                    "furniture": ["weapon_rack"]}}

    async def load_sheet(uid):
        return copy.deepcopy(sheets[str(uid)])

    async def save_sheet(sheet):
        sheets[str(sheet["user_id"])] = copy.deepcopy(sheet)

    monkeypatch.setattr(hh, "load", load_sheet)
    monkeypatch.setattr(hh, "save", save_sheet)
    monkeypatch.setattr(H, "load_housing", lambda uid: copy.deepcopy(homes[str(uid)]))
    monkeypatch.setattr(H, "save_housing", lambda housing: homes.__setitem__(str(housing["user_id"]), copy.deepcopy(housing)))

    send = AsyncMock()
    msg = types.SimpleNamespace(channel=object())

    async def go():
        await hh._handle_buy_furniture.__wrapped__(
            None, msg, send, "weapon_rack", "42", "P", False
        )
    asyncio.run(go())

    assert sheets["42"]["gil"] == 500
    assert homes["42"]["furniture"] == ["weapon_rack"]
    send.assert_awaited_once()
    assert "already own" in send.await_args.args[1]


def test_stale_first_home_button_cannot_charge_twice_or_reset_estate(monkeypatch):
    """A stale purchase view cannot replace a home created after it was opened."""
    import copy
    from unittest.mock import AsyncMock, MagicMock
    import utils.ttrpg.rpg_housing_handler as hh
    import utils.ttrpg.housing as H

    sheets = {"42": {"user_id": "42", "character_name": "P", "location": "housing_district",
                    "gil": 500, "hp": {"current": 20, "max": 20}}}
    homes = {}

    async def load_sheet(uid):
        return copy.deepcopy(sheets.get(str(uid)))

    async def save_sheet(sheet):
        sheets[str(sheet["user_id"])] = copy.deepcopy(sheet)

    def load_home(uid):
        return copy.deepcopy(homes.get(str(uid)))

    def save_home(home):
        homes[str(home["user_id"])] = copy.deepcopy(home)

    monkeypatch.setattr(hh, "load", load_sheet)
    monkeypatch.setattr(hh, "save", save_sheet)
    monkeypatch.setattr(H, "load_housing", load_home)
    monkeypatch.setattr(H, "save_housing", save_home)
    monkeypatch.setattr(hh, "_log_world_event", AsyncMock())

    sent = {}
    async def channel_send(*args, embed=None, view=None, **kwargs):
        sent["view"] = view

    async def go():
        msg = types.SimpleNamespace(channel=types.SimpleNamespace(send=channel_send))
        await hh._handle_my_home(None, msg, None, "", "42", "P", False)
        button = next(b for b in sent["view"].children if "Purchase Hut" in (b.label or ""))

        def interaction():
            i = MagicMock()
            i.user.id = 42
            i.response.send_message = AsyncMock()
            return i

        # First click creates the hut and charges once.
        await button.callback(interaction())
        homes["42"]["furniture"] = ["weapon_rack"]
        homes["42"]["house_name"] = "The Kept Estate"

        # The same still-live button is pressed again after the estate changed.
        second = interaction()
        await button.callback(second)
        return second

    second = asyncio.run(go())
    assert sheets["42"]["gil"] == 500 - H.HOUSING_TIERS["hut"]["cost"]
    assert homes["42"]["furniture"] == ["weapon_rack"]
    assert homes["42"]["house_name"] == "The Kept Estate"
    second.response.send_message.assert_awaited_once()
    assert "already own" in second.response.send_message.await_args.args[0]


def test_non_owner_cannot_dispatch_mail_from_another_players_view(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import utils.ttrpg.rpg_views as rv

    sender = {"user_id": "42", "character_name": "Victim", "gil": 500,
              "inventory": ["tonic"], "mailbox": []}
    recipient = {"user_id": "99", "character_name": "Recipient", "level": 1, "class": "Mage"}

    load = AsyncMock(return_value=sender.copy())
    save = AsyncMock()
    monkeypatch.setattr(rv, "load", load)
    monkeypatch.setattr(rv, "save", save)

    view = rv.MailSendView(
        types.SimpleNamespace(), types.SimpleNamespace(), "42", "Victim", False,
        sender.copy(), [recipient]
    )
    view.selected_recipient_id = "99"
    view.selected_item = "tonic"

    interaction = MagicMock()
    interaction.user.id = 666
    interaction.response.send_message = AsyncMock()

    asyncio.run(view.dispatch_callback(interaction))

    interaction.response.send_message.assert_awaited_once()
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True
    load.assert_not_awaited()
    save.assert_not_awaited()
    assert sender["gil"] == 500
    assert sender["inventory"] == ["tonic"]


def test_moogle_mail_dispatch_is_single_use_and_delivered_once(monkeypatch):
    import copy
    import types
    from unittest.mock import AsyncMock, MagicMock
    import utils.ttrpg.rpg_views as rv

    disk = {
        "42": {"user_id": "42", "character_name": "Sender", "gil": 500,
               "inventory": ["tonic"], "pending_mail_dispatches": []},
        "99": {"user_id": "99", "character_name": "Recipient", "level": 1, "class": "Mage",
               "gil": 0, "inventory": [], "mailbox": []},
    }

    async def load_sheet(uid):
        return copy.deepcopy(disk.get(str(uid)))

    async def save_sheet(sheet):
        disk[str(sheet["user_id"])] = copy.deepcopy(sheet)

    monkeypatch.setattr(rv, "load", load_sheet)
    monkeypatch.setattr(rv, "save", save_sheet)

    view = rv.MailSendView(
        types.SimpleNamespace(), types.SimpleNamespace(), "42", "Sender", False,
        copy.deepcopy(disk["42"]), [disk["99"]],
    )
    view.selected_recipient_id = "99"
    view.selected_item = None
    view.gil_to_send = 125

    def interaction():
        i = MagicMock()
        i.user.id = 42
        i.response.defer = AsyncMock()
        i.response.send_message = AsyncMock()
        i.followup.send = AsyncMock()
        return i

    async def go():
        first = interaction()
        second = interaction()
        await asyncio.gather(
            view.dispatch_callback(first),
            view.dispatch_callback(second),
        )
        return first, second

    first, second = asyncio.run(go())
    assert disk["42"]["gil"] == 375
    assert disk["42"]["inventory"] == ["tonic"]
    assert disk["42"]["pending_mail_dispatches"] == []
    assert len(disk["99"]["mailbox"]) == 1
    assert disk["99"]["mailbox"][0]["item"] is None
    assert disk["99"]["mailbox"][0]["gil"] == 125
    assert disk["99"]["gil"] == 0
    first.followup.send.assert_awaited_once()
    second.response.send_message.assert_awaited_once()


def test_moogle_mail_pending_dispatch_recovers_without_duplicate_delivery(monkeypatch):
    import copy
    import asyncio
    from utils.ttrpg import rpg_views as rv

    dispatch = {
        "dispatch_id": "dispatch-123",
        "to_user_id": "99",
        "from_name": "Sender",
        "item": "tonic",
        "gil": 125,
        "timestamp": 123.0,
    }
    disk = {
        "42": {"user_id": "42", "character_name": "Sender", "gil": 375,
               "inventory": [], "pending_mail_dispatches": [dispatch]},
        "99": {"user_id": "99", "character_name": "Recipient", "gil": 0,
               "inventory": [], "mailbox": []},
    }

    async def load_sheet(uid):
        return copy.deepcopy(disk.get(str(uid)))

    async def save_sheet(sheet):
        disk[str(sheet["user_id"])] = copy.deepcopy(sheet)

    monkeypatch.setattr(rv, "load", load_sheet)
    monkeypatch.setattr(rv, "save", save_sheet)

    async def go():
        first = await rv.recover_pending_mail_dispatches("42")
        second = await rv.recover_pending_mail_dispatches("42")
        return first, second

    first, second = asyncio.run(go())
    assert first == (1, 0)
    assert second == (0, 0)
    assert disk["42"]["gil"] == 375
    assert disk["42"]["inventory"] == []
    assert disk["42"]["pending_mail_dispatches"] == []
    assert len(disk["99"]["mailbox"]) == 1
    assert disk["99"]["mailbox"][0]["dispatch_id"] == "dispatch-123"


def test_moogle_mail_keeps_pending_dispatch_when_recipient_is_missing(monkeypatch):
    import copy
    import asyncio
    from utils.ttrpg import rpg_views as rv

    dispatch = {
        "dispatch_id": "dispatch-404",
        "to_user_id": "99",
        "from_name": "Sender",
        "item": None,
        "gil": 50,
        "timestamp": 123.0,
    }
    sender = {"user_id": "42", "character_name": "Sender", "gil": 450,
              "inventory": [], "pending_mail_dispatches": [dispatch]}

    async def load_sheet(uid):
        return copy.deepcopy(sender) if str(uid) == "42" else None

    async def save_sheet(sheet):
        sender.clear()
        sender.update(copy.deepcopy(sheet))

    monkeypatch.setattr(rv, "load", load_sheet)
    monkeypatch.setattr(rv, "save", save_sheet)

    delivered, pending = asyncio.run(rv.recover_pending_mail_dispatches("42"))
    assert delivered == 0
    assert pending == 1
    assert sender["gil"] == 450
    assert sender["pending_mail_dispatches"] == [dispatch]



def test_moogle_mail_does_not_charge_when_recipient_no_longer_exists(monkeypatch):
    import copy
    import types
    from unittest.mock import AsyncMock, MagicMock
    import utils.ttrpg.rpg_views as rv

    sender = {"user_id": "42", "character_name": "Sender", "gil": 500,
              "inventory": ["tonic"], "pending_mail_dispatches": []}

    async def load_sheet(uid):
        return copy.deepcopy(sender) if str(uid) == "42" else None

    save = AsyncMock()
    monkeypatch.setattr(rv, "load", load_sheet)
    monkeypatch.setattr(rv, "save", save)

    view = rv.MailSendView(
        types.SimpleNamespace(), types.SimpleNamespace(), "42", "Sender", False,
        copy.deepcopy(sender),
        [{"user_id": "99", "character_name": "Recipient", "level": 1, "class": "Mage"}],
    )
    view.selected_recipient_id = "99"
    view.gil_to_send = 125

    interaction = MagicMock()
    interaction.user.id = 42
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(view.dispatch_callback(interaction))

    save.assert_not_awaited()
    assert sender["gil"] == 500
    assert sender["inventory"] == ["tonic"]
    assert sender["pending_mail_dispatches"] == []
    interaction.followup.send.assert_awaited_once()
    assert view._dispatch_started is False


def _spine_lift_test_context(monkeypatch, fresh_sheet, target_floor="5",
                             active_dungeon=None):
    import copy
    from unittest.mock import AsyncMock, MagicMock
    import utils.ttrpg.rpg_views as rv
    import utils.ttrpg.character_manager as cm
    import utils.ttrpg.progression as progression
    import utils.ttrpg.spine_dungeon as spine
    import utils.ttrpg.rpg_combat_handler as combat

    disk = {"sheet": copy.deepcopy(fresh_sheet)}
    saved_sheets = []
    saved_dungeons = []
    sent_rooms = []

    async def load_sheet(uid):
        return copy.deepcopy(disk["sheet"])

    async def save_sheet(sheet):
        disk["sheet"] = copy.deepcopy(sheet)
        saved_sheets.append(copy.deepcopy(sheet))

    async def load_dungeon(uid):
        return copy.deepcopy(active_dungeon)

    async def save_dungeon(uid, dungeon):
        saved_dungeons.append(copy.deepcopy(dungeon))

    def generate_floor(floor, level):
        return {"floor_num": floor, "player_level": level, "active": False}

    async def send_dungeon_room(*args):
        sent_rooms.append(args[-1])

    monkeypatch.setattr(cm, "load", load_sheet)
    monkeypatch.setattr(cm, "save", save_sheet)
    monkeypatch.setattr(progression, "check_and_reset_hunts", lambda sheet: sheet)
    monkeypatch.setattr(progression, "hunts_remaining", lambda sheet: max(0, 5 - sheet.get("hunts_today", 0)))
    monkeypatch.setattr(progression, "get_max_hunts", lambda sheet: 5)
    monkeypatch.setattr(spine, "load_spine_dungeon", load_dungeon)
    monkeypatch.setattr(spine, "save_spine_dungeon", save_dungeon)
    monkeypatch.setattr(spine, "generate_spine_floor", generate_floor)
    monkeypatch.setattr(combat, "_send_dungeon_room", send_dungeon_room)

    view = rv.SpineLiftView(
        types.SimpleNamespace(),
        "42",
        "Sender",
        False,
        5,
    )
    stop_calls = []
    original_stop = view.stop

    def track_stop():
        stop_calls.append(True)
        return original_stop()

    view.stop = track_stop

    interaction = MagicMock()
    interaction.user.id = 42
    interaction.data = {"values": [str(target_floor)]}
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.channel = object()

    return view, interaction, disk, saved_sheets, saved_dungeons, sent_rooms, stop_calls


def _spine_sheet(location="aeridor_ruins", inventory=None, hunts_today=0):
    return {
        "user_id": "42",
        "character_name": "Delver",
        "location": location,
        "level": 15,
        "inventory": list(inventory or []),
        "hunts_today": hunts_today,
        "hunts_reset_date": __import__("datetime").date.today().strftime("%Y-%m-%d"),
        "spine_defeated_guards": [4],
    }


def test_spine_lift_revalidates_location_before_entry(monkeypatch):
    sheet = _spine_sheet(location="trade_road", inventory=["torch"])
    view, interaction, _, saved, dungeon_saves, rooms, stop_calls = _spine_lift_test_context(
        monkeypatch, sheet
    )

    asyncio.run(view.children[0].callback(interaction))

    assert saved == []
    assert dungeon_saves == []
    assert rooms == []
    interaction.followup.send.assert_awaited_once()
    assert "Aeridor Ruins" in interaction.followup.send.await_args.args[0]
    assert stop_calls == [True]


def test_spine_lift_revalidates_light_source_from_fresh_sheet(monkeypatch):
    fresh_sheet = _spine_sheet(inventory=[])
    view, interaction, _, saved, dungeon_saves, rooms, _ = _spine_lift_test_context(
        monkeypatch, fresh_sheet
    )

    asyncio.run(view.children[0].callback(interaction))

    assert saved == []
    assert dungeon_saves == []
    assert rooms == []
    interaction.followup.send.assert_awaited_once()
    assert "Lightstone or a Torch" in interaction.followup.send.await_args.args[0]
    assert view._lift_started is False


def test_spine_lift_rejects_an_already_active_spine_floor(monkeypatch):
    sheet = _spine_sheet(inventory=["torch"])
    active = {"floor_num": 10, "active": True}
    view, interaction, _, saved, dungeon_saves, rooms, stop_calls = _spine_lift_test_context(
        monkeypatch, sheet, active_dungeon=active
    )

    asyncio.run(view.children[0].callback(interaction))

    assert saved == []
    assert dungeon_saves == []
    assert rooms == []
    interaction.followup.send.assert_awaited_once()
    assert "already inside the Spine" in interaction.followup.send.await_args.args[0]
    assert stop_calls == [True]


def test_spine_lift_rejects_a_checkpoint_that_is_no_longer_unlocked(monkeypatch):
    sheet = _spine_sheet(inventory=["torch"])
    view, interaction, _, saved, dungeon_saves, rooms, stop_calls = _spine_lift_test_context(
        monkeypatch, sheet, target_floor="10"
    )

    asyncio.run(view.children[0].callback(interaction))

    assert saved == []
    assert dungeon_saves == []
    assert rooms == []
    interaction.followup.send.assert_awaited_once()
    assert "no longer unlocked" in interaction.followup.send.await_args.args[0]
    assert stop_calls == [True]


def test_spine_lift_is_single_use_and_consumes_only_one_torch(monkeypatch):
    sheet = _spine_sheet(inventory=["torch", "torch"])
    view, interaction, disk, saved, dungeon_saves, rooms, stop_calls = _spine_lift_test_context(
        monkeypatch, sheet
    )

    from unittest.mock import AsyncMock, MagicMock
    second = MagicMock()
    second.user.id = 42
    second.data = {"values": ["5"]}
    second.response.defer = AsyncMock()
    second.response.send_message = AsyncMock()
    second.followup.send = AsyncMock()
    second.channel = object()

    async def go():
        await asyncio.gather(
            view.children[0].callback(interaction),
            view.children[0].callback(second),
        )

    asyncio.run(go())

    assert len(saved) == 1
    assert saved[0]["hunts_today"] == 2
    assert saved[0]["inventory"] == ["torch"]
    assert len(dungeon_saves) == 1
    assert dungeon_saves[0]["floor_num"] == 5
    assert dungeon_saves[0]["active"] is True
    assert len(rooms) == 1
    assert stop_calls == [True]
    assert interaction.response.defer.await_count + second.response.defer.await_count == 1
    assert interaction.response.send_message.await_count + second.response.send_message.await_count == 1


def test_spine_lift_does_not_consume_torch_when_fresh_sheet_has_lightstone(monkeypatch):
    fresh_sheet = _spine_sheet(inventory=["lightstone", "torch"])
    view, interaction, _, saved, dungeon_saves, rooms, _ = _spine_lift_test_context(
        monkeypatch, fresh_sheet
    )

    asyncio.run(view.children[0].callback(interaction))

    assert len(saved) == 1
    assert saved[0]["inventory"] == ["lightstone", "torch"]
    assert saved[0]["hunts_today"] == 2
    assert len(dungeon_saves) == 1
    assert len(rooms) == 1



def test_concurrent_npc_quest_acceptance_only_commits_once(monkeypatch):
    import copy
    from unittest.mock import AsyncMock
    import utils.ttrpg.rpg_social_handler as social

    state = {
        "user_id": "42",
        "level": 5,
        "active_quests": [],
        "completed_quests": [],
    }
    saves = []

    async def load_sheet(uid):
        return copy.deepcopy(state)

    async def save_sheet(sheet):
        saves.append(copy.deepcopy(sheet))
        state.clear()
        state.update(copy.deepcopy(sheet))

    monkeypatch.setattr(social, "load", load_sheet)
    monkeypatch.setattr(social, "save", save_sheet)
    quest = {
        "id": "lost_reliquary",
        "name": "The Lost Reliquary",
        "requirements": {"level": 1},
    }

    async def go():
        return await asyncio.gather(
            social._accept_quest_for_player("42", quest),
            social._accept_quest_for_player("42", quest),
        )

    results = asyncio.run(go())

    assert sum(1 for accepted, _ in results if accepted) == 1
    assert sum(1 for accepted, _ in results if not accepted) == 1
    assert state["active_quests"] == ["lost_reliquary"]
    assert len(saves) == 1


def test_concurrent_quest_abandonment_reloads_after_taking_player_lock(monkeypatch):
    import copy
    from unittest.mock import AsyncMock
    import utils.ttrpg.rpg_social_handler as social

    state = {
        "user_id": "42",
        "active_quests": ["lost_reliquary"],
        "quest_progress": {"lost_reliquary": ["find_map"]},
    }
    saves = []

    async def load_sheet(uid):
        return copy.deepcopy(state)

    async def save_sheet(sheet):
        saves.append(copy.deepcopy(sheet))
        state.clear()
        state.update(copy.deepcopy(sheet))

    monkeypatch.setattr(social, "load", load_sheet)
    monkeypatch.setattr(social, "save", save_sheet)
    send = AsyncMock()
    msg = types.SimpleNamespace(channel=types.SimpleNamespace(send=send))

    async def go():
        await asyncio.gather(
            social._handle_abandon(None, msg, None, "lost_reliquary", "42", "P", False),
            social._handle_abandon(None, msg, None, "lost_reliquary", "42", "P", False),
        )

    asyncio.run(go())

    assert social._handle_abandon._serialized is True
    assert state["active_quests"] == []
    assert state["quest_progress"] == {}
    assert len(saves) == 1
    assert send.await_count == 2
    assert any(
        "abandoned" in (call.kwargs.get("embed").description or "").lower()
        for call in send.await_args_list
    )
    assert any(
        "no active quest" in (call.kwargs.get("embed").description or "").lower()
        for call in send.await_args_list
    )


def test_house_rename_modal_rejects_a_non_owner_without_loading_or_writing(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    import utils.ttrpg.rpg_views as rv
    import utils.ttrpg.housing as housing

    load_sheet = AsyncMock(return_value={"user_id": "42"})
    load_home = AsyncMock(return_value={"user_id": "42", "house_name": "Old Home"})
    save_home = AsyncMock()
    monkeypatch.setattr(rv, "load", load_sheet)
    monkeypatch.setattr(housing, "load_housing_async", load_home)
    monkeypatch.setattr(housing, "save_housing_async", save_home)

    modal = rv.RenameHouseModal("42")
    interaction = MagicMock()
    interaction.user.id = 99
    interaction.response.send_message = AsyncMock()

    asyncio.run(modal.on_submit(interaction))

    interaction.response.send_message.assert_awaited_once()
    assert "another player" in interaction.response.send_message.await_args.args[0]
    load_sheet.assert_not_awaited()
    load_home.assert_not_awaited()
    save_home.assert_not_awaited()


def test_concurrent_house_rename_modals_share_owner_lock_and_reload_estate(monkeypatch):
    import asyncio
    import copy
    from unittest.mock import AsyncMock, MagicMock
    import utils.ttrpg.rpg_views as rv
    import utils.ttrpg.housing as housing
    from utils.ttrpg.session_manager import get_action_lock

    sheet = {"user_id": "42", "character_name": "P"}
    estate = {"user_id": "42", "house_name": "Starting Home", "furniture": ["weapon_rack"]}
    saved = []

    monkeypatch.setattr(rv, "load", AsyncMock(return_value=sheet))

    async def load_home(uid):
        lock = await get_action_lock("user:42")
        assert lock.locked()
        return copy.deepcopy(estate)

    async def save_home(current):
        lock = await get_action_lock("user:42")
        assert lock.locked()
        saved.append(copy.deepcopy(current))
        estate.clear()
        estate.update(copy.deepcopy(current))

    monkeypatch.setattr(housing, "load_housing_async", load_home)
    monkeypatch.setattr(housing, "save_housing_async", save_home)

    first = rv.RenameHouseModal("42")
    second = rv.RenameHouseModal("42")
    # The estate changes after the modal is created; submit must reload it.
    estate["furniture"].append("garden_fountain")
    first.new_name._value = "First Name"
    second.new_name._value = "Second Name"

    def interaction():
        result = MagicMock()
        result.user.id = 42
        result.response.send_message = AsyncMock()
        return result

    first_interaction = interaction()
    second_interaction = interaction()

    async def go():
        await asyncio.gather(
            first.on_submit(first_interaction),
            second.on_submit(second_interaction),
        )

    asyncio.run(go())

    assert len(saved) == 2
    assert estate["house_name"] in {"First Name", "Second Name"}
    assert estate["furniture"] == ["weapon_rack", "garden_fountain"]
    assert all(x["furniture"] == ["weapon_rack", "garden_fountain"] for x in saved)
    assert first_interaction.response.send_message.await_count == 1
    assert second_interaction.response.send_message.await_count == 1
    assert all(
        "Your home is now named" in call.args[0]
        for interaction in (first_interaction, second_interaction)
        for call in interaction.response.send_message.await_args_list
    )


@pytest.mark.parametrize("moved_uid", ["1", "2"])
def test_duel_accept_rejects_challenge_after_either_player_moves(monkeypatch, moved_uid):
    import copy
    from unittest.mock import AsyncMock, MagicMock
    import utils.ttrpg.rpg_combat_handler as combat
    from utils.ttrpg import combat_engine

    sheets = {
        "1": {
            "user_id": "1",
            "character_name": "Challenger",
            "location": "stone_hearth",
            "level": 5,
            "class": "Warrior",
            "hp": {"current": 20, "max": 20},
            "stats": {"str": 10},
            "equipment": {},
        },
        "2": {
            "user_id": "2",
            "character_name": "Target",
            "location": "stone_hearth",
            "level": 5,
            "class": "Warrior",
            "hp": {"current": 20, "max": 20},
            "stats": {"str": 10},
            "equipment": {},
        },
    }
    sheets[moved_uid]["location"] = "whisperwood_edge"

    async def load_sheet(uid):
        return copy.deepcopy(sheets[str(uid)])

    save_sheet = AsyncMock()
    resolve = MagicMock()
    send = AsyncMock()
    monkeypatch.setattr(combat, "load", load_sheet)
    monkeypatch.setattr(combat, "save", save_sheet)
    monkeypatch.setattr(combat, "PENDING_DUELS", {
        ("1", "2"): {
            "created_at": combat.time.time(),
            "location": "stone_hearth",
        }
    })
    monkeypatch.setattr(combat, "_log_world_event", AsyncMock())
    monkeypatch.setattr(combat_engine, "_resolve_combat", resolve)

    msg = types.SimpleNamespace(channel=types.SimpleNamespace(id=7, send=send))

    asyncio.run(combat._handle_accept(None, msg, None, "", "2", "Target", False))

    resolve.assert_not_called()
    save_sheet.assert_not_awaited()
    assert combat.PENDING_DUELS == {}
    assert send.await_count == 1
    assert "stale" in send.await_args.kwargs["embed"].description.lower()


def test_duel_accept_holds_both_sorted_locks_until_both_sheets_are_saved(monkeypatch):
    import copy
    from unittest.mock import AsyncMock, MagicMock
    import utils.ttrpg.rpg_combat_handler as combat
    from utils.ttrpg import combat_engine, housing, session_manager
    from utils.ttrpg.session_manager import _action_locks, serialize_user_action

    sheets = {
        "1": {
            "user_id": "1",
            "character_name": "Challenger",
            "location": "stone_hearth",
            "level": 5,
            "class": "Warrior",
            "hp": {"current": 3, "max": 20},
            "stats": {"str": 10},
            "equipment": {},
            "conditions": [],
        },
        "2": {
            "user_id": "2",
            "character_name": "Target",
            "location": "stone_hearth",
            "level": 5,
            "class": "Warrior",
            "hp": {"current": 4, "max": 20},
            "stats": {"str": 10},
            "equipment": {},
            "conditions": [],
        },
    }

    async def load_sheet(uid):
        return copy.deepcopy(sheets[str(uid)])

    async def save_sheet(sheet):
        sheets[str(sheet["user_id"])] = copy.deepcopy(sheet)

    housing_started = asyncio.Event()
    release_duel = asyncio.Event()
    lock_requests = []
    original_get_action_lock = session_manager.get_action_lock

    async def track_action_lock(key):
        lock_requests.append(key)
        return await original_get_action_lock(key)

    monkeypatch.setattr(session_manager, "get_action_lock", track_action_lock)

    async def load_housing(uid):
        # The duel is paused here after acquiring both participant locks.
        assert _action_locks["user:1"].locked()
        assert _action_locks["user:2"].locked()
        housing_started.set()
        await release_duel.wait()
        return None

    def resolve(c_sheet, target, **kwargs):
        assert _action_locks["user:1"].locked()
        assert _action_locks["user:2"].locked()
        c_sheet["hp"]["current"] = 1
        target["hp"]["current"] = 1
        return {
            "sheet": c_sheet,
            "monster": target,
            "exchanges": ["The duel ends with both fighters standing."],
        }

    send = AsyncMock()
    msg = types.SimpleNamespace(channel=types.SimpleNamespace(id=7, send=send))
    monkeypatch.setattr(combat, "load", load_sheet)
    monkeypatch.setattr(combat, "save", save_sheet)
    monkeypatch.setattr(combat, "PENDING_DUELS", {
        ("1", "2"): {
            "created_at": combat.time.time(),
            "location": "stone_hearth",
        }
    })
    monkeypatch.setattr(combat, "_log_world_event", AsyncMock())
    monkeypatch.setattr(combat_engine, "_compute_player_defense", lambda *a, **k: 2)
    monkeypatch.setattr(combat_engine, "_resolve_combat", resolve)
    monkeypatch.setattr(housing, "load_housing_async", load_housing)

    @serialize_user_action
    async def participant_follow_up(ctx, action_msg, send_fn, rest, uid, uname, is_owner):
        current = await load_sheet(uid)
        current["conditions"].append("potion_used")
        await save_sheet(current)

    async def go():
        duel_task = asyncio.create_task(
            combat._handle_accept(None, msg, None, "", "2", "Target", False)
        )
        await housing_started.wait()

        # Both participants' ordinary serialized actions must wait for the duel.
        challenger_task = asyncio.create_task(
            participant_follow_up(None, msg, None, "", "1", "Challenger", False)
        )
        target_task = asyncio.create_task(
            participant_follow_up(None, msg, None, "", "2", "Target", False)
        )
        await asyncio.sleep(0)
        assert not challenger_task.done()
        assert not target_task.done()

        release_duel.set()
        await asyncio.gather(duel_task, challenger_task, target_task)

    asyncio.run(go())

    assert lock_requests[:2] == ["user:1", "user:2"]
    assert _action_locks["user:1"].locked() is False
    assert _action_locks["user:2"].locked() is False
    assert sheets["1"]["hp"]["current"] == 1
    assert sheets["1"]["conditions"] == ["potion_used"]
    assert sheets["2"]["hp"]["current"] == 1
    assert sheets["2"]["conditions"] == ["potion_used"]
    assert combat.PENDING_DUELS == {}
    assert send.await_count == 1
    assert "DUEL RESULTS" in send.await_args.kwargs["embed"].title


def test_accept_handler_owns_both_locks_instead_of_dispatcher_locking_target():
    import utils.ttrpg.rpg_combat_handler as combat

    assert combat._handle_accept._serialized is True
