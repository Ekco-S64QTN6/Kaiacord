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


def _hiss(seconds: float) -> np.ndarray:
    """FM with nothing on the channel: loud noise rising with frequency."""
    rng = np.random.default_rng(1)
    return (np.diff(rng.normal(size=int(12000 * seconds) + 1)) * 5000).astype(np.int16)


def _catch(freq, audio, seconds=8.0):
    # Every hold ends in the squelch tail it waited out.
    audio = np.concatenate([audio, _hiss(2.0)]) if len(audio) >= 12000 else audio
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
    # Under a carrier, well below the hiss of an empty channel.
    noise = (np.diff(np.random.default_rng(0).normal(size=12000 * 5 + 1)) * 1000).astype(np.int16)
    scanner.classify(_catch(444_200_000, noise, seconds=5))
    assert ledger.recent(1)[0]["kind"] == "data" and not called


def test_static_is_ledgered_as_noise_and_never_transcribed_or_kept(monkeypatch):
    """Hiss that trips the trigger has no carrier under it; Whisper would
    write words onto it ("We'll be right back." on 445.51)."""
    called, saved = [], []
    monkeypatch.setattr(scanner, "_transcribe", lambda a: called.append(1) or "we'll be right back")
    monkeypatch.setattr(scanner, "_save_clip", lambda *a: saved.append(1) or "clip.ogg")
    scanner.classify(_catch(445_510_000, _hiss(8.0)))
    rows = ledger.catches_since(0)
    assert not called and not saved and not rows and not (ledger.channel(445_510_000) or {}).get("hits")


def test_a_digital_channel_is_not_taken_for_static(monkeypatch):
    monkeypatch.setattr(scanner, "_cfg", lambda k, d: [{"mhz": 444.2, "mode": "digital"}] if k == "channels" else d)
    scanner.classify(_catch(444_200_000, _hiss(5.0), seconds=5))
    assert ledger.recent(1)[0]["kind"] == "data"


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
    audio = (np.sin(np.linspace(0, 2000 * np.pi, 12000 * 6)) * 3000).astype(np.int16)
    scanner.classify(_catch(147_570_000, audio, seconds=6))
    assert calls == [] and clips == []                    # open scan: budget spent, a carrier, no clip
    monkeypatch.setattr(scanner, "_pinned", {"freq_hz": 147_570_000, "label": "net", "until": 0})
    scanner.classify(_catch(147_570_000, audio, seconds=6))
    assert calls == [1] and clips == [147_570_000]        # on the net: transcribed, and kept to listen to


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
        for f, start, dur, *kind in self.txs:
            off = f - self.center
            if abs(off) < w.FS / 2 and start < t[-1] and start + dur > t[0]:
                on = (t >= start) & (t < start + dur)
                # A tone, or a voice: the same tone swelling and fading at a syllable rate.
                dev = 3.75 * (0.1 + np.abs(np.sin(2 * np.pi * 2.5 * t))) if kind == ["voice"] else 3.75
                x += (self.amp * on * np.exp(1j * (2 * np.pi * off * t + dev * np.sin(2 * np.pi * 800 * t)))).astype(np.complex64)
        self.t += n / w.FS
        return x


def _simulate(monkeypatch, txs, seconds, snr_db=20, noise_step=None, sink=None):
    import threading
    import utils.radio.dongle as dongle
    from utils.radio import waterfall as w
    d = _SimDongle(txs, seconds, snr_db, noise_step)
    d.stop = threading.Event()
    monkeypatch.setattr(w, "time", NS(time=lambda: d.t))
    monkeypatch.setattr(dongle, "Dongle", lambda **k: d)
    caught = []
    watcher = w.Watcher(caught.append, stop=d.stop, sink=sink, hops=w.hop_plan([c["freq_hz"] for c in scanner.seed_channels()]))
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


def test_a_conversation_is_followed_into_one_recording(monkeypatch):
    """Voice keeps the watch on the channel for the reply; each over within
    FOLLOW_IDLE_S joins the same catch, the gaps cut to SILENCE_S, and the
    listener hears silence rather than hiss between overs. An over after the
    channel has sat idle is a new catch."""
    from utils.radio import waterfall as w
    heard = []
    txs = [(146_860_000, 40, 6, "voice"), (146_860_000, 52, 5, "voice"), (146_860_000, 63, 4, "voice"),
           (146_860_000, 100, 5, "voice")]
    _, caught = _simulate(monkeypatch, txs, 125, sink=heard.append)
    mine = [c for c in caught if abs(c.freq_hz - 146_860_000) < 5000]
    assert len(mine) == 2
    first = mine[0]
    assert first.seconds >= 63 + 4 - 40 + w.FOLLOW_IDLE_S - 3            # stayed through the replies, then waited
    kept = len(first.audio) / w.AUDIO_FS
    assert 15 - 2 <= kept <= 15 + 3 * (w.SILENCE_S + 0.5)                # three overs, gaps trimmed
    assert w.voice_like(first.audio) and any(not c.any() for c in heard if len(c) == w.AUDIO_FS // 5)


def test_a_data_burst_is_not_followed(monkeypatch):
    """A steady tone is not voice: the watch goes back to hopping after it."""
    from utils.radio import waterfall as w
    _, caught = _simulate(monkeypatch, [(146_860_000, 40, 4)], 60)
    c = next(c for c in caught if abs(c.freq_hz - 146_860_000) < 5000)
    assert not w.voice_like(c.audio) and c.seconds < 4 + w.SILENCE_S + 2


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


def test_the_band_notebook_describes_what_was_heard_and_keeps_the_notes(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("band_nb", "tools/maintenance/band_notebook.py")
    nb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nb)
    db = tmp_path / "ledger.sqlite3"
    monkeypatch.setattr(ledger, "telemetry_path", lambda p: str(db))
    ledger.seed(scanner.seed_channels())
    t0 = 1_790_000_000.0
    for i in range(10):
        ledger.record(462_275_000, "carrier", 5.0, 3000, 0.3, when=t0 + 60 * i)
    ledger.record(460_575_000, "voice", 25.0, 2300, 0.16, transcript="engine 28, 812 meadows road", when=t0 + 30)
    ledger.record(445_510_000, "voice", 30.0, 5600, 0.01, transcript="We'll be right back.", when=t0 + 90)
    monkeypatch.setattr(nb, "LEDGER", db)
    monkeypatch.setattr(nb, "CLIPS", tmp_path / "clips")
    monkeypatch.setattr(nb, "OUT", tmp_path / "notebook.md")
    (tmp_path / "notebook.md").write_text("old\n\n## My notes\n\nthe 462.275 thing is the water tower\n")
    monkeypatch.setattr("sys.argv", ["band_notebook.py", "--write"])
    nb.main()
    text = (tmp_path / "notebook.md").read_text()
    assert "462.2750" in text and "every ~60 s (regular" in text
    assert "meadows road" in text
    assert "not speech" in text                                          # the Whisper sign-off is flagged
    assert text.rstrip().endswith("the 462.275 thing is the water tower")


def test_scanner_scan_joins_the_callers_voice_channel(monkeypatch):
    """`!scanner scan` is the 🎧 button typed: the same listen-along."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from utils.commands import scanner_handler as sh
    from utils.radio import rtl
    started = []
    monkeypatch.setattr(rtl, "available", lambda: True)
    monkeypatch.setattr(scanner, "start_listen_along", AsyncMock(side_effect=lambda v, t, who: started.append((v, who))))
    vc = MagicMock()
    vc.name = "Night Shift"
    msg = MagicMock(content="!scanner scan")
    msg.author.voice.channel = vc
    msg.author.display_name = "ekco"
    msg.channel.send = AsyncMock()
    asyncio.run(sh.handle_scanner_command(None, msg))
    assert started == [(vc, "ekco")]
    assert "Night Shift" in msg.channel.send.call_args.kwargs["embed"].description


def test_the_notebook_never_calls_a_spoken_id_packet():
    """448.775's voice and Morse ID put 5% of its frames on the AFSK tones."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("band_nb", "tools/maintenance/band_notebook.py")
    nb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nb)
    ev = [{"kind": "carrier", "seconds": 32.0, "transcript": "", "ts": 0, "id": 1}]
    spoken = {"signal_s": 20.0, "afsk_share": 0.05, "edge_hz": 3000, "voice_like": True}
    packet = dict(spoken, voice_like=False)
    assert "packet" not in nb._what(448_775_000, {}, ev, spoken)
    assert "packet" in nb._what(448_775_000, {}, ev, packet)


def test_a_drifting_constant_carrier_costs_one_minute_not_one_per_step(monkeypatch):
    """424.365–424.42 took a full-minute hold on each step it wandered to."""
    _, caught = _simulate(monkeypatch, [(147_300_000, 20, 75), (147_330_000, 100, 75)], 180)
    near = [c for c in caught if abs(c.freq_hz - 147_315_000) <= 40_000]
    assert len(near) == 1 and near[0].seconds >= 59


def test_a_conversation_that_keeps_the_repeater_keyed_is_not_locked_out(monkeypatch):
    """A linked node holds its carrier up through a conversation; at the
    minute mark speech is followed, not given the half-hour cooldown."""
    from utils.radio import waterfall as w
    _, caught = _simulate(monkeypatch, [(146_860_000, 20, 90, "voice")], 140)
    mine = [c for c in caught if abs(c.freq_hz - 146_860_000) < 5000]
    assert len(mine) == 1 and mine[0].seconds >= 90


def test_a_carrier_keyed_the_whole_minute_is_still_left_alone(monkeypatch):
    from utils.radio import waterfall as w
    _, caught = _simulate(monkeypatch, [(146_860_000, 20, 110)], 140)
    mine = [c for c in caught if abs(c.freq_hz - 146_860_000) < 5000]
    assert len(mine) == 1 and w.MAX_HOLD_S - 1 <= mine[0].seconds < w.MAX_HOLD_S + 2


def test_a_data_burst_keeps_no_clip_and_a_spoken_id_does(monkeypatch):
    """Data isn't worth hearing back; a repeater's ID, spoken or in Morse,
    and voice Whisper missed are (448.775's ID transcribed to nothing)."""
    from utils.radio import waterfall as w
    clips = []
    monkeypatch.setattr(scanner, "_transcribe", lambda a, **k: "")
    monkeypatch.setattr(scanner, "_save_clip", lambda audio, f, t: clips.append(f) or "clip.ogg")
    burst = (np.sin(np.linspace(0, 2000 * np.pi, 12000 * 4)) * 3000).astype(np.int16)
    scanner.classify(_catch(462_275_000, burst, seconds=4))
    monkeypatch.setattr(w, "voice_like", lambda a: True)
    scanner.classify(_catch(448_775_000, burst, seconds=4))
    assert clips == [448_775_000]
    assert [e["kind"] for e in ledger.recent(2)] == ["carrier", "carrier"]


def test_a_repeated_morse_id_is_kept_once_every_six_hours(monkeypatch):
    """145.690 sends its ID every few minutes; seven were kept in forty."""
    from utils.radio import waterfall as w
    clips = []
    monkeypatch.setattr(scanner, "_transcribe", lambda a, **k: "")
    monkeypatch.setattr(scanner, "_save_clip", lambda audio, f, t: clips.append(t) or "clip.ogg")
    monkeypatch.setattr(w, "voice_like", lambda a: True)
    monkeypatch.setattr(scanner, "morse_id", lambda a: True)
    monkeypatch.setattr(scanner, "_id_clips", {})
    burst = (np.sin(np.linspace(0, 2000 * np.pi, 12000 * 6)) * 3000).astype(np.int16)
    for minutes in (0, 10, 20, 7 * 60):
        c = _catch(145_690_000, burst, seconds=6)
        c.started += minutes * 60
        scanner.classify(c)
    assert len(clips) == 2 and clips[1] - clips[0] == 7 * 3600


def test_speech_the_strict_pass_drops_gets_a_second_pass(monkeypatch):
    """The speech filter scored real repeater voice low on 145.690 ("I can't
    believe this. Yeah, I can't either."); a speech-like catch that isn't Morse
    is transcribed again without it."""
    from utils.radio import waterfall as w
    passes = []
    monkeypatch.setattr(scanner, "_transcribe",
                        lambda a, speech_only=True: passes.append(speech_only) or ("" if speech_only else "I can't believe this. Yeah, I can't either."))
    monkeypatch.setattr(w, "voice_like", lambda a: True)
    monkeypatch.setattr(scanner, "morse_id", lambda a: False)
    burst = (np.sin(np.linspace(0, 2000 * np.pi, 12000 * 6)) * 3000).astype(np.int16)
    scanner.classify(_catch(145_690_000, burst, seconds=6))
    assert passes == [True, False] and ledger.recent(1)[0]["kind"] == "voice"



def test_a_steady_keyed_tone_is_a_morse_id_and_speech_is_not():
    """W5EBQ's 1045 Hz ID was missed by the shortwave detector, which picked
    2440 Hz; an ID keys one tone at one level, speech never holds a level."""
    rng = np.random.default_rng(0)
    t = np.arange(12000 * 6) / 12000
    quiet = rng.normal(size=len(t)) * 30                                   # a carrier's quieted hiss
    keying = (np.sin(2 * np.pi * 3 * t) > 0).astype(float)                 # 3 key-downs a second
    morse = quiet + keying * np.sin(2 * np.pi * 1045 * t) * 6000
    # Syllables at uneven loudness on a pitch that glides, as a voice's does.
    pitch = 1045 + 150 * np.sin(2 * np.pi * 0.7 * t)
    loud = np.repeat(rng.uniform(0.2, 1.0, 20), len(t) // 20 + 1)[:len(t)]
    speech = quiet + np.sin(2 * np.pi * np.cumsum(pitch) / 12000) * 6000 * np.abs(np.sin(2 * np.pi * 2.3 * t)) * loud
    tail = rng.normal(size=12000 * 2) * 6000                               # squelch tail
    as_clip = lambda x: np.clip(np.concatenate([x, tail]), -32767, 32767).astype(np.int16)
    assert scanner._steady_keyed_tone(as_clip(morse))
    assert not scanner._steady_keyed_tone(as_clip(speech))
