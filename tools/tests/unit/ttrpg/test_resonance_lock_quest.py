"""What Sings Below: the crystal quest, rewritten when Grimstone was cut. It
used to break a lock on the Trade Road to Grimstone; that town and its quest
were removed in May, and the crystals went on promising it to every player
who looked at them. Now the crystals point into the Ironvein Deep, and the
quest ends at its floor-33 guardian."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg.look_targets import LOCATION_LOOK_TARGETS
from utils.ttrpg.monster_registry import MONSTERS
from utils.ttrpg.npc_registry import NPCS
from utils.ttrpg.quest_registry import QUESTS, get_npc_quests
from utils.ttrpg.spine_dungeon import STAIR_GUARDIANS
from utils.ttrpg.world import LOCATION_DATA


def test_every_quest_task_names_something_that_exists():
    """A quest whose task points at a removed place, NPC, monster or look
    target can be taken and never finished."""
    looks = {k for targets in LOCATION_LOOK_TARGETS.values() for k in targets}
    for q in QUESTS.values():
        assert q["npc"] in NPCS, q["id"]
        for t in q["tasks"]:
            verb, _, obj = t.partition("_")
            if verb == "talk":
                assert obj in NPCS, (q["id"], t)
            elif verb == "hunt":
                assert obj in LOCATION_DATA, (q["id"], t)
            elif verb == "kill":
                assert any(obj in k for k in MONSTERS), (q["id"], t)
            elif verb == "look":
                assert obj in looks, (q["id"], t)


def test_the_crystals_point_into_the_deep_not_at_grimstone():
    text = LOCATION_LOOK_TARGETS["aeridor_ruins"]["crystals"]
    assert "Trade Road" not in text and "Ironvein" in text and "hooded figure" in text
    q = QUESTS["resonance_lock"]
    assert q in get_npc_quests("hooded_figure") and q["requirements"]["level"] == 15
    assert STAIR_GUARDIANS[33] == "crystal_dragon" and "kill_crystal_dragon" in q["tasks"]


def test_looking_at_the_crystals_counts_for_the_quest():
    sheet = {"character_name": "Jimjam", "location": "aeridor_ruins", "inventory": [],
             "active_quests": ["resonance_lock"], "quest_progress": {}}
    msg = MagicMock()
    msg.channel.send = AsyncMock()

    async def go():
        with patch.object(core, "load", AsyncMock(return_value=sheet)), \
             patch.object(core, "save", AsyncMock()):
            await core._handle_look(None, msg, None, "at the crystals", "1", "Jimjam", False)
    asyncio.run(go())
    assert sheet["quest_progress"]["resonance_lock"] == ["look_crystals"]


def test_the_floor_33_guardian_counts_for_the_quest(monkeypatch):
    """Kill tasks were only counted in open-world hunts; a stair guardian in
    the Deep is fought in a dungeon round."""
    from utils.ttrpg import rpg_combat_handler as ch
    from utils.ttrpg import combat_engine, spine_dungeon, housing
    sheet = {"user_id": "1", "character_name": "Jimjam", "location": "aeridor_ruins", "level": 15,
             "xp": 0, "gil": 0, "hp": {"current": 100, "max": 100}, "inventory": [], "conditions": [],
             "active_quests": ["resonance_lock"], "quest_progress": {"resonance_lock": ["look_crystals"]},
             "spine_defeated_guards": list(range(1, 33))}
    monster = dict(MONSTERS["crystal_dragon"], key="crystal_dragon")
    state = spine_dungeon.generate_spine_floor(33, 15)
    state["active_combat"] = {"monster": monster, "monster_key": "crystal_dragon", "is_boss": False,
                              "room_key": spine_dungeon._key(*state["player_pos"])}
    saved = {}
    monkeypatch.setattr(ch, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(ch, "save", AsyncMock(side_effect=lambda s: saved.update(sheet=s)))
    monkeypatch.setattr(spine_dungeon, "load_spine_dungeon", AsyncMock(return_value=state))
    monkeypatch.setattr(spine_dungeon, "save_spine_dungeon", AsyncMock())
    monkeypatch.setattr(housing, "load_housing_async", AsyncMock(return_value=None))
    monkeypatch.setattr(combat_engine, "_resolve_combat", lambda s, m, **k: {
        "sheet": s, "monster": m, "exchanges": ["The dragon's last note fades."], "player_hit": True,
        "player_crit": False, "player_fumble": False, "player_damage": 75, "monster_hit": False,
        "monster_damage": 0, "monster_defeated": True, "player_alive": True})
    inter = MagicMock()
    inter.followup.send = AsyncMock()
    inter.channel.send = AsyncMock()
    asyncio.run(ch._dungeon_combat_round(None, inter, "1", "Jimjam", False))
    prog = saved["sheet"]["quest_progress"]["resonance_lock"]
    assert "kill_crystal_dragon" in prog and 33 in saved["sheet"]["spine_defeated_guards"]
    sent = inter.followup.send.await_args.kwargs["embed"].description
    assert "What Sings Below" in sent

