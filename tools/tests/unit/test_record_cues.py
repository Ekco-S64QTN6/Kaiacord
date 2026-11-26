"""Persistent DJ hot/memory cue banks: identity, durability and concurrency."""
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from utils.audio import audio_identity, record_cues

@pytest.fixture
def cue_store(tmp_path, monkeypatch):
    path = tmp_path / "memory" / "records" / "cues.json"
    monkeypatch.setattr(record_cues, "telemetry_path", lambda _path: str(path))
    identities = {
        "original-name.mp3": "audio-v1:stable-payload",
        "renamed-after-tags.mp3": "audio-v1:stable-payload",
        "different-track.mp3": "audio-v1:other-payload",
    }
    monkeypatch.setattr(audio_identity, "audio_signature", lambda value: identities.get(Path(value).name))
    record_cues.clear_cache()
    yield path
    record_cues.clear_cache()

def record(name):
    return SimpleNamespace(path=f"/music/{name}")

def test_cue_banks_are_persistent_and_follow_audio_identity_across_rename(cue_store):
    original = record("original-name.mp3")
    renamed = record("renamed-after-tags.mp3")
    other = record("different-track.mp3")
    assert record_cues.set_hot(original, 0, 12.375)
    assert record_cues.set_hot(original, 7, 188.0)
    assert record_cues.set_memory(original, 42.5)
    assert record_cues.load(renamed) == {"memory": 42.5, "hot": [12.375, None, None, None, None, None, None, 188.0]}
    assert record_cues.load(other) == record_cues._empty()
    persisted = json.loads(cue_store.read_text(encoding="utf-8"))
    assert persisted["version"] == record_cues.VERSION
    assert list(persisted["records"]) == ["audio-v1:stable-payload"]

def test_cue_bank_load_returns_defensive_hot_pad_copies(cue_store):
    source = record("original-name.mp3")
    assert record_cues.set_hot(source, 2, 9.0)
    loaded = record_cues.load(source)
    loaded["hot"][2] = 999.0
    assert record_cues.load(source)["hot"][2] == 9.0

@pytest.mark.parametrize("index", [-1, 8, True, 1.5, "1"])
def test_hot_cue_indices_are_strictly_bounded(cue_store, index):
    assert not record_cues.set_hot(record("original-name.mp3"), index, 1.0)
    assert not record_cues.clear_hot(record("original-name.mp3"), index)

@pytest.mark.parametrize("position", [-1.0, float("nan"), float("inf"), True, "2", 10**500])
def test_cue_positions_reject_invalid_or_unrepresentable_values(cue_store, position):
    assert not record_cues.set_hot(record("original-name.mp3"), 0, position)
    assert not record_cues.set_memory(record("original-name.mp3"), position)

def test_mutation_preserves_a_corrupt_cue_store_before_replacing_it(cue_store):
    cue_store.parent.mkdir(parents=True)
    cue_store.write_text("{not valid json", encoding="utf-8")
    assert record_cues.set_hot(record("original-name.mp3"), 0, 7.25)
    backups = list(cue_store.parent.glob("cues.json.unreadable-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{not valid json"
    assert record_cues.load(record("original-name.mp3"))["hot"][0] == 7.25

def test_concurrent_hot_pad_writes_do_not_lose_other_updates(cue_store):
    source = record("original-name.mp3")
    results = []
    workers = [threading.Thread(target=lambda i=i: results.append(record_cues.set_hot(source, i, i + 0.5)))
               for i in range(record_cues.HOT_CUE_COUNT)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=3)
    assert all(not worker.is_alive() for worker in workers)
    assert results == [True] * record_cues.HOT_CUE_COUNT
    assert record_cues.load(source)["hot"] == [i + 0.5 for i in range(record_cues.HOT_CUE_COUNT)]

def test_unknown_audio_identity_is_not_written(cue_store):
    missing = record("missing.mp3")
    assert record_cues.record_key(missing) is None
    assert not record_cues.set_memory(missing, 5.0)
    assert not cue_store.exists()
