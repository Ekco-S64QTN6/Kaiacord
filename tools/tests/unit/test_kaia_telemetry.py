"""Real numbers, only at extremes, never an invitation to invent."""
from utils.core import kaia_telemetry as t
from utils.core.hallucination_detector import HallucinationDetector as H

NOW = 1790000000.0


def test_only_an_extreme_reading_is_offered(monkeypatch):
    monkeypatch.setattr(t, "_prompt_share", {})
    today = "2026-09-24"
    assert t.reading(1, 0.6, today, NOW) == ""
    t.record_prompt(1, 13500, 16384)
    assert "82%" in t.reading(1, 0.6, today, t._prompt_share[1][1])
    assert "social energy reads 10" in t.reading(2, 0.1, today, NOW)
    assert "haven't dreamt in" in t.reading(2, 0.6, "2026-01-01", NOW)


def test_once_per_channel_per_cooldown(monkeypatch):
    monkeypatch.setattr(t, "_last_note", {})
    assert t.note_for(3, 0.05, "", NOW)
    assert t.note_for(3, 0.05, "", NOW + 60) == ""
    assert t.note_for(3, 0.05, "", NOW + t.NOTE_COOLDOWN + 1)


def test_a_measured_context_reading_is_not_treated_as_a_hallucination():
    assert not H.contains_hallucination("my context window is about 82% full right now.")
    assert H.contains_hallucination("my context window is optimized for long threads.")
