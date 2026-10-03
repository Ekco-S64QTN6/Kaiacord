"""Records: a set from the local music library, mixed record to record.

`!music records` plays the crate in `library.py` the way a DJ would: each next
record chosen to sit with the last in key and tempo, stretched to its tempo
(ffmpeg's rubberband, which keeps the pitch and the kicks where they were), its
bar one dropped on a phrase of the record playing, and blended per band over
32–128 beats — or, where the beats cannot be laid over each other, faded over
eight bars. All of it is ffmpeg and NumPy on the CPU: no model, no VRAM.

The free deck can also be worked by hand from the DJ booth: a record loaded
onto it (`load`), its cue point moved (`set_cue`), played synced and on the
beat (`play_hand`) while the faders do the mix, taking over once the record on
air has gone quiet — or finished by Kaia (`finish`).

Same contract as the Strudel source: `read()` hands discord.py one 20 ms frame
every 20 ms and never blocks; ffmpeg output is pumped into a buffer on a
thread, and anything slow (choosing, measuring, starting ffmpeg) happens on
another before its frames are needed.
"""
from __future__ import annotations

import asyncio
import functools
import random
import re
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
from pathlib import Path

try:
    import discord
    _AudioSource = discord.AudioSource
except Exception:                      # pragma: no cover
    _AudioSource = object

from utils.audio import library
from utils.infrastructure.logging.kaia_logger import log_action, log_debug, log_error, log_info, log_warning
from utils.infrastructure.system.gc_quiet import settle

RATE = 48000
FRAME_MS = 20
FRAME_BYTES = RATE * 2 * 2 * FRAME_MS // 1000          # s16le stereo
FRAMES_PER_S = 1000 // FRAME_MS
SILENCE = b"\x00" * FRAME_BYTES
#: A record shorter than this is not crossfaded into: there is no room.
MIN_RECORD_S = 30.0


def probe_seconds(path: str) -> Optional[float]:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nokey=1:noprint_wrappers=1", path],
            capture_output=True, text=True, timeout=20)
        return float(out.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


#: Every record is brought to this integrated loudness (EBU R128, what the ear
#: hears as loud), so the next one is not louder than the last. A record is
#: raised only as far as its true peak allows, plus BOOST_HEADROOM_DB the soft
#: limiter takes; it is lowered as far as needed whatever its peak.
TARGET_LUFS = -11.0
BOOST_HEADROOM_DB = 2.0


@functools.lru_cache(maxsize=1024)
def gain_db(path: str) -> float:
    """The gain that brings a record to TARGET_LUFS. 0 if it cannot be measured."""
    try:
        out = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", path,
                              "-af", "ebur128=peak=true:framelog=quiet", "-f", "null", "-"],
                             capture_output=True, text=True, timeout=90).stderr
        lufs = float(re.findall(r"I:\s*(-?[\d.]+) LUFS", out)[-1])
        peak = float(re.findall(r"Peak:\s*(-?[\d.]+) dBFS", out)[-1])
    except (OSError, IndexError, ValueError, subprocess.SubprocessError):
        return 0.0
    gain = TARGET_LUFS - lufs
    if gain > 0:
        gain = min(gain, max(0.0, -1.0 - peak) + BOOST_HEADROOM_DB)
    return round(max(-12.0, min(gain, 12.0)), 1)


def open_pcm(path: str, ratio: float = 1.0, gain: float = 0.0, offset: float = 0.0,
             semitones: int = 0) -> subprocess.Popen:
    """ffmpeg decoding a record to 48 kHz stereo s16le from `offset` seconds
    of its own time, stretched by `ratio` (`beatgrid.stretch_filter`: tempo
    changed, pitch and kick timing kept), its key moved by `semitones`."""
    from utils.audio.beatgrid import stretch_filter
    args = ["ffmpeg", "-nostdin", "-loglevel", "error"]
    if offset > 0:
        args += ["-ss", f"{offset:.4f}"]
    args += ["-i", path]
    filters = []
    if (stretch := stretch_filter(ratio, semitones)):
        filters.append(stretch)
    if abs(gain) >= 0.1:
        filters.append(f"volume={gain:.1f}dB")
    if filters:
        args += ["-af", ",".join(filters)]
    args += ["-f", "s16le", "-ar", str(RATE), "-ac", "2", "pipe:1"]
    return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)


FRAME_SAMPLES = RATE * FRAME_MS // 1000
#: The blend: this many beats from the incoming record's first downbeat to the
#: outgoing record gone. The bass swaps halfway, on a bar.
MIX_BEATS = 64
#: Cut transitions (no common tempo, or no clear beat): the outgoing record
#: fades over this many seconds, ending on its bar, and the next starts clean.
CUT_FADE_S = 1.5
#: Both records need a beat at least this clear (`beatgrid.Grid.contrast`) for
#: their grooves to be laid over each other. Four-on-the-floor dance records
#: measure 4.2 and up where they are mixed; rock, breaks and sparse intros
#: (Big Country, Evil Nine, an ambient opening) measure 1.8–3.3, and blending
#: those beat against beat is a clash. Below it the transition is a cut on the bar.
BLEND_CONTRAST = 3.5
#: A transition that cannot be beat-matched — a loose or beatless record on
#: either side, tempos too far apart — is a fade over this many bars: the new
#: record from its first sound, the two crossfaded equal-power, the basslines
#: handed over halfway. Halved where the outgoing has no room for it.
FADE_BARS = 8
#: The kick cross-correlation may move the incoming record by at most this
#: much. The counted grids land within a few ms (click tracks; a 2 ms comb at
#: a real mix point agreed to 1 ms); larger corrections came from sparse
#: intros and basslines the correlation latched onto.
MAX_FINE_S = 0.020
#: A blend leaves the incoming record at least this long to play on its own.
IN_LEFT_S = 30.0
#: How much of the incoming record before its first beat is decoded in a blend.
PREROLL_S = 1.0
#: A gap between frame requests longer than this is counted as late.
LATE_S = 0.06


#: The mixer's three bands: LOW under this, HIGH over MID_TOP_HZ, MID between.
#: The automix swaps the bass at LOW_TOP_HZ; the booth's EQ uses all three.
LOW_TOP_HZ = 180
MID_TOP_HZ = 2500


def _bands():
    from scipy.signal import butter
    return (butter(2, LOW_TOP_HZ, btype="low", fs=RATE, output="sos"),
            butter(2, MID_TOP_HZ, btype="high", fs=RATE, output="sos"))


_SOS = None


class Deck:
    """One record being decoded: frames pumped from a byte stream into a buffer.

    `pad` samples of silence go in front, so the record can start part-way
    through a 20 ms frame — which is how its first downbeat is put exactly on
    the outgoing record's bar rather than up to 20 ms off it."""

    def __init__(self, record: library.Record, ratio: float, seconds: float,
                 stream_factory: Callable[..., object] = open_pcm, buffer_frames: int = 150,
                 gain: float = 0.0, pad: int = 0, offset: float = 0.0, semitones: int = 0):
        self.record = record
        self.ratio = ratio
        self.gain = gain
        self.semitones = int(semitones)                     # key moved by key sync
        self.grid = None                                    # beatgrid.Grid of its opening, for display
        self.slot = 1                                       # which CDJ: records alternate 1, 2, 1…
        self.loaded_at = time.time()
        self.pad = max(0, int(pad))
        self.offset = max(0.0, offset)                      # seconds of the record skipped, own time
        self.total_frames = int(((seconds - self.offset) / ratio * RATE + self.pad) / FRAME_SAMPLES)
        self.played = 0
        extra = {**({"gain": gain} if gain else {}), **({"offset": self.offset} if self.offset else {}),
                 **({"semitones": self.semitones} if self.semitones else {})}
        self._proc = stream_factory(record.path, ratio, **extra)
        self._frames: deque[bytes] = deque()
        self._lock = threading.Lock()
        self._room = threading.Semaphore(buffer_frames)
        self._eof = False
        self._closed = False
        self._zi = None
        threading.Thread(target=self._pump, daemon=True, name="kaia-records-deck").start()

    def _pump(self) -> None:
        out = getattr(self._proc, "stdout", self._proc)
        carry = b"\x00" * (self.pad * 4)                    # s16le stereo: 4 bytes a sample
        try:
            while not self._closed:
                self._room.acquire()
                need = FRAME_BYTES - len(carry)
                chunk = carry + (out.read(need) if need > 0 else b"")
                carry = b""
                if len(chunk) > FRAME_BYTES:
                    chunk, carry = chunk[:FRAME_BYTES], chunk[FRAME_BYTES:]
                if not chunk:
                    break
                if len(chunk) < FRAME_BYTES:
                    chunk = chunk + b"\x00" * (FRAME_BYTES - len(chunk))
                with self._lock:
                    self._frames.append(chunk)
        except Exception as e:
            log_debug(f"[records] deck read ended: {e}")
        self._eof = True

    def ready(self, frames: int = 25) -> bool:
        with self._lock:
            return len(self._frames) >= frames or self._eof

    def frame(self) -> Optional[bytes]:
        """The next frame; silence if decoding is behind; None once the record is over."""
        with self._lock:
            if self._frames:
                self.played += 1
                self._room.release()
                return self._frames.popleft()
        return None if self._eof else SILENCE

    def at(self, frames: Optional[int] = None) -> float:
        """Seconds into the record as played (stretched) at the start of frame `frames`."""
        n = self.played if frames is None else frames
        return (n * FRAME_SAMPLES - self.pad) / RATE + self.offset / self.ratio

    @property
    def key(self) -> Optional[str]:
        """The key it is sounding in: its own, moved by any key sync."""
        return library.shift_key(self.record.key, self.semitones)

    @property
    def remaining(self) -> int:
        return max(0, self.total_frames - self.played)

    @property
    def end(self) -> float:
        return self.at(self.total_frames)

    def split(self, frame: bytes) -> tuple:
        """(low, mid, high) of a frame as float stereo, filtered with carried
        state so consecutive frames join without a seam. The three sum back to
        the frame exactly."""
        global _SOS
        from scipy.signal import sosfilt
        if _SOS is None:
            _SOS = _bands()
        lo_sos, hi_sos = _SOS
        x = np.frombuffer(frame, dtype=np.int16).astype(np.float32).reshape(-1, 2)
        if self._zi is None:
            self._zi = (np.zeros((lo_sos.shape[0], 2, 2)), np.zeros((hi_sos.shape[0], 2, 2)))
        low, zl = sosfilt(lo_sos, x, axis=0, zi=self._zi[0])
        high, zh = sosfilt(hi_sos, x, axis=0, zi=self._zi[1])
        self._zi = (zl, zh)
        return low, x - low - high, high

    def close(self) -> None:
        self._closed = True
        self._room.release()
        proc = self._proc
        try:
            if hasattr(proc, "kill"):
                proc.kill()
        except Exception:
            pass


@dataclass
class Next:
    """The record chosen to come next, analysed and waiting."""
    record: library.Record
    seconds: float
    gain: float = 0.0
    grid: Optional["beatgrid.Grid"] = None
    #: Seconds to its first sound: a fade starts it there, not in its silence.
    lead: float = 0.0
    #: The bar (from bar one) its bassline comes in on, if found: a blend
    #: starts it so that bar lands on the bass swap.
    bass_in: Optional[int] = None


@dataclass
class Plan:
    """When and how the next record comes in, in seconds of the outgoing record
    as played. A blend: the incoming starts at `start` so its first downbeat
    lands on the outgoing bar at `drop`; its top end rises over `length/2`, the
    bass swaps on the bar halfway, the outgoing top falls away by
    `drop + length`. A cut: the outgoing fades out by `drop` and the next
    record starts there."""
    kind: str
    start: float
    drop: float
    length: float
    beat: float
    ratio: float
    nxt: Next
    #: Seconds of the incoming record (its own time) skipped: its muted run-up
    #: to the first beat, so a skip does not wait out a long intro.
    offset: float = 0.0
    mode: str = "skip"
    why: str = ""
    #: Why it is not a blend: "beat" (not steady or bar unknown), "tempo",
    #: "room" (the blend would not fit before the music ends), or "".
    fallback: str = ""

    @property
    def done(self) -> float:
        return self.drop + (self.length if self.kind in ("blend", "fade", "out") else 0.0)


def plan_transition(now: float, out_ratio: float, out_grid, out_end: float, nxt: Next,
                    mode: str = "skip", mix_beats: int = MIX_BEATS, lead: float = 0.4) -> Plan:
    """Plan the next transition from where the outgoing record is (`now`).

    A blend needs both beats clear (BLEND_CONTRAST) and a common tempo within
    stretching range; otherwise it is a cut, which never overlaps two grooves."""
    in_grid = nxt.grid
    playing_bpm = out_grid.bpm * out_ratio if out_grid else None
    # Steady, and with both bars known: kicks on kicks is not enough, the
    # incoming's bar one has to fall on a bar one, or its claps land on the
    # outgoing's kicks and its phrases start mid-bar.
    steady = bool(out_grid and in_grid and min(out_grid.contrast, in_grid.contrast) >= BLEND_CONTRAST
                  and out_grid.bar_known and in_grid.bar_known)
    ratio = library.tempo_ratio(playing_bpm, in_grid.bpm) if steady else None
    if ratio is not None:
        beat = 60.0 / playing_bpm
        length = mix_beats * beat
        # The bass swap lands where the incoming's bassline comes in: if that
        # is later than the swap's bar, the incoming starts that many bars into
        # its intro (always on a phrase), or the new low end would be a kick
        # alone. The incoming is started just short of the bar it drops on.
        swap_bars = mix_beats // 8
        late = (nxt.bass_in - swap_bars) if nxt.bass_in is not None and nxt.bass_in > swap_bars else 0
        bar_in = in_grid.downbeat + late * 4 * in_grid.beat
        offset = max(0.0, bar_in - PREROLL_S)
        lead_in = (bar_in - offset) / ratio                  # incoming: start to the bar it drops on
        earliest = now + lead_in + lead
        bar = 4 * beat
        drop = None
        if mode == "end":
            # The last phrase of eight bars (else four, else any bar) that
            # leaves room for the whole blend before the record ends.
            latest = out_end - length - 0.5
            for every in (8, 4, 1):
                d = out_grid.next_bar(latest - every * bar, out_ratio, every)
                if earliest <= d <= latest + 0.01:
                    drop = d
                    break
        else:
            # A skip comes in on the next four-bar phrase, or the next bar if
            # that would not leave room.
            for every in (4, 1):
                d = out_grid.next_bar(earliest, out_ratio, every)
                if d + length <= out_end + 0.01:
                    drop = d
                    break
        if drop is None:
            drop = out_grid.next_bar(earliest, out_ratio)
        # Room on both sides: the outgoing before its music ends, and the
        # incoming with IN_LEFT_S still to play once it is the record on air.
        if drop + length <= out_end + 0.01 and length <= (nxt.seconds - offset) / ratio - IN_LEFT_S:
            return Plan("blend", drop - lead_in, drop, length, beat, ratio, nxt, offset)
    # Not beat-matched: a fade on the outgoing bar, the incoming from its
    # first sound, stretched to the tempo where the tempos are close enough.
    fallback = "beat" if not steady else ("tempo" if ratio is None else "room")
    beat = 60.0 / playing_bpm if playing_bpm else 0.5
    fade_ratio = 1.0
    if out_grid and in_grid:
        fade_ratio = library.tempo_ratio(playing_bpm, in_grid.bpm) or 1.0
    for bars in (FADE_BARS, FADE_BARS // 2, 2):
        length = bars * 4 * beat
        if mode == "end":
            latest = out_end - length - 0.2
            drop = None
            if out_grid:
                for every in (8, 4, 1):
                    d = out_grid.next_bar(latest - every * 4 * beat, out_ratio, every)
                    if now + lead <= d <= latest + 0.01:
                        drop = d
                        break
            if drop is None:
                drop = max(now + lead, latest)
        else:
            drop = out_grid.next_bar(now + lead, out_ratio) if out_grid else now + lead
        if drop + length <= out_end + 0.01:
            return Plan("fade", drop, drop, length, beat, fade_ratio, nxt, nxt.lead, fallback=fallback)
    # No room even for two bars: a cut where the music ends.
    fade = CUT_FADE_S
    drop = max(now + lead, min(out_end - 0.05, now + fade + lead))
    return Plan("cut", drop, drop, fade, beat, 1.0, nxt, nxt.lead, fallback="room")


def _ease(x):
    """0→1 along a cosine S: slow off the mark, slow into place."""
    return 0.5 - 0.5 * np.cos(np.pi * np.clip(x, 0.0, 1.0))


#: Where the mids sit while both records are playing: each record's mids
#: are thinned so two sets of vocals and synths never stack at full.
MID_SHARE = 0.55


def gains(plan: Plan, t: np.ndarray) -> tuple:
    """(outgoing low, mid, high, incoming low, mid, high) gains at times t.

    A blend staged the way DJs ride a long EQ mix: the incoming record comes
    in from the top down — its highs (hats, air) over the first ramp, its mids
    over the second while the outgoing's are thinned to make room — then the
    ride, both records up and locked, with the basslines swapped on the bar
    halfway, over one beat (never two basslines, never none). The outgoing
    leaves from the bottom up: bass at the swap, its mids over the second-last
    ramp, its highs over the last. `ramp` is a quarter of a short blend, so a
    32- or 64-beat blend is in quarters; a long one rides for half its length."""
    if plan.kind == "cut":
        out = np.clip((plan.drop - t) / plan.length, 0.0, 1.0)
        inc = (t >= plan.drop).astype(np.float32)
        return out, out, out, inc, inc, inc
    if plan.kind == "out":
        # The incoming is already playing (started by hand): only the outgoing
        # moves — its bass gone on the bar, the rest fading out equal-power.
        x = np.clip((t - plan.drop) / plan.length, 0.0, 1.0)
        out = np.cos(x * np.pi / 2)
        one = np.ones_like(out)
        return 1.0 - np.clip((t - plan.drop) / plan.beat, 0.0, 1.0), out, out, one, one, one
    if plan.kind == "fade":
        x = np.clip((t - plan.drop) / plan.length, 0.0, 1.0)
        out, inc = np.cos(x * np.pi / 2), np.sin(x * np.pi / 2)        # equal power
        bass = np.clip((t - (plan.drop + plan.length / 2)) / plan.beat, 0.0, 1.0)
        return 1.0 - bass, out, out, bass, inc, inc
    L, d = plan.length, plan.drop
    r = ramp(plan)
    swap = d + L / 2
    bass = np.clip((t - swap) / plan.beat, 0.0, 1.0)
    in_high = _ease((t - d) / r)
    # Incoming mids: up to MID_SHARE over the second ramp, the rest at the swap.
    in_mid = MID_SHARE * _ease((t - (d + r)) / r) + (1 - MID_SHARE) * bass
    # Outgoing mids: thinned to MID_SHARE alongside, out over the second-last ramp.
    out_mid = (1 - (1 - MID_SHARE) * _ease((t - (d + r)) / r)) * (1 - _ease((t - (d + L - 2 * r)) / r))
    out_high = 1.0 - _ease((t - (d + L - r)) / r)
    return 1.0 - bass, out_mid, out_high, bass, in_mid, in_high


def ramp(plan: Plan) -> float:
    """How long each stage of a blend's way in and way out takes: a quarter
    of a short blend, an eighth of a long one (never under four bars), so a
    long blend is mostly the ride — both records up, locked, the bass swapped
    halfway through it."""
    return min(plan.length / 4, max(plan.length / 8, 16 * plan.beat))


# ── Kaia's hands ─────────────────────────────────────────────────────
#
# On top of the automix she rides the mixer the way a DJ does, every move
# locked to the bars: while two records ride together she pulls both down a
# touch so they sit under the limiter, trades the mids between them phrase by
# phrase, and kills both basslines for the beat before the swap so the new
# one lands; with one record playing she reaches for the EQ into the end of a
# phrase — bass held back, air lifted, mids scooped — and lets go on the one.
# How deep and how often follows her energy. No model, no randomness: which
# gesture comes is a hash of the record and the phrase.

#: Both records while they ride together: about -1.5 dB each.
STAGE = 0.84
#: Bars in the phrases she gestures into, and trades mids over in a ride.
PHRASE_BARS = 16
TRADE_BARS = 8


def kaia_hands(plan: Optional[Plan], t: np.ndarray, energy: float = 0.5, grid=None,
               ratio: float = 1.0, seed: int = 0) -> tuple:
    """Multipliers on the automix — (outgoing low, mid, high, incoming low,
    mid, high), per sample — and a few words for what she is doing."""
    one = np.ones_like(t, dtype=np.float32)
    f = [one.copy() for _ in range(6)]
    e = min(1.0, max(0.0, float(energy)))
    label = ""
    if plan is not None and plan.kind == "blend":
        L, d, b = plan.length, plan.drop, plan.beat
        r = ramp(plan)
        swap = d + L / 2
        lo_w, hi_w = d + 2 * r, d + L - 2 * r
        now = float(t[-1])
        if hi_w - lo_w >= 16 * b:
            inside = _ease((t - lo_w) / b) * (1 - _ease((t - (hi_w - b)) / b))
            stage = 1 - (1 - STAGE) * inside
            for i in range(6):
                f[i] = f[i] * stage
            # Trading mids: one record leads each TRADE_BARS, the other steps back.
            depth = 0.12 + 0.18 * e
            phrase = TRADE_BARS * 4 * b
            k = np.floor((t - lo_w) / phrase)
            lead = (k % 2 == 1).astype(np.float32)                   # 1: the incoming leads
            prev = np.where(k >= 1, 1 - lead, lead)
            lead = prev + (lead - prev) * _ease((t - (lo_w + k * phrase)) / b)
            swing = depth * (2 * lead - 1) * inside
            f[1] = f[1] * (1 - swing)
            f[4] = f[4] * (1 + swing)
            if lo_w <= now < hi_w:
                label = f"riding both, trading the mids — the {'new' if lead[-1] > 0.5 else 'old'} one leads"
        if e >= 0.45:
            # The beat before the swap with no bass at all, then the new bassline lands.
            f[0] = f[0] * (1 - np.clip((t - (swap - b)) / (b / 8), 0.0, 1.0))
            f[3] = f[3] * (1 - np.clip((t - (swap - b)) / (b / 8), 0.0, 1.0) * (t < swap))
            # The old record's air pulled back over the bar into it.
            bump = _ease((t - (swap - 4 * b)) / (3 * b)) * (1 - _ease((t - swap) / b))
            f[2] = f[2] * (1 - 0.35 * e * bump)
            if swap - 4 * b <= now < swap:
                label = "pulling the old one's air back — bass out for the beat before the swap"
    elif plan is None and grid is not None and getattr(grid, "bar_known", False) and e > 0.15:
        bar = 4 * grid.beat / ratio
        bi = (t - grid.downbeat / ratio) / bar + grid.bar0
        ph = int(np.floor(float(bi[-1]) / PHRASE_BARS))
        every = 1 if e > 0.7 else 2 if e > 0.4 else 4
        depth = 0.6 + 0.4 * e

        def gesture(n):
            import zlib
            if n < 1 or n % every:
                return None
            return ("tension", "air", "scoop")[zlib.crc32(f"{seed}:{n}".encode()) % 3]

        pos = bi - ph * PHRASE_BARS                                 # bars into this phrase
        g = gesture(ph + 1)                                         # the one being built towards
        if g == "tension":
            f[0] = 1 - 0.4 * depth * _ease(pos - 14)
            label = "holding the bass back into the phrase"
        elif g == "air":
            f[2] = 1 + 0.18 * depth * _ease((pos - 12) / 4)
            label = "lifting the air into the phrase"
        elif g == "scoop":
            f[1] = 1 - 0.22 * depth * _ease((pos - 12) / 2)
            label = "scooping the mids into the phrase"
        if gesture(ph) == "air":                                    # let the last lift down gently
            f[2] = f[2] * (1 + 0.18 * depth * (1 - _ease(pos / 2)))
        if float(pos[-1]) < 12 and not (gesture(ph) == "air" and float(pos[-1]) < 2):
            label = ""
    return tuple(f), label


IDENTITY = (1.0, 1.0, 1.0, 1.0)
#: The automix with one record playing and nothing coming in.
SOLO = (1.0, 1.0, 1.0, 0.0, 0.0, 0.0)
#: Both decks open: the booth's hands are the whole mix.
BOTH = (1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
#: A deck played by hand takes over once the record on air has been silent
#: (paused, faded down, crossfaded away) this long, or has ended.
HANDOVER_S = 2.0
#: Kaia finishing a mix that was started by hand: the outgoing's fade, in bars.
FINISH_BARS = 8


def mix_frames(out_parts, in_parts, g, uo=IDENTITY, ui=IDENTITY, master: float = 1.0) -> bytes:
    """The two decks summed: each band times the automix gain (`g`: low, mid,
    high for each record, per sample or constant) times the hands on the
    mixer (`uo`/`ui`: low, mid, high, channel gain)."""
    gol, gom, goh, gil, gim, gih = (np.asarray(x, dtype=np.float32).reshape(-1, 1) for x in g)
    y = np.zeros((FRAME_SAMPLES, 2), dtype=np.float32)
    if out_parts is not None:
        lo, mi, hi = out_parts
        y += (lo * (gol * uo[0]) + mi * (gom * uo[1]) + hi * (goh * uo[2])) * uo[3]
    if in_parts is not None:
        lo, mi, hi = in_parts
        y += (lo * (gil * ui[0]) + mi * (gim * ui[1]) + hi * (gih * ui[2])) * ui[3]
    if master != 1.0:
        y *= master
    return np.clip(np.rint(_soft_limit(y)), -32768, 32767).astype(np.int16).tobytes()


#: Above this level the sum is bent smoothly toward full scale rather than
#: clipped: two full records playing together run hot.
LIMIT_FROM = 0.80 * 32767


def _soft_limit(y: np.ndarray) -> np.ndarray:
    a = np.abs(y)
    if a.max() <= LIMIT_FROM:
        return y
    head = 32767 - LIMIT_FROM
    over = a > LIMIT_FROM
    out = y.copy()
    out[over] = np.sign(y[over]) * (LIMIT_FROM + head * np.tanh((a[over] - LIMIT_FROM) / head))
    return out


class Controls:
    """The mixer as someone at the booth has set it, on top of the automix:
    per channel TRIM (dB), HI / MID / LOW (0 kills, 1 is flat, up to 1.5),
    the channel fader (0–1); the crossfader (None until touched, then 0 = all
    channel 1, 1 = all channel 2, both full in the middle); MASTER (0–1.5).
    Kaia's automix still runs underneath: the two multiply."""

    LIMITS = {"trim": (-12.0, 12.0), "high": (0.0, 1.5), "mid": (0.0, 1.5), "low": (0.0, 1.5),
              "fader": (0.0, 1.0)}

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.channels = {1: self._flat(), 2: self._flat()}
        self.xfader: Optional[float] = None
        self.master = 1.0

    @staticmethod
    def _flat() -> dict:
        return {"trim": 0.0, "high": 1.0, "mid": 1.0, "low": 1.0, "fader": 1.0}

    def set(self, slot: Optional[int], name: str, value: float) -> bool:
        if name == "xfader":
            self.xfader = None if value is None else min(1.0, max(0.0, float(value)))
            return True
        if name == "master":
            self.master = min(1.5, max(0.0, float(value)))
            return True
        if slot in self.channels and name in self.LIMITS:
            lo, hi = self.LIMITS[name]
            self.channels[slot][name] = min(hi, max(lo, float(value)))
            return True
        return False

    def channel(self, slot: int) -> tuple:
        """(low, mid, high, gain) multipliers for one channel."""
        c = self.channels.get(slot) or self._flat()
        gain = c["fader"] * 10 ** (c["trim"] / 20)
        if self.xfader is not None:
            gain *= min(1.0, 2 * (1 - self.xfader)) if slot == 1 else min(1.0, 2 * self.xfader)
        return (c["low"], c["mid"], c["high"], gain)

    def flat(self) -> bool:
        return (self.xfader is None and self.master == 1.0
                and all(c == self._flat() for c in self.channels.values()))

    def state(self) -> dict:
        return {"channels": {str(k): dict(v) for k, v in self.channels.items()},
                "xfader": self.xfader, "master": self.master}


class CrossfadeSource(_AudioSource):
    """Plays decks one after another, mixing each into the next on the beat.

    `pick(deck)` returns the Next record for after `deck`, or None. `grid_at`
    finds the outgoing record's beat round a point (patched out in tests)."""

    def __init__(self, first: Deck, pick: Callable[[Deck], Optional[Next]],
                 stream_factory=open_pcm, on_change: Optional[Callable[[library.Record], None]] = None,
                 mix_beats: int = MIX_BEATS, grid_at: Optional[Callable] = None):
        self.current: Optional[Deck] = first
        self.incoming: Optional[Deck] = None
        self.plan: Optional[Plan] = None
        self._pick = pick
        self._factory = stream_factory
        self._on_change = on_change
        self._mix_beats = mix_beats
        self._grid_at = grid_at or _default_grid_at
        self._queued: Optional[Next] = None
        self._picking = False
        self._exhausted = False             # the last pick found nothing to play
        self._planning = False
        self._start_frame: Optional[int] = None
        self.frames_sent = 0
        # How late discord.py's voice thread came back for a frame: every gap
        # over LATE_S is one a listener may hear as a stutter.
        self._last_read: Optional[float] = None
        self.late: list[float] = []
        # What the mixer is doing, for the DJ dashboard: pre-fader levels of
        # each deck and the mix (dBFS), the band gains applied this frame, and
        # every transition planned.
        self.levels = {"a": -90.0, "b": -90.0, "master": -90.0}
        self.applied = SOLO
        self.history: list[dict] = []
        self.planning_mode: Optional[str] = None
        self.controls = Controls()
        self.paused: set = set()                  # deck slots someone paused at the booth
        # The free deck at the booth: a record loaded by hand (`by_hand`), its
        # cue point (seconds of its own time; None: Kaia's choice), and a deck
        # played by hand (`hand`), started synced on the beat, mixed by the
        # faders until it takes over.
        self.cue: Optional[float] = None
        self.by_hand = False
        self.hand: Optional[Deck] = None
        self.hand_next: Optional[Next] = None
        self.hand_synced = False
        self._hand_k: Optional[int] = None        # the on-air deck's frame it starts on
        self._hand_on = False
        self._hand_quiet = 0
        self._hand_starting = False
        self._gen = 0                             # bumped by every hand on the free deck
        # Kaia's hands on the mixer (`kaia_hands`), how much energy she has
        # for them (0–1, from her mood), and what she is doing right now.
        self.rides = True
        self.key_sync = True                      # shift a clashing incoming a semitone to fit
        self.energy = 0.5
        self.gesture = ""
        self._lock = threading.RLock()
        self._prefetch()

    def is_opus(self) -> bool:
        return False

    def _prefetch(self) -> None:
        if self._picking or self._queued or self.current is None:
            return
        self._picking = True
        deck, gen = self.current, self._gen

        def run():
            picked = None
            try:
                picked = self._pick(deck)
            except Exception as e:
                log_warning(f"[records] could not choose the next record: {e}")
            finally:
                with self._lock:
                    if gen == self._gen and self._queued is None:
                        self._queued = picked
                        self._exhausted = picked is None
                    self._picking = False
        threading.Thread(target=run, daemon=True, name="kaia-records-pick").start()

    def skip(self) -> None:
        """Bring the next record in at the next phrase it can land on. A blend
        planned for later (the end of the record) that has not started is
        called off and planned again from here. With a deck playing by hand,
        Kaia finishes that mix instead."""
        if self.hand is not None:
            self.finish()
            return
        with self._lock:
            if self._call_off_plan():
                log_debug("[records] the planned blend was called off for a skip")
        self._begin_planning("skip")

    # ── the free deck, by hand ──────────────────────────────────────

    def blend_started(self) -> bool:
        cur, plan = self.current, self.plan
        if plan is None or cur is None:
            return False
        return plan.kind == "out" or (self._start_frame is not None and cur.played >= self._start_frame - 10)

    def _call_off_plan(self) -> bool:
        """Call off a planned transition that has not started (and any being
        planned). True if one was."""
        self._gen += 1
        plan = self.plan
        if plan is None or self.blend_started():
            return False
        incoming, self.incoming = self.incoming, None
        self.plan, self._start_frame = None, None
        if incoming:
            incoming.close()
        self._queued = self._queued or plan.nxt
        log_info(f"[records] the {plan.kind} into {plan.nxt.record.name} was called off before it began")
        self._journal_row({"status": "called_off", "kind": plan.kind, "to": plan.nxt.record.name})
        return True

    def free_slot(self) -> int:
        return 3 - self.current.slot if self.current else 2

    def hand_audible(self) -> bool:
        return self.hand is not None and self._hand_on and self.controls.channel(self.hand.slot)[3] > 1e-3

    def load(self, nxt: Next) -> str:
        """Put `nxt` on the free deck now, replacing whatever Kaia had lined up
        there (a blend not yet started is called off). Its channel fader goes
        down, as a DJ's would; Kaia brings it back up if she mixes it in.
        "loaded", "after" (a blend into that deck is under way: it can only
        come after), or "busy" (a deck playing by hand is up on its fader)."""
        with self._lock:
            if self.blend_started():
                return "after"
            if self.hand_audible():
                return "busy"
            self._drop_hand()
            self._call_off_plan()
            self._queued, self._exhausted = nxt, False
            self.cue, self.by_hand = None, True
            self.controls.set(self.free_slot(), "fader", 0.0)
        log_action(f"[records] {nxt.record.name} loaded on deck {self.free_slot()} from the booth")
        return "loaded"

    def default_cue(self, nxt: Optional[Next]) -> float:
        """Where Kaia would start a record: its bar one, else its first sound."""
        if nxt is None:
            return 0.0
        return nxt.grid.downbeat if nxt.grid and nxt.grid.bar_known else nxt.lead

    @staticmethod
    def snap(grid, pos: float) -> float:
        """`pos` on the nearest bar of `grid` (the nearest beat if the bar is not known)."""
        if grid is None:
            return max(0.0, pos)
        step = grid.beat * (4 if grid.bar_known else 1)
        k = round((pos - grid.downbeat) / step)
        out = grid.downbeat + k * step
        return out if out >= 0 else out + step

    def set_cue(self, pos: float) -> bool:
        """Move the free deck's cue point (snapped to a bar). A deck playing by
        hand jumps there, back on the beat."""
        with self._lock:
            nxt = self.hand_next if self.hand is not None else self._queued
            if nxt is None:
                return False
            pos = min(max(0.0, float(pos)), max(0.0, nxt.seconds - 8.0))
            self.cue = self.snap(nxt.grid, pos)
            playing = self.hand is not None
            replan = None
            if playing:
                self._drop_hand(keep_cue=True)
            elif not self.blend_started():
                # A plan made, or being made, from the old cue is called off;
                # the next one is made from this one, for the same reason.
                replan = self.plan.mode if self.plan is not None else None
                self._call_off_plan()
        if playing:
            self.play_hand()
        elif replan:
            self._begin_planning(replan)
        return True

    def _cued(self, nxt: Next) -> Next:
        """`nxt` as it comes in from the cue point: bar one at the cue. A cue
        set at the booth is kept whoever lined the record up."""
        if self.cue is None:
            return nxt
        from utils.audio import beatgrid
        g = self._grid_at(nxt.record, max(0.0, self.cue - 4.0), 30.0) or nxt.grid
        if g is None:
            return Next(nxt.record, nxt.seconds, nxt.gain, None, self.cue)
        c = self.snap(g, self.cue)
        return Next(nxt.record, nxt.seconds, nxt.gain,
                    beatgrid.Grid(g.bpm, c, g.contrast, bar_known=g.bar_known), c)

    def play_hand(self) -> str:
        """Start the free deck by hand: at the record on air's tempo where it
        can be stretched to it, its cue landing on the beat — on the same beat
        of the bar — of the record on air. Faders do the mixing; it takes over
        when the record on air has gone quiet. "starting", or "nothing"."""
        with self._lock:
            if self.hand is not None or self._hand_starting:
                return "starting"
            if self.blend_started():
                return "nothing"
            self._call_off_plan()
            nxt, cur = self._queued, self.current
            if nxt is None or cur is None:
                return "nothing"
            self._hand_starting = True
            gen = self._gen
            cue = self.cue if self.cue is not None else self.default_cue(nxt)

        def run():
            try:
                self._start_hand(nxt, cur, cue, gen)
            except Exception as e:
                log_warning(f"[records] the deck would not start: {e}")
            finally:
                self._hand_starting = False
        threading.Thread(target=run, daemon=True, name="kaia-records-hand").start()
        return "starting"

    def _semitones(self, playing: Deck, nxt: Next) -> int:
        from utils.audio.beatgrid import has_rubberband
        if not self.key_sync or not has_rubberband():
            return 0
        return library.key_sync(playing.key, nxt.record.key)

    def _start_hand(self, nxt: Next, cur: Deck, cue: float, gen: int) -> None:
        global _SOS
        if _SOS is None:
            _SOS = _bands()
        in_g = self._grid_at(nxt.record, max(0.0, cue - 4.0), 30.0) or nxt.grid
        out_g = self._grid_at(cur.record, max(0.0, cur.at() * cur.ratio - 8.0), 30.0) or cur.grid
        master_bpm = out_g.bpm * cur.ratio if out_g else None
        ratio = library.tempo_ratio(master_bpm, in_g.bpm if in_g else nxt.record.bpm)
        synced = ratio is not None and in_g is not None and out_g is not None
        ratio = ratio or 1.0
        c = self.snap(in_g, cue) if in_g else cue
        phase = None
        if synced and in_g.bar_known and out_g.bar_known:
            phase = int(round((c - in_g.downbeat) / in_g.beat)) % 4
        deck = None
        for attempt in range(4):
            lead = 0.8 + 0.5 * attempt
            if synced and cur.slot not in self.paused:
                bm, first = out_g.beat / cur.ratio, out_g.downbeat / cur.ratio
                j = int(np.ceil((cur.at() + lead - first) / bm))
                while phase is not None and j % 4 != phase:
                    j += 1
                when = first + j * bm
            else:
                when = cur.at() + lead
            at = (when - cur.offset / cur.ratio) * RATE + cur.pad
            k = int(np.floor(at / FRAME_SAMPLES))
            pad = int(round(at - k * FRAME_SAMPLES))
            deck = Deck(nxt.record, ratio, nxt.seconds, self._factory, gain=nxt.gain, pad=max(0, pad), offset=c,
                        semitones=self._semitones(cur, nxt) if synced else 0)
            deadline = time.time() + 1.0
            while not deck.ready() and time.time() < deadline:
                time.sleep(0.02)
            if (k > cur.played + 1 or cur.slot in self.paused) and deck.ready():
                break
            deck.close()
            deck = None
        if deck is None:
            return
        with self._lock:
            if gen != self._gen or cur is not self.current or self.hand is not None or self.plan is not None:
                deck.close()
                return
            deck.grid = in_g
            deck.slot = 3 - cur.slot
            self.hand, self.hand_next, self.hand_synced = deck, nxt, synced
            self._hand_k, self._hand_on, self._hand_quiet = k, False, 0
            self._queued = None
            self.cue = c
        log_action(f"[records] {nxt.record.name} played by hand on deck {deck.slot} from {c:.1f}s"
                   + (f", synced ×{ratio:.4f}" if synced else ", not synced (tempo or beat)"))

    def _drop_hand(self, keep_cue: bool = False) -> None:
        """Take the deck playing by hand off: back to loaded, cued where it
        was (or at its cue point)."""
        hand, nxt, was_on = self.hand, self.hand_next, self._hand_on
        if hand is None:
            return
        pos = hand.at() * hand.ratio
        self.hand, self.hand_next, self._hand_k, self._hand_on = None, None, None, False
        self._gen += 1
        hand.close()
        if nxt is not None:
            self._queued, self.by_hand = nxt, True
            if not keep_cue and was_on:
                self.cue = min(max(0.0, pos), max(0.0, nxt.seconds - 8.0))

    def stop_hand(self, back_to_cue: bool = False) -> bool:
        """Pause the deck playing by hand (it holds its place) or, like a
        CDJ's CUE pressed while playing, stop it back at its cue point."""
        with self._lock:
            if self.hand is None:
                return False
            self._drop_hand(keep_cue=back_to_cue)
        return True

    def finish(self) -> bool:
        """Kaia finishes a mix started by hand: from the next bar the record on
        air loses its bass and fades out over FINISH_BARS; the faders go back
        up so nothing she leaves playing is silent."""
        with self._lock:
            cur, hand = self.current, self.hand
            if cur is None or hand is None or self.plan is not None:
                return False
            g = cur.grid
            beat = g.beat / cur.ratio if g else 0.5
            drop = g.next_bar(cur.at() + 0.3, cur.ratio) if g else cur.at() + 0.3
            length = max(beat, min(FINISH_BARS * 4 * beat, cur.end - drop - 0.05))
            nxt = self.hand_next or Next(hand.record, hand.total_frames / FRAMES_PER_S)
            plan = Plan("out", drop, drop, length, beat, hand.ratio, nxt, mode="skip", why="finishing the mix by hand")
            self.incoming, self.plan = hand, plan
            self._start_frame = 0 if self._hand_on else self._hand_k
            self.hand, self.hand_next, self._hand_k, self._hand_on = None, None, None, False
            for slot in (1, 2):
                self.controls.set(slot, "fader", 1.0)
            self.controls.xfader = None
            self.paused.discard(cur.slot)
            self.history.append({"ts": time.time(), "kind": "out", "mode": "skip", "from": cur.record.name,
                                 "to": hand.record.name, "at": round(drop, 2), "ratio": round(hand.ratio, 4),
                                 "why": plan.why})
        log_action(f"[records] finishing the hand mix into {hand.record.name} over {length:.1f}s")
        return True

    def _adopt_hand(self) -> None:
        """The deck played by hand is the record on air now."""
        old, hand = self.current, self.hand
        self.current = hand
        self.hand, self.hand_next, self._hand_k, self._hand_on, self._hand_quiet = None, None, None, False, 0
        self.cue, self.by_hand = None, False
        if old is not None:
            self.paused.discard(old.slot)
            # The channel the next record comes in on starts flat; centring the
            # crossfader is silent now that one side is empty.
            self.controls.channels[old.slot] = Controls._flat()
            old.close()
            self.history.append({"ts": time.time(), "kind": "hand", "mode": "hand", "from": old.record.name,
                                 "to": hand.record.name, "at": round(old.at(), 2), "ratio": round(hand.ratio, 4),
                                 "why": "mixed by hand"})
            del self.history[:-50]
            self._journal_row({"status": "done", "kind": "hand", "from": old.record.name, "to": hand.record.name})
        self.controls.xfader = None
        if self._on_change:
            try:
                self._on_change(hand.record)
            except Exception as e:
                log_debug(f"[records] on_change: {e}")
        self._prefetch()

    #: The booth's blend lengths, in beats — at 125 bpm about 15 s, 30 s, and
    #: two minutes, a full minute of it both records up together.
    BLEND_CHOICES = (32, 64, 256)

    def set_mix_beats(self, beats: int) -> bool:
        """The length of the next blend (one already planned keeps its own)."""
        if int(beats) not in self.BLEND_CHOICES:
            return False
        with self._lock:
            self._mix_beats = int(beats)
            # A blend planned at the old length and not yet begun is planned
            # again at this one, for the same reason (a skip stays a skip).
            plan = self.plan
            if plan is not None and not self.blend_started() and plan.kind == "blend":
                self._call_off_plan()
                replan = plan.mode
            else:
                replan = None
        if replan:
            self._begin_planning(replan)
        return True

    @staticmethod
    def _db(frame: Optional[bytes]) -> float:
        if not frame:
            return -90.0
        x = np.frombuffer(frame, dtype=np.int16)[::8].astype(np.float32)
        rms = float(np.sqrt(np.mean(x * x))) if len(x) else 0.0
        return round(20 * np.log10(rms / 32768.0), 1) if rms > 1 else -90.0

    def _begin_planning(self, mode: str) -> None:
        if self._planning or self.plan or self.current is None or self.hand is not None or self._hand_starting:
            return
        self._planning = True
        self.planning_mode = mode
        deck, gen = self.current, self._gen

        def run():
            try:
                deadline = time.time() + 30
                while self._queued is None and time.time() < deadline:
                    if not self._picking:
                        if self._exhausted:
                            break
                        self._prefetch()
                    time.sleep(0.05)
                nxt = self._queued
                if nxt is None or deck is not self.current:
                    return
                queued = nxt
                nxt = self._cued(nxt)
                # Nothing slow may happen on discord.py's audio thread, which
                # must hand over a frame every 20 ms: the filter (and scipy's
                # import) is readied here, and the incoming ffmpeg is started
                # and buffered here, before the plan is published.
                global _SOS
                if _SOS is None:
                    _SOS = _bands()
                # Where the outgoing's music ends: its last strong beat, a bar
                # on, not the end of the file. A blend is fitted before it.
                music_end = deck.end
                try:
                    from utils.audio import beatgrid as _bg
                    last = _bg.last_strong_beat(deck.record.path, deck.record.bpm, round(deck.end * deck.ratio, 1))
                    if last:
                        music_end = min(deck.end, (last + 240.0 / max(1.0, deck.record.bpm)) / deck.ratio)
                except Exception as e:
                    log_debug(f"[records] last beat not found: {e}")
                here = (music_end - 60.0 if mode == "end" else deck.at()) * deck.ratio
                out_grid = self._grid_at(deck.record, max(0.0, here - 8.0), 45.0)
                if out_grid is not None:
                    deck.grid = out_grid                     # measured here, where it is mixed out
                for attempt in range(4):
                    lead = 2.0 + attempt                     # room to check the kicks, start ffmpeg, fill
                    # The chosen length, halved (not below 16 beats) where the
                    # record has no room left for it, before giving up to a cut.
                    beats = self._mix_beats
                    plan = plan_transition(deck.at(), deck.ratio, out_grid, music_end, nxt, mode, beats, lead=lead)
                    while plan.kind != "blend" and plan.fallback == "room" and beats > 16:
                        beats //= 2
                        plan = plan_transition(deck.at(), deck.ratio, out_grid, music_end, nxt, mode, beats, lead=lead)
                    if plan.kind == "blend":
                        # The grids put the downbeats together; the kicks
                        # themselves have the last word, as a DJ's ear would.
                        shift = self._fine(deck, plan)
                        if shift is not None and abs(shift) <= MAX_FINE_S:
                            plan.start += shift
                    # A stretch that moves onsets early is started that much
                    # later (only the atempo fallback does; rubberband does not).
                    from utils.audio.beatgrid import stretch_latency
                    plan.start += stretch_latency(plan.ratio) - stretch_latency(deck.ratio)
                    # It starts part-way into its first frame, so its downbeat
                    # lands on the outgoing bar to the sample.
                    at = (plan.start - deck.offset / deck.ratio) * RATE + deck.pad   # outgoing samples
                    k = int(np.floor(at / FRAME_SAMPLES))
                    pad = int(round(at - k * FRAME_SAMPLES))
                    incoming = Deck(nxt.record, plan.ratio, nxt.seconds, self._factory,
                                    gain=nxt.gain, pad=max(0, pad), offset=plan.offset,
                                    semitones=self._semitones(deck, nxt))
                    deadline = time.time() + 1.0
                    while not incoming.ready() and time.time() < deadline:
                        time.sleep(0.02)
                    if k > deck.played + 2 and incoming.ready():
                        break
                    incoming.close()
                    incoming = None
                if incoming is None:
                    return
                with self._lock:
                    if (deck is not self.current or gen != self._gen or self._queued is not queued
                            or self.hand is not None or self.plan is not None):
                        incoming.close()
                        return
                    incoming.grid = nxt.grid
                    incoming.slot = 3 - deck.slot
                    plan.mode = mode
                    self._queued = None
                    self._start_frame = k
                    self.incoming = incoming
                    self.plan = plan

                why = ""
                if plan.kind != "blend":
                    why = ("; no clear beat" if not (out_grid and nxt.grid) else
                           f"; beat not steady enough to blend (contrast {out_grid.contrast:.1f} / "
                           f"{nxt.grid.contrast:.1f})" if min(out_grid.contrast, nxt.grid.contrast) < BLEND_CONTRAST
                           else "; bar not found" if not (out_grid.bar_known and nxt.grid.bar_known)
                           else "; tempos too far apart" if plan.fallback == "tempo"
                           else "; no room left to blend")
                plan.why = why.lstrip("; ")
                self._journal(deck, nxt, plan, out_grid, music_end, mode)
                self.history.append({"ts": time.time(), "kind": plan.kind, "mode": mode,
                                     "from": deck.record.name, "to": nxt.record.name,
                                     "at": round(plan.drop, 2), "ratio": round(plan.ratio, 4),
                                     "why": plan.why})
                del self.history[:-50]
                shift = (f", key sync {incoming.semitones:+d} ({nxt.record.key} → {incoming.key} against {deck.key})"
                         if incoming.semitones else "")
                log_action(f"[records] planned: {plan.kind} into {nxt.record.name} at {plan.drop:.2f}s "
                           f"(stretch {plan.ratio:.4f}, {mode}{why}{shift})")
            except Exception as e:
                log_warning(f"[records] transition not planned: {e}")
            finally:
                self._planning = False
                self.planning_mode = None
        threading.Thread(target=run, daemon=True, name="kaia-records-plan").start()

    def _journal_row(self, row: dict) -> None:
        try:
            import json
            from utils.infrastructure.monitoring.telemetry_paths import telemetry_path
            path = Path(telemetry_path("memory/records/transitions.jsonl"))
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": time.time(), **row}, ensure_ascii=False) + "\n")
        except Exception as e:
            log_debug(f"[records] transition not journalled: {e}")

    def _journal(self, deck: Deck, nxt: Next, plan: Plan, out_grid, music_end: float, mode: str) -> None:
        """Every transition planned, with what it was decided from, in
        memory/records/transitions.jsonl — the record to read back when a mix
        sounded wrong. A plan is `planned`; a later row says it was `called_off`
        or `done`."""
        try:
            g = lambda x: {"bpm": round(x.bpm, 3), "contrast": round(x.contrast, 2), "bar_known": x.bar_known,
                           "downbeat": round(x.downbeat, 3), "bar0": x.bar0} if x else None
            row = {"status": "planned", "mode": mode, "kind": plan.kind, "why": plan.why, "fallback": plan.fallback,
                   "from": deck.record.name, "to": nxt.record.name, "out_at": round(deck.at(), 2),
                   "out_ratio": round(deck.ratio, 5), "drop": round(plan.drop, 3), "length": round(plan.length, 2),
                   "beats": round(plan.length / plan.beat) if plan.beat else None, "ratio": round(plan.ratio, 5),
                   "offset": round(plan.offset, 3), "music_end": round(music_end, 2), "file_end": round(deck.end, 2),
                   "out_grid": g(out_grid), "in_grid": g(nxt.grid), "controls_flat": self.controls.flat(),
                   "bass_in": nxt.bass_in, "keys": [deck.key, nxt.record.key], "rides": self.rides,
                   "semitones": self.incoming.semitones if self.incoming else 0}
            self._journal_row(row)
        except Exception as e:
            log_debug(f"[records] transition not journalled: {e}")

    def _fine(self, deck: Deck, plan: Plan) -> Optional[float]:
        from utils.audio import beatgrid
        shift = beatgrid.fine_offset(deck.record.path, deck.ratio, plan.drop, plan.nxt.record.path,
                                     plan.ratio, plan.drop - plan.start + plan.offset / plan.ratio, plan.beat)
        if shift is not None:
            log_debug(f"[records] kicks lined up: incoming moved {shift * 1000:+.0f} ms"
                      + ("" if abs(shift) <= MAX_FINE_S else " (too far to trust; kept the grid's alignment)"))
        return shift

    def read(self) -> bytes:
        now = time.perf_counter()
        if self._last_read is not None and now - self._last_read > LATE_S:
            gap = now - self._last_read
            self.late.append(gap)
            log_debug(f"[records] voice thread {gap * 1000:.0f} ms between frames")
        self._last_read = now
        cur = self.current
        if cur is None:
            return b""
        plan = self.plan
        # Early enough to fit a blend before a long outro: the plan places
        # itself on the last phrase that leaves room, however soon it is made.
        if (plan is None and self.hand is None and not self._planning
                and cur.remaining <= int((self._mix_beats * 0.6 + 90) * FRAMES_PER_S)):
            self._begin_planning("end")
        if self.hand is not None and plan is None:
            return self._read_hand(cur, self.hand)
        if cur.slot in self.paused:
            self.frames_sent += 1
            self.levels["a"] = self.levels["master"] = -90.0
            return SILENCE
        k = cur.played
        t0 = cur.at(k)
        out = cur.frame()
        if out is None and self.incoming is None:
            # Ended with nothing planned: silence while the next is found, or stop.
            if self._planning or self._picking or self._queued:
                if not self._planning and self._queued:
                    self._begin_planning("skip")
                self.frames_sent += 1
                return SILENCE
            cur.close()
            self.current = None
            return b""
        inc = None
        if (self.incoming is not None and self._start_frame is not None and k >= self._start_frame
                and self.incoming.slot not in self.paused):
            if k == self._start_frame and self.by_hand and self.controls.channels[self.incoming.slot]["fader"] <= 0.0:
                self.controls.set(self.incoming.slot, "fader", 1.0)    # loaded with its fader down: she brings it in
            inc = self.incoming.frame() or SILENCE
        hands = self.controls
        solo = SOLO
        if plan is None and self.rides and out is not None and cur.grid is not None:
            times = t0 + np.arange(FRAME_SAMPLES, dtype=np.float32) / RATE
            fac, self.gesture = kaia_hands(None, times, self.energy, cur.grid, cur.ratio,
                                           seed=hash(cur.record.path) & 0xFFFF)
            if any(float(np.abs(x - 1).max()) > 1e-4 for x in fac[:3]):
                solo = tuple(fac[:3]) + (0.0, 0.0, 0.0)
        if plan is None and hands.flat() and solo is SOLO:
            frame = out
            self.applied = SOLO
            self.levels["b"] = -90.0
        elif plan is None:
            frame = mix_frames(cur.split(out) if out is not None else None, None, solo,
                               hands.channel(cur.slot), IDENTITY, hands.master)
            self.applied = tuple(round(float(np.asarray(x).reshape(-1)[-1]), 3) for x in solo)
            self.levels["b"] = -90.0
        else:
            times = t0 + np.arange(FRAME_SAMPLES, dtype=np.float32) / RATE
            g = gains(plan, times)
            if self.rides:
                fac, self.gesture = kaia_hands(plan, times, self.energy)
                g = tuple(a * b for a, b in zip(g, fac))
            out_parts = cur.split(out) if out is not None else None
            in_parts = self.incoming.split(inc) if inc is not None else None
            frame = mix_frames(out_parts, in_parts, g, hands.channel(cur.slot),
                               hands.channel(self.incoming.slot), hands.master)
            self.applied = tuple(round(float(x[-1]), 3) for x in g)
            self.levels["b"] = self._db(inc)
            if out is None or t0 + FRAME_MS / 1000 >= plan.done:
                self._advance()
        if self.frames_sent % 2 == 0:                       # every 40 ms is plenty for meters
            self.levels["a"] = self._db(out)
            self.levels["master"] = self._db(frame)
        self.frames_sent += 1
        return frame or SILENCE

    def _read_hand(self, cur: Deck, hand: Deck) -> bytes:
        """Both decks open, mixed by the booth's hands: the record on air (unless
        paused) and the deck played by hand, from its frame on."""
        cur_paused = cur.slot in self.paused
        out = None if cur_paused else cur.frame()
        ended = not cur_paused and out is None
        if not self._hand_on and (cur_paused or ended or cur.played >= (self._hand_k or 0)):
            self._hand_on = True
        hf = hand.frame() if self._hand_on else None
        if self._hand_on and hf is None:
            # The hand deck ran out before taking over: it comes off.
            with self._lock:
                self._drop_hand()
            self.frames_sent += 1
            return out or SILENCE
        hands = self.controls
        co, ch = hands.channel(cur.slot), hands.channel(hand.slot)
        frame = mix_frames(cur.split(out) if out is not None else None,
                           hand.split(hf) if hf is not None else None, BOTH, co, ch, hands.master)
        self.applied = BOTH if hf is not None else SOLO
        if self.frames_sent % 2 == 0:
            self.levels["a"] = self._db(out)
            self.levels["b"] = self._db(hf)
            self.levels["master"] = self._db(frame)
        if self._hand_on:
            quiet = ended or cur_paused or co[3] <= 1e-3
            self._hand_quiet = self._hand_quiet + 1 if quiet else 0
            if ended or self._hand_quiet >= int(HANDOVER_S * FRAMES_PER_S):
                with self._lock:
                    if self.hand is hand:
                        self._adopt_hand()
        self.frames_sent += 1
        return frame

    def _advance(self) -> None:
        if self.plan is not None and self.incoming is not None:
            self._journal_row({"status": "done", "kind": self.plan.kind, "to": self.incoming.record.name})
        old, self.current, self.incoming = self.current, self.incoming, None
        self.plan, self._start_frame = None, None
        self.cue, self.by_hand = None, False
        self.gesture = ""
        if old:
            old.close()
        if self.current and self._on_change:
            try:
                self._on_change(self.current.record)
            except Exception as e:
                log_debug(f"[records] on_change: {e}")
        self._prefetch()

    def cleanup(self) -> None:
        for deck in (self.current, self.incoming, self.hand):
            if deck:
                deck.close()
        self.current = self.incoming = self.hand = None


def _default_grid_at(record: library.Record, start: float, seconds: float):
    """The record's grid round `start`, its bars counted from its first beat."""
    from utils.audio import beatgrid
    return beatgrid.grid_at(record.path, record.bpm, start, seconds,
                            anchor=beatgrid.grid_for(record.path, record.bpm))


# ── Sessions ─────────────────────────────────────────────────────────

_sessions: dict[int, "RecordsSession"] = {}


def get_records(guild_id: int) -> Optional["RecordsSession"]:
    return _sessions.get(guild_id)


class RecordsSession:
    def __init__(self, vc, crate: list[library.Record], requested_by: str, text_channel=None,
                 alone_grace_s: float = 120.0):
        self.vc = vc
        self.crate = crate
        self.requested_by = requested_by
        self.text_channel = text_channel
        self.started_at = time.time()
        self.played: list[str] = []
        self.names: list[str] = []
        self.listeners_seen: set[str] = set()
        self.source: Optional[CrossfadeSource] = None
        self._alone_grace = alone_grace_s
        self._closing = False
        self._task: Optional[asyncio.Task] = None
        self._rng = random.Random()
        self.requests: list[str] = []             # paths asked for at the booth, in order
        self.loading: Optional[str] = None        # a record being readied for the free deck
        self.last_load: Optional[dict] = None

    @property
    def guild_id(self) -> int:
        return self.vc.guild.id

    @property
    def channel_name(self) -> str:
        return getattr(self.vc.channel, "name", "voice")

    @property
    def now(self) -> Optional[library.Record]:
        return self.source.current.record if self.source and self.source.current else None

    #: How many fitting records are looked at for one whose opening has a
    #: beat steady enough to blend into, before settling for a cut.
    STEADY_TRIES = 3

    def _prepare(self, rec: library.Record) -> Optional[Next]:
        """A record made ready to come next, whatever its beat: the person
        asked for it."""
        from utils.audio import beatgrid
        seconds = probe_seconds(rec.path)
        if not seconds or seconds < MIN_RECORD_S:
            return None
        return Next(rec, seconds, gain_db(rec.path), beatgrid.grid_for(rec.path, rec.bpm),
                    beatgrid.first_sound(rec.path), beatgrid.bass_entry(rec.path, rec.bpm))

    def load(self, rec: library.Record) -> None:
        """Put `rec` on the free deck, now if it can be (`CrossfadeSource.load`),
        else next after the blend under way."""
        self.loading = rec.name

        def run():
            try:
                nxt = self._prepare(rec)
                src = self.source
                if nxt is None or src is None:
                    log_warning(f"[records] {rec.name} could not be read; not loaded")
                    self.last_load = {"name": rec.name, "result": "unreadable", "ts": time.time()}
                    return
                result = src.load(nxt)
                if result == "after" and rec.path not in self.requests:
                    self.requests.append(rec.path)
                self.last_load = {"name": rec.name, "result": result, "ts": time.time()}
            finally:
                self.loading = None
        threading.Thread(target=run, daemon=True, name="kaia-records-load").start()

    def _choose(self, deck: Deck) -> Optional[Next]:
        from utils.audio import beatgrid
        while self.requests:
            path = self.requests.pop(0)
            rec = next((r for r in self.crate if r.path == path), None)
            nxt = self._prepare(rec) if rec else None
            if nxt:
                return nxt
        passed_over: list[str] = []
        fallback: Optional[Next] = None
        rec = library.next_record(deck.record, self.crate, self.played, self._rng)
        for _ in range(5 + self.STEADY_TRIES):
            if rec is None:
                break
            seconds = probe_seconds(rec.path)
            if not seconds or seconds < MIN_RECORD_S:
                self.played.append(rec.path)
            else:
                grid = beatgrid.grid_for(rec.path, rec.bpm)
                if grid and grid.contrast >= BLEND_CONTRAST:
                    return Next(rec, seconds, gain_db(rec.path), grid, beatgrid.first_sound(rec.path),
                                beatgrid.bass_entry(rec.path, rec.bpm))
                fallback = fallback or Next(rec, seconds, None, grid, beatgrid.first_sound(rec.path),
                                            beatgrid.bass_entry(rec.path, rec.bpm))
                passed_over.append(rec.path)
                if len(passed_over) >= self.STEADY_TRIES:
                    break
            rec = library.next_record(deck.record, self.crate, self.played + passed_over, self._rng)
        if fallback is not None:
            fallback.gain = gain_db(fallback.record.path)
        return fallback

    def _changed(self, record: library.Record) -> None:
        self.played.append(record.path)
        self.names.append(record.name)
        log_action(f"[records] now playing {record.name} ({record.bpm or '?'} bpm, {record.key or '?'})")

    def _humans(self) -> list[str]:
        return [m.display_name for m in getattr(self.vc.channel, "members", []) if not m.bot]

    def _feel(self) -> None:
        """Her energy for the mixer, from her mood (arousal and energy)."""
        try:
            from utils.core.kaia_art_intent import mood
            m = mood() or {}
            vals = [float(m[k]) for k in ("arousal", "energy") if isinstance(m.get(k), (int, float))]
            if vals and self.source is not None:
                self.source.energy = min(1.0, max(0.0, sum(vals) / len(vals)))
        except Exception as e:
            log_debug(f"[records] mood not read: {e}")

    async def _watch(self) -> None:
        alone_since = None
        await asyncio.to_thread(self._feel)
        while not self._closing:
            await asyncio.sleep(15)
            await asyncio.to_thread(self._feel)
            people = self._humans()
            self.listeners_seen.update(people)
            if people:
                alone_since = None
            elif alone_since is None:
                alone_since = time.time()
            elif time.time() - alone_since >= self._alone_grace:
                log_action("[records] the channel emptied; stopping.")
                await self.stop()
                return
            if not self.vc.is_playing() and not self._closing:
                await self.stop()
                return

    def skip(self) -> None:
        if self.source:
            self.source.skip()

    async def stop(self, disconnect: bool = True) -> None:
        """End the set. `disconnect=False` when something else is taking the
        voice connection over (radio, a live set)."""
        if self._closing:
            return
        self._closing = True
        _sessions.pop(self.guild_id, None)
        try:
            if self.vc.is_playing():
                self.vc.stop()
        except Exception as e:
            log_debug(f"[records] stop playback: {e}")
        if self.source:
            self.source.cleanup()
        if disconnect:
            try:
                await self.vc.disconnect(force=True)
            except Exception as e:
                log_debug(f"[records] disconnect: {e}")
        if self._task and not self._task.done() and self._task is not asyncio.current_task():
            self._task.cancel()
        try:
            from utils.audio import dj_dashboard
            if not _sessions:
                await asyncio.to_thread(dj_dashboard.close_window)
        except Exception as e:
            log_debug(f"[records] DJ booth not closed: {e}")
        minutes = (time.time() - self.started_at) / 60
        late = self.source.late if self.source else []
        log_action(f"[records] set ended after {minutes:.1f} min, {len(self.names)} records; "
                   + (f"the voice thread was late {len(late)} times, worst {max(late) * 1000:.0f} ms."
                      if late else "no late frames."))
        self._remember(minutes)

    def _remember(self, minutes: float) -> None:
        if minutes < 1 or not self.names:
            return
        try:
            from utils.core.kaia_expression import remember
            crowd = sorted(self.listeners_seen - {self.requested_by})
            who = ", ".join(([self.requested_by] if self.requested_by else []) + crowd[:5])
            some = ", ".join(self.names[:3]) + ("…" if len(self.names) > 3 else "")
            remember("music",
                     f"[i played records in {self.channel_name} for {minutes:.0f} minutes — "
                     f"{len(self.names)} of them, starting with {some}"
                     f"{'; ' + who + ' listened' if who else ''}.]",
                     channel_id=getattr(self.text_channel, "id", None),
                     title="a records set",
                     detail={"kind": "records", "minutes": round(minutes, 1), "records": self.names,
                             "listeners": sorted(self.listeners_seen)})
        except Exception as e:
            log_debug(f"[records] set not remembered: {e}")

    def stats(self) -> dict:
        q = self.source._queued if self.source else None
        nxt = q.record.name if q else (self.source.incoming.record.name if self.source and self.source.incoming else None)
        now = self.now
        return {"now": now.name if now else None, "bpm": now.bpm if now else None,
                "key": now.key if now else None, "genre": now.genre if now else None,
                "next": nxt, "played": len(self.names), "channel": self.channel_name,
                "uptime_min": round((time.time() - self.started_at) / 60), "listeners": len(self._humans())}


async def start_records(channel, crate: list[library.Record], first: library.Record, *,
                        requested_by: str, text_channel=None, mix_beats: int = MIX_BEATS,
                        alone_grace_s: float = 120.0) -> RecordsSession:
    """Join `channel` and start the set at `first`. Stops whatever was playing there."""
    guild = channel.guild
    if (old := _sessions.get(guild.id)):
        await old.stop()
    try:
        from utils.audio.strudel_session import get_session
        if (synth := get_session(guild.id)):
            await synth.stop()
    except Exception as e:
        log_debug(f"[records] no live set to stop: {e}")
    try:
        from utils.radio import live
        await live.free_voice(guild)
    except Exception as e:
        log_debug(f"[records] radio not stopped: {e}")

    seconds = await asyncio.to_thread(probe_seconds, first.path)
    if not seconds:
        raise RuntimeError(f"could not read {first.name}")
    if not discord.opus.is_loaded():
        try:
            discord.opus._load_default()
        except Exception as exc:
            raise RuntimeError("libopus is not loaded") from exc

    vc = guild.voice_client
    if vc and vc.is_connected():
        await vc.move_to(channel)
    else:
        vc = await channel.connect(timeout=30.0, reconnect=True)

    session = RecordsSession(vc, crate, requested_by, text_channel, alone_grace_s)
    deck = Deck(first, 1.0, seconds, gain=await asyncio.to_thread(gain_db, first.path))
    from utils.audio import beatgrid
    deck.grid = await asyncio.to_thread(beatgrid.grid_for, first.path, first.bpm)
    session._changed(first)
    session.source = CrossfadeSource(deck, session._choose, on_change=session._changed,
                                     mix_beats=int(mix_beats))
    try:
        from utils.infrastructure.system.yaml_config import config
        session.source.rides = bool(config.get("music.records_kaia_hands", True))
        session.source.key_sync = bool(config.get("music.records_key_sync", True))
    except Exception as e:
        log_debug(f"[records] records_kaia_hands not read: {e}")
    settle("a records set")
    vc.play(session.source, after=lambda e: log_error(f"[records] playback error: {e}") if e else None)
    _sessions[guild.id] = session
    try:
        from utils.audio import dj_dashboard
        await asyncio.to_thread(dj_dashboard.serve)
        session._booth = asyncio.create_task(asyncio.to_thread(dj_dashboard.open_window))
        session._booth.add_done_callback(
            lambda t: t.cancelled() or not t.exception() or log_warning(f"[records] DJ booth window: {t.exception()}"))
    except Exception as e:
        log_debug(f"[records] DJ booth not opened: {e}")
    from utils.infrastructure.monitoring.async_task_registry import task_registry
    session._task = asyncio.create_task(session._watch())
    task_registry.register(f"records_watch_{guild.id}", session._task)
    return session


async def stop_all() -> None:
    for s in list(_sessions.values()):
        try:
            await s.stop()
        except Exception as e:
            log_debug(f"[records] stop_all: {e}")
