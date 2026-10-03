"""A picture of a radio clip: time across, frequency up, loudness as colour.

Every clip the scanner or the shortwave watch keeps can be shown as a
spectrogram, so what was caught can be seen before it is played — a voice's
formant bands, packet radio's two tones, a carrier's flat line, a Morse ID's
dashes. NumPy for the transform, PIL for the picture, CPU only; rendered once,
next to the clip (`<clip>.png`), and removed with it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import numpy as np

RATE = 16000
N_FFT = 512                      # 32 ms windows: voice harmonics resolve, bursts stay sharp
HOP = 128                        # 8 ms
#: Loudness shown, in dB below the clip's loudest.
RANGE_DB = 60.0
WIDTH, HEIGHT = 1000, 300        # the plot; margins are added round it
LEFT, RIGHT, TOP, BOTTOM = 52, 14, 30, 30

# The booth's palette: night, deep blue, purple, pink, cyan, white.
_STOPS = [(0.00, (4, 6, 12)), (0.25, (20, 28, 90)), (0.45, (110, 40, 190)), (0.62, (255, 47, 209)),
          (0.82, (0, 240, 255)), (1.00, (235, 250, 255))]


def _palette() -> np.ndarray:
    xs = np.linspace(0, 1, 256)
    out = np.zeros((256, 3))
    for i in range(3):
        out[:, i] = np.interp(xs, [s[0] for s in _STOPS], [s[1][i] for s in _STOPS])
    return out.astype(np.uint8)


def _decode(path: Path, seconds: float = 120.0) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-t", str(seconds), "-i", str(path),
                          "-ac", "1", "-ar", str(RATE), "-f", "s16le", "pipe:1"],
                         capture_output=True, timeout=60).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def levels(samples: np.ndarray, max_hz: float = RATE / 2) -> np.ndarray:
    """dB below the loudest, (frequency bins × frames), lowest frequency first."""
    if len(samples) < N_FFT:
        samples = np.pad(samples, (0, N_FFT - len(samples)))
    frames = 1 + (len(samples) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(frames)[:, None]
    spec = np.abs(np.fft.rfft(samples[idx] * np.hanning(N_FFT), axis=1)).T
    spec = spec[: int(len(spec) * min(1.0, max_hz / (RATE / 2)))]
    db = 20 * np.log10(spec + 1e-9)
    return db - np.percentile(db, 99.7)


def render(clip: Path, title: str = "", max_hz: float = 8000.0) -> Optional[Path]:
    """The clip's spectrogram as a PNG beside it, made once. None if the clip
    cannot be read."""
    clip = Path(clip)
    out = clip.with_suffix(".png")
    try:
        if out.is_file() and out.stat().st_mtime >= clip.stat().st_mtime:
            return out
        samples = _decode(clip)
    except (OSError, subprocess.SubprocessError):
        return None
    if len(samples) < RATE // 10:
        return None
    from PIL import Image, ImageDraw, ImageFont
    db = levels(samples, max_hz)
    v = np.clip((db + RANGE_DB) / RANGE_DB, 0.0, 1.0)
    img = Image.fromarray(_palette()[(v[::-1] * 255).astype(np.uint8)], "RGB")
    img = img.resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)
    canvas = Image.new("RGB", (LEFT + WIDTH + RIGHT, TOP + HEIGHT + BOTTOM), (4, 6, 12))
    canvas.paste(img, (LEFT, TOP))
    d = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default(size=13)
    except TypeError:                           # Pillow before 10.1
        font = ImageFont.load_default()
    dim, cyan = (93, 107, 143), (0, 240, 255)
    seconds = len(samples) / RATE
    for khz in range(0, int(max_hz // 1000) + 1):
        y = TOP + HEIGHT - khz * 1000 / max_hz * HEIGHT
        d.line([(LEFT - 5, y), (LEFT, y)], fill=dim)
        d.text((6, y - 7), f"{khz} kHz", fill=dim, font=font)
    step = next(s for s in (1, 2, 5, 10, 15, 30, 60) if seconds / s <= 12)
    for t in np.arange(0, seconds + 1e-6, step):
        x = LEFT + t / seconds * WIDTH
        d.line([(x, TOP + HEIGHT), (x, TOP + HEIGHT + 5)], fill=dim)
        d.text((x - 8, TOP + HEIGHT + 8), f"{t:g}s", fill=dim, font=font)
    d.rectangle([LEFT - 1, TOP - 1, LEFT + WIDTH, TOP + HEIGHT], outline=(24, 34, 58))
    d.text((LEFT, 8), title[:120], fill=cyan, font=font)
    # Written beside its destination and moved into place, so an interrupted
    # render never leaves a half picture that reads as done.
    tmp = out.with_name(f".{out.name}.tmp")
    try:
        canvas.save(tmp, format="PNG", optimize=True)
        tmp.replace(out)
    except OSError:
        tmp.unlink(missing_ok=True)
        return None
    return out
