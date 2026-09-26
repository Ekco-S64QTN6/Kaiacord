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
    assert "Local scanner" in embed.title and "midnight to 6" in embed.description
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
