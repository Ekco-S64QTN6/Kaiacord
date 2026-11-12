"""A record's file name never reaches a shell or a filter graph (GitHub #328).

Every decoder passes the path to ffmpeg/ffprobe as its own argument, so spaces,
quotes, brackets, Unicode and shell metacharacters in a library path must decode
exactly like a plain name. Each name here is a real file decoded through the
real functions.
"""
import shutil
import wave

import numpy as np
import pytest

from utils.audio import beatgrid, mixcheck, records

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")

NAMES = [
    "plain.wav",
    "Artist - Title (Extended Mix) [2001].wav",
    "it's a \"quoted\" name.wav",
    "$(touch pwned) `id` ; rm -rf x & echo |.wav",
    "Sigur Rós — Hoppípolla ünïcödé.wav",
    "colon: and #hash %percent.wav",
]


def _click_track(path, seconds=3.0, rate=44100):
    t = np.arange(int(seconds * rate)) / rate
    clicks = (np.mod(t, 0.5) < 0.01) * np.sin(2 * np.pi * 1000 * t)       # 120 bpm
    pcm = (np.stack([clicks, clicks], axis=1) * 20000).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


@pytest.fixture
def crate(tmp_path):
    folder = tmp_path / "a [crate] with 'quotes'"
    folder.mkdir()
    for name in NAMES:
        _click_track(folder / name)
    return folder


@pytest.mark.parametrize("name", NAMES)
def test_every_decoder_reads_an_awkward_name_like_a_plain_one(crate, name, tmp_path):
    path = str(crate / name)
    plain = str(crate / "plain.wav")
    assert len(beatgrid._decode(path, 2.0)) == len(beatgrid._decode(plain, 2.0)) > 0
    assert len(mixcheck._decode(path)) == len(mixcheck._decode(plain)) > 0
    proc = records.open_pcm(path)
    out, _ = proc.communicate(timeout=30)
    assert proc.returncode == 0 and len(out) > 0
    assert not (tmp_path / "pwned").exists() and not (crate / "pwned").exists()


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="needs ffprobe")
@pytest.mark.parametrize("name", NAMES)
def test_duration_and_loudness_read_an_awkward_name(crate, name):
    path = str(crate / name)
    assert records.probe_seconds(path) == pytest.approx(3.0, abs=0.05)
    assert records.gain_db(path) == records.gain_db(str(crate / "plain.wav"))
