"""
Discord audio source fed by the Strudel engine's ffmpeg capture.

Same contract as the synth source it replaces: read() returns exactly one 20 ms
frame every 20 ms and never blocks discord.py's sender thread. The difference
is where the bytes come from — an ffmpeg pipe rather than numpy — so the
failure modes are pipe failure modes: a short read means ffmpeg is behind, and
EOF means it died and the stream needs restarting.
"""

from __future__ import annotations

import threading
import time
from collections import deque

try:
    import discord
    _AudioSource = discord.AudioSource
except Exception:                      # pragma: no cover
    _AudioSource = object

from utils.audio.strudel_engine import FRAME_BYTES, StrudelEngine
from utils.infrastructure.logging.kaia_logger import log_debug, log_warning

SILENCE = b"\x00" * FRAME_BYTES


class StrudelAudioSource(_AudioSource):
    def __init__(self, engine: StrudelEngine, buffer_frames: int = 100):
        self.engine = engine
        self._frames: deque[bytes] = deque()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._target = buffer_frames          # 100 frames = 2 s
        self.frames_sent = 0
        self.underruns = 0
        self.restarts = 0

        self._proc = engine.open_capture()
        self._thread = threading.Thread(target=self._pump, daemon=True,
                                        name="kaia-strudel-capture")
        self._thread.start()
        # Let the ring fill before discord.py pulls the first frame. ffmpeg
        # takes a moment to open the pulse source, and without this the very
        # first reads are underruns — harmless, but they are the first thing
        # in the log after a successful join and read as a fault.
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            with self._lock:
                if len(self._frames) >= min(25, self._target):
                    break
            time.sleep(0.05)

    def _pump(self) -> None:
        while not self._stop.is_set():
            proc = self._proc
            if proc is None or proc.stdout is None:
                break
            try:
                # readexactly semantics: a pulse capture can return short reads
                # and a partial frame would desynchronise the whole stream.
                buf = b""
                while len(buf) < FRAME_BYTES and not self._stop.is_set():
                    chunk = proc.stdout.read(FRAME_BYTES - len(buf))
                    if not chunk:
                        raise EOFError("ffmpeg capture ended")
                    buf += chunk
            except Exception as exc:
                if self._stop.is_set():
                    return
                self.restarts += 1
                log_warning(f"[music] capture died ({exc}); restarting (#{self.restarts})")
                try:
                    self._proc = self.engine.open_capture()
                except Exception as exc2:
                    log_warning(f"[music] could not restart capture: {exc2}")
                    return
                continue

            with self._lock:
                self._frames.append(buf)
                # Drop the oldest rather than grow without bound: this is a
                # live feed, so falling behind should cost latency once, not
                # accumulate a delay that keeps growing.
                while len(self._frames) > self._target * 3:
                    self._frames.popleft()

    def is_opus(self) -> bool:
        return False

    def read(self) -> bytes:
        with self._lock:
            if self._frames:
                self.frames_sent += 1
                return self._frames.popleft()
        self.underruns += 1
        if self.underruns in (1, 50, 500, 5000):
            log_warning(f"[music] capture underrun #{self.underruns}")
        return SILENCE

    def cleanup(self) -> None:
        self._stop.set()
        try:
            self.engine.close_capture()
        except Exception:
            pass
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        log_debug(f"[music] source cleaned up: {self.frames_sent} frames, "
                  f"{self.underruns} underruns, {self.restarts} restarts")

    def stats(self) -> dict:
        with self._lock:
            buffered = len(self._frames)
        return {
            "played_s": round(self.frames_sent * 0.02, 1),
            "buffered_s": round(buffered * 0.02, 2),
            "underruns": self.underruns,
            "capture_restarts": self.restarts,
        }
