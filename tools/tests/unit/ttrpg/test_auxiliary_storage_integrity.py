"""Persistent RPG auxiliary stores must not silently reset damaged JSON."""
import asyncio
import json

import pytest

from utils.ttrpg import fishing_engine, outing


def test_missing_fishing_record_book_initializes_and_updates(tmp_path, monkeypatch):
    path = tmp_path / "fishing_records.json"
    monkeypatch.setattr(fishing_engine, "FISHING_RECORDS_PATH", str(path))

    assert fishing_engine._ensure_records() == {
        "world_records": {}, "species_totals": {}, "angler_totals": {},
    }
    assert fishing_engine.update_world_records("river_trout", 2.5, "Ash", "42") is True

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["world_records"]["river_trout"]["holder"] == "Ash"
    assert saved["species_totals"]["river_trout"] == 1
    assert saved["angler_totals"]["42"] == 1


@pytest.mark.parametrize("payload", ["{broken", "[]", "null", '"not-a-record-book"'])
def test_corrupt_fishing_record_book_is_preserved(tmp_path, monkeypatch, payload):
    path = tmp_path / "fishing_records.json"
    original = payload.encode("utf-8")
    path.write_bytes(original)
    monkeypatch.setattr(fishing_engine, "FISHING_RECORDS_PATH", str(path))

    with pytest.raises(RuntimeError, match="Cannot safely load fishing records"):
        fishing_engine.update_world_records("river_trout", 2.5, "Ash", "42")

    assert path.read_bytes() == original


def test_fishing_record_book_rejects_malformed_nested_collections(tmp_path, monkeypatch):
    path = tmp_path / "fishing_records.json"
    original = json.dumps({
        "world_records": [],
        "species_totals": {},
        "angler_totals": {},
    }).encode("utf-8")
    path.write_bytes(original)
    monkeypatch.setattr(fishing_engine, "FISHING_RECORDS_PATH", str(path))

    with pytest.raises(RuntimeError, match="world_records"):
        fishing_engine.update_world_records("river_trout", 2.5, "Ash", "42")

    assert path.read_bytes() == original


def test_missing_outing_file_is_treated_as_absent_not_corrupt(tmp_path, monkeypatch):
    path = tmp_path / "42.json"
    monkeypatch.setattr(outing, "_path", lambda uid: str(path))
    monkeypatch.setattr(outing, "OUTING_DIR", str(tmp_path))

    result = outing._update_sync("42", lambda data: data["zones"].append("whisperwood_edge"))

    assert result["zones"] == ["whisperwood_edge"]
    assert json.loads(path.read_text(encoding="utf-8"))["zones"] == ["whisperwood_edge"]


@pytest.mark.parametrize("payload", ["{broken", "[]", "null", '"not-an-outing"'])
def test_corrupt_open_outing_is_preserved_on_update(tmp_path, monkeypatch, payload):
    path = tmp_path / "42.json"
    original = payload.encode("utf-8")
    path.write_bytes(original)
    monkeypatch.setattr(outing, "_path", lambda uid: str(path))
    monkeypatch.setattr(outing, "OUTING_DIR", str(tmp_path))

    with pytest.raises(RuntimeError, match="Cannot safely load RPG outing record"):
        outing._update_sync("42", lambda data: data["zones"].append("whisperwood_edge"))

    assert path.read_bytes() == original


def test_corrupt_daily_digest_is_preserved_on_merge(tmp_path, monkeypatch):
    day = "2026-11-04"
    path = tmp_path / f"{day}_42.json"
    original = b"{broken daily digest"
    path.write_bytes(original)
    monkeypatch.setattr(outing, "_daily_path", lambda uid, value: str(path))
    monkeypatch.setattr(outing, "DAILY_DIR", str(tmp_path))

    with pytest.raises(RuntimeError, match="Cannot safely load RPG outing record"):
        outing._merge_daily_sync({
            "uid": "42",
            "outing_id": "42:test",
            "day": day,
            "started": 1,
            "ended": 2,
            "zones": ["whisperwood_edge"],
            "fights": [],
            "events": [],
            "fight_count": 1,
            "wins": 1,
            "losses": 0,
            "xp": 10,
            "gil": 2,
            "loot": [],
            "levels": [],
        })

    assert path.read_bytes() == original


def test_midnight_finalizer_preserves_bad_digest_and_continues(tmp_path, monkeypatch):
    day = "2026-11-04"
    bad = tmp_path / f"{day}_42.json"
    original = b"not json"
    bad.write_bytes(original)
    good = tmp_path / f"{day}_99.json"
    good.write_text(json.dumps({
        "uid": "99", "day": day, "zones": [], "fights": [],
        "events": [], "fight_count": 0, "wins": 0, "losses": 0, "xp": 0,
        "gil": 0, "loot": [], "levels": [], "notes": {}, "trips": 1,
        "trip_ids": ["99:test"], "duration_seconds": 1,
    }), encoding="utf-8")
    untold_dir = tmp_path / "untold"

    monkeypatch.setattr(outing, "DAILY_DIR", str(tmp_path))
    monkeypatch.setattr(outing, "UNTOLD_DIR", str(untold_dir))

    ready = outing._finalize_daily_sync(day)

    assert bad.read_bytes() == original
    assert bad.exists()
    assert ready == [str(untold_dir / f"daily_{day}_99.json")]
    assert (untold_dir / f"daily_{day}_99.json").exists()


def test_malformed_untold_record_is_preserved_and_not_posted(tmp_path, monkeypatch):
    path = tmp_path / "daily_2026-11-04_42.json"
    original = b"[]"
    path.write_bytes(original)
    monkeypatch.setattr(outing, "_rpg_channel", lambda *a: None)

    assert asyncio.run(outing.tell(None, str(path))) is False
    assert path.read_bytes() == original



def test_outing_rejects_structurally_damaged_nested_values(tmp_path, monkeypatch):
    path = tmp_path / "42.json"
    original = json.dumps({
        "uid": "42",
        "outing_id": "42:test",
        "day": "2026-11-04",
        "started": 1,
        "zones": ["whisperwood_edge"],
        "fights": ["not a fight object"],
        "events": [],
        "fight_count": 1,
        "wins": 1,
        "losses": 0,
        "xp": 10,
        "gil": 2,
        "loot": [],
        "levels": [],
    }).encode("utf-8")
    path.write_bytes(original)
    monkeypatch.setattr(outing, "_path", lambda uid: str(path))

    with pytest.raises(RuntimeError, match="fights entries"):
        outing._update_sync("42", lambda data: data["zones"].append("trade_road"))

    assert path.read_bytes() == original


def test_midnight_open_outing_is_retained_when_daily_digest_is_corrupt(tmp_path, monkeypatch):
    day = "2026-11-04"
    outing_dir = tmp_path / "outings"
    daily_dir = outing_dir / "daily"
    outing_dir.mkdir()
    daily_dir.mkdir()
    open_path = outing_dir / "42.json"
    open_record = {
        "uid": "42", "outing_id": "42:test", "day": day, "started": 1,
        "zones": ["whisperwood_edge"], "fights": [{"monster": "cave bat"}], "events": [],
        "fight_count": 1, "wins": 1, "losses": 0, "xp": 10, "gil": 2,
        "loot": [], "levels": [],
    }
    open_bytes = json.dumps(open_record).encode("utf-8")
    open_path.write_bytes(open_bytes)
    daily_path = daily_dir / f"{day}_42.json"
    daily_bytes = b"broken daily json"
    daily_path.write_bytes(daily_bytes)

    monkeypatch.setattr(outing, "OUTING_DIR", str(outing_dir))
    monkeypatch.setattr(outing, "DAILY_DIR", str(daily_dir))

    assert outing._take_open_outings_sync(day) == 0
    assert open_path.read_bytes() == open_bytes
    assert daily_path.read_bytes() == daily_bytes



def test_missing_world_event_log_initializes_and_serializes_concurrent_writes(tmp_path, monkeypatch):
    from utils.ttrpg import broadcast
    monkeypatch.chdir(tmp_path)

    async def go():
        await asyncio.gather(*(broadcast.log_world_event(f"event-{i}") for i in range(12)))
    asyncio.run(go())

    events = json.loads((tmp_path / "memory" / "ttrpg" / "world_events.json").read_text(encoding="utf-8"))
    assert len(events) == 10
    assert set(events) == {f"event-{i}" for i in range(12)} - {"event-0", "event-1"}


@pytest.mark.parametrize("payload", ["{broken", "[]", "null", '{"event": "not a list"}'])
def test_corrupt_world_event_log_is_preserved(tmp_path, monkeypatch, payload):
    from utils.ttrpg import broadcast
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "memory" / "ttrpg" / "world_events.json"
    path.parent.mkdir(parents=True)
    original = payload.encode("utf-8")
    path.write_bytes(original)

    with pytest.raises(RuntimeError, match="Cannot safely load RPG world event log"):
        asyncio.run(broadcast.log_world_event("new event"))

    assert path.read_bytes() == original
