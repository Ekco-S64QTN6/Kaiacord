"""Records: a set from the local music library, mixed record to record.

`!music records` plays the crate in `library.py` the way a DJ would: each next
record chosen to sit with the last in key and tempo, stretched to its tempo
(ffmpeg's rubberband, which keeps the pitch and the kicks where they were), its
first downbeat dropped on a bar of the record playing, and blended over sixteen
beats with the bass swapped halfway — or, where either beat is not steady
enough to lay over the other, cut cleanly on the bar. All of it is ffmpeg and NumPy on the
CPU: no model, no VRAM, nothing analysed live — the catalog already holds BPM
and key.

Same contract as the Strudel source: `read()` hands discord.py one 20 ms frame
every 20 ms and never blocks; ffmpeg output is pumped into a buffer on a
thread, and the next record is picked and probed on another, long before its
fade begins.
"""
from __future__ import annotations

import asyncio
import random
import re
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

try:
    import discord
    _AudioSource = discord.AudioSource
except Exception:                      # pragma: no cover
    _AudioSource = object

from utils.audio import library
from utils.infrastructure.logging.kaia_logger import log_action, log_debug, log_error, log_warning
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


#: Every record is brought to about this mean level, so the next one is not
#: twice as loud as the last. Never raised past its own peak.
TARGET_MEAN_DB = -14.0


def gain_db(path: str) -> float:
    """The gain that brings a record's mean level to TARGET_MEAN_DB without
    pushing its peak past full scale. 0 if it cannot be measured."""
    try:
        out = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-af", "volumedetect",
                              "-f", "null", "-"], capture_output=True, text=True, timeout=60).stderr
        mean = float(re.search(r"mean_volume:\s*(-?[\d.]+) dB", out).group(1))
        peak = float(re.search(r"max_volume:\s*(-?[\d.]+) dB", out).group(1))
    except (OSError, AttributeError, ValueError, subprocess.SubprocessError):
        return 0.0
    return round(max(-12.0, min(TARGET_MEAN_DB - mean, -peak, 12.0)), 1)


def open_pcm(path: str, ratio: float = 1.0, gain: float = 0.0, offset: float = 0.0) -> subprocess.Popen:
    """ffmpeg decoding a record to 48 kHz stereo s16le from `offset` seconds
    of its own time, stretched by `ratio` (`beatgrid.stretch_filter`: tempo
    changed, pitch and kick timing kept)."""
    from utils.audio.beatgrid import stretch_filter
    args = ["ffmpeg", "-nostdin", "-loglevel", "error"]
    if offset > 0:
        args += ["-ss", f"{offset:.4f}"]
    args += ["-i", path]
    filters = []
    if (stretch := stretch_filter(ratio)):
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
MIX_BEATS = 16
#: Cut transitions (no common tempo, or no clear beat): the outgoing record
#: fades over this many seconds, ending on its bar, and the next starts clean.
CUT_FADE_S = 1.5
#: Both records need a beat at least this clear (`beatgrid.Grid.contrast`) for
#: their grooves to be laid over each other. Four-on-the-floor dance records
#: measure 4.2 and up where they are mixed; rock, breaks and sparse intros
#: (Big Country, Evil Nine, an ambient opening) measure 1.8–3.3, and blending
#: those beat against beat is a clash. Below it the transition is a cut on the bar.
BLEND_CONTRAST = 4.0
#: The kick cross-correlation may move the incoming record by at most this
#: much. The counted grids land within a few ms (click tracks; a 2 ms comb at
#: a real mix point agreed to 1 ms); larger corrections came from sparse
#: intros and basslines the correlation latched onto.
MAX_FINE_S = 0.020
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
                 gain: float = 0.0, pad: int = 0, offset: float = 0.0):
        self.record = record
        self.ratio = ratio
        self.gain = gain
        self.grid = None                                    # beatgrid.Grid of its opening, for display
        self.slot = 1                                       # which CDJ: records alternate 1, 2, 1…
        self.loaded_at = time.time()
        self.pad = max(0, int(pad))
        self.offset = max(0.0, offset)                      # seconds of the record skipped, own time
        self.total_frames = int(((seconds - self.offset) / ratio * RATE + self.pad) / FRAME_SAMPLES)
        self.played = 0
        extra = {**({"gain": gain} if gain else {}), **({"offset": self.offset} if self.offset else {})}
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

    @property
    def done(self) -> float:
        return self.drop + (self.length if self.kind == "blend" else 0.0)


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
        # The incoming is silent until its first downbeat, so it is started
        # just short of it rather than from the top.
        offset = max(0.0, in_grid.downbeat - PREROLL_S)
        lead_in = (in_grid.downbeat - offset) / ratio       # incoming: start to its first downbeat
        earliest = now + lead_in + lead
        if mode == "end":
            latest = out_end - length - 0.5
            drop = out_grid.next_bar(latest - 4 * beat, out_ratio)
            if drop < earliest:
                drop = out_grid.next_bar(earliest, out_ratio)
        else:
            drop = out_grid.next_bar(earliest, out_ratio)
        if drop + length <= out_end + 0.01:
            return Plan("blend", drop - lead_in, drop, length, beat, ratio, nxt, offset)
    # A cut, on the outgoing bar where there is one.
    fade = CUT_FADE_S
    if mode == "end":
        drop = max(now + fade + lead, out_end - 0.05)
    elif out_grid:
        drop = out_grid.next_bar(now + fade + lead, out_ratio)
    else:
        drop = now + fade + lead
    drop = min(drop, max(now + lead, out_end))
    return Plan("cut", drop, drop, fade, 60.0 / playing_bpm if playing_bpm else 0.5, 1.0, nxt)


def gains(plan: Plan, t: np.ndarray) -> tuple:
    """(outgoing low, outgoing high, incoming low, incoming high) gains at times t."""
    if plan.kind == "cut":
        out = np.clip((plan.drop - t) / plan.length, 0.0, 1.0)
        inc = (t >= plan.drop).astype(np.float32)
        return out, out, inc, inc
    half = plan.length / 2
    swap = plan.drop + half
    rise = np.clip((t - plan.drop) / half, 0.0, 1.0)
    fall = np.clip((t - swap) / half, 0.0, 1.0)
    bass = np.clip((t - swap) / plan.beat, 0.0, 1.0)
    return 1.0 - bass, np.cos(fall * np.pi / 2), bass, np.sin(rise * np.pi / 2)


IDENTITY = (1.0, 1.0, 1.0, 1.0)


def mix_frames(out_parts, in_parts, g, uo=IDENTITY, ui=IDENTITY, master: float = 1.0) -> bytes:
    """The two decks summed: each band times the automix gain (`g`: the low
    and the rest, per sample) times the hands on the mixer (`uo`/`ui`: low,
    mid, high, channel gain)."""
    gol, goh, gil, gih = (np.asarray(x, dtype=np.float32).reshape(-1, 1) for x in g)
    y = np.zeros((FRAME_SAMPLES, 2), dtype=np.float32)
    if out_parts is not None:
        lo, mi, hi = out_parts
        y += (lo * (gol * uo[0]) + mi * (goh * uo[1]) + hi * (goh * uo[2])) * uo[3]
    if in_parts is not None:
        lo, mi, hi = in_parts
        y += (lo * (gil * ui[0]) + mi * (gih * ui[1]) + hi * (gih * ui[2])) * ui[3]
    if master != 1.0:
        y *= master
    return np.clip(np.rint(y), -32768, 32767).astype(np.int16).tobytes()


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
        self.applied = (1.0, 1.0, 0.0, 0.0)
        self.history: list[dict] = []
        self.planning_mode: Optional[str] = None
        self.controls = Controls()
        self.paused: set = set()                  # deck slots someone paused at the booth
        self._prefetch()

    def is_opus(self) -> bool:
        return False

    def _prefetch(self) -> None:
        if self._picking or self._queued or self.current is None:
            return
        self._picking = True
        deck = self.current

        def run():
            try:
                self._queued = self._pick(deck)
            except Exception as e:
                log_warning(f"[records] could not choose the next record: {e}")
                self._queued = None
            finally:
                self._exhausted = self._queued is None
                self._picking = False
        threading.Thread(target=run, daemon=True, name="kaia-records-pick").start()

    def skip(self) -> None:
        """Bring the next record in at the next bar it can land on."""
        self._begin_planning("skip")

    @staticmethod
    def _db(frame: Optional[bytes]) -> float:
        if not frame:
            return -90.0
        x = np.frombuffer(frame, dtype=np.int16)[::8].astype(np.float32)
        rms = float(np.sqrt(np.mean(x * x))) if len(x) else 0.0
        return round(20 * np.log10(rms / 32768.0), 1) if rms > 1 else -90.0

    def _begin_planning(self, mode: str) -> None:
        if self._planning or self.plan or self.current is None:
            return
        self._planning = True
        self.planning_mode = mode
        deck = self.current

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
                # Nothing slow may happen on discord.py's audio thread, which
                # must hand over a frame every 20 ms: the filter (and scipy's
                # import) is readied here, and the incoming ffmpeg is started
                # and buffered here, before the plan is published.
                global _SOS
                if _SOS is None:
                    _SOS = _bands()
                here = (deck.end - 60.0 if mode == "end" else deck.at()) * deck.ratio
                out_grid = self._grid_at(deck.record, max(0.0, here - 8.0), 45.0)
                if out_grid is not None:
                    deck.grid = out_grid                     # measured here, where it is mixed out
                for attempt in range(4):
                    lead = 2.0 + attempt                     # room to check the kicks, start ffmpeg, fill
                    plan = plan_transition(deck.at(), deck.ratio, out_grid, deck.end, nxt, mode,
                                           self._mix_beats, lead=lead)
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
                                    gain=nxt.gain, pad=max(0, pad), offset=plan.offset)
                    deadline = time.time() + 1.0
                    while not incoming.ready() and time.time() < deadline:
                        time.sleep(0.02)
                    if k > deck.played + 2 and incoming.ready():
                        break
                    incoming.close()
                    incoming = None
                if incoming is None or deck is not self.current:
                    return
                incoming.grid = nxt.grid
                incoming.slot = 3 - deck.slot
                plan.mode = mode
                self._queued = None
                self._start_frame = k
                self.incoming = incoming
                self.plan = plan
                why = ""
                if plan.kind == "cut":
                    why = ("; no clear beat" if not (out_grid and nxt.grid) else
                           f"; beat not steady enough to blend (contrast {out_grid.contrast:.1f} / "
                           f"{nxt.grid.contrast:.1f})" if min(out_grid.contrast, nxt.grid.contrast) < BLEND_CONTRAST
                           else "; bar not found" if not (out_grid.bar_known and nxt.grid.bar_known)
                           else "; tempos too far apart, or no room left to blend")
                plan.why = why.lstrip("; ")
                self.history.append({"ts": time.time(), "kind": plan.kind, "mode": mode,
                                     "from": deck.record.name, "to": nxt.record.name,
                                     "at": round(plan.drop, 2), "ratio": round(plan.ratio, 4),
                                     "why": plan.why})
                del self.history[:-50]
                log_action(f"[records] {plan.kind} into {nxt.record.name} at {plan.drop:.2f}s "
                           f"(stretch {plan.ratio:.4f}, {mode}{why})")
            except Exception as e:
                log_warning(f"[records] transition not planned: {e}")
            finally:
                self._planning = False
                self.planning_mode = None
        threading.Thread(target=run, daemon=True, name="kaia-records-plan").start()

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
        if plan is None and not self._planning and cur.remaining <= int((self._mix_beats * 0.6 + 25) * FRAMES_PER_S):
            self._begin_planning("end")
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
            inc = self.incoming.frame() or SILENCE
        hands = self.controls
        if plan is None and hands.flat():
            frame = out
            self.applied = (1.0, 1.0, 0.0, 0.0)
            self.levels["b"] = -90.0
        elif plan is None:
            frame = mix_frames(cur.split(out) if out is not None else None, None, (1.0, 1.0, 0.0, 0.0),
                               hands.channel(cur.slot), IDENTITY, hands.master)
            self.applied = (1.0, 1.0, 0.0, 0.0)
            self.levels["b"] = -90.0
        else:
            times = t0 + np.arange(FRAME_SAMPLES, dtype=np.float32) / RATE
            g = gains(plan, times)
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

    def _advance(self) -> None:
        old, self.current, self.incoming = self.current, self.incoming, None
        self.plan, self._start_frame = None, None
        if old:
            old.close()
        if self.current and self._on_change:
            try:
                self._on_change(self.current.record)
            except Exception as e:
                log_debug(f"[records] on_change: {e}")
        self._prefetch()

    def cleanup(self) -> None:
        for deck in (self.current, self.incoming):
            if deck:
                deck.close()
        self.current = self.incoming = None


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
        return Next(rec, seconds, gain_db(rec.path), beatgrid.grid_for(rec.path, rec.bpm))

    def request(self, rec: library.Record) -> None:
        """Play `rec` next. If nothing is mid-transition it replaces the record
        lined up now; otherwise it comes after the one already coming in."""
        if rec.path not in self.requests:
            self.requests.append(rec.path)
        log_action(f"[records] {rec.name} requested from the booth")
        src = self.source
        if src is None or src.plan is not None or src._planning:
            return

        def run():
            nxt = self._prepare(rec)
            if nxt is None:
                log_warning(f"[records] {rec.name} could not be read; not queued")
                if rec.path in self.requests:
                    self.requests.remove(rec.path)
                return
            if src.plan is None and not src._planning and rec.path in self.requests:
                src._queued = nxt
                src._exhausted = False
                self.requests.remove(rec.path)
        threading.Thread(target=run, daemon=True, name="kaia-records-request").start()

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
                    return Next(rec, seconds, gain_db(rec.path), grid)
                fallback = fallback or Next(rec, seconds, None, grid)
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

    async def _watch(self) -> None:
        alone_since = None
        while not self._closing:
            await asyncio.sleep(15)
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
    settle("a records set")
    vc.play(session.source, after=lambda e: log_error(f"[records] playback error: {e}") if e else None)
    _sessions[guild.id] = session
    try:
        from utils.audio import dj_dashboard
        await asyncio.to_thread(dj_dashboard.serve)
        session._booth = asyncio.create_task(asyncio.to_thread(dj_dashboard.open_window))
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
