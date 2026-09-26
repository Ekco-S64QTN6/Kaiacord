"""A player's Spine floors live in one container file. Saves that overlapped
each read it and wrote it back, and a floor could be lost."""
import asyncio
import json

from utils.ttrpg import spine_dungeon as sd


def test_concurrent_saves_keep_every_floor(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, "SPINE_DIR", str(tmp_path))
    async def go():
        await asyncio.gather(*(sd.save_spine_dungeon("1", {"floor_num": n, "active": True, "rooms": {}})
                               for n in range(1, 11)))
    asyncio.run(go())
    floors = json.loads((tmp_path / "1_spine.json").read_text())["floors"]
    assert sorted(map(int, floors)) == list(range(1, 11))
    assert not list(tmp_path.glob("*.tmp"))


def test_a_saved_floor_loads_back(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, "SPINE_DIR", str(tmp_path))
    state = {"floor_num": 3, "active": True, "rooms": {}}
    asyncio.run(sd.save_spine_dungeon("1", state))
    back = asyncio.run(sd.load_spine_dungeon("1"))
    assert back["floor_num"] == 3 and back["active"] is True
