"""Bounded tempo-synchronised master effects for the records renderer.

The first live bus effect is a beat-synchronised echo. It owns a fixed-size
float32 delay ring, caps feedback/wet gain, ramps parameter changes over PCM
frames and stops accepting dry input when the operator releases it. The
remaining feedback tail is finite and fades before the ring is cleared.
"""
from __future__ import annotations

import math

import numpy as np

RATE = 48_000
FRAME_MS = 20
FRAME_SAMPLES = RATE * FRAME_MS // 1000
FRAME_BYTES = FRAME_SAMPLES * 2 * 2

MAX_DELAY_S = 5.0
MIN_BPM = 50.0
MAX_BPM = 240.0
SUPPORTED_ECHO_BEATS = (0.5, 1.0, 2.0, 4.0)
MAX_FEEDBACK = 0.65
MAX_WET = 0.50
PARAMETER_RAMP_FRAMES = 8
TAIL_REPEATS = 6
TAIL_FADE_FRAMES = 8
LIMIT_FROM = 0.80 * 32767.0


def _finite_number(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _soft_limit(samples: np.ndarray) -> np.ndarray:
    """The same bounded soft knee used by the program mixer."""
    magnitude = np.abs(samples)
    if magnitude.size == 0 or float(magnitude.max()) <= LIMIT_FROM:
        return samples
    headroom = 32767.0 - LIMIT_FROM
    over = magnitude > LIMIT_FROM
    out = samples.copy()
    out[over] = (
        np.sign(samples[over])
        * (LIMIT_FROM + headroom * np.tanh((magnitude[over] - LIMIT_FROM) / headroom))
    )
    return out


class TempoEcho:
    """A finite feedback echo on the rendered master bus.

    The delay is selected from the on-air tempo when enabled. Delay length
    cannot change while an echo or its tail is active, avoiding a moving read
    head and discontinuous repeats. Feedback is always <= 0.65 and wet gain
    <= 0.50. Stopping closes the input gate but lets six repeats decay, with
    the final eight frames ramped to silence.
    """

    def __init__(self) -> None:
        capacity = int(MAX_DELAY_S * RATE) + 1
        self._buffer = np.zeros((capacity, 2), dtype=np.float32)
        self._write = 0
        self._delay_samples = 0
        self._beats = 1.0
        self._bpm = 0.0
        self._feeding = False
        self._tail_frames = 0
        self._tail_fade_started = False
        self._feedback = 0.0
        self._wet = 0.0
        self._feedback_from = 0.0
        self._feedback_target = 0.0
        self._wet_from = 0.0
        self._wet_target = 0.0
        self._ramp_remaining = 0

    @property
    def active(self) -> bool:
        return self._feeding

    @property
    def tail_active(self) -> bool:
        return not self._feeding and self._tail_frames > 0

    def _start_ramp(self, feedback: float, wet: float) -> None:
        self._feedback_from = self._feedback
        self._feedback_target = feedback
        self._wet_from = self._wet
        self._wet_target = wet
        self._ramp_remaining = PARAMETER_RAMP_FRAMES

    def set(
        self,
        enabled: bool,
        *,
        bpm: float | None = None,
        beats: float = 1.0,
        feedback: float = 0.35,
        wet: float = 0.30,
    ) -> bool:
        """Start/update the echo, or stop feeding it and release its finite tail.

        Invalid or unsupported parameters are rejected instead of silently
        widening the advertised range. Enabling requires a known, plausible
        playback BPM. A running delay can change its feedback/wet values, but
        not its beat length; a new length is accepted after the tail clears.
        """
        if not isinstance(enabled, bool):
            return False
        if not enabled:
            if self._feeding:
                self._feeding = False
                repeats = int(math.ceil(self._delay_samples / FRAME_SAMPLES))
                self._tail_frames = repeats * TAIL_REPEATS
                self._tail_fade_started = False
            return True

        tempo = _finite_number(bpm)
        beat_count = _finite_number(beats)
        fb = _finite_number(feedback)
        wet_gain = _finite_number(wet)
        if (
            tempo is None or not MIN_BPM <= tempo <= MAX_BPM
            or beat_count not in SUPPORTED_ECHO_BEATS
            or fb is None or not 0.0 <= fb <= MAX_FEEDBACK
            or wet_gain is None or not 0.0 <= wet_gain <= MAX_WET
        ):
            return False

        delay_samples = int(round(RATE * 60.0 / tempo * beat_count))
        if not FRAME_SAMPLES < delay_samples < len(self._buffer) - FRAME_SAMPLES:
            return False
        if (self._feeding or self.tail_active) and delay_samples != self._delay_samples:
            return False

        if not self._feeding and not self.tail_active:
            self._buffer.fill(0.0)
            self._write = 0
            self._delay_samples = delay_samples
        self._delay_samples = delay_samples
        self._beats = beat_count
        self._bpm = tempo
        self._feeding = True
        self._tail_frames = 0
        self._tail_fade_started = False
        self._start_ramp(fb, wet_gain)
        return True

    def process(self, frame: bytes) -> bytes:
        """Process exactly one 20 ms stereo s16le frame; no decode or allocation growth."""
        if len(frame) != FRAME_BYTES or (not self._feeding and not self.tail_active):
            return frame

        dry = np.frombuffer(frame, dtype=np.int16).astype(np.float32).reshape(FRAME_SAMPLES, 2)
        if self._ramp_remaining:
            elapsed = PARAMETER_RAMP_FRAMES - self._ramp_remaining + 1
            phase = elapsed / PARAMETER_RAMP_FRAMES
            weight = 0.5 - 0.5 * math.cos(math.pi * phase)
            self._feedback = self._feedback_from + (
                self._feedback_target - self._feedback_from
            ) * weight
            self._wet = self._wet_from + (self._wet_target - self._wet_from) * weight
            self._ramp_remaining -= 1

        offsets = np.arange(FRAME_SAMPLES, dtype=np.int64)
        write_indices = (self._write + offsets) % len(self._buffer)
        read_indices = (write_indices - self._delay_samples) % len(self._buffer)
        delayed = self._buffer[read_indices].copy()
        if self._feeding:
            self._buffer[write_indices] = dry + delayed * self._feedback
        else:
            self._buffer[write_indices] = delayed * self._feedback
        mixed = dry + delayed * self._wet
        self._write = (self._write + FRAME_SAMPLES) % len(self._buffer)

        if not self._feeding:
            self._tail_frames -= 1
            if self._tail_frames <= TAIL_FADE_FRAMES and not self._tail_fade_started:
                self._tail_fade_started = True
                self._start_ramp(0.0, 0.0)
            if self._tail_frames <= 0:
                self.cancel()
        limited = _soft_limit(mixed)
        return np.clip(np.rint(limited), -32768, 32767).astype(np.int16).tobytes()

    def cancel(self) -> None:
        """Immediately clear all delay state for hand-back, skip reset or shutdown."""
        self._buffer.fill(0.0)
        self._write = 0
        self._delay_samples = 0
        self._beats = 1.0
        self._bpm = 0.0
        self._feeding = False
        self._tail_frames = 0
        self._tail_fade_started = False
        self._feedback = self._wet = 0.0
        self._feedback_from = self._feedback_target = 0.0
        self._wet_from = self._wet_target = 0.0
        self._ramp_remaining = 0

    def snapshot(self) -> dict:
        return {
            "enabled": self._feeding,
            "tail": self.tail_active,
            "beats": self._beats,
            "bpm": round(self._bpm, 2) if self._bpm else None,
            "delay_s": round(self._delay_samples / RATE, 4) if self._delay_samples else 0.0,
            "feedback": round(self._feedback_target, 3),
            "wet": round(self._wet_target, 3),
            "tail_remaining_s": round(self._tail_frames * FRAME_MS / 1000.0, 2),
        }
