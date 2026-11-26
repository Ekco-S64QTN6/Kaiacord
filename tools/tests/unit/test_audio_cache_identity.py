"""Record audio identity invalidates every path-keyed audio cache."""

import json
import os
from types import SimpleNamespace

import numpy as np
import pytest

from utils.audio import audio_identity, beatgrid, library, mixcheck


def _same_stat_replacement(path):
    before = path.stat()
    path.write_bytes(b"B" * before.st_size)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    after = path.stat()
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns


def test_tick_json_is_rejected_when_audio_at_the_path_is_replaced(tmp_path, monkeypatch):
    monkeypatch.setattr(beatgrid, "TICKS_DIR", tmp_path / "ticks")
    path = tmp_path / "record.mp3"
    path.write_bytes(b"A" * 4096)
    audio_identity.clear_audio_signature_cache()
    signature = library.audio_signature(str(path))
    assert signature

    cache = beatgrid._ticks_path(str(path))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"bpm": 124, "confidence": 0.9,
                                 "audio_signature": signature,
                                 "ticks": [i * 0.48 for i in range(20)]}), encoding="utf-8")
    beatgrid._read_ticks.cache_clear()
    assert len(beatgrid.ticks_for(str(path))) == 20

    _same_stat_replacement(path)
    assert beatgrid.ticks_for(str(path)) is None
    beatgrid._read_ticks.cache_clear()
    audio_identity.clear_audio_signature_cache()


def test_opening_grid_lru_is_keyed_by_audio_identity(tmp_path, monkeypatch):
    path = tmp_path / "record.mp3"
    path.write_bytes(b"A" * 4096)
    audio_identity.clear_audio_signature_cache()
    calls = []
    monkeypatch.setattr(beatgrid, "_window", lambda *_args: np.zeros(32, dtype=np.float32))
    monkeypatch.setattr(beatgrid, "find_grid",
                        lambda *_args: calls.append(1) or beatgrid.Grid(124.0, 0.0, 8.0))
    monkeypatch.setattr(beatgrid, "first_strong_beat", lambda *_args: 0.0)
    monkeypatch.setattr(beatgrid, "TICKS_DIR", tmp_path / "no-ticks")
    beatgrid._grid_for.cache_clear()

    first = beatgrid.grid_for(str(path), 124.0)
    second = beatgrid.grid_for(str(path), 124.0)
    assert first is not None and second is not None and len(calls) == 1

    _same_stat_replacement(path)
    replaced = beatgrid.grid_for(str(path), 124.0)
    assert replaced is not None and len(calls) == 2
    beatgrid._grid_for.cache_clear()
    audio_identity.clear_audio_signature_cache()


def test_mixcheck_envelope_and_level_are_recomputed_for_replaced_audio(tmp_path, monkeypatch):
    path = tmp_path / "record.mp3"
    path.write_bytes(b"A" * 4096)
    monkeypatch.setattr(mixcheck, "ENV_DIR", tmp_path / "env")
    monkeypatch.setattr(mixcheck, "HITS_DIR", tmp_path / "hits")
    decoded = []
    monkeypatch.setattr(mixcheck, "_decode",
                        lambda _path: decoded.append(len(decoded) + 1) or
                        np.array([[float(decoded[-1]), 0.0]], dtype=np.float32))
    monkeypatch.setattr(mixcheck, "kick_envelope",
                        lambda samples: np.full(int(mixcheck.ENV_RATE * 10), samples[0, 0], dtype=np.float32))
    monkeypatch.setattr(mixcheck, "hits_envelope",
                        lambda samples: np.full(int(mixcheck.ENV_RATE * 10), samples[0, 0] / 2, dtype=np.float32))
    mixcheck._MEM.clear()
    mixcheck._levels.clear()
    audio_identity.clear_audio_signature_cache()

    first = mixcheck.envelope(str(path))
    assert first is not None and len(decoded) == 1
    cache = mixcheck._cache_path(str(path))
    with np.load(cache) as saved:
        assert str(saved["signature"].item()) == library.audio_signature(str(path))
        assert np.array_equal(saved["env"].astype(np.float32), first)
    mixcheck._MEM.clear()
    assert np.array_equal(mixcheck.envelope(str(path)), first)
    assert len(decoded) == 1
    level_one = mixcheck.kick_level(str(path))
    assert level_one is not None

    _same_stat_replacement(path)
    second = mixcheck.envelope(str(path))
    assert second is not None and len(decoded) == 2
    assert not np.array_equal(first, second)
    level_two = mixcheck.kick_level(str(path))
    assert level_two is not None and level_two != level_one

    mixcheck._MEM.clear()
    mixcheck._levels.clear()
    audio_identity.clear_audio_signature_cache()


def test_transition_graph_identity_detects_same_mtime_audio_replacement(tmp_path):
    from utils.audio import setlist

    path = tmp_path / "record.mp3"
    path.write_bytes(b"A" * 4096)
    audio_identity.clear_audio_signature_cache()
    record = library.Record(str(path), "Artist", "Record", 124.0, "8A", "House")
    graph = {
        "method": setlist.METHOD,
        "sets_method": setlist.SET_METHOD,
        "records": {str(path): {
            "mtime": path.stat().st_mtime,
            "sig": library.audio_signature(str(path)),
        }},
        "edges": {},
        "checked": {},
    }
    assert not setlist.needs_build(graph, [record])

    _same_stat_replacement(path)
    assert setlist.needs_build(graph, [record])
    audio_identity.clear_audio_signature_cache()


def test_forgetting_changed_record_removes_inbound_and_outbound_graph_evidence():
    from utils.audio import setlist

    graph = {
        "records": {"a": {"sig": "old"}, "b": {"sig": "b"}},
        "edges": {"a": {"b": {"beats": 64}}, "b": {"a": {"beats": 32}}},
        "checked": {"a": ["b"], "b": ["a"]},
    }
    setlist._forget_record(graph, "a")
    assert "a" not in graph["records"]
    assert "a" not in graph["edges"]
    assert graph["edges"]["b"] == {}
    assert graph["checked"]["b"] == []
    assert "a" not in graph["checked"]


def test_tick_maintenance_replaces_cache_when_signature_changes(tmp_path, monkeypatch):
    import runpy
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[3] / "tools" / "maintenance" / "beat_ticks.py"
    namespace = runpy.run_path(str(script), run_name="beat_ticks_test")
    path = tmp_path / "record.mp3"
    path.write_bytes(b"A" * 4096)
    old_signature = library.audio_signature(str(path))
    assert old_signature
    cache_dir = tmp_path / "ticks"
    dest = namespace["cache_path"](str(path), cache_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"audio_signature": old_signature, "ticks": []}), encoding="utf-8")
    _same_stat_replacement(path)
    signature = library.audio_signature(str(path))
    assert signature and signature != old_signature

    analysed = []

    def fake_analyse(record_path, bpm=None, identity=None):
        analysed.append(identity)
        return {"audio_signature": identity, "bpm": 124.0, "confidence": 0.9, "ticks": [i * 0.48 for i in range(20)]}

    namespace["analyse"] = fake_analyse
    monkeypatch.setattr(sys, "argv", ["beat_ticks.py", str(path), "--cache", str(cache_dir)])
    assert namespace["main"]() == 0
    assert analysed == [signature]
    assert json.loads(dest.read_text(encoding="utf-8"))["audio_signature"] == signature

    # A second invocation with an unchanged record reuses the correctly
    # identified tick cache instead of invoking Essentia again.
    assert namespace["main"]() == 0
    assert analysed == [signature]


def test_setlist_worker_side_cache_uses_the_new_audio_identity(tmp_path, monkeypatch):
    from utils.audio import setlist

    path = tmp_path / "record.mp3"
    path.write_bytes(b"A" * 4096)
    audio_identity.clear_audio_signature_cache()
    record = library.Record(str(path), "Artist", "Record", 124.0, "8A", "House")
    created = []

    class FakeSide:
        def __init__(self, rec):
            self.record = rec
            self.ok = True
            created.append(rec.path)

    monkeypatch.setattr(setlist, "_Side", FakeSide)
    original_live, original_ids, original_sides = setlist._W_LIVE, setlist._W_IDENTITIES, setlist._W_SIDES
    setlist._W_LIVE = {str(path): record}
    setlist._W_IDENTITIES = {str(path): library.audio_signature(str(path))}
    setlist._W_SIDES = {}
    try:
        assert setlist._side(str(path)) is not None
        _same_stat_replacement(path)
        setlist._W_IDENTITIES[str(path)] = library.audio_signature(str(path))
        assert setlist._side(str(path)) is not None
        assert created == [str(path), str(path)]
    finally:
        setlist._W_LIVE, setlist._W_IDENTITIES, setlist._W_SIDES = original_live, original_ids, original_sides
        audio_identity.clear_audio_signature_cache()


def test_first_sound_lru_refreshes_after_same_path_audio_replacement(tmp_path, monkeypatch):
    path = tmp_path / "record.mp3"
    path.write_bytes(b"A" * 8192)
    audio_identity.clear_audio_signature_cache()
    beatgrid.first_sound.cache_clear()
    calls = []

    def decode(*_args, **_kwargs):
        calls.append(1)
        samples = np.zeros(8000 * 10, dtype=np.int16)
        first_loud_frame = 20 if len(calls) == 1 else 5
        samples[first_loud_frame * 400:(first_loud_frame + 1) * 400] = 12000
        return SimpleNamespace(stdout=samples.tobytes())

    monkeypatch.setattr(beatgrid.subprocess, "run", decode)
    first = beatgrid.first_sound(str(path))
    assert beatgrid.first_sound(str(path)) == first
    assert len(calls) == 1

    _same_stat_replacement(path)
    replaced = beatgrid.first_sound(str(path))
    assert len(calls) == 2
    assert replaced != first
    beatgrid.first_sound.cache_clear()
    audio_identity.clear_audio_signature_cache()


def test_bass_entry_lru_refreshes_after_same_path_audio_replacement(tmp_path, monkeypatch):
    from scipy import signal

    path = tmp_path / "record.mp3"
    path.write_bytes(b"A" * 8192)
    audio_identity.clear_audio_signature_cache()
    beatgrid.bass_entry.cache_clear()
    decoded = []

    monkeypatch.setattr(beatgrid, "grid_for",
                        lambda *_args: beatgrid.Grid(120.0, 0.0, 8.0, bar_known=True))
    monkeypatch.setattr(beatgrid.subprocess, "run",
                        lambda *_args, **_kwargs: decoded.append(1) or
                        SimpleNamespace(stdout=np.zeros(10 * int(2 * beatgrid.RATE), dtype=np.int16).tobytes()))
    monkeypatch.setattr(signal, "butter", lambda *_args, **_kwargs: None)

    def filtered(_sos, samples):
        if len(decoded) == 1:
            return np.ones(len(samples), dtype=np.float32)
        bar_samples = int(2 * beatgrid.RATE)
        levels = np.ones(10 * bar_samples, dtype=np.float32)
        levels[:4 * bar_samples] = 0.0
        return levels

    monkeypatch.setattr(signal, "sosfilt", filtered)
    first = beatgrid.bass_entry(str(path), 120.0)
    assert first == 0
    assert beatgrid.bass_entry(str(path), 120.0) == first
    assert len(decoded) == 1

    _same_stat_replacement(path)
    replaced = beatgrid.bass_entry(str(path), 120.0)
    assert replaced == 4
    assert len(decoded) == 2
    beatgrid.bass_entry.cache_clear()
    audio_identity.clear_audio_signature_cache()


def test_last_strong_beat_lru_refreshes_after_same_path_audio_replacement(tmp_path, monkeypatch):
    path = tmp_path / "record.mp3"
    path.write_bytes(b"A" * 8192)
    audio_identity.clear_audio_signature_cache()
    beatgrid.last_strong_beat.cache_clear()
    calls = []

    monkeypatch.setattr(beatgrid, "find_grid",
                        lambda *_args: beatgrid.Grid(120.0, 0.0, 8.0))
    def window(_path, _start, seconds):
        calls.append(1)
        duration = 120.0 if len(calls) == 1 else 80.0
        return np.ones(int(duration * beatgrid.HOPS_PER_S), dtype=np.float32)

    monkeypatch.setattr(beatgrid, "_window", window)
    first = beatgrid.last_strong_beat(str(path), 120.0, 120.0, 120.0)
    assert first is not None
    assert beatgrid.last_strong_beat(str(path), 120.0, 120.0, 120.0) == first
    assert len(calls) == 1

    _same_stat_replacement(path)
    replaced = beatgrid.last_strong_beat(str(path), 120.0, 120.0, 120.0)
    assert replaced is not None and replaced < first
    assert len(calls) == 2
    beatgrid.last_strong_beat.cache_clear()
    audio_identity.clear_audio_signature_cache()
