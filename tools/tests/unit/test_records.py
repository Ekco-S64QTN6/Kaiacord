"""!music records: choosing the next record, and mixing one into the next."""
import io
import json
import random
import time

import numpy as np
import pytest

from utils.audio import library
from utils.audio.records import FRAME_BYTES, FRAMES_PER_S, CrossfadeSource, Deck, mix


def rec(name, bpm, key, genre="House"):
    return library.Record(path=f"/music/{name}.mp3", artist="A", title=name, bpm=bpm, key=key, genre=genre)


# ── The crate ─────────────────────────────────────────────────────────

def test_the_catalog_loads_only_records_that_exist(tmp_path):
    real = tmp_path / "a.mp3"
    real.write_bytes(b"x")
    cat = tmp_path / "dj_catalog.json"
    cat.write_text(json.dumps([
        {"filepath": str(real), "bpm": 124, "key": "8A", "genre": "House", "artist": "X", "title": "One"},
        {"filepath": str(tmp_path / "gone.mp3"), "bpm": 120, "key": "8A"},
        {"filepath": str(real), "bpm": "n/a", "key": "13Z"},
        "not a row",
    ]))
    crate = library.load(cat)
    assert [r.title for r in crate] == ["One", "a"]
    assert crate[1].bpm is None and crate[1].key is None
    assert library.load("") == [] and library.load(tmp_path / "missing.json") == []


@pytest.mark.parametrize("a, b, step", [
    ("8A", "8A", 0), ("8A", "9A", 1), ("12A", "1A", 1), ("8A", "8B", 1),
    ("8A", "10A", 2), ("8A", "9B", None), ("8A", "3A", None), ("8A", None, None),
])
def test_moves_round_the_camelot_wheel(a, b, step):
    assert library.key_step(a, b) == step


def test_tempo_matches_count_half_and_double_time():
    assert library.tempo_ratio(124, 120) == pytest.approx(124 / 120)
    assert library.tempo_ratio(174, 88) == pytest.approx(87 / 88)       # half time
    assert library.tempo_ratio(124, 100) is None                         # too far to stretch
    assert library.tempo_ratio(None, 120) is None


def test_the_next_record_fits_the_last():
    current = rec("now", 124, "8A")
    crate = [current, rec("clash", 90, "3B", "Pop"), rec("fits", 125, "9A"), rec("ok", 123, "8B", "Techno")]
    picks = {library.next_record(current, crate, [current.path], random.Random(i)).title for i in range(30)}
    assert "clash" not in picks and "fits" in picks


def test_nothing_recent_is_played_again_while_others_remain():
    crate = [rec(str(i), 124, "8A") for i in range(5)]
    played = [r.path for r in crate[:4]]
    assert library.next_record(crate[0], crate, played).title == "4"


def test_her_opener_follows_her_mood():
    crate = [rec("slow", 90, "8A"), rec("mid", 120, "8A"), rec("fast", 140, "8A")]
    assert library.opener(crate, {"arousal": 0.1}, 14).title == "slow"
    assert library.opener(crate, {"arousal": 0.9}, 14).title == "fast"
    assert library.opener(crate, {"arousal": 0.9}, 3).title == "mid"       # late: no faster than mid


def test_a_request_finds_a_record_by_its_words():
    crate = [rec("Drowning", 176, "8A"), rec("We Are Connected", 130, "2A")]
    assert library.find(crate, "connected").title == "We Are Connected"
    assert library.find(crate, "nothing like it") is None


# ── The mix ──────────────────────────────────────────────────────────

def tone(value: int, seconds: float):
    """A fake decoded record: every sample `value`."""
    frames = int(seconds * FRAMES_PER_S)
    data = np.full(frames * FRAME_BYTES // 2, value, dtype=np.int16).tobytes()
    return lambda path, ratio: io.BytesIO(data)


def level(frame: bytes) -> float:
    return float(np.frombuffer(frame, dtype=np.int16).astype(np.float32).mean())


def wait_for(deck, frames):
    deadline = time.time() + 2
    while time.time() < deadline and len(deck._frames) < frames:
        time.sleep(0.01)


def test_equal_power_crossfade_ends_where_it_should():
    a = np.full(FRAME_BYTES // 2, 1000, dtype=np.int16).tobytes()
    b = np.full(FRAME_BYTES // 2, -1000, dtype=np.int16).tobytes()
    assert level(mix(a, b, 0.0)) == pytest.approx(1000)
    assert level(mix(a, b, 1.0)) == pytest.approx(-1000)


def test_the_next_record_comes_in_under_the_last_and_takes_over():
    first = Deck(rec("one", 124, "8A"), 1.0, 2.0, tone(1000, 2.0))
    second = (rec("two", 124, "8A"), 1.0, 2.0)
    changed = []
    queue = [second]
    src = CrossfadeSource(first, lambda deck: queue.pop() if queue else None, fade_s=0.5,
                          stream_factory=tone(-1000, 2.0),
                          on_change=changed.append)
    wait_for(first, 100)
    deadline = time.time() + 2
    while src._queued is None and time.time() < deadline:
        time.sleep(0.01)
    levels = []
    for _ in range(int(3.5 * FRAMES_PER_S)):
        frame = src.read()
        if frame == b"":
            break
        levels.append(level(frame))
        if src.incoming is not None:
            wait_for(src.incoming, 20)
    assert levels[0] == pytest.approx(1000)
    # The fade passes through a mix, then the second record plays alone.
    assert any(-900 < x < 900 for x in levels)
    assert [r.title for r in changed] == ["two"]
    assert levels[-1] == pytest.approx(-1000) or levels[-1] == 0
    # Two records of two seconds, overlapped by half a second.
    assert len([x for x in levels if x != 0]) <= int(3.6 * FRAMES_PER_S)


def test_the_set_ends_when_nothing_comes_next():
    first = Deck(rec("one", 124, "8A"), 1.0, 0.4, tone(500, 0.4))
    src = CrossfadeSource(first, lambda deck: None, fade_s=0.1)
    wait_for(first, 20)
    frames = [src.read() for _ in range(60)]
    assert b"" in frames


def test_a_quiet_record_is_raised_but_never_past_its_peak(tmp_path):
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    from utils.audio.records import gain_db
    quiet = tmp_path / "quiet.wav"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2", "-af", "volume=-30dB", str(quiet)], check=True)
    g = gain_db(str(quiet))
    assert g == 12.0              # raised toward the target, never more than 12 dB
    assert gain_db(str(tmp_path / "missing.wav")) == 0.0
