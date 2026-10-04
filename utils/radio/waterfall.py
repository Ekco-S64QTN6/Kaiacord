"""Continuous waterfall watch: hop the voice bands, catch whatever keys up.

A channel that carries one transmission an hour is missed by any scheme that
visits it for a few seconds per cycle. This hops the dongle across the bands
people talk on — every slice of the busy bands each pass (hop_plan), a few of
the quieter ones in rotation, a pass every two or three seconds — and keeps, for every frequency bin, a rolling floor of what that bin
usually reads. A bin that stands well over its own floor on consecutive visits
is a transmission: the watcher holds on that slice, demodulates the channel,
records until it has been quiet a couple of seconds — longer if it is voice,
to catch the reply — and goes back to hopping.

The approach — a rolling per-channel noise floor (low percentile of recent
frames), activation only after persistence over consecutive frames, then
scan-and-hold with a silence release and a per-channel cooldown — follows
radiotui (github.com/n0nuser/radiotui, MIT). A constant carrier (NOAA, a
birdie) raises its own floor and stops triggering within a minute; one that
runs a whole hold anyway is left alone for a lengthening cooldown.
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
# What a listener hears of a hold (Squelch): a carrier held OPEN_S opens it,
# dropouts up to GAP_S don't break the run. A pulsing beacon (463.71875: a
# 0.2 s burst every 1.5 s) and a rise in the noise never open it.
OPEN_S = 0.4
GAP_S = 0.06
# A hold whose squelch has not opened in this long is a pulse train or noise,
# not a transmission: the watch goes back to hopping and leaves the channel
# alone for PULSED_COOLDOWN_S, doubling on each return as a constant carrier's
# lockout does. The beacon above otherwise held the watch the whole minute.
PULSED_DECIDE_S = 4.0
PULSED_COOLDOWN_S = 5 * 60

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


def _power(iq: np.ndarray) -> np.ndarray:
    """Power per FFT bin, averaged over frames."""
    frames = len(iq) // NFFT
    x = iq[: frames * NFFT].reshape(frames, NFFT) * np.hanning(NFFT)
    return np.mean(np.abs(np.fft.fftshift(np.fft.fft(x, axis=1), axes=1)) ** 2, axis=0)


def _db(p: np.ndarray, width_hz: float) -> np.ndarray:
    width = max(1, int(width_hz / (FS / NFFT)))
    return 10 * np.log10(np.convolve(p, np.ones(width) / width, mode="same") + 1e-12)


def _smooth_spectrum(iq: np.ndarray) -> np.ndarray:
    """Power (dB) per FFT bin, averaged over frames and smoothed across ~12 kHz
    so a whole NBFM channel reads as one peak."""
    return _db(_power(iq), 12_500)


def _spectra(iq: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(the trigger's smoothed spectrum, the dashboard's): the dashboard's is
    smoothed over only two bins, so zooming in shows channels apart."""
    p = _power(iq)
    return _db(p, 12_500), _db(p, 2 * FS / NFFT)


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


def speech_audio(audio: np.ndarray, pad_frames: int = 3, gap_s: float = 0.3) -> np.ndarray:
    """What to hand a transcriber: each carried run with `pad_frames` either
    side (word onsets sit under the carrier's first frames), runs under 0.2 s
    dropped, a short silence between them. A clip that was mostly squelch
    tail and gaps — 66 s of hiss round a 2 s "audio check" — gave Whisper the
    hiss to write words onto, and diluted its speech scores."""
    on, _ = carried(audio)
    k = len(on)
    if not k or not on.any():
        return audio[:0]
    keep = on.copy()
    for d in range(1, pad_frames + 1):
        keep[d:] |= on[:-d]
        keep[:-d] |= on[d:]
    frames = audio[:k * FRAME].reshape(k, FRAME)
    edges = np.flatnonzero(np.diff(np.concatenate(([0], keep.astype(np.int8), [0]))))
    gap = np.zeros(int(gap_s * AUDIO_FS), dtype=audio.dtype)
    runs = [frames[a:b].ravel() for a, b in zip(edges[::2], edges[1::2]) if (b - a) * FRAME >= 0.2 * AUDIO_FS]
    if not runs:
        return audio[:0]
    out = [runs[0]]
    for r in runs[1:]:
        out += [gap, r]
    return np.concatenate(out)


#: A catch is packet data (APRS, AX.25) when the Bell 202 tones hold this share
#: of at least AFSK_MIN_FRAMES carrier frames. Measured: APRS packets off the
#: air 52–62%, idle hiss 0%, the most tone-like voice clip 36%; a Morse ID hits
#: the tones but keys for only a few frames.
AFSK_SHARE = 0.45
AFSK_MIN_FRAMES = 10


def afsk_profile(audio: np.ndarray, rate: int = 12000) -> tuple[float, int]:
    """(share of carrier frames whose voice-band energy sits on the 1200/2200 Hz
    pair, number of carrier frames), in 50 ms frames. A frame has a carrier
    when the demodulated noise above 3 kHz has gone quiet under it."""
    a = np.asarray(audio, dtype=float)
    n = rate // 20
    if len(a) < n * 2:
        return 0.0, 0
    k = len(a) // n
    frames = a[:k * n].reshape(k, n) * np.hanning(n)
    sp = np.abs(np.fft.rfft(frames, axis=1)) ** 2
    f = np.fft.rfftfreq(n, 1 / rate)
    band = (f > 300) & (f < 3000)
    tones = ((abs(f - 1200) < 150) | (abs(f - 2200) < 150)) & band
    total = sp[:, f > 100].sum(axis=1) + 1e-9
    carrier = sp[:, f > 3000].sum(axis=1) / total < 0.15
    if not carrier.any():
        return 0.0, 0
    on_tones = sp[carrier][:, tones].sum(axis=1) / (sp[carrier][:, band].sum(axis=1) + 1e-9) > 0.6
    return float(on_tones.mean()), int(carrier.sum())


def is_packet(audio: np.ndarray) -> bool:
    share, frames = afsk_profile(audio)
    return frames >= AFSK_MIN_FRAMES and share >= AFSK_SHARE


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


class Squelch:
    """What a listener hears of a hold. Audio passes only where a carrier ran
    OPEN_S or longer (dropouts under GAP_S bridged), plus SQUELCH_S after it
    drops; everything else is silence. Output runs OPEN_S behind the input, so
    the run that opens it is heard from its first syllable."""

    def __init__(self):
        self.flags = np.zeros(0, bool)
        self.pending: list = []
        self.sent = 0                      # frames already emitted
        self.opened = False                # a run has opened it, this hold

    def _mask(self) -> np.ndarray:
        on = self.flags.copy()
        gap, need, hang = round(GAP_S * 50), round(OPEN_S * 50), round(SQUELCH_S * 50)
        edges = np.flatnonzero(np.diff(np.concatenate(([0], on.astype(np.int8), [0]))))
        starts, ends = edges[::2], edges[1::2]
        for a, b in zip(starts[1:], ends[:-1]):            # bridge short dropouts
            if a - b <= gap:
                on[b:a] = True
        edges = np.flatnonzero(np.diff(np.concatenate(([0], on.astype(np.int8), [0]))))
        out = np.zeros(len(on), bool)
        for a, b in zip(edges[::2], edges[1::2]):
            if b - a >= need:
                out[max(0, a - 2):min(len(on), b + hang)] = True
                self.opened = True
        return out

    def push(self, audio: np.ndarray, final: bool = False) -> list:
        """Feed one chunk; returns the chunks now ready for the listener."""
        if len(audio):
            self.flags = np.concatenate([self.flags, carried(audio)[0]])
            self.pending.append(audio)
        mask = self._mask()
        ready = len(self.flags) - (0 if final else round(OPEN_S * 50))
        out = []
        while self.pending and self.sent + len(self.pending[0]) // FRAME <= ready:
            chunk = self.pending.pop(0)
            n = len(chunk) // FRAME
            keep = np.repeat(mask[self.sent:self.sent + n], FRAME)
            heard = np.zeros_like(chunk)
            heard[:n * FRAME] = np.where(keep, chunk[:n * FRAME], 0)
            out.append(heard)
            self.sent += n
        return out


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
                 hops: Optional[tuple[list[int], list[int]]] = None,
                 scope: Optional[Callable[[dict], None]] = None,
                 exempt: Optional[list[int]] = None):
        self.on_catch = on_catch
        self.ppm = ppm
        # The receiver dashboard (rx_dashboard): every spectrum measured, and
        # each pass's lockouts. Called from the watcher's thread; must not block.
        self.scope = scope
        # Listen-along and the dashboard's monitor: 12 kHz int16 audio of a
        # hold, through the Squelch. Nothing while hopping. Called from the
        # watcher's thread.
        self.sink = sink
        # Channels whose audio is hiss-shaped by nature (configured `mode:
        # digital`): never released as a pulse train.
        self.exempt = list(exempt or [])
        self.gain_db = gain_db
        self.stop = stop or threading.Event()
        self.fast, self.slow = hops or (FAST_HOPS, SLOW_HOPS)
        self.slices = {c: _Slice(c) for c in self.fast + self.slow}
        self.cooldown: dict[int, float] = {}
        self.reach: dict[int, int] = {}          # freq -> how far either side its cooldown covers
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
        spec, shown = _spectra(dongle.read(NFFT * 32))
        self._show(center, shown, "hop")
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
        if any(abs(f - freq) <= self.reach.get(f, COOLDOWN_SPAN_HZ) and now < until
               for f, until in self.cooldown.items()):
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
        follow = constant = pulsed = False
        squelch = Squelch()
        exempt = any(abs(f - freq) <= 5000 for f in self.exempt)
        chunk_n = FS // 5                                      # 0.2 s
        while not self.stop.is_set():
            iq = dongle.read(chunk_n)
            audio = demod(iq)
            spec, shown = _spectra(iq)
            over = spec - floor
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
            heard = squelch.push(audio)
            if self.sink:
                for h in heard:
                    self.sink(h)
            self._show(center, shown, "follow" if follow else "hold", freq, float(level),
                       bool(squelch.flags[-round(SQUELCH_S * 50):].any()) and squelch.opened)
            held = time.time() - started
            if not follow and not exempt and held >= PULSED_DECIDE_S and not squelch.opened:
                pulsed = True
                break
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
        # Held the whole minute with no speech: something near-constant (425.950
        # ran the full minute eight times in an hour). Left alone for
        # LONG_COOLDOWN_S, doubling on each return.
        if self.sink:
            for h in squelch.push(np.zeros(0, np.int16), final=True):
                self.sink(h)
        wait = COOLDOWN_S
        if constant or pulsed:
            # Again within twice its last lockout, near the same spot: longer.
            # A pulse train stays put, so its lockout covers its own channel only.
            near = DRIFT_SPAN_HZ if constant else COOLDOWN_SPAN_HZ
            prior = [v for f, v in self.constant.items() if abs(f - freq) <= near
                     and self.cooldown.get(f, 0) + v > time.time()]
            wait = min(MAX_LONG_COOLDOWN_S, 2 * max(prior)) if prior else \
                (LONG_COOLDOWN_S if constant else PULSED_COOLDOWN_S)
            self.constant[freq] = wait
        self.cooldown[freq] = time.time() + wait
        self.reach[freq] = DRIFT_SPAN_HZ if constant else COOLDOWN_SPAN_HZ
        s.persist = None
        audio = np.concatenate(chunks) if chunks else np.zeros(0, np.int16)
        return Catch(freq, started, time.time() - started, peak_db, audio)

    #: Bins sent to the dashboard per slice: its lightly smoothed spectrum, every 2nd bin.
    SCOPE_STEP = 2

    def _show(self, center: int, spec: np.ndarray, state: str, freq: int = 0,
              level: float = 0.0, open_: bool = False) -> None:
        if self.scope is None:
            return
        try:
            self.scope({"kind": "spec", "t": time.time(), "center": int(center), "state": state,
                        "freq": int(freq), "level": round(level, 1), "open": bool(open_), "pass": self.passes,
                        "spec": spec[::self.SCOPE_STEP].astype(np.float16)})
        except Exception:
            pass

    def _show_pass(self) -> None:
        if self.scope is None:
            return
        now = time.time()
        try:
            self.scope({"kind": "pass", "t": now, "pass": self.passes,
                        "lockouts": [(int(f), round(u - now)) for f, u in self.cooldown.items() if u - now > COOLDOWN_S]})
        except Exception:
            pass

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
                    spec, shown = _spectra(d.read(NFFT * 32))
                    self._show(center, shown, "pinned", freq_hz)
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
                        if hit:
                            self.catches.put(self._hold(d, center, *hit))
                    self.passes += 1
                    self._show_pass()
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
               stop, catches, audio, passes, hops=None, spectra=None, exempt=None) -> None:
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

    def _scope(msg) -> None:
        try:
            spectra.put_nowait(msg)
        except Exception:
            pass                             # nobody is draining it: the dashboard simply misses a frame

    class _Stop:
        def is_set(self):
            return stop.is_set()

    w = Watcher(_send, gain_db=gain_db, stop=_Stop(), sink=_sink, ppm=ppm, hops=hops,
                scope=_scope if spectra is not None else None, exempt=exempt)
    try:
        if mode == "pinned":
            w.run_pinned(freq_hz, until)
        else:
            w.run()
    finally:
        passes.value = w.passes
        catches.put(None)
