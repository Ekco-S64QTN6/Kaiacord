"""The local scanner: the ledger it keeps, how a catch is classified, when it
runs, and the !scanner panel."""
from datetime import datetime
from types import SimpleNamespace as NS

import numpy as np
import pytest

from utils.radio import ledger, scanner


@pytest.fixture(autouse=True)
def tmp_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "telemetry_path", lambda p: str(tmp_path / "ledger.sqlite3"))
    monkeypatch.setattr(scanner, "_save_clip", lambda audio, f, t: "clip.ogg")
    ledger.seed(scanner.seed_channels())


def test_the_seed_names_the_listed_channels(monkeypatch):
    monkeypatch.setattr(scanner, "_cfg", lambda k, d: [{"mhz": 146.94, "label": "W1XYZ repeater (FM)"}]
                        if k == "channels" else d)
    ledger.seed(scanner.seed_channels())
    ch = ledger.channel(146_940_000)
    assert ch["label"] == "W1XYZ repeater (FM)" and ch["source"] == "listed"
    assert ledger.channel(462_562_500)["label"] == "FRS/GMRS ch 1"


def _catch(freq, audio, seconds=8.0):
    return NS(freq_hz=freq, started=datetime(2026, 9, 26, 2, 30).timestamp(), seconds=seconds,
              peak_db=20.0, audio=audio)


def test_a_catch_with_words_is_voice_and_lands_in_its_hour(monkeypatch):
    monkeypatch.setattr(scanner, "_transcribe", lambda a: "checking in from the north side, over")
    quiet = (np.sin(np.linspace(0, 2000 * np.pi, 12000 * 8)) * 3000).astype(np.int16)
    scanner.classify(_catch(146_860_000, quiet))
    ch = ledger.channel(146_860_000)
    assert ch["voice"] == 1 and "north side" in ch["last_transcript"]
    assert __import__("json").loads(ch["hours"])[2] == 1
    assert ledger.recent(1)[0]["kind"] == "voice"


def test_a_kerchunk_is_ignored(monkeypatch):
    monkeypatch.setattr(scanner, "_transcribe", lambda a: "should not be called")
    scanner.classify(_catch(146_860_000, np.zeros(6000, np.int16), seconds=0.5))
    assert ledger.recent(5) == []


def test_digital_audio_is_data_and_not_transcribed(monkeypatch):
    called = []
    monkeypatch.setattr(scanner, "_transcribe", lambda a: called.append(1) or "")
    # FM-demodulated digital audio rises with frequency (the Fusion repeater on
    # 444.200 measured 73% above 3 kHz); differentiated noise has that shape.
    noise = (np.diff(np.random.default_rng(0).normal(size=12000 * 5 + 1)) * 5000).astype(np.int16)
    scanner.classify(_catch(444_200_000, noise, seconds=5))
    assert ledger.recent(1)[0]["kind"] == "data" and not called


@pytest.mark.parametrize("hhmm,inside", [("00:05", True), ("05:59", True), ("06:00", False), ("23:30", False)])
def test_scanning_hours(hhmm, inside):
    h, m = map(int, hhmm.split(":"))
    assert scanner.within_hours(datetime(2026, 9, 26, h, m)) is inside


def test_the_panel_and_presets_render():
    from utils.commands.scanner_handler import history_embed, panel_embed
    embed = panel_embed()
    assert "Local scanner" in embed.title and "00:00–06:00" in embed.description
    assert len(ledger.presets()) == 25
    assert "Nothing yet" in history_embed().description


def test_whisper_looping_on_noise_is_not_voice():
    assert not scanner.looks_like_speech("Stavros Stavrides, Stavros Stavrides, Stavros Stavrides")
    assert not scanner.looks_like_speech("Thank you.")
    assert scanner.looks_like_speech("checking in from the north side, over")


def test_business_radio_is_not_labelled_frs():
    assert scanner._service_of(463_757_500) == "business"
    assert scanner._service_of(462_562_500) == "FRS / GMRS"
    assert scanner._service_of(151_820_000) == "MURS"


def test_history_offers_recorded_catches_to_play(monkeypatch, tmp_path):
    import asyncio
    from unittest.mock import AsyncMock
    from utils.commands import scanner_handler as sh
    monkeypatch.setattr(scanner, "_clips_dir", lambda: tmp_path)
    monkeypatch.setattr(scanner, "_transcribe", lambda a: "net control, this is kilo five, over")
    audio = (np.sin(np.linspace(0, 2000 * np.pi, 12000 * 6)) * 3000).astype(np.int16)
    scanner.classify(_catch(146_860_000, audio))
    assert sh._recorded() == []                  # the clip isn't on disk: nothing to play
    (tmp_path / "clip.ogg").write_bytes(b"x")
    catches = sh._recorded()
    assert catches and catches[0]["clip"] == "clip.ogg"

    async def go():
        view = sh.HistoryView(catches)
        played = AsyncMock()
        monkeypatch.setattr("utils.radio.live.play_clip", played)
        member = NS(voice=NS(channel=NS(name="General")), display_name="Ekco")
        inter = NS(user=member, response=NS(defer=AsyncMock(), send_message=AsyncMock()),
                   followup=NS(send=AsyncMock()))
        await view.play.callback(inter)
        return played
    played = asyncio.run(go())
    assert played.await_count == 1


def test_listen_along_audio_is_steady_20ms_frames():
    src = scanner.ScanAudio()
    assert src.read() == bytes(3840)                        # silence while nothing is held
    scanner._along[1] = {}
    try:
        scanner._sink(np.full(240, 1000, np.int16))
        frame = np.frombuffer(src.read(), np.int16)
        assert len(frame) == 1920 and frame.max() == 1000    # 960 stereo samples at 48 kHz
    finally:
        scanner._along.clear()
    scanner._sink(np.full(240, 1000, np.int16))              # nobody listening: dropped
    assert src.read() == bytes(3840)


def test_one_transmitter_is_one_row():
    """The waterfall rounds to 2.5 kHz, which split 462.2775 and 462.275."""
    scanner._NAMED_CACHE["rows"] = [c["freq_hz"] for c in scanner.seed_channels()]
    assert scanner.snap_channel(462_277_500) == 462_275_000
    assert scanner.snap_channel(146_861_000) == 146_860_000          # ham: 5 kHz grid
    assert scanner.snap_channel(462_563_000) == 462_562_500          # FRS/GMRS ch 1
    ledger.record(463_225_000, "carrier", 5, 3000, 0.3)
    assert scanner.snap_channel(463_221_000) == 463_225_000          # a channel already heard
    ledger.record(463_727_500, "carrier", 5, 3000, 0.3)              # an off-grid row from before snapping
    assert scanner.snap_channel(463_727_500) == 463_725_000          # does not attract its own catches


def test_a_channel_that_never_carries_voice_stops_being_transcribed(monkeypatch):
    calls = []
    monkeypatch.setattr(scanner, "_transcribe", lambda a: calls.append(1) or "")
    audio = (np.sin(np.linspace(0, 2000 * np.pi, 12000 * 6)) * 3000).astype(np.int16)
    for _ in range(scanner.QUIET_CHANNEL_HITS + 2):
        scanner.classify(_catch(462_275_000, audio, seconds=6))
    assert len(calls) == scanner.QUIET_CHANNEL_HITS           # then quiet…
    scanner.classify(_catch(462_275_000, audio, seconds=6))
    assert len(calls) == scanner.QUIET_CHANNEL_HITS + 1       # …until every tenth catch rechecks


def test_a_net_is_transcribed_and_clipped_whatever_the_nights_budget(monkeypatch):
    """The overnight scan spends the same date's allowance; a net at 20:15 must still be heard."""
    calls, clips = [], []
    monkeypatch.setattr(scanner, "_transcribe", lambda a: calls.append(1) or "")
    monkeypatch.setattr(scanner, "_save_clip", lambda audio, f, t: clips.append(f) or "clip.ogg")
    monkeypatch.setitem(scanner._transcribed, "date", datetime.now().strftime("%Y-%m-%d"))
    monkeypatch.setitem(scanner._transcribed, "count", scanner.TRANSCRIBE_PER_NIGHT)
    monkeypatch.setitem(scanner._carrier_samples, "date", datetime.now().strftime("%Y-%m-%d"))
    monkeypatch.setitem(scanner._carrier_samples, "channels", {147_570_000})    # tonight's sample taken
    audio = (np.sin(np.linspace(0, 2000 * np.pi, 12000 * 6)) * 3000).astype(np.int16)
    scanner.classify(_catch(147_570_000, audio, seconds=6))
    assert calls == [] and clips == []                    # open scan: budget spent, a carrier, no clip
    monkeypatch.setattr(scanner, "_pinned", {"freq_hz": 147_570_000, "label": "net", "until": 0})
    scanner.classify(_catch(147_570_000, audio, seconds=6))
    assert calls == [1] and clips == [147_570_000]        # on the net: transcribed, and kept to listen to



def test_the_first_carrier_a_channel_sends_each_night_keeps_its_clip(monkeypatch):
    """500 carrier events, not one clip: the verdict could never be checked,
    and 56 of them were on the APRS frequency."""
    clips = []
    monkeypatch.setattr(scanner, "_transcribe", lambda a: "")
    monkeypatch.setattr(scanner, "_save_clip", lambda audio, f, t: clips.append(f) or "clip.ogg")
    monkeypatch.setitem(scanner._carrier_samples, "date", "")
    audio = (np.sin(np.linspace(0, 2000 * np.pi, 12000 * 6)) * 3000).astype(np.int16)
    for _ in range(3):
        scanner.classify(_catch(144_390_000, audio, seconds=3))
    scanner.classify(_catch(462_275_000, audio, seconds=6))
    assert clips == [144_390_000, 462_275_000]
    assert [e["clip"] for e in ledger.recent(4)].count("clip.ogg") == 2


def test_a_rotated_clip_is_not_named_by_the_ledger(tmp_path, monkeypatch):
    ledger.record(146_860_000, "voice", 5.0, 5000, 0.4, clip="old.ogg")
    ledger.forget_clips(["old.ogg"])
    assert ledger.recent(1)[0]["clip"] is None


def test_the_overnight_count_is_not_capped_at_the_display_limit(monkeypatch):
    """ledger.recent(500) stops at 500, and a night's watch logs about that
    many: a busier night would have been reported as exactly 500 catches."""
    import asyncio
    from datetime import timezone
    from unittest.mock import AsyncMock
    from utils.radio import overnight
    t0 = 1_790_000_000.0
    for i in range(620):
        ledger.record(462_275_000 if i % 3 else 144_390_000, "carrier", 5.0, 3000, 0.3, when=t0 + i)
    monkeypatch.setattr("utils.sky.feeds.space_weather", AsyncMock(side_effect=RuntimeError))
    monkeypatch.setattr("utils.sky.feeds.close_approaches", AsyncMock(return_value=[]))
    monkeypatch.setattr("utils.sky.feeds.quakes", AsyncMock(return_value=[]))
    facts = asyncio.run(overnight.gather(since=datetime.fromtimestamp(t0 - 1, timezone.utc)))
    local = [f for f in facts if f.section == "local"][0]
    assert "620 transmissions" in local.text and "462.2750" in local.text


def test_the_panel_counts_every_catch_of_the_night():
    """recent(200) capped "Last 12 hours" at 200 on a night of 330."""
    import time as _t
    from utils.commands import scanner_handler
    now = _t.time()
    for i in range(330):
        ledger.record(462_275_000, "carrier", 5.0, 3000, 0.3, when=now - i)
    field = next(f for f in scanner_handler.panel_embed().fields if f.name == "Last 12 hours")
    assert field.value.startswith("330 catches")


# ── Does the waterfall find the traffic? A simulated dongle ─────────────────

class _SimDongle:
    """FM transmissions (freq, start s, seconds) in noise, on a simulated clock."""

    def __init__(self, txs, until, snr_db=20, noise_step=None):
        from utils.radio import waterfall as w
        self.w, self.txs, self.until, self.t, self.center = w, txs, until, 0.0, 0
        rng = np.random.default_rng(1)
        self.rng = rng
        self.noise = ((rng.standard_normal(1_000_000) + 1j * rng.standard_normal(1_000_000)) * 0.7).astype(np.complex64)
        self.amp = 10 ** (snr_db / 20) / np.sqrt(w.FS / 12.5e3) * 4       # ~snr_db over the channel's floor
        self.stop = None
        self.noise_step = noise_step          # (from s, amplitude factor): a household noise source switching on

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def tune(self, c):
        self.center, self.t = c, self.t + 0.06
        if self.t >= self.until:
            self.stop.set()
        return True

    def read(self, n):
        w = self.w
        t = self.t + np.arange(n) / w.FS
        o = int(self.rng.integers(0, len(self.noise) - n))
        x = self.noise[o:o + n].copy()
        if self.noise_step and self.t >= self.noise_step[0]:
            x *= self.noise_step[1]
        for f, start, dur in self.txs:
            off = f - self.center
            if abs(off) < w.FS / 2 and start < t[-1] and start + dur > t[0]:
                on = (t >= start) & (t < start + dur)
                x += (self.amp * on * np.exp(1j * (2 * np.pi * off * t + 3.75 * np.sin(2 * np.pi * 800 * t)))).astype(np.complex64)
        self.t += n / w.FS
        return x


def _simulate(monkeypatch, txs, seconds, snr_db=20, noise_step=None):
    import threading
    import utils.radio.dongle as dongle
    from utils.radio import waterfall as w
    d = _SimDongle(txs, seconds, snr_db, noise_step)
    d.stop = threading.Event()
    monkeypatch.setattr(w, "time", NS(time=lambda: d.t))
    monkeypatch.setattr(dongle, "Dongle", lambda **k: d)
    caught = []
    watcher = w.Watcher(caught.append, stop=d.stop, hops=w.hop_plan([c["freq_hz"] for c in scanner.seed_channels()]))
    watcher.run()
    import time as _t
    _t.sleep(0.2)                                   # the catch worker drains
    return sorted({round(c.freq_hz / 5000) * 5000 for c in caught}), caught


def test_the_waterfall_hears_what_the_old_plan_missed(monkeypatch):
    """Simulated against the old plan, 2 of 7 were caught: the reply 3 s after
    an over (30 s cooldown), repeaters on a slice's blind centre (147.000,
    445.000), a notebook channel between slices (463.848) and a short over
    were all lost."""
    txs = [(146_860_000, 40, 8), (146_860_000, 51, 6), (147_000_000, 65, 10),
           (463_848_000, 82, 10), (443_675_000, 96, 2.5), (445_000_000, 104, 8), (160_425_000, 116, 6)]
    freqs, caught = _simulate(monkeypatch, txs, 130)
    assert sum(1 for c in caught if abs(c.freq_hz - 146_860_000) < 5000) == 2       # the over and its reply
    for f in (147_000_000, 463_850_000, 443_675_000, 445_000_000, 160_425_000):
        assert any(abs(g - f) <= 5000 for g in freqs), f


def test_noise_alone_is_never_a_catch(monkeypatch):
    freqs, caught = _simulate(monkeypatch, [], 120)
    assert caught == []


def test_a_weak_signal_is_confirmed_on_a_second_visit(monkeypatch):
    freqs, _ = _simulate(monkeypatch, [(443_850_000, 40, 10)], 70, snr_db=12)
    assert any(abs(f - 443_850_000) <= 5000 for f in freqs)


def test_every_listed_channel_is_outside_a_blind_centre(monkeypatch):
    """Local channels are deployment facts in config; the plan is built around them."""
    from utils.radio import waterfall as w
    monkeypatch.setattr(scanner, "_cfg", lambda k, d: [{"mhz": 147.000}, {"mhz": 443.000}, {"mhz": 464.600}]
                        if k == "channels" else d)
    chans = [c["freq_hz"] for c in scanner.seed_channels()]
    fast, slow = w.hop_plan(chans)
    assert all(w.covered(f, fast + slow) for f in chans)
    for lo, hi in w.FAST_BANDS + w.SLOW_BANDS:                   # no gaps between slices
        edges = sorted(c for c in fast + slow if lo - 2_000_000 < c < hi + 2_000_000)
        assert all(b - a <= w.FS * w.USABLE for a, b in zip(edges, edges[1:]))



def test_a_rise_in_the_noise_is_not_a_run_of_catches(monkeypatch):
    """On 27 Sept from 05:46, something nearby raised the noise across the UHF
    slices: the watch held noise for a full minute on a new frequency almost
    every minute, fourteen clips of hiss, and was deaf meanwhile. The floor
    adapts only through visits, and every hot visit started another hold."""
    freqs, caught = _simulate(monkeypatch, [(460_575_000, 110, 20)], 150, snr_db=30,
                              noise_step=(60, 5.0))                      # +14 dB across every slice at 60 s
    noise = [c for c in caught if abs(c.freq_hz - 460_575_000) > 5000]
    assert noise == [], [(round(c.freq_hz / 1e6, 4), round(c.seconds)) for c in noise]
    assert any(abs(f - 460_575_000) <= 5000 for f in freqs)              # the call after the rise is still heard


def test_a_broadcast_sign_off_off_a_carrier_is_not_speech():
    assert not scanner.looks_like_speech("We'll be right back.")
    assert scanner.looks_like_speech("National 28, 8213 Meadows Road, number 1116")


def test_a_carrier_sample_is_short(monkeypatch):
    saved = []
    monkeypatch.setattr(scanner, "_transcribe", lambda a: "")
    monkeypatch.setattr(scanner, "_save_clip", lambda audio, f, t: saved.append(len(audio)) or "clip.ogg")
    monkeypatch.setitem(scanner._carrier_samples, "date", "")
    audio = (np.sin(np.linspace(0, 2000 * np.pi, 12000 * 60)) * 3000).astype(np.int16)
    scanner.classify(_catch(450_900_000, audio, seconds=60))
    assert saved == [scanner.CARRIER_SAMPLE_S * 12000]
