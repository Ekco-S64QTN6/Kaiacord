"""Concurrent combat actions must not lose each other's damage.

Player report: "player hp calculation kinda funky, sometimes displayed hp
increases without rhyme or reason. reported hp mismatched with actual hp?"

The screenshot showed a Wyrm at 80/116 in one round and 101/116 in the next —
HP rising by exactly the 21 damage that had just been dealt — and the player's
HP moving 77 -> 91 while both counter-attacks missed.

Cause: `load()` and `save()` each take the per-user lock and release it in
between, so each file write is atomic but the read-modify-write around it is
not. A combat round loads the sheet, resolves, waits on the model for
narration, then saves. Two rounds overlapping in that window both read the same
state, and the second save discards the first round's damage.
"""
import asyncio

import pytest

from utils.ttrpg.session_manager import get_action_lock, serialize_combat_action


class _Chan:
    def __init__(self, cid="chan-1"):
        self.id = cid


class _Msg:
    def __init__(self, cid="chan-1"):
        self.channel = _Chan(cid)


@pytest.fixture(autouse=True)
def _fresh_locks(monkeypatch):
    import utils.ttrpg.session_manager as sm
    monkeypatch.setattr(sm, "_action_locks", {})


def _make_store(hp=116):
    """A load/save pair with an await between them, like the real handlers."""
    store = {"hp": hp}

    async def load():
        await asyncio.sleep(0)          # the real load hits a thread
        return dict(store)

    async def save(sheet):
        await asyncio.sleep(0)
        store.update(sheet)

    return store, load, save


def test_the_race_is_real_without_the_guard():
    """Establishes that the test would catch the bug. If this ever stops
    failing, the reproduction has stopped reproducing and the guard test below
    proves nothing."""
    store, load, save = _make_store()

    async def unguarded_round(damage):
        sheet = await load()
        await asyncio.sleep(0.01)       # narration / GPU wait
        sheet["hp"] -= damage
        await save(sheet)

    async def main():
        await asyncio.gather(unguarded_round(21), unguarded_round(14))

    asyncio.run(main())
    assert store["hp"] != 116 - 21 - 14, "expected lost damage without a guard"


def test_the_guard_serialises_the_whole_read_modify_write():
    store, load, save = _make_store()

    @serialize_combat_action
    async def guarded_round(ctx, msg, send, rest, uid, uname, is_owner, *, damage):
        sheet = await load()
        await asyncio.sleep(0.01)
        sheet["hp"] -= damage
        await save(sheet)

    async def main():
        m = _Msg()
        await asyncio.gather(
            guarded_round(None, m, None, "", "u1", "u", False, damage=21),
            guarded_round(None, m, None, "", "u1", "u", False, damage=14),
        )

    asyncio.run(main())
    assert store["hp"] == 116 - 21 - 14, "both rounds' damage must survive"


def test_hp_never_moves_backwards_under_load():
    """The visible symptom was HP going *up*. Ten overlapping rounds must
    produce a monotonically decreasing sequence."""
    store, load, save = _make_store(hp=1000)
    seen = []

    @serialize_combat_action
    async def guarded_round(ctx, msg, send, rest, uid, uname, is_owner):
        sheet = await load()
        await asyncio.sleep(0.001)
        sheet["hp"] -= 10
        await save(sheet)
        seen.append(sheet["hp"])

    async def main():
        m = _Msg()
        await asyncio.gather(*[
            guarded_round(None, m, None, "", "u1", "u", False) for _ in range(10)
        ])

    asyncio.run(main())
    assert seen == sorted(seen, reverse=True), f"HP moved backwards: {seen}"
    assert store["hp"] == 900


def test_different_channels_do_not_block_each_other():
    """Two tables should not queue behind one another."""
    order = []

    @serialize_combat_action
    async def slow(ctx, msg, send, rest, uid, uname, is_owner):
        order.append(f"start-{msg.channel.id}")
        await asyncio.sleep(0.02)
        order.append(f"end-{msg.channel.id}")

    async def main():
        await asyncio.gather(
            slow(None, _Msg("a"), None, "", "u1", "u", False),
            slow(None, _Msg("b"), None, "", "u2", "u", False),
        )

    asyncio.run(main())
    assert order[:2] == ["start-a", "start-b"], f"channels serialised: {order}"


def test_the_action_lock_is_not_the_file_lock():
    """asyncio.Lock is not reentrant. If the guard reused the lock that
    load()/save() take internally, the first save inside a guarded action would
    deadlock."""
    import utils.ttrpg.session_manager as sm

    async def main():
        # Namespaced keys, so a channel's action lock and its file lock cannot
        # collide even though both are keyed by channel id.
        action = await sm.get_action_lock("chan:chan-1")
        file_lock = await sm.get_session_lock("chan-1")
        assert action is not file_lock
        assert await sm.get_action_lock("chan:1") is not await sm.get_action_lock("user:1")

    asyncio.run(main())


def test_the_real_handlers_are_guarded():
    """Dungeon combat has the same load/resolve/await/save shape and is reached
    from its own Attack button, so leaving it out would have fixed the symptom
    in the overworld only."""
    from utils.ttrpg.rpg_combat_handler import (
        _handle_attack, _handle_flee, _dungeon_combat_round,
    )
    from utils.ttrpg.rpg_core_handler import _handle_use
    from utils.ttrpg.rpg_views import _dungeon_combat_flee

    for fn in (_handle_attack, _handle_flee, _handle_use,
               _dungeon_combat_round, _dungeon_combat_flee):
        assert hasattr(fn, "__wrapped__"), f"{fn.__name__} is not serialised"


def test_the_hp_label_does_not_claim_full_health():
    """"(untouched)" was shown beside 77/141. It only ever meant the
    counter-attack missed that round.

    Checks string literals rather than the file text — the first version of
    this test grepped the source and failed on the comment explaining the fix.
    """
    import ast
    from pathlib import Path

    tree = ast.parse(Path("utils/ttrpg/combat_engine.py").read_text(encoding="utf-8"))
    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not any("untouched" in s for s in literals)
    assert any("no damage taken" in s for s in literals)


def test_the_same_user_is_serialised_across_different_channels():
    """The character sheet is per-user; a channel lock does not protect it. The
    Use Item flow runs from an ephemeral interaction, so a potion drunk there
    and an attack in the party channel take different channel locks and
    interleave their load/save on the same sheet."""
    store, load, save = _make_store(hp=100)

    @serialize_combat_action
    async def guarded(ctx, msg, send, rest, uid, uname, is_owner, *, delta):
        sheet = await load()
        await asyncio.sleep(0.01)
        sheet["hp"] += delta
        await save(sheet)

    async def main():
        await asyncio.gather(
            guarded(None, _Msg("party"), None, "", "u1", "u", False, delta=-20),
            guarded(None, _Msg("ephemeral"), None, "", "u1", "u", False, delta=+30),
        )

    asyncio.run(main())
    assert store["hp"] == 110, "both the damage and the heal must survive"


def test_different_users_in_one_channel_still_share_the_session_guard():
    """Monsters are shared, so two players attacking at once must serialise."""
    order = []

    @serialize_combat_action
    async def guarded(ctx, msg, send, rest, uid, uname, is_owner):
        order.append(f"start-{uid}")
        await asyncio.sleep(0.01)
        order.append(f"end-{uid}")

    async def main():
        await asyncio.gather(
            guarded(None, _Msg("party"), None, "", "111", "a", False),
            guarded(None, _Msg("party"), None, "", "222", "b", False),
        )

    asyncio.run(main())
    assert order in (["start-111", "end-111", "start-222", "end-222"],
                     ["start-222", "end-222", "start-111", "end-111"]), order


def test_the_dungeon_handler_shape_is_understood():
    """Dungeon handlers take (ctx, interaction, uid, uname, is_owner) — a
    different shape from the command handlers, and the first version of the
    decorator could only read the command shape."""
    from utils.ttrpg.session_manager import _action_keys

    class _I:
        channel = _Chan("dungeon-chan")

    async def dungeon(ctx_obj, interaction, uid, uname, is_owner): ...
    async def command(ctx, msg, send, rest, uid, uname, is_owner): ...

    assert _action_keys(dungeon, (None, _I(), "4242", "name", False), {}) == ("dungeon-chan", "4242")
    assert _action_keys(command, (None, _Msg("c"), None, "", "999", "n", False), {}) == ("c", "999")
