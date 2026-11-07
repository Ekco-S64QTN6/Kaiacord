"""The rescue is announced where the notice went up; event blessings do what they say."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from utils.ttrpg import combat_engine as ce
from utils.ttrpg import forest_events
from utils.ttrpg import rpg_combat_handler as rch


def _sheet(**kw):
    base = {"user_id": "1", "character_name": "Tess", "class": "Warrior", "level": 5,
            "location": "whisperwood_edge", "hp": {"current": 20, "max": 30}, "gil": 100, "xp": 0,
            "inventory": [], "conditions": [], "stats": {"str": 14, "dex": 12, "wis": 12},
            "equipment": {"weapon": None, "armor": None}}
    base.update(kw)
    return base


# ─── The rescue is town news ──────────────────────────────────────────────────

def _event_ctx():
    msg = MagicMock()
    msg.channel = MagicMock()
    msg.channel.id = 111
    msg.channel.send = AsyncMock()
    return MagicMock(), msg


def test_a_missing_person_found_is_announced_in_the_rpg_channel(monkeypatch):
    from utils.ttrpg import world_state, outing
    ctx, msg = _event_ctx()
    sheet = _sheet()
    state = {"missing_person_name": "Lily (the herbalist's daughter)",
             "missing_person_loc": "whisperwood_edge", "missing_person_expiry": 10**12}

    async def fake_mutate(mutator, current_sheet):
        ok, payload = mutator(current_sheet, state)
        return payload if ok else None

    monkeypatch.setattr(world_state, "mutate_world_state", fake_mutate)
    broadcast, logged = AsyncMock(), AsyncMock()
    monkeypatch.setattr(rch, "_broadcast_world_event", broadcast)
    monkeypatch.setattr(rch, "_log_world_event", logged)
    monkeypatch.setattr(outing, "record_event", AsyncMock())

    result = forest_events.resolve_event("missing_persons_found", sheet)
    handled = asyncio.run(rch._apply_and_narrate_event(ctx, msg, None, sheet, result, "tess", uid="1"))

    assert handled is True
    embed = broadcast.await_args.args[1]
    assert "Lily" in embed.description and "Tess" in embed.description
    assert "Whisperwood" in embed.description
    assert broadcast.await_args.kwargs["skip_channel"] is msg.channel
    assert any("Lily" in c.args[0] for c in logged.await_args_list)

    # The notice is gone: a second searcher gets no reward and no announcement.
    broadcast.reset_mock()
    again = asyncio.run(rch._apply_and_narrate_event(
        ctx, msg, None, _sheet(), forest_events.resolve_event("missing_persons_found", _sheet()), "bob", uid="2"))
    assert again is False
    broadcast.assert_not_awaited()


def test_a_broadcast_is_not_posted_twice_into_the_channel_it_was_played_in():
    from utils.ttrpg import broadcast as b
    channel = SimpleNamespace(id=5, name="aethelgard", send=AsyncMock())
    ctx = SimpleNamespace(bot=SimpleNamespace(get_all_channels=lambda: [channel]))
    asyncio.run(b.broadcast_world_event(ctx, MagicMock(), skip_channel=SimpleNamespace(id=5)))
    channel.send.assert_not_awaited()
    asyncio.run(b.broadcast_world_event(ctx, MagicMock(), skip_channel=SimpleNamespace(id=6)))
    channel.send.assert_awaited_once()


# ─── Blessings combat reads ───────────────────────────────────────────────────

def _brute(name="Forest Boar"):
    return {"name": name, "defense": 1, "attack": 6, "tier": "trivial", "hp": {"current": 999, "max": 999}}


def _monster_damage(conditions, monster):
    with patch.object(ce.secrets, "randbelow", return_value=9):
        res = ce._resolve_combat(_sheet(hp={"current": 200, "max": 200}, conditions=list(conditions)), monster)
    return res["monster_damage"]


def test_tree_memory_softens_natural_creatures_only():
    assert _monster_damage(["tree_memory"], _brute()) == _monster_damage([], _brute()) - 2
    golem = _brute("Iron Golem")
    assert _monster_damage(["tree_memory"], golem) == _monster_damage([], golem)


def test_wisp_ward_is_a_point_of_defence():
    base = ce._compute_player_defense(_sheet())
    assert ce._compute_player_defense(_sheet(conditions=["wisp_ward"])) == base + 1


def test_aeridorian_attunement_answers_only_in_the_ruins():
    def log(loc):
        with patch.object(ce.secrets, "randbelow", return_value=9):
            res = ce._resolve_combat(_sheet(location=loc, conditions=["aeridorian_attunement"]), _brute())
        return " ".join(res["exchanges"])
    assert "Aeridorian Attunement" in log("aeridor_ruins")
    assert "Aeridorian Attunement" not in log("trade_road")
