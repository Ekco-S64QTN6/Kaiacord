"""PCM-level regression tests for the bounded tempo-synchronised echo bus."""
import numpy as np
import pytest

from utils.audio.dj_fx import (
    FRAME_BYTES,
    FRAME_SAMPLES,
    MAX_FEEDBACK,
    MAX_WET,
    RATE,
    TempoEcho,
)


def _frame(values=None):
    samples = np.zeros((FRAME_SAMPLES, 2), dtype=np.int16)
    if values:
        for index, value in values.items():
            samples[index] = value
    return samples.tobytes()


def _samples(frame):
    return np.frombuffer(frame, dtype=np.int16).reshape(FRAME_SAMPLES, 2)


def test_echo_uses_the_selected_beat_interval_and_decaying_feedback():
    effect = TempoEcho()
    assert effect.set(True, bpm=120, beats=1, feedback=0.5, wet=0.30)
    initial = effect.snapshot()
    assert initial["enabled"] is True
    assert initial["tail"] is False
    assert initial["delay_s"] == pytest.approx(0.5)
    assert initial["bpm"] == 120.0

    impulse = _frame({0: (12000, -12000)})
    first = effect.process(impulse)
    assert _samples(first)[0].tolist() == [12000, -12000]

    # Allow the wet/feedback ramp to reach its target before releasing input.
    for _ in range(7):
        effect.process(_frame())
    assert effect.set(False)
    assert effect.snapshot()["tail"] is True

    # A one-beat delay at 120 BPM is exactly 25 complete 20 ms frames.
    for _ in range(17):
        output = effect.process(_frame())
        assert np.max(np.abs(_samples(output))) == 0
    first_repeat = _samples(effect.process(_frame()))
    assert first_repeat[0, 0] == pytest.approx(3600, abs=2)
    assert first_repeat[0, 1] == pytest.approx(-3600, abs=2)

    for _ in range(24):
        effect.process(_frame())
    second_repeat = _samples(effect.process(_frame()))
    assert second_repeat[0, 0] == pytest.approx(1800, abs=3)
    assert second_repeat[0, 1] == pytest.approx(-1800, abs=3)
    assert abs(int(second_repeat[0, 0])) < abs(int(first_repeat[0, 0]))


def test_echo_parameters_are_bounded_and_reject_unsupported_values():
    effect = TempoEcho()
    for params in (
        {"bpm": 0, "beats": 1, "feedback": 0.3, "wet": 0.3},
        {"bpm": 241, "beats": 1, "feedback": 0.3, "wet": 0.3},
        {"bpm": 120, "beats": 3, "feedback": 0.3, "wet": 0.3},
        {"bpm": 120, "beats": 1, "feedback": MAX_FEEDBACK + 0.01, "wet": 0.3},
        {"bpm": 120, "beats": 1, "feedback": 0.3, "wet": MAX_WET + 0.01},
        {"bpm": 120, "beats": True, "feedback": 0.3, "wet": 0.3},
        {"bpm": float("nan"), "beats": 1, "feedback": 0.3, "wet": 0.3},
        {"bpm": 120, "beats": 1, "feedback": float("inf"), "wet": 0.3},
    ):
        assert effect.set(True, **params) is False
        assert effect.snapshot()["enabled"] is False


def test_active_echo_keeps_its_original_tempo_lock_but_allows_gain_changes():
    effect = TempoEcho()
    assert effect.set(True, bpm=120, beats=1, feedback=0.3, wet=0.25)
    original_delay = effect.snapshot()["delay_s"]

    # A tempo glide elsewhere in the set must not move the running delay head.
    assert effect.set(True, bpm=123, beats=1, feedback=0.5, wet=0.4)
    state = effect.snapshot()
    assert state["delay_s"] == original_delay
    assert state["bpm"] == 120.0
    assert state["feedback"] == 0.5
    assert state["wet"] == 0.4

    # Changing subdivisions while the ring contains audio is refused.
    assert effect.set(True, bpm=123, beats=2, feedback=0.5, wet=0.4) is False
    assert effect.snapshot()["delay_s"] == original_delay


def test_stopping_echo_closes_the_input_gate_then_releases_a_finite_tail():
    effect = TempoEcho()
    assert effect.set(True, bpm=120, beats=0.5, feedback=0.6, wet=0.45)
    for _ in range(12):
        effect.process(_frame({0: (5000, 5000)}))
    assert effect.set(False)
    state = effect.snapshot()
    assert not state["enabled"] and state["tail"]
    assert state["tail_remaining_s"] > 0

    frames = 0
    while effect.tail_active and frames < 500:
        output = effect.process(_frame())
        assert len(output) == FRAME_BYTES
        frames += 1
    assert not effect.active and not effect.tail_active
    assert effect.snapshot()["tail_remaining_s"] == 0
    assert frames < 500


def test_cancel_clears_a_live_echo_and_returns_dry_frames_unchanged():
    effect = TempoEcho()
    assert effect.set(True, bpm=128, beats=2, feedback=0.65, wet=0.5)
    effect.process(_frame({0: (16000, -16000)}))
    effect.cancel()
    dry = _frame({13: (1234, -2345)})
    assert effect.process(dry) is dry
    assert effect.snapshot()["enabled"] is False
    assert effect.snapshot()["tail"] is False


def test_wrong_sized_frames_are_not_touched_or_used_to_advance_the_ring():
    effect = TempoEcho()
    assert effect.set(True, bpm=120, beats=1, feedback=0.4, wet=0.3)
    malformed = b"\x01\x02"
    assert effect.process(malformed) is malformed
    assert effect.snapshot()["enabled"] is True
