"""!beacons and the overnight log."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import numpy as np
import pytest

from utils.radio import beacons, overnight


def test_the_beacon_schedule_is_arithmetic():
    t0 = datetime(2026, 9, 24, 0, 0, 0, tzinfo=timezone.utc)          # a cycle boundary
    assert beacons.BEACONS[beacons.on_air(t0, 0)][0] == "4U1UN"        # 14.100 opens with 4U1UN
    assert beacons.BEACONS[beacons.on_air(t0 + timedelta(seconds=10), 1)][0] == "4U1UN"   # 18.110 one slot later
    assert beacons.BEACONS[beacons.on_air(t0 + timedelta(seconds=175), 0)][0] == "YV5B"   # last of 18
    assert len(beacons.now_on_air(t0)) == 5


def test_a_strong_slot_is_heard_and_quiet_ones_are_not():
    """Readings are the receiver's S-meter (dBm), ~6 a second, whole-second stamps."""
    start = datetime(2026, 9, 24, 0, 0, 0, tzinfo=timezone.utc)
    rng = np.random.default_rng(0)
    readings = []
    for sec in range(beacons.CYCLE_S):
        slot = sec // 10
        base = -120.0 + (18.0 if slot in (0, 4) else 0.0)      # 4U1UN and ZL6B come through
        for _ in range(6):
            readings.append((start + timedelta(seconds=sec), base + rng.normal(0, 1.5)))
    heard = {h.call for h in beacons.judge(beacons.slot_levels(readings)) if h.heard}
    assert heard == {"4U1UN", "ZL6B"}


def test_a_short_recording_is_an_error_not_a_verdict():
    from utils.radio.fetch import FeedError
    with pytest.raises(FeedError):
        beacons.judge({0: 1.0, 1: 1.0})


def test_the_overnight_log_may_not_invent_numbers():
    facts = ["asteroid 2026 SC will pass Earth at 1.7 lunar distances (25 Sep 13:47 UTC)"]
    assert overnight.invented_numbers("2026 sc will pass at 1.7 lunar distances, 13:47 utc", facts) == set()
    assert overnight.invented_numbers("it passed at 3.2 lunar distances", facts) == {"3.2"}
    # the same number written another way is not an invention
    facts = ["you recorded E11 at 08:05 UTC", "an E-6B was broadcasting at 1,250 ft"]
    assert overnight.invented_numbers("e11 at 8:05, and a plane at 1250 ft", facts) == set()


def test_the_overnight_log_is_due_once_a_morning():
    from utils.radio import fetch
    fetch.cache_path(overnight.STATE).unlink(missing_ok=True)
    morning = datetime(2026, 9, 24, 8, 45)
    assert overnight.due(morning, "08:30")
    assert not overnight.due(datetime(2026, 9, 24, 7, 0), "08:30")
    fetch.write_cache(overnight.STATE, {"last_posted": morning.timestamp()})
    assert not overnight.due(morning + timedelta(minutes=30), "08:30")
    fetch.cache_path(overnight.STATE).unlink(missing_ok=True)


def test_overnight_is_an_unprompted_source_with_its_own_label():
    from utils.core import unprompted
    assert "overnight" in unprompted.SOURCES
    assert unprompted.KIND_LABELS["overnight"] == ["overnight_log"]
    with patch.object(unprompted, "_config", return_value={}):
        assert unprompted.cross_posts("overnight") is False     # never public unless asked


def test_the_overnight_log_is_a_box_with_a_field_per_section():
    facts = [overnight.Fact("sun", "🟢 Kp **1.7** · quiet", "the planetary K index is 1.7 (quiet)"),
             overnight.Fact("air", "🔢 **E07** · 18287 kHz USB · recorded 09:59Z", "you recorded E07"),
             overnight.Fact("air", "🔢 **E11** · 9079 kHz USB · recorded 06:59Z", "you recorded E11")]
    e = overnight.embed(facts, "a quiet night.", datetime(2026, 9, 26))
    assert e.title == "🌙  Overnight log · Sat 26 Sep" and e.description == "a quiet night."
    assert [f.name for f in e.fields] == [overnight.SECTIONS["air"], overnight.SECTIONS["sun"]]
    assert e.fields[0].value.count("\n") == 1 and e.footer.text
    assert overnight.embed(facts, "").description is None          # no note: the readings alone


def test_kp_wears_the_colour_of_its_storm_level():
    assert [overnight.kp_icon(k) for k in (1.7, 4.3, 5.7, 8.0)] == ["🟢", "🟡", "🟠", "🔴"]


def test_the_overnight_note_is_written_by_her_pipeline(monkeypatch):
    """A bare "You are Kaia" prompt at temperature 0.4 wrote it — no persona,
    memory or mood — and four mornings in six opened "it was a slow one,
    mostly. the scanner was chattering away". It goes through the chat
    pipeline as the quip does, and an invented number still rejects a draft."""
    import asyncio
    from utils.radio import overnight
    drafts = iter(["the k index sat at 9.", "it was a slow one, mostly. the scanner chattered.",
                   "quiet. the k index stayed at 0.7 and the busiest channel was 462.2750 mhz."])
    seen = []

    async def fake(ctx, content, author, author_id, platform, conversation_key=None, no_persist=False):
        seen.append((author, platform, no_persist, content))
        return next(drafts)
    monkeypatch.setattr("utils.infrastructure.system.external_mention.process_external_mention", fake)
    facts = [overnight.Fact("sun", "", "the planetary K index is 0.7 (quiet)"),
             overnight.Fact("scanner", "", "the busiest channel was 462.2750 MHz")]
    recent = ["it was a slow one, mostly.", "it was a slow night again."]
    note = asyncio.run(overnight.write(None, facts, recent))
    assert note.startswith("quiet.")
    assert seen[0][:3] == ("Kaia", overnight.PLATFORM, True)
    assert "the planetary K index is 0.7" in seen[0][3]


def _readings(period=3.2, on=0.4, seconds=120, rate=5.9, lo=-108.0, hi=-78.0, buzz=True):
    import numpy as np
    t = np.arange(0, seconds, 1 / rate)
    rng = np.random.default_rng(1)
    v = np.where((t % period) < on * period, hi, lo) if buzz else np.full_like(t, lo)
    return [(float(x), float(y)) for x, y in zip(t, v + rng.normal(0, 1.5, len(t)))]


def test_the_uvb76_buzz_is_told_from_silence_and_from_a_change():
    """Measured on 22 night samples (five receivers): period 3.0-3.3 s, on ~40%,
    strength 0.42-0.58; a daytime North American receiver read 2.3 dB of spread."""
    from utils.radio.watch import buzz_state
    assert buzz_state(_readings())["state"] == "buzz"
    assert buzz_state(_readings(buzz=False))["state"] == "quiet"
    import numpy as np
    rng = np.random.default_rng(2)
    voice = [(t, -80.0 + rng.normal(0, 6)) for t in np.arange(0, 120, 1 / 5.9)]   # carrier, no rhythm
    assert buzz_state(voice)["state"] == "changed"
    assert buzz_state(_readings(seconds=10))["state"] == "unknown"


def test_a_silent_uvb76_clip_is_not_kept(tmp_path):
    """21 of 23 clips were 60 s of zeros while the S-meter read the buzz."""
    import wave
    import numpy as np
    from utils.radio.watch import _silent
    def wav(name, data):
        p = tmp_path / name
        with wave.open(str(p), "wb") as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(12000)
            f.writeframes(np.asarray(data, np.int16).tobytes())
        return p
    assert _silent(wav("zeros.wav", np.zeros(12000)))
    assert not _silent(wav("hiss.wav", np.random.default_rng(0).normal(0, 2000, 12000)))


def test_the_uvb76_sample_takes_its_clip_from_a_receiver_that_sends_sound(tmp_path, monkeypatch):
    import asyncio, json, types, wave
    import numpy as np
    from utils.radio import kiwi, watch, log as radio_log
    monkeypatch.setattr(radio_log, "clips_dir", lambda: tmp_path / "clips")
    (tmp_path / "clips").mkdir()
    a = types.SimpleNamespace(host="muurame", location="Muurame", port=8073)
    b = types.SimpleNamespace(host="plonsk", location="Płońsk", port=8073)
    async def directory():
        return []
    monkeypatch.setattr(kiwi, "directory", directory)
    monkeypatch.setattr(kiwi, "choose", lambda *args, **k: [a, b])
    from datetime import datetime, timezone
    async def smeter(r, khz, mode, seconds):
        return [(datetime.fromtimestamp(t, timezone.utc), v) for t, v in _readings()]
    monkeypatch.setattr(kiwi, "smeter", smeter)
    async def record(r, khz, mode, seconds, out_dir, label, squelch_db=None):
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{r.host}.wav"
        data = np.zeros(12000) if r.host == "muurame" else np.random.default_rng(0).normal(0, 2000, 12000)
        with wave.open(str(p), "wb") as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(12000)
            f.writeframes(data.astype(np.int16).tobytes())
        return [p]
    monkeypatch.setattr(kiwi, "record", record)
    monkeypatch.setattr(watch, "_to_opus", lambda wav, dest: (dest.write_bytes(b"ogg"), dest)[1])
    out = asyncio.run(watch.sample_uvb76({"khz": 4625.0, "region": "ne", "seconds": 120}))
    meta = json.loads(out.read_text())
    assert meta["receiver"] == "muurame" and meta["clip_receiver"] == "plonsk"
    assert meta["buzz"]["state"] == "buzz"
