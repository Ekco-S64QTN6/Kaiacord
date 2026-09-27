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
# A signal this far over its floor is taken on first sight. Averaged over 32
# frames and a 12.5 kHz channel, noise barely moves a decibel, so 16 dB is a
# transmission; waiting for a second visit a whole pass later lost every over
# shorter than a pass (a 2.5 s and a 3.5 s over, in simulation).
STRONG_DB = GATE_DB + 6
SILENCE_S = 2.0
MAX_HOLD_S = 60.0
# Long enough not to re-trigger on the tail of the transmission just released,
# short enough to catch the reply: at 30 s the answer to every first over on a
# simplex channel or a quiet repeater was ignored.
COOLDOWN_S = 3.0
LONG_COOLDOWN_S = 30 * 60        # after a hold that ran the whole MAX_HOLD_S: a near-constant carrier
# Doubled each time the same spot runs the minute again, to this: 463.7125 and
# 462.35 came back every half hour, four minutes of deafness an hour.
MAX_LONG_COOLDOWN_S = 4 * 3600
COOLDOWN_SPAN_HZ = 12_500        # one channel, whichever 2.5 kHz step a wide signal rounds to
# A near-constant carrier that wanders (424.365–424.42, 450.83–450.96 on 27
# Sept) took a full minute on each step it drifted to; its long cooldown covers
# this far either side.
DRIFT_SPAN_HZ = 75_000
AUDIO_FS = 12_000
# Following a conversation: once an over that sounds like voice ends, the
# watch stays on the channel for the reply, recording each over into the same
# catch, and goes back to hopping after FOLLOW_IDLE_S with nothing on it.
FOLLOW_IDLE_S = 15.0
FOLLOW_MAX_S = 300.0
HISS_DB = 108.6                  # NbfmDemod's output on an empty channel, per 20 ms frame above 3.2 kHz
QUIET_DB = 6.0                   # hiss this far under it: a carrier is up (noise's 5th percentile is 1.3 under)
FULL_QUIETING_DB = 10.0          # a carrier strong enough to follow: voice quieted 12–14 dB, weak fades 5–7
VOICE_SWING_DB = 3.0             # voice-band level spread under a carrier: speech swings, data and tones sit flat
SQUELCH_S = 0.4                  # a listener hears silence, not hiss, this long after a channel drops

MHZ = 1_000_000
#: The bands people talk on, visited every pass: (low, high) in Hz.
FAST_BANDS = [
    (144_000_000, 148_000_000),        # 2m ham
    (150_800_000, 162_560_000),        # MURS, VHF business and public safety, marine, railroad, NOAA
    (440_000_000, 450_000_000),        # 70cm repeaters
    (460_000_000, 470_000_000),        # UHF business, FRS / GMRS
]
#: Wider, quieter territory: SLOW_PER_PASS of these slices per pass, in rotation.
SLOW_BANDS = [
    (222_000_000, 225_000_000),        # 1.25m ham
    (420_000_000, 440_000_000),        # 70cm below the repeaters
    (450_000_000, 460_000_000),        # UHF business
    (926_200_000, 928_200_000),        # 900 MHz ham repeater outputs
]
SLOW_PER_PASS = 3
NUDGE_HZ = 90_000                     # how far a centre may move off its tile
HOLE_MARGIN_HZ = 7_500                # a channel this close to the guard edge counts as in it


def _tile(lo: int, hi: int, avoid: list[int]) -> list[int]:
    """Slice centres covering lo..hi with no gaps, each moved (by up to
    NUDGE_HZ) until no channel in `avoid` sits in its centre guard.

    The plan this replaced had fixed round centres: 147.000, 443.000, 445.000
    and 449.000 are all common repeater outputs and sat in the tuner's blind
    centre, 80 kHz between neighbouring slices was never looked at, and whole
    stretches (railroad, 158.4–160.6, 463.8–466.3) weren't visited at all —
    two of the notebook channels among them."""
    half = int(FS * USABLE / 2)
    step = 2 * half - 2 * NUDGE_HZ                     # overlap enough to nudge without opening a gap
    first, last = lo - NUDGE_HZ + half, hi + NUDGE_HZ - half
    n = max(1, -(-(last - first) // step) + 1)
    centres = [first + round(i * (last - first) / max(1, n - 1)) for i in range(n)] if n > 1 else [(lo + hi) // 2]
    out = []
    guard = DC_GUARD_HZ + HOLE_MARGIN_HZ
    for c in centres:
        for k in range(0, NUDGE_HZ // 2500 + 1):
            for cand in ((c + k * 2500, c - k * 2500) if k else (c,)):
                if not any(abs(f - cand) <= guard for f in avoid):
                    out.append(cand)
                    break
            else:
                continue
            break
        else:
            out.append(c)                              # nothing clear within reach: keep the tile
    return out


def hop_plan(avoid: Optional[list[int]] = None) -> tuple[list[int], list[int]]:
    """(fast, slow) slice centres for the bands above, clear of `avoid` — the
    seeded and configured channels (scanner.seed_channels)."""
    avoid = sorted(avoid or [])
    fast = [c for lo, hi in FAST_BANDS for c in _tile(lo, hi, avoid)]
    slow = [c for lo, hi in SLOW_BANDS for c in _tile(lo, hi, avoid)]
    return fast, slow


def covered(freq_hz: int, centres: list[int]) -> bool:
    """Whether a slice in `centres` sees freq_hz outside its centre guard."""
    half = FS * USABLE / 2
    return any(DC_GUARD_HZ <= abs(freq_hz - c) <= half for c in centres)


FAST_HOPS, SLOW_HOPS = hop_plan()


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


FRAME = AUDIO_FS // 50                                        # 20 ms


def _frame_levels(audio: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per 20 ms frame of demodulated audio: the hiss level above 3.2 kHz and
    the voice-band level, both in dB."""
    k = len(audio) // FRAME
    if not k:
        return np.zeros(0), np.zeros(0)
    frames = audio[:k * FRAME].astype(float).reshape(k, FRAME) * np.hanning(FRAME)
    sp = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    f = np.fft.rfftfreq(FRAME, 1 / AUDIO_FS)
    hiss = 10 * np.log10(sp[:, f > 3200].sum(axis=1) + 1e-9)
    voice = 10 * np.log10(sp[:, (f >= 300) & (f <= 2500)].sum(axis=1) + 1e-9)
    return hiss, voice


def carried(audio: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Which frames had a carrier under them, and the voice-band levels.

    FM demodulates an empty channel to hiss at a fixed level, HISS_DB, since
    the discriminator reads phase and not amplitude; a carrier quiets it. The
    reference is that level rather than the recording's own tail, because a
    hold cut off at its time limit has no tail to measure."""
    hiss, voice = _frame_levels(audio)
    return hiss < HISS_DB - QUIET_DB, voice


def carried_audio(audio: np.ndarray) -> np.ndarray:
    """Only the frames with a carrier under them: what a measure of the
    signal should see, without the squelch tail and the gaps between overs."""
    on, _ = carried(audio)
    k = len(on)
    return audio[:k * FRAME].reshape(k, FRAME)[on].ravel() if k else audio[:0]


def carrier_seconds(audio: np.ndarray) -> float:
    return float(carried(audio)[0].sum()) / 50


def voice_like(audio: np.ndarray) -> bool:
    """Speech under a carrier, from level alone: syllables swing the voice
    band several dB, where a data burst, a tone or a dead carrier holds flat.
    Measured on the 27 Sept clips, voice spread 4.2–9.7 dB and data 0.4–1.8.

    Only under a full-quieting carrier: a weak signal fading in and out also
    swings, through the noise riding on it, and was followed for five minutes."""
    hiss, voice = _frame_levels(audio)
    on = hiss < HISS_DB - QUIET_DB
    if on.sum() < 50 or HISS_DB - np.median(hiss[on]) < FULL_QUIETING_DB:
        return False
    # And steadily: a fluttering carrier drops in and out of quieting several
    # times a second (469.04: 57% of its carried frames fully quieted, 7.7
    # flips a second); every voice clip held 90% or more and 0.2 flips or fewer.
    first, last = np.where(on)[0][[0, -1]]
    flips = np.abs(np.diff(on[first:last + 1].astype(int))).sum() / ((last - first + 1) / 50)
    if (hiss[on] < HISS_DB - FULL_QUIETING_DB).mean() < 0.85 or flips > 1.0:
        return False
    return float(np.std(voice[on])) >= VOICE_SWING_DB


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
                 sink: Optional[Callable[[np.ndarray], None]] = None, ppm: int = 0,
                 hops: Optional[tuple[list[int], list[int]]] = None):
        self.on_catch = on_catch
        self.ppm = ppm
        # Listen-along: 12 kHz int16 audio — a soft tick per hop, and the
        # channel itself while holding. Called from the watcher's thread.
        self.sink = sink
        self.gain_db = gain_db
        self.stop = stop or threading.Event()
        self.fast, self.slow = hops or (FAST_HOPS, SLOW_HOPS)
        self.slices = {c: _Slice(c) for c in self.fast + self.slow}
        self.cooldown: dict[int, float] = {}
        self.constant: dict[int, float] = {}     # freq -> the long cooldown it was last given
        self.catches: "queue.Queue[Optional[Catch]]" = queue.Queue()
        self.passes = 0

    def _schedule(self):
        k = (self.passes * SLOW_PER_PASS) % max(1, len(self.slow))
        return self.fast + [self.slow[(k + i) % len(self.slow)] for i in range(min(SLOW_PER_PASS, len(self.slow)))]

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
        valid = _valid_mask(center)
        # A transmission is a channel standing over the rest of its slice; a
        # rise in the noise lifts the whole slice. Measured over the slice's
        # typical rise, not the floor alone: on 27 Sept a household noise
        # source put the UHF slices 10+ dB over their floors and the watch held
        # hiss for a minute at a time on frequency after frequency.
        over = over - np.median(over[valid])
        hot = (over > GATE_DB) & valid
        s.persist = np.where(hot, (s.persist if s.persist is not None else 0) + 1, 0)
        ready = np.where((s.persist >= PERSIST) | (hot & (over >= STRONG_DB)))[0]
        if not len(ready):
            return None
        best = ready[np.argmax(over[ready])]
        freq = int(round(_bin_freqs(center)[best] / 2500) * 2500)
        now = time.time()
        # Only a long cooldown (a near-constant carrier) runs past a few seconds.
        if any(abs(f - freq) <= (DRIFT_SPAN_HZ if until - now > COOLDOWN_S * 10 else COOLDOWN_SPAN_HZ)
               and now < until for f, until in self.cooldown.items()):
            return None
        return freq, float(over[best])

    def _hold(self, dongle, center: int, freq: int, peak_db: float) -> Catch:
        """Record the channel until it's been quiet SILENCE_S, or MAX_HOLD_S.

        If what was recorded sounds like voice, stay for the reply: each over
        that follows within FOLLOW_IDLE_S goes into the same catch, with only
        SILENCE_S of each gap kept, until the channel has been idle that long
        or FOLLOW_MAX_S has passed."""
        demod = NbfmDemod(freq - center)
        s = self.slices[center]
        floor = np.percentile(np.array(s.history), FLOOR_PCT, axis=0)
        idx = int(np.argmin(np.abs(_bin_freqs(center) - freq)))
        valid = _valid_mask(center)
        chunks, quiet, started, resumed = [], 0.0, time.time(), None
        follow = constant = False
        chunk_n = FS // 5                                      # 0.2 s
        while not self.stop.is_set():
            iq = dongle.read(chunk_n)
            audio = demod(iq)
            over = _smooth_spectrum(iq) - floor
            # Over the slice's own rise, as the trigger is: against the floor
            # alone, a hold begun during a rise in the noise never went quiet.
            level = over[idx] - np.median(over[valid])
            if quiet >= SILENCE_S:
                # Between overs only a full key-up, as the trigger takes, resumes.
                if level > GATE_DB:
                    quiet, resumed = 0.0, len(chunks)
                else:
                    quiet += 0.2
            else:
                quiet = quiet + 0.2 if level < GATE_DB - 3 else 0.0
            if quiet <= SILENCE_S:
                chunks.append(audio)
            if self.sink:
                self.sink(audio if quiet < SQUELCH_S else np.zeros_like(audio))
            held = time.time() - started
            if not follow:
                if held >= MAX_HOLD_S:
                    # Keyed the whole minute: a stuck or constant carrier, or a
                    # linked repeater holding its transmitter up through a
                    # conversation (145.690 did, and was then locked out for
                    # half an hour). Speech keeps it followed.
                    if not voice_like(np.concatenate(chunks)):
                        constant = True
                        break
                    follow = True
                if quiet >= SILENCE_S:
                    if not voice_like(np.concatenate(chunks)):
                        break
                    follow = True
            elif resumed is not None and (quiet >= SILENCE_S or len(chunks) - resumed >= MAX_HOLD_S * 5):
                # A reply is kept only if a carrier was under it: noise that
                # crossed the gate would otherwise hold the channel open.
                if carrier_seconds(np.concatenate(chunks[resumed:])) < 0.5:
                    del chunks[resumed:]
                    break
                resumed = None
            elif quiet >= SILENCE_S + FOLLOW_IDLE_S or held >= FOLLOW_MAX_S:
                break
        # Held the whole time: something near-constant (425.950 ran the full
        # minute eight times in an hour). Leave it for half an hour.
        wait = COOLDOWN_S
        if constant:
            # Again within twice its last lockout, near the same spot: longer.
            prior = [v for f, v in self.constant.items() if abs(f - freq) <= DRIFT_SPAN_HZ
                     and self.cooldown.get(f, 0) + v > time.time()]
            wait = min(MAX_LONG_COOLDOWN_S, 2 * max(prior)) if prior else LONG_COOLDOWN_S
            self.constant[freq] = wait
        self.cooldown[freq] = time.time() + wait
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
                    over = spec - floor
                    level = over[idx] - np.median(over[_valid_mask(center)])
                    if level > GATE_DB:
                        self.catches.put(self._hold(d, center, freq_hz, float(level)))
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
               stop, catches, audio, passes, hops=None) -> None:
    import os
    # The bot leaves by os._exit, which skips multiprocessing's cleanup of
    # daemon children: an orphaned watcher kept the dongle, and the next boot's
    # watch failed "busy or could not be opened" every fifteen minutes.
    parent = os.getppid()
    from utils.radio.kiwi import _die_with_parent
    _die_with_parent()
    if os.getppid() != parent:           # the parent went before the signal was armed
        os._exit(0)
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

    w = Watcher(_send, gain_db=gain_db, stop=_Stop(), sink=_sink, ppm=ppm, hops=hops)
    try:
        if mode == "pinned":
            w.run_pinned(freq_hz, until)
        else:
            w.run()
    finally:
        passes.value = w.passes
        catches.put(None)
