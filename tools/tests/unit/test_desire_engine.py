"""Conversational Desire Engine (roadmap 55-4).

The roadmap's success table marked *Desire & Initiative* as partial —
"proactive engine, but not needs-driven" — because the engine initiated when a
timer elapsed rather than when Kaia wanted something. These tests pin the
dynamics that make it needs-driven.
"""
import time

import pytest

from utils.core.kaia_desires import NEEDS, RISE_HOURS, DesireEngine


@pytest.fixture
def engine(tmp_path):
    return DesireEngine(path=str(tmp_path / "desires.json"))


def _age(engine, hours):
    engine.state.last_updated -= hours * 3600


# ── Dynamics ─────────────────────────────────────────────────────────

def test_outward_needs_rise_while_unmet(engine):
    before = engine.current()
    _age(engine, 6)
    after = engine.current()
    for need in ("social", "intellectual", "creative"):
        assert after[need] > before[need], need


def test_rest_recovers_during_silence(engine):
    """Fatigue, not appetite. Accruing rest with elapsed time like the other
    needs left her starved of contact and too tired to seek it at the same
    time, which suppressed initiative exactly when it should have risen."""
    engine.state.rest = 0.9
    _age(engine, 6)
    assert engine.current()["rest"] < 0.2


def test_silence_makes_her_want_to_initiate(engine):
    assert engine.wants_to_initiate() is False
    _age(engine, 12)
    assert engine.wants_to_initiate() is True
    assert engine.pressure() > 0.8


def test_a_long_conversation_leaves_her_quiet(engine):
    _age(engine, 12)
    assert engine.wants_to_initiate() is True
    for _ in range(6):
        engine.observe_exchange(grounded=True, length=500)
    assert engine.wants_to_initiate() is False
    assert engine.current()["rest"] > 0.5, "activity should accumulate fatigue"


def test_needs_are_clamped_to_the_unit_interval(engine):
    _age(engine, 500)
    for need, level in engine.current().items():
        assert 0.0 <= level <= 1.0, need
    for _ in range(50):
        engine.observe_exchange(grounded=True, length=900)
    for need, level in engine.current().items():
        assert 0.0 <= level <= 1.0, need


def test_a_brief_exchange_satisfies_less_than_a_substantial_one(engine, tmp_path):
    other = DesireEngine(path=str(tmp_path / "other.json"))
    engine.observe_exchange(grounded=False, length=10)
    other.observe_exchange(grounded=True, length=900)
    assert engine.current()["social"] > other.current()["social"]
    assert engine.current()["intellectual"] > other.current()["intellectual"]


def test_creation_discharges_only_the_creative_need(engine):
    before = engine.current()
    engine.observe_creation()
    after = engine.current()
    assert after["creative"] < before["creative"]
    assert after["intellectual"] >= before["intellectual"] - 1e-9


# ── Influence on behaviour ───────────────────────────────────────────

def test_source_multiplier_favours_the_unmet_need(engine):
    engine.state.social, engine.state.creative = 1.0, 0.0
    engine.state.last_updated = time.time()
    assert engine.source_multiplier("conversation_followup") > engine.source_multiplier("idle_quirk")


def test_unmapped_sources_are_left_at_their_configured_weight(engine):
    assert engine.source_multiplier("something_new") == 1.0


def test_multiplier_reshapes_rather_than_replaces(engine):
    """It must stay a bias: a source Kaia does not currently need should still
    be reachable, or the diversity rules stop meaning anything."""
    for source in DesireEngine.SOURCE_NEEDS:
        for level in (0.0, 1.0):
            for need in NEEDS:
                setattr(engine.state, need, level)
            engine.state.last_updated = time.time()
            assert 0.4 <= engine.source_multiplier(source) <= 2.0


def test_every_mapped_need_is_a_real_need():
    assert set(DesireEngine.SOURCE_NEEDS.values()) <= set(NEEDS)


def test_prompt_injection_is_silent_until_a_need_is_pressing(engine):
    assert engine.get_prompt_injection() == ""
    _age(engine, 12)
    line = engine.get_prompt_injection()
    assert line.startswith("[private:") and line.endswith("]")


def test_prompt_injection_mentions_depletion_when_tired(engine):
    """Starved of contact but freshly worn out.

    Reached by going quiet (social rises, fatigue clears) and then making
    several things in a row, which discharges the creative need while
    accumulating rest. Setting `rest` directly after ageing would not work —
    the next read recovers it, which is the point of the field.
    """
    _age(engine, 12)
    for _ in range(4):
        engine.observe_creation()
    assert engine.current()["rest"] > 0.75
    assert "depleted" in engine.get_prompt_injection()


def test_injection_is_a_single_line(engine):
    """It is prepended to the system prompt on every qualifying turn."""
    _age(engine, 20)
    assert "\n" not in engine.get_prompt_injection()


# ── Persistence ──────────────────────────────────────────────────────

def test_state_survives_a_restart(engine, tmp_path):
    engine.observe_creation()
    saved = engine.current()["creative"]
    reloaded = DesireEngine(path=engine.path).current()["creative"]
    assert abs(reloaded - saved) < 0.05


def test_a_missing_or_corrupt_state_file_yields_defaults(tmp_path):
    bad = tmp_path / "corrupt.json"
    bad.write_text("{not json", encoding="utf-8")
    for path in (str(bad), str(tmp_path / "absent.json")):
        levels = DesireEngine(path=path).current()
        assert set(levels) == set(NEEDS)
        assert all(0.0 <= v <= 1.0 for v in levels.values())


def test_rise_hours_are_all_positive():
    assert all(h > 0 for h in RISE_HOURS.values())
