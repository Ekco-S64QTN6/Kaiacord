"""The records caches carried from the old head/tail fingerprint to the
complete-payload identity, only where the old evidence still holds."""
import json
import os
from pathlib import Path

import pytest

from tools.maintenance import migrate_record_identity as M
from utils.audio import beatgrid
from utils.audio.audio_identity import audio_signature, clear_audio_signature_cache


def _record(tmp_path, name, payload=b"\xff\xfb" * 400_000):
    path = tmp_path / f"{name}.mp3"
    path.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x05tags." + payload)
    clear_audio_signature_cache(str(path))
    return str(path)


def test_graph_keeps_its_measurements_where_the_old_fingerprint_still_matches(tmp_path):
    same = _record(tmp_path, "same")
    edited = _record(tmp_path, "edited")
    old_edited = M.legacy_signature(edited)
    Path(edited).write_bytes(Path(edited).read_bytes()[:-10] + b"0123456789")
    clear_audio_signature_cache(edited)
    g = {"records": {
        same: {"mtime": 1.0, "sig": M.legacy_signature(same)},
        edited: {"mtime": 1.0, "sig": old_edited},
        str(tmp_path / "gone.mp3"): {"sig": "0" * 20},
    }}

    counts = M.migrate_graph(g)

    assert counts == {"kept": 0, "upgraded": 1, "changed": 1, "missing": 1}
    assert g["records"][same]["sig"] == audio_signature(same)
    assert g["records"][edited]["sig"] == old_edited      # remeasured by the build
    assert M.migrate_graph(g)["kept"] == 1                # idempotent


def test_ticks_are_adopted_only_when_they_are_evidently_this_records(tmp_path, monkeypatch):
    monkeypatch.setattr(beatgrid, "TICKS_DIR", tmp_path / "ticks")
    (tmp_path / "ticks").mkdir()
    ticks = [round(0.5 * i, 4) for i in range(40)]

    def legacy_ticks(path, bpm, *, record_newer):
        cache = beatgrid._ticks_path(path)
        cache.write_text(json.dumps({"bpm": bpm, "confidence": 3.1, "ticks": ticks}))
        if record_newer:                       # retagged after its beats were found
            os.utime(cache, (1_000_000, 1_000_000))
        return cache

    retagged = _record(tmp_path, "retagged")
    replaced = _record(tmp_path, "replaced")
    written_after = _record(tmp_path, "written_after")
    a = legacy_ticks(retagged, 120.4, record_newer=True)
    b = legacy_ticks(replaced, 87.0, record_newer=True)
    c = legacy_ticks(written_after, 87.0, record_newer=False)

    dry = M.migrate_ticks({retagged: 120.0, replaced: 120.0, written_after: 120.0}, apply=False)
    assert dry == {"kept": 0, "upgraded": 2, "unverified": 1, "unreadable": 0}
    assert "audio_signature" not in json.loads(a.read_text())

    M.migrate_ticks({retagged: 120.0, replaced: 120.0, written_after: 120.0}, apply=True)
    for cache, path in ((a, retagged), (c, written_after)):
        data = json.loads(cache.read_text())
        assert data["audio_signature"] == audio_signature(path)
        assert data["target_bpm"] == 120.0 and data["alternate_ticks"] is None
    assert "audio_signature" not in json.loads(b.read_text())

    # The runtime reads an adopted file as it read the legacy one.
    assert beatgrid.ticks_available(retagged, 120.0)
    assert list(beatgrid.ticks_for(retagged, 120.0)) == pytest.approx(ticks)
    assert not beatgrid.ticks_available(replaced, 120.0)
