"""The local RTL-SDR: sweep, probe, record and stream, one user at a time.

A dongle serves one process. The nightly waterfall watch holds DEVICE while it
runs; a live `!scanner` listen sets YIELD, the watcher stops within a hop, and
the listen holds DEVICE for its session.

Measured on a stock RTL-SDR v3 antenna (26 Sept): pure FM noise from
`rtl_fm` has an RMS near 9,200 with ~52% of its energy above 3 kHz. An FM
carrier quiets it — NOAA on 162.550 read RMS 4,600 and 32% — and a digital
voice repeater has its own shape (the Fusion repeater on 444.200: 73%).
"""
from __future__ import annotations

import asyncio
import subprocess
import threading
from dataclasses import dataclass
import numpy as np

SAMPLE_RATE = 12000
DEFAULT_GAIN = 40
DEVICE = asyncio.Lock()
#: Set by a live listen that wants the dongle: the waterfall watcher stops
#: within one hop and gives it up.
YIELD = threading.Event()


def available() -> bool:
    import shutil
    return bool(shutil.which("rtl_fm") and shutil.which("rtl_power"))


@dataclass
class Probe:
    freq_hz: int
    rms: float
    hf_ratio: float            # share of audio energy above 3 kHz

    @property
    def carrier(self) -> bool:
        """A signal is present: the FM hiss has quieted, or the audio has the
        broadband shape of a digital voice mode."""
        return self.hf_ratio < 0.42 or self.hf_ratio > 0.64 or self.rms < 6500

    @property
    def digital(self) -> bool:
        return self.hf_ratio > 0.64


def measure(audio: np.ndarray, freq_hz: int) -> Probe:
    a = audio.astype(float)
    if len(a) < SAMPLE_RATE // 2:
        return Probe(freq_hz, 0.0, 0.0)
    spec = np.abs(np.fft.rfft(a)) ** 2
    f = np.fft.rfftfreq(len(a), 1 / SAMPLE_RATE)
    total = float(spec.sum()) or 1.0
    return Probe(freq_hz, float(np.sqrt((a ** 2).mean())), float(spec[f > 3000].sum() / total))


def ppm() -> int:
    """The dongle's frequency correction (radio.local.ppm)."""
    from utils.infrastructure.system.yaml_config import config
    try:
        return int(config.get("radio.local.ppm", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _fm_cmd(freq_hz: int, gain: int = DEFAULT_GAIN, mode: str = "fm") -> list[str]:
    cmd = ["rtl_fm", "-f", str(int(freq_hz)), "-M", mode, "-s", str(SAMPLE_RATE), "-g", str(gain)]
    if ppm():
        cmd += ["-p", str(ppm())]
    return cmd + ["-"]


def open_stream(freq_hz: int, gain: int = DEFAULT_GAIN, mode: str = "fm") -> subprocess.Popen:
    """A live stream of s16le mono at SAMPLE_RATE on stdout, for discord.py.
    The caller must hold DEVICE for the life of the stream."""
    return subprocess.Popen(_fm_cmd(freq_hz, gain, mode), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
