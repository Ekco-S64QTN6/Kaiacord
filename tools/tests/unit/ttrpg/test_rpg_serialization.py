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
