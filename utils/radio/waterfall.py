"""Continuous waterfall watch: hop the voice bands, catch whatever keys up.

A channel that carries one transmission an hour is missed by any scheme that
visits it for a few seconds per cycle. This hops the dongle across the bands
people talk on — about fourteen 2 MHz slices, a full pass every couple of
seconds — and keeps, for every frequency bin, a rolling floor of what that bin
usually reads. A bin that stands well over its own floor on consecutive visits
is a transmission: the watcher holds on that slice, demodulates the channel,
records until it has been quiet a couple of seconds, and goes back to hopping.

The approach — a rolling per-channel noise floor (low percentile of recent
frames), activation only after persistence over consecutive frames, then
scan-and-hold with a silence release and a per-channel cooldown — follows
radiotui (github.com/n0nuser/radiotui, MIT). A constant carrier (NOAA, a
birdie) raises its own floor and stops triggering within a minute.
"""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

FS = 2_400_000
NFFT = 2048
USABLE = 0.80                     # of each slice; the edges roll off
DC_GUARD_HZ = 20_000              # the tuner's own spike at centre
FLOOR_VISITS = 24
FLOOR_PCT = 25
WARM_VISITS = 8
GATE_DB = 10.0
PERSIST = 2
SILENCE_S = 2.0
MAX_HOLD_S = 60.0
COOLDOWN_S = 30.0
LONG_COOLDOWN_S = 30 * 60        # after a hold that ran the whole MAX_HOLD_S: a near-constant carrier
COOLDOWN_SPAN_HZ = 12_500        # one channel, whichever 2.5 kHz step a wide signal rounds to
AUDIO_FS = 12_000

MHZ = 1_000_000
#: Slices visited every pass: the bands people talk on.
FAST_HOPS = [int(f * MHZ) for f in (
    145.0, 147.0,                                   # 2m ham
    151.8, 153.8, 155.8, 157.4,                     # MURS, VHF business, marine
    161.6,                                          # railroad + NOAA
    441.0, 443.0, 445.0, 447.0, 449.0,              # 70cm repeaters
    462.8, 467.3,                                   # FRS / GMRS
)]
#: One of these per pass, in rotation: wider, quieter territory.
SLOW_HOPS = [int(f * MHZ) for f in (
    223.0, 224.5,                                   # 1.25m ham
    421.0, 423.0, 425.0, 427.0, 429.0, 431.0, 433.0, 435.0, 437.0, 439.0,
    451.0, 453.0, 455.0, 457.0, 459.0, 461.0,       # UHF business
    927.2,                                          # 900 MHz ham repeaters
)]


def _smooth_spectrum(iq: np.ndarray) -> np.ndarray:
    """Power (dB) per FFT bin, averaged over frames and smoothed across ~12 kHz
    so a whole NBFM channel reads as one peak."""
    frames = len(iq) // NFFT
    x = iq[: frames * NFFT].reshape(frames, NFFT) * np.hanning(NFFT)
    p = np.mean(np.abs(np.fft.fftshift(np.fft.fft(x, axis=1), axes=1)) ** 2, axis=0)
    width = max(1, int(12_500 / (FS / NFFT)))
    p = np.convolve(p, np.ones(width) / width, mode="same")
    return 10 * np.log10(p + 1e-12)


def _bin_freqs(center: int) -> np.ndarray:
    return center + (np.arange(NFFT) - NFFT // 2) * (FS / NFFT)


def _valid_mask(center: int) -> np.ndarray:
    f = _bin_freqs(center) - center
    return (np.abs(f) <= FS * USABLE / 2) & (np.abs(f) >= DC_GUARD_HZ)


@dataclass
class _Slice:
    center: int
    history: list = field(default_factory=list)       # recent spectra
    persist: Optional[np.ndarray] = None
    visits: int = 0


class NbfmDemod:
    """Channel at `offset` from the slice centre → 12 kHz audio, phase kept
    continuous across chunks."""

    def __init__(self, offset_hz: float):
        from scipy.signal import firwin
        self.offset = offset_hz
        self.phase = 0.0
        self.taps = firwin(129, 6500, fs=48_000)
        self.zi = np.zeros(len(self.taps) - 1, dtype=np.complex64)
        self.last = np.complex64(1)

    def __call__(self, iq: np.ndarray) -> np.ndarray:
        from scipy.signal import lfilter, resample_poly
        n = np.arange(len(iq))
        mix = np.exp(-1j * (2 * np.pi * self.offset * n / FS + self.phase)).astype(np.complex64)
        self.phase = (self.phase + 2 * np.pi * self.offset * len(iq) / FS) % (2 * np.pi)
        x = resample_poly(iq * mix, 1, FS // 48_000)                  # 48 kHz
        x, self.zi = lfilter(self.taps, 1.0, x, zi=self.zi)
        x = np.concatenate([[self.last], x])
        self.last = x[-1]
        audio = np.angle(x[1:] * np.conj(x[:-1]))                    # FM discriminator
        audio = resample_poly(audio, 1, 48_000 // AUDIO_FS)
        return np.clip(audio * 9000, -32767, 32767).astype(np.int16)


# What a hop sounds like to someone listening along: 40 ms of faint static,
# then a breath of silence — the sound of a scanner stepping.
_TICK = np.concatenate([
    (np.random.default_rng(7).normal(size=AUDIO_FS // 25) * 700).astype(np.int16),
    np.zeros(AUDIO_FS // 12, np.int16)])


@dataclass
class Catch:
    freq_hz: int
    started: float
    seconds: float
    peak_db: float
    audio: np.ndarray


class Watcher:
    """Runs on its own thread; catches go to `on_catch` from a worker thread
    so classifying one never stalls the sweep."""

    def __init__(self, on_catch: Callable[[Catch], None], gain_db: float = 40.0,
                 stop: Optional[threading.Event] = None,
                 sink: Optional[Callable[[np.ndarray], None]] = None, ppm: int = 0):
        self.on_catch = on_catch
        self.ppm = ppm
        # Listen-along: 12 kHz int16 audio — a soft tick per hop, and the
        # channel itself while holding. Called from the watcher's thread.
        self.sink = sink
        self.gain_db = gain_db
        self.stop = stop or threading.Event()
        self.slices = {c: _Slice(c) for c in FAST_HOPS + SLOW_HOPS}
        self.cooldown: dict[int, float] = {}
        self.catches: "queue.Queue[Optional[Catch]]" = queue.Queue()
        self.passes = 0

    def _schedule(self):
        slow = SLOW_HOPS[self.passes % len(SLOW_HOPS)]
        return FAST_HOPS + [slow]

    def _visit(self, dongle, center: int) -> Optional[tuple[int, float]]:
        """Measure one slice; return (freq, dB over floor) if something keyed up."""
        s = self.slices[center]
        if dongle.tune(center) is False:
            return None                      # a failed retune would read the last slice
        spec = _smooth_spectrum(dongle.read(NFFT * 32))
        s.history.append(spec)
        s.history = s.history[-FLOOR_VISITS:]
        s.visits += 1
        if s.visits < WARM_VISITS:
            return None
        floor = np.percentile(np.array(s.history[:-1]), FLOOR_PCT, axis=0)
        over = spec - floor
        hot = (over > GATE_DB) & _valid_mask(center)
        s.persist = np.where(hot, (s.persist if s.persist is not None else 0) + 1, 0)
        ready = np.where(s.persist >= PERSIST)[0]
        if not len(ready):
            return None
        best = ready[np.argmax(over[ready])]
        freq = int(round(_bin_freqs(center)[best] / 2500) * 2500)
        now = time.time()
        if any(abs(f - freq) <= COOLDOWN_SPAN_HZ and now < until for f, until in self.cooldown.items()):
            return None
        return freq, float(over[best])

    def _hold(self, dongle, center: int, freq: int, peak_db: float) -> Catch:
        """Record the channel until it's been quiet SILENCE_S, or MAX_HOLD_S."""
        demod = NbfmDemod(freq - center)
        s = self.slices[center]
        floor = np.percentile(np.array(s.history), FLOOR_PCT, axis=0)
        idx = int(np.argmin(np.abs(_bin_freqs(center) - freq)))
        chunks, quiet, started = [], 0.0, time.time()
        chunk_n = FS // 5                                      # 0.2 s
        while not self.stop.is_set() and time.time() - started < MAX_HOLD_S:
            iq = dongle.read(chunk_n)
            chunks.append(demod(iq))
            if self.sink:
                self.sink(chunks[-1])
            level = _smooth_spectrum(iq)[idx] - floor[idx]
            quiet = quiet + 0.2 if level < GATE_DB - 3 else 0.0
            if quiet >= SILENCE_S:
                break
        held = time.time() - started
        # Held the whole time: something near-constant (425.950 ran the full
        # minute eight times in an hour). Leave it for half an hour.
        self.cooldown[freq] = time.time() + (LONG_COOLDOWN_S if held >= MAX_HOLD_S - 0.5 else COOLDOWN_S)
        s.persist = None
        audio = np.concatenate(chunks) if chunks else np.zeros(0, np.int16)
        return Catch(freq, started, time.time() - started, peak_db, audio)

    def _worker(self):
        while True:
            c = self.catches.get()
            if c is None:
                return
            try:
                self.on_catch(c)
            except Exception:
                pass

    def run_pinned(self, freq_hz: int, until: float) -> None:
        """Blocking: sit on one channel until `until` (a net), recording each
        transmission. The slice is tuned 400 kHz off so the channel is clear
        of the tuner's centre spike; the channel's own level is tracked
        against its rolling floor, and a transmission is held exactly as the
        waterfall holds one."""
        from utils.radio.dongle import Dongle
        worker = threading.Thread(target=self._worker, name="scanner-catches", daemon=True)
        worker.start()
        center = freq_hz - 400_000
        self.slices.setdefault(center, _Slice(center))
        try:
            with Dongle(sample_rate=FS, gain_db=self.gain_db, ppm=self.ppm) as d:
                d.tune(center)
                idx = int(np.argmin(np.abs(_bin_freqs(center) - freq_hz)))
                s = self.slices[center]
                while not self.stop.is_set() and time.time() < until:
                    spec = _smooth_spectrum(d.read(NFFT * 32))
                    s.history = (s.history + [spec])[-FLOOR_VISITS * 4:]
                    self.passes += 1
                    if len(s.history) < WARM_VISITS:
                        continue
                    floor = np.percentile(np.array(s.history[:-1]), FLOOR_PCT, axis=0)
                    if spec[idx] - floor[idx] > GATE_DB:
                        self.catches.put(self._hold(d, center, freq_hz, float(spec[idx] - floor[idx])))
        finally:
            self.catches.put(None)

    def run(self) -> None:
        """Blocking: hop until `stop` is set. Opens and closes the dongle."""
        from utils.radio.dongle import Dongle
        worker = threading.Thread(target=self._worker, name="scanner-catches", daemon=True)
        worker.start()
        try:
            with Dongle(sample_rate=FS, gain_db=self.gain_db, ppm=self.ppm) as d:
                while not self.stop.is_set():
                    for center in self._schedule():
                        if self.stop.is_set():
                            break
                        hit = self._visit(d, center)
                        if self.sink:
                            self.sink(_TICK)
                        if hit:
                            self.catches.put(self._hold(d, center, *hit))
                    self.passes += 1
        finally:
            self.catches.put(None)


# ── Running in a child process ──────────────────────────────────────────────
# librtlsdr prints its tuner chatter ("Found Rafael Micro R820T tuner",
# "r82xx_write: i2c wr failed") from C straight to fd 2, beneath Python's
# logging — and in the bot's process that is the terminal the curses
# dashboard draws on. The watcher runs in its own process with stdout and
# stderr on /dev/null, and hands catches and listen-along audio back through
# queues.

def child_main(mode: str, freq_hz: int, until: float, gain_db: float, ppm: int,
               stop, catches, audio, passes) -> None:
    import os
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)

    def _send(c: "Catch") -> None:
        catches.put(c)

    def _sink(chunk) -> None:
        try:
            audio.put_nowait(chunk)
        except Exception:
            pass

    class _Stop:
        def is_set(self):
            return stop.is_set()

    w = Watcher(_send, gain_db=gain_db, stop=_Stop(), sink=_sink, ppm=ppm)
    try:
        if mode == "pinned":
            w.run_pinned(freq_hz, until)
        else:
            w.run()
    finally:
        passes.value = w.passes
        catches.put(None)
