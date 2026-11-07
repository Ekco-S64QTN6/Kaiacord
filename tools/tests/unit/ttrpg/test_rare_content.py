"""Rare events, lore pages, rare variants and the noon events that drive them."""
import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.ttrpg import combat_engine as ce
from utils.ttrpg import encounter_tables, forest_events, lore, noon_events, rare_spawns
from utils.ttrpg import forest_events_rare as rare
from utils.ttrpg import rpg_combat_handler as rch


def _sheet(**kw):
    base = {"user_id": "1", "character_name": "Tess", "class": "Warrior", "level": 5,
            "location": "whisperwood_edge", "hp": {"current": 20, "max": 30}, "gil": 100, "xp": 0,
            "inventory": [], "conditions": [], "stats": {"str": 14, "dex": 12, "wis": 12},
            "equipment": {"weapon": None, "armor": None}}
    base.update(kw)
    return base


def _event_ctx():
    msg = MagicMock()
    msg.channel = MagicMock()
    msg.channel.id = 111
    msg.channel.send = AsyncMock()
    return MagicMock(), msg


# ─── Which events can roll ────────────────────────────────────────────────────

def test_night_only_events_wait_for_dark_unless_stars_are_falling():
    table = [("fallen_star", 2), ("quiet_hunter", 3), ("songstone", 4)]
    assert [k for k, _ in rare.adjust_table(table, {}, hour=12)] == ["songstone"]
    assert dict(rare.adjust_table(table, {}, hour=22)) == dict(table)
    day_starfall = dict(rare.adjust_table(table, {"starfall_until": 200}, hour=12, now=100))
    assert day_starfall == {"fallen_star": 6, "songstone": 4}
    assert dict(rare.adjust_table(table, {"lore_scholar_until": 200}, hour=22, now=100))["songstone"] == 8
    assert dict(rare.adjust_table(table, {"lore_scholar_until": 50}, hour=22, now=100))["songstone"] == 4


def test_every_rare_and_legendary_event_resolves():
    for key in rare.HANDLERS:
        r = forest_events.resolve_event(key, _sheet())
        assert r["event_key"] == key and r["title"] and r["outcome"]
    rolled = {ek for t in encounter_tables.EVENTS.values() for ek, _ in t}
    assert set(rare.HANDLERS) - set(rare.LEGENDARY) <= rolled
    assert not set(rare.LEGENDARY) & rolled, "legendary events come only from roll_legendary"


def test_legendary_events_happen_only_where_they_live():
    with patch.object(rare.secrets, "randbelow", return_value=0):
        assert rare.roll_legendary("aeridor_ruins") == "the_tablet"
        assert rare.roll_legendary("oakhaven") is None
    with patch.object(rare.secrets, "randbelow", return_value=1):
        assert rare.roll_legendary("aeridor_ruins") is None


def test_event_rewards_name_real_items_and_real_lore():
    from utils.ttrpg.shop import find_item
    for key in rare.HANDLERS:
        for seed in range(4):
            with patch.object(rare.secrets, "randbelow", return_value=seed):
                r = forest_events.resolve_event(key, _sheet())
            if r["item_add"]:
                assert find_item(r["item_add"]), (key, r["item_add"])
            if r["lore_add"]:
                assert r["lore_add"] in lore.LORE_PAGES or r["lore_add"] in lore.LORE_SETS
            if r["condition_add"]:
                assert r["condition_add"] in ce.ONE_FIGHT_BUFFS or r["condition_add"] == "lucky"


def test_a_lore_event_pays_gil_once_its_set_is_complete():
    sheet = _sheet(lore_pages=lore.pages_in_set("road"))
    r = rare.cartographers_cairn(sheet)
    assert r["lore_add"] == "" and r["gil"] == 25


def test_the_lantern_shrine_never_takes_gil_you_do_not_have():
    assert rare.lantern_shrine(_sheet(gil=3))["gil"] == 0
    assert rare.lantern_shrine(_sheet(gil=50))["gil"] == -10


# ─── The codex ────────────────────────────────────────────────────────────────

def test_completing_a_set_pays_once():
    sheet = _sheet(gil=0)
    grants = [lore.grant_page(sheet, "tonberry") for _ in lore.pages_in_set("tonberry")]
    assert [g["set_done"] for g in grants] == [None, None, "tonberry"]
    assert sheet["gil"] == lore.LORE_SETS["tonberry"][2]
    assert "black_pearl" in sheet["inventory"]
    assert lore.grant_page(sheet, "tonberry") is None
    assert lore.grant_page(sheet, "tonberry_1") is None
    assert sheet["gil"] == lore.LORE_SETS["tonberry"][2]


def test_a_page_is_read_only_once_found():
    sheet = _sheet(lore_pages=["aeridor_3"])
    assert "???" in lore.codex_text(sheet)[1]
    assert "gardeners of stone" in lore.codex_text(sheet, "3")[1]
    assert "haven't found" in lore.codex_text(sheet, "1")[1]
    assert "No such page" in lore.codex_text(sheet, "999")[1]


def test_a_found_page_is_shown_on_the_event_card():
    sheet = _sheet()
    result = rare.fallen_courier(sheet)
    rch._apply_forest_event_mechanics(sheet, result)
    assert sheet["lore_pages"] == ["aeridor_1"]
    assert result["lore_grant"]["page"] == "aeridor_1"


# ─── Rare variants ────────────────────────────────────────────────────────────

def test_variants_are_rare_and_never_bosses():
    wolf = {"name": "Wolf", "tier": "easy"}
    with patch.object(rare_spawns.secrets, "randbelow", return_value=0), \
         patch.object(rare_spawns.secrets, "choice", side_effect=lambda xs: xs[0]):
        assert rare_spawns.roll_variant("trade_road", wolf, {}, hour=12) == "gilded"
        assert rare_spawns.roll_variant("trade_road", {"tier": "boss"}, {}) is None
    with patch.object(rare_spawns.secrets, "randbelow", return_value=1):
        assert rare_spawns.roll_variant("trade_road", wolf, {}) is None


def test_the_migration_makes_variants_four_times_as_common():
    seen = []
    with patch.object(rare_spawns.secrets, "randbelow", side_effect=lambda n: seen.append(n) or 1):
        rare_spawns.roll_variant("trade_road", {"tier": "easy"}, {"rare_spawn_boost_until": 200}, now=100)
        rare_spawns.roll_variant("trade_road", {"tier": "easy"}, {"rare_spawn_boost_until": 50}, now=100)
    assert seen == [rare_spawns.RARE_BOOSTED_ONE_IN, rare_spawns.RARE_ONE_IN]


def test_variants_respect_their_place_and_hour():
    assert "pale" not in rare_spawns.eligible_variants("trade_road", hour=12)
    assert "pale" in rare_spawns.eligible_variants("trade_road", hour=23)
    assert "resonant" in rare_spawns.eligible_variants("aeridor_ruins", hour=12)
    assert "whispering" not in rare_spawns.eligible_variants("aeridor_ruins", hour=12)


def test_a_variant_keeps_its_key_and_attack_and_pays_more():
    m = {"key": "wolf", "name": "Wolf", "hp": {"current": 20, "max": 20}, "attack": 4,
         "xp": 30, "gil": 8, "tier": "easy", "desc": "A wolf."}
    rare_spawns.apply_variant(m, "elder")
    assert m["key"] == "wolf" and m["attack"] == 4
    assert m["name"] == "Elder Wolf" and m["hp"] == {"current": 32, "max": 32}
    assert m["xp"] == 90 and m["gil"] == 16


def test_a_lore_variant_carries_a_gem_once_every_page_is_found():
    sheet = _sheet(lore_pages=lore.pages_in_set("silvani"))
    lines, grant = rare_spawns.kill_rewards(sheet, {"rare_variant": "whispering", "tier": "easy"})
    assert grant is None and lines and lines[0].startswith("💎")
    lines, grant = rare_spawns.kill_rewards(_sheet(), {"rare_variant": "whispering", "tier": "easy"})
    assert grant["page"] == "silvani_1"


def test_gem_drops_are_real_items():
    from utils.ttrpg.shop import find_item
    assert all(find_item(k) for k, _ in rare_spawns.GEM_DROPS)


# ─── Noon events ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fn,keys", [
    (noon_events.run_starfall, {"starfall_until"}),
    (noon_events.run_wandering_scholar, {"lore_scholar_until"}),
    (noon_events.run_gilded_migration, {"rare_spawn_boost_until"}),
    (noon_events.run_hollow_sun, {"rare_spawn_boost_until", "encounter_mod", "encounter_mod_expiry"}),
    (noon_events.run_ghost_caravan, {"encounter_mod", "forest_event_bonus", "forest_event_bonus_expiry"}),
])
def test_each_noon_event_sets_its_window_and_announces_itself(monkeypatch, fn, keys):
    from utils.ttrpg import world_state, broadcast
    state = {}

    async def fake_update(mutator):
        mutator(state)
        return True

    monkeypatch.setattr(world_state, "update_world_state", fake_update)
    monkeypatch.setattr(broadcast, "log_world_event", AsyncMock())
    channel = SimpleNamespace(send=AsyncMock())
    asyncio.run(fn(None, channel))
    assert keys <= set(state)
    channel.send.assert_awaited_once()


def test_the_new_noon_events_are_in_the_pool_and_on_the_event_command():
    from utils.core import background_tasks
    from utils.ttrpg import rpg_social_handler
    pool = inspect.getsource(background_tasks)
    command = inspect.getsource(rpg_social_handler._handle_event)
    for name in ("run_starfall", "run_wandering_scholar", "run_gilded_migration",
                 "run_hollow_sun", "run_ghost_caravan"):
        assert f"noon_events.{name}" in pool
        assert f"noon_events.{name}" in command


# ─── End to end: spawn a variant, kill it, hear about it ─────────────────────

def test_a_rare_variant_spawns_drops_its_gem_and_is_announced(monkeypatch):
    from utils.ttrpg import combat_outcomes, outing, session_manager, housing, world_state
    sheet = _sheet(uid="1", hunts_today=0, location="trade_road", level=3,
                   hp={"current": 500, "max": 500}, hunt_date="2999-01-01")
    session = {}

    async def load_sheet(uid):
        return sheet

    async def load_sess(cid):
        return session or None

    async def save_sess(value):
        session.clear()
        session.update(value)

    monkeypatch.setattr(rch, "load", load_sheet)
    monkeypatch.setattr(rch, "save", AsyncMock())
    for mod in (rch, session_manager):
        monkeypatch.setattr(mod, "load_session", load_sess)
        monkeypatch.setattr(mod, "save_session", save_sess)
    monkeypatch.setattr(rch, "check_and_reset_hunts", lambda s: s)
    monkeypatch.setattr(rch, "_recover_pending_combat_outcomes", AsyncMock())
    monkeypatch.setattr(rch, "_attempt_free_forest_event", AsyncMock(return_value=False))
    monkeypatch.setattr(rch, "random_encounter", lambda loc, lvl: "goblin")
    monkeypatch.setattr(rare_spawns, "roll_variant", lambda *a, **k: "gilded")
    monkeypatch.setattr(rare_spawns, "_weighted", lambda pairs: "star_ruby")
    monkeypatch.setattr(rch, "RPGCombatView", MagicMock())
    monkeypatch.setattr(rch, "get_weather", lambda: {}, raising=False)
    monkeypatch.setattr(housing, "load_housing_async", AsyncMock(return_value=None))
    monkeypatch.setattr(world_state, "load_world_state", lambda: dict(world_state.DEFAULT_STATE))
    monkeypatch.setattr(outing, "record_fight", AsyncMock())
    broadcast, logged = AsyncMock(), AsyncMock()
    monkeypatch.setattr(rch, "_broadcast_world_event", broadcast)
    monkeypatch.setattr(rch, "_log_world_event", logged)

    async def fake_commit(sheet_, outcome, *, save_sheet, persist_encounter):
        await save_sheet(sheet_)
        await persist_encounter(outcome)
    monkeypatch.setattr(combat_outcomes, "commit_outcome", fake_commit)

    ctx, msg = _event_ctx()
    asyncio.run(rch._handle_hunt(ctx, msg, None, "", "1", "tess", False))
    spawned = session["monsters"][0]
    assert spawned["name"] == "Gilded Goblin" and spawned["rare_variant"] == "gilded"
    first = msg.channel.send.await_args_list[0].kwargs["embed"].description
    assert "rare sighting" in first.lower()

    spawned["hp"] = {"current": 1, "max": spawned["hp"]["max"]}
    spawned["defense"] = 0
    with patch.object(ce.secrets, "randbelow", return_value=15):
        asyncio.run(rch._handle_attack.__wrapped__(ctx, msg, None, "", "1", "tess", False))

    assert "star_ruby" in sheet["inventory"]
    titles = [c.args[1].title for c in broadcast.await_args_list]
    assert "✨ Rare Hunt" in titles
    assert any("Gilded Goblin" in c.args[0] for c in logged.await_args_list)
