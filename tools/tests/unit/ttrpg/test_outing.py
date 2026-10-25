"""Trips out are told once, when they end (utils/ttrpg/outing.py), and a Spine
death keeps the player's progress. The dungeon tests drive the real
`_dungeon_combat_round`; only combat resolution, broadcasts and Discord are faked."""
import asyncio
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.ttrpg import outing


def _round(monster="cave bat", *, dealt=4, taken=1, won=False, alive=True, crit=False):
    return {"uid": "u1", "monster_name": monster, "monster_desc": "a leathery thing",
            "player_hit": True, "player_crit": crit, "player_fumble": False, "player_damage": dealt,
            "monster_hit": bool(taken), "monster_damage": taken, "monster_defeated": won,
            "player_alive": alive, "player_hp_after": 9, "player_hp_max": 12}


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    """Every RPG store is a path relative to the working directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_fights_and_events_accumulate_per_player(in_tmp):
    async def go():
        await outing.record_fight("u1", "whisperwood_edge", [_round(), _round(won=True)], xp=10, gil=4,
                                  loot=["Bat Wing"])
        await outing.record_fight("u1", "whisperwood_deep", [_round("wolf", won=True)], xp=20, gil=6)
        await outing.record_event("u1", "whisperwood_deep", "Riddle", "an old man posed a riddle")
        await outing.record_fight("u2", "trade_road", [_round("bandit", won=True)], xp=5)
        return await outing.peek("u1"), await outing.peek("u2")
    one, two = asyncio.run(go())
    assert one["zones"] == ["whisperwood_edge", "whisperwood_deep"]
    assert (one["fight_count"], one["wins"], one["xp"], one["gil"]) == (2, 2, 30, 10)
    assert one["loot"] == ["Bat Wing"] and one["events"][0]["title"] == "Riddle"
    assert one["fights"][0]["rounds"] == 2 and one["fights"][0]["dealt"] == 8
    assert two["fight_count"] == 1 and two["zones"] == ["trade_road"]     # their own trip


def test_closing_with_nothing_recorded_tells_nothing(in_tmp):
    assert asyncio.run(outing.close(None, None, "nobody", "x", {}, reason="came back")) is False


def _fake_model(monkeypatch):
    from utils.infrastructure.gpu import gpu_manager

    async def guard(model_name, coro, task_id=None, priority=None):
        return await (coro() if callable(coro) else coro)
    monkeypatch.setattr(gpu_manager.gpu_memory_manager, "run_with_gpu_guard", guard)
    import utils.social.kaia_social_responder as responder
    monkeypatch.setattr(responder, "load_persona_async", AsyncMock(return_value="persona"))


def test_closing_narrates_once_in_the_background_and_clears_the_record(in_tmp, monkeypatch):
    from utils.infrastructure.gpu import gpu_manager
    from utils.ttrpg import rpg_prompt_builder

    _fake_model(monkeypatch)
    prompts = []
    real_builder = rpg_prompt_builder.build_outing_summary_prompt
    monkeypatch.setattr(rpg_prompt_builder, "build_outing_summary_prompt",
                        lambda *a: prompts.append(real_builder(*a)) or prompts[-1])

    chat = AsyncMock(return_value={"message": {"content": "the bats kept coming until the light failed."}})
    ctx = SimpleNamespace(ollama_client=SimpleNamespace(chat=chat))
    channel = SimpleNamespace(send=AsyncMock())
    sheet = {"user_id": "u1", "character_name": "Ash", "class": "Ranger", "level": 3}

    async def go():
        for _ in range(3):                                         # three bats, one round each
            await outing.record_fight("u1", "whisperwood_edge", [_round(won=True)], xp=10)
        assert await outing.close(ctx, channel, "u1", "Ash", sheet, reason="came back to Oakhaven") is True
        assert await outing.peek("u1") is None                    # cleared at once
        for _ in range(50):                                        # the narration runs in the background
            if channel.send.await_count and not outing._telling:
                break
            await asyncio.sleep(0.01)
    asyncio.run(go())

    assert chat.await_count == 1                                   # one call for the whole trip
    embed = channel.send.await_args.kwargs["embed"]
    assert "the bats kept coming" in embed.description
    fields = {f.name: f.value for f in embed.fields}
    assert "ASH" in embed.title and "Whisperwood" in embed.title
    assert fields["⚔️ Fights"].startswith("3 won") and "+30 XP" in fields["✨ Earned"]
    assert "cave bat: fought 3x, won 3" in prompts[0] and "came back to Oakhaven" in prompts[0]
    assert "Ranger Lv.3" in embed.footer.text
    assert os.listdir(outing.UNTOLD_DIR) == []                     # told, so no longer waiting


class _Bot:
    """A bot whose guild has #aethelgard, and the channel the trip was played in."""
    def __init__(self, fail=False):
        async def send(**kw):
            if fail:
                raise RuntimeError("discord said no")
            self.posted.append(kw["embed"])
            return SimpleNamespace(id=1)
        self.posted = []
        self.aethelgard = SimpleNamespace(name="aethelgard", id=7, send=send)

    def get_all_channels(self):
        return [SimpleNamespace(name="general", id=3), self.aethelgard]

    def get_channel(self, cid):
        return None


async def _hunt_and_return(ctx, channel, uid="u1"):
    await outing.record_fight(uid, "whisperwood_edge", [_round(won=True)], xp=10)
    await outing.close(ctx, channel, uid, "Ash", {"user_id": uid, "character_name": "Ash", "level": 3},
                       reason="came back to Oakhaven")
    for _ in range(100):
        await asyncio.sleep(0.01)
        if not outing._telling:
            break


def test_the_trip_is_posted_to_aethelgard_not_the_play_channel(in_tmp, monkeypatch):
    _fake_model(monkeypatch)
    bot = _Bot()
    ctx = SimpleNamespace(bot=bot, ollama_client=SimpleNamespace(
        chat=AsyncMock(return_value={"message": {"content": "the edge was quiet."}})))
    play = SimpleNamespace(id=99, send=AsyncMock())
    asyncio.run(_hunt_and_return(ctx, play))
    assert len(bot.posted) == 1 and "the edge was quiet" in bot.posted[0].description
    play.send.assert_not_awaited()                                 # a button's follow-up is not the channel


def test_an_unposted_trip_waits_and_is_told_at_the_next_boot_without_rewriting(in_tmp, monkeypatch):
    _fake_model(monkeypatch)
    chat = AsyncMock(return_value={"message": {"content": "the edge was quiet."}})
    ctx = SimpleNamespace(bot=_Bot(fail=True), ollama_client=SimpleNamespace(chat=chat))
    asyncio.run(_hunt_and_return(ctx, None))
    [waiting] = os.listdir(outing.UNTOLD_DIR)                       # the post failed: kept, text and all
    assert json.load(open(os.path.join(outing.UNTOLD_DIR, waiting)))["text"] == "the edge was quiet."

    ctx.bot = _Bot()                                               # the restart
    assert asyncio.run(outing.tell_untold(ctx)) == 1
    assert chat.await_count == 1                                   # posted what was written, not a new one
    assert len(ctx.bot.posted) == 1 and os.listdir(outing.UNTOLD_DIR) == []


def test_a_failed_narration_is_kept_for_the_next_boot(in_tmp, monkeypatch):
    _fake_model(monkeypatch)
    ctx = SimpleNamespace(bot=_Bot(), ollama_client=SimpleNamespace(chat=AsyncMock(side_effect=TimeoutError())))
    asyncio.run(_hunt_and_return(ctx, None))
    assert len(os.listdir(outing.UNTOLD_DIR)) == 1 and not ctx.bot.posted
    ctx.ollama_client.chat = AsyncMock(return_value={"message": {"content": "it came back to her."}})
    assert asyncio.run(outing.tell_untold(ctx)) == 1


def test_outings_written_by_the_suite_never_reach_the_live_store():
    assert outing.OUTING_DIR.endswith(".test") and outing.UNTOLD_DIR.startswith(outing.OUTING_DIR)


def test_a_knockout_is_not_told_as_a_clean_victory():
    from utils.ttrpg.rpg_prompt_builder import build_outing_summary_prompt
    data = {"zones": ["whisperwood_deep"], "fight_count": 2, "wins": 1, "losses": 1, "loot": [],
            "levels": [], "events": [],
            "fights": [outing.summarize_rounds([_round(won=True)]),
                       outing.summarize_rounds([_round("troll", taken=12, alive=False)])]}
    prompt = build_outing_summary_prompt({"character_name": "Ash"}, data, "was knocked out")
    assert "WAS KNOCKED OUT" in prompt and "HARDEST FIGHT: troll" in prompt


def test_only_leaving_the_hunting_grounds_ends_a_trip():
    assert outing.is_hunting_ground("whisperwood_edge") and outing.is_hunting_ground("whisperwood_deep")
    assert not outing.is_hunting_ground("oakhaven") and not outing.is_hunting_ground("shrine")


# ── the Spine keeps its progress on death ─────────────────────────────────────

async def _dungeon_death(monkeypatch, *, spine: bool):
    from utils.ttrpg import character_manager as cm
    from utils.ttrpg import rpg_combat_handler as rch
    from utils.ttrpg import spine_dungeon as sd
    from utils.ttrpg import combat_engine

    sheet = await cm.create("u1", "Ash", "Ash", "Human", "Warrior",
                            {"str": 14, "dex": 12, "con": 12, "int": 10, "wis": 10, "cha": 10})
    sheet["location"] = "aeridor_ruins" if spine else "whisperwood_deep"
    sheet["spine_defeated_guards"] = list(range(1, 10))           # floors 1-9 beaten: lift to 10
    await cm.save(sheet)

    # A regular dungeon save that a Spine death must not touch.
    os.makedirs("memory/ttrpg/dungeons", exist_ok=True)
    with open("memory/ttrpg/dungeons/u1.json", "w") as fh:
        json.dump({"theme_name": "a regular run", "rooms": {}, "active_combat": None}, fh)

    monster = {"name": "Slag Horror", "hp": {"current": 30, "max": 30}, "xp": 50, "gil": 20}
    if spine:
        state = sd.generate_spine_floor(10, 1)
        room_key = next(iter(state["rooms"]))
        state["active_combat"] = {"monster": monster, "monster_key": "slag_horror", "room_key": room_key}
        state["active"] = True
        await sd.save_spine_dungeon("u1", state)
    else:
        from utils.ttrpg import dungeon as dg
        with open("memory/ttrpg/dungeons/u1.json", "w") as fh:
            json.dump({"theme_name": "the Barrow", "rooms": {"0,0": {"cleared": False}},
                       "active_combat": {"monster": monster, "monster_key": "wight", "room_key": "0,0"}}, fh)

    def defeat(sheet_in, monster_in, **_kw):
        sheet_in["hp"]["current"] = 0
        return {"sheet": sheet_in, "monster": monster_in, "exchanges": ["the slag closed over them."],
                "player_hit": False, "player_crit": False, "player_fumble": False, "player_damage": 0,
                "monster_hit": True, "monster_damage": 99, "monster_defeated": False,
                "player_alive": False, "monster_alive": True, "spent_buffs": ()}
    monkeypatch.setattr(combat_engine, "_resolve_combat", defeat)
    monkeypatch.setattr(rch, "_log_world_event", AsyncMock())
    monkeypatch.setattr(rch, "_broadcast_world_event", AsyncMock())
    monkeypatch.setattr(rch, "_make_status_view", lambda *a, **k: None)
    closed = []
    monkeypatch.setattr(outing, "close", AsyncMock(side_effect=lambda *a, **k: closed.append(k["reason"])))

    channel = SimpleNamespace(id=77, send=AsyncMock())
    interaction = SimpleNamespace(channel=channel, followup=SimpleNamespace(send=AsyncMock()))
    await rch._dungeon_combat_round(None, interaction, "u1", "Ash", False)
    return closed


def test_a_spine_death_keeps_progress_and_leaves_the_regular_dungeon_alone(in_tmp, monkeypatch):
    closed = asyncio.run(_dungeon_death(monkeypatch, spine=True))

    from utils.ttrpg import character_manager as cm
    from utils.ttrpg import spine_dungeon as sd
    sheet = asyncio.run(cm.load("u1"))
    assert sheet["location"] == "shrine" and sheet["deaths"] == 1
    assert sheet["spine_defeated_guards"] == list(range(1, 10))   # the lift still reaches floor 10
    assert sd.deepest_reached(sheet) == 10
    assert os.path.exists("memory/ttrpg/dungeons/u1.json")         # the regular save survived
    container = json.load(open("memory/ttrpg/dungeons/u1_spine.json"))
    assert container["active"] is False                            # the run ended...
    assert "active_combat" not in container["floors"]["10"]        # ...and not mid-fight
    assert closed and "fell" in closed[0]


def test_a_regular_dungeon_death_still_ends_that_run(in_tmp, monkeypatch):
    closed = asyncio.run(_dungeon_death(monkeypatch, spine=False))
    assert not os.path.exists("memory/ttrpg/dungeons/u1.json")
    assert closed and "fell" in closed[0]


def test_quests_escapes_and_potions_join_the_trip_and_its_box(in_tmp):
    async def go():
        await outing.note("u1", "used", "Healing Herb")             # in town: no trip, not recorded
        assert await outing.peek("u1") is None
        await outing.note("u1", "quest", "Wolf Trouble", start=True)  # a kill's quest progress opens it
        await outing.record_fight("u1", "whisperwood_deep", [_round("wolf", won=True)], xp=20)
        await outing.note("u1", "fled", "Thornback Boar")
        await outing.note("u1", "used", "Healing Herb")
        await outing.note("u1", "used", "Healing Herb")
        await outing.note("u1", "quest_done", "Wolf Trouble", start=True)
        return await outing.peek("u1")
    data = asyncio.run(go())
    data.update(text="the wolves came at dusk.", reason="came back to Oakhaven",
                sheet={"character_name": "Ash", "class": "Ranger", "level": 3, "hp": {"current": 9, "max": 12}})
    fields = {f.name: f.value for f in outing._embed(data).fields}
    assert fields["📜 Quests"] == "✅ Wolf Trouble"                 # finished, not also "moved on"
    assert "🏃 fled a Thornback Boar" in fields["🗺️ Along the way"]
    assert "🧪 Healing Herb ×2" in fields["🗺️ Along the way"]
    assert "```ansi" in fields["❤️ HP home"]

    from utils.ttrpg.rpg_prompt_builder import build_outing_summary_prompt
    prompt = build_outing_summary_prompt(data["sheet"], data, data["reason"])
    assert "QUEST FINISHED: Wolf Trouble" in prompt and "QUEST MOVED ON" not in prompt
    assert "RAN FROM: Thornback Boar" in prompt and "DRANK OR USED: Healing Herb x2" in prompt


def test_what_did_not_happen_is_neither_boxed_nor_prompted():
    from utils.ttrpg.rpg_prompt_builder import build_outing_summary_prompt
    data = {"zones": ["whisperwood_edge"], "fight_count": 1, "wins": 1, "losses": 0, "xp": 5, "gil": 0,
            "loot": [], "levels": [], "events": [], "notes": {},
            "fights": [outing.summarize_rounds([_round(won=True)])],
            "text": "a bat, and home.", "reason": "came back to Oakhaven", "sheet": {"character_name": "Ash"}}
    names = {f.name for f in outing._embed(data).fields}
    assert names == {"⚔️ Fights", "✨ Earned", "🐾 Met"}
    prompt = build_outing_summary_prompt(data["sheet"], data, data["reason"])
    for absent in ("EVENTS", "LOOT", "QUEST", "RAN FROM", "DRANK", "LEVELLED", "none", "nothing of note"):
        assert absent not in prompt.split("YOUR TASK")[0], absent
