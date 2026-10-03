"""A kept radio clip can be seen: its spectrogram, rendered once beside it."""
import shutil
import subprocess

import numpy as np
import pytest

from utils.radio import spectrogram

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def _clip(tmp_path, freq=1500):
    path = tmp_path / "c.ogg"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"sine=frequency={freq}:duration=3", "-c:a", "libopus", str(path)], check=True)
    return path


def test_a_tone_shows_as_a_bright_line_at_its_pitch(tmp_path):
    from PIL import Image
    out = spectrogram.render(_clip(tmp_path, 1500), "1500 Hz test", max_hz=4000)
    assert out == tmp_path / "c.png" and out.is_file()
    img = np.asarray(Image.open(out).convert("L")).astype(float)
    plot = img[spectrogram.TOP:spectrogram.TOP + spectrogram.HEIGHT, spectrogram.LEFT:spectrogram.LEFT + spectrogram.WIDTH]
    row = int(np.argmax(plot.mean(axis=1)))
    hz = (spectrogram.HEIGHT - row) / spectrogram.HEIGHT * 4000
    assert abs(hz - 1500) < 60


def test_it_is_made_once_and_unreadable_clips_get_none(tmp_path):
    clip = _clip(tmp_path)
    first = spectrogram.render(clip)
    mtime = first.stat().st_mtime_ns
    assert spectrogram.render(clip).stat().st_mtime_ns == mtime             # not redrawn
    bad = tmp_path / "bad.ogg"
    bad.write_bytes(b"not audio")
    assert spectrogram.render(bad) is None and not (tmp_path / "bad.png").exists()


def test_a_pruned_clip_takes_its_picture_with_it(tmp_path, monkeypatch):
    from utils.radio import log as radio_log
    monkeypatch.setattr(radio_log, "clips_dir", lambda: tmp_path)
    monkeypatch.setattr(radio_log, "MAX_CLIPS", 0)
    clip = _clip(tmp_path)
    spectrogram.render(clip)
    radio_log.prune_clips()
    assert not clip.exists() and not clip.with_suffix(".png").exists()
