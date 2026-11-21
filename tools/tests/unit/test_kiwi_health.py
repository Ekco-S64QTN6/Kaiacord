"""Receiver health: the directory says a KiwiSDR is up, not that it will talk
to us. From 12 Oct 2026 the two best north-eastern receivers sent digital
silence on 4625 kHz while their S-meter read the buzz, and ranking by SNR
alone picked them every night."""
import asyncio
import wave
from pathlib import Path

import numpy as np
import pytest

from utils.radio import kiwi
from utils.radio.fetch import FeedError


@pytest.fixture
def store(monkeypatch):
    data = {}
    monkeypatch.setattr(kiwi, "read_cache", lambda name: dict(data.get(name, {})))
    monkeypatch.setattr(kiwi, "write_cache", lambda name, d: data.__setitem__(name, dict(d)))
    return data


def _rx(host, snr=30, lat=60.0, lon=25.0):
    return kiwi.Receiver(host=host, port=8073, name=host, location=host, lat=lat, lon=lon,
                         users=0, users_max=4, snr=snr, low_hz=0, high_hz=30_000_000,
                         ext_api=4, connect_host="8.8.8.8")


def test_silence_benches_a_receiver_on_that_frequency_only(store):
    muted, other = _rx("muurame", snr=36), _rx("plonsk", snr=20)
    kiwi.note_silent(muted, 4625)
    assert [r.host for r in kiwi.choose([muted, other], 4625, "ne")] == ["plonsk"]
    assert [r.host for r in kiwi.choose([muted, other], 9420, "ne")][0] == "muurame"


def test_refusals_bench_the_host_and_grow(store):
    r = _rx("busy")
    kiwi.note_failed(r, "Too busy")
    first = store["kiwi_health"]["hosts"]["busy"]["until"]
    kiwi.note_failed(r, "Too busy")
    second = store["kiwi_health"]["hosts"]["busy"]["until"]
    assert second - first > kiwi.REFUSED_HOLD_S * 0.9          # doubled
    assert kiwi.choose([r], 4625, "ne") == []
    kiwi.note_ok(r, 4625)
    assert kiwi.choose([r], 4625, "ne") == [r]


def test_a_receiver_that_has_worked_outranks_a_slightly_better_stranger(store):
    proven, stranger = _rx("proven", snr=30), _rx("stranger", snr=34)
    kiwi.note_ok(proven, 4625)
    assert kiwi.choose([stranger, proven], 4625, "ne")[0].host == "proven"


def test_record_raises_and_benches_on_digital_silence(store, tmp_path, monkeypatch):
    """An unsquelched recording that is all zeros is the receiver muting the
    frequency; a squelched one with no openings is just a quiet band."""
    async def fake_exec(*cmd, **kw):
        out = Path(cmd[cmd.index("-d") + 1])
        with wave.open(str(out / "x.wav"), "wb") as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(12000)
            f.writeframes(np.zeros(12000 * 10, np.int16).tobytes())

        class P:
            returncode = 0
            pid = 1
            stderr = None
            async def wait(self): return 0
        return P()

    async def no_stderr(proc, deadline):
        return "", ""
    monkeypatch.setattr(kiwi, "available", lambda: True)
    monkeypatch.setattr(kiwi.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(kiwi, "_watch_stderr", no_stderr)
    r = _rx("muurame")
    with pytest.raises(FeedError, match="digital silence"):
        asyncio.run(kiwi.record(r, 4625, "usb", 10, tmp_path, "uvb76"))
    assert not list(tmp_path.glob("*.wav"))
    assert kiwi.benched(r, 4625) and not kiwi.benched(r, 9420)


def test_silent_pcm():
    assert kiwi.silent_pcm(np.zeros(1000, np.int16).tobytes())
    assert not kiwi.silent_pcm(np.full(1000, 300, np.int16).tobytes())


def test_a_cancelled_recording_stops_its_recorder(tmp_path, monkeypatch):
    """The recorder holds a slot on someone else's receiver; cancelled mid-way,
    it was left running while its folder was removed under it."""
    import asyncio
    from utils.radio import kiwi as kw
    stopped = []
    proc = type("P", (), {"returncode": None, "pid": 1})()

    async def spawn(*a, **k):
        return proc

    async def hang(p, deadline):
        await asyncio.sleep(60)

    async def stop(p, grace=8.0):
        stopped.append(p)

    monkeypatch.setattr(kw.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(kw, "_watch_stderr", hang)
    monkeypatch.setattr(kw, "_stop", stop)
    r = kw.Receiver("kiwi.example.org", 8073, "x", "y", 0.0, 0.0, 0, 4, 20, 0, 30000, connect_host="93.184.216.34")

    async def run():
        t = asyncio.create_task(kw._record_in(r, 4625, "usb", 60, tmp_path, tmp_path, "uvb76", -100))
        await asyncio.sleep(0.05)
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            return True
    assert asyncio.run(run()) and stopped == [proc]
