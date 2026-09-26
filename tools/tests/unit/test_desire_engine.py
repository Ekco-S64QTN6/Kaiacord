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
    """Silence raises pressure, and she acts on it.

    This used to open by asserting she would *not* initiate from a fresh
    engine (needs at 0.5/0.5/0.4, pressure 0.37). That only held because the
    threshold was 0.55, and that threshold is what made her mute: on live state
    the ceiling was pressure 0.16, so 101 of 102 proactive evaluations in the
    production log declined and she spoke first exactly once. Moderate need is
    now a perfectly good reason to say something — the gate shapes what she
    reaches for, it does not keep her quiet.
    """
    resting = engine.pressure()
    _age(engine, 12)
    assert engine.wants_to_initiate() is True
    assert engine.pressure() > 0.8
    assert engine.pressure() > resting, "silence did not raise pressure"


def test_she_will_speak_first_under_ordinary_conditions(engine):
    """The regression that matters: a bot that cannot chat first.

    Pressure on the real `memory/desires.json` measured 0.27. Anything at or
    below that has to clear the bar, or the proactive engine — nine sources,
    a whole subsystem — never fires.
    """
    assert engine.pressure() >= 0.12
    assert engine.wants_to_initiate() is True, \
        "she cannot initiate from a resting state"


def test_the_gate_can_be_reduced_to_decoration(engine, monkeypatch):
    """`desires.gate_enabled: false` keeps the needs vector shaping source
    choice and the prompt injection while never blocking initiation."""
    from utils.infrastructure.system import yaml_config

    for _ in range(10):
        engine.observe_exchange(grounded=True, length=900)
    assert engine.wants_to_initiate() is False, "precondition: talked out"

    real_get = yaml_config.config.get
    monkeypatch.setattr(
        yaml_config.config, "get",
        lambda k, d=None: False if k == "desires.gate_enabled" else real_get(k, d))
    assert engine.wants_to_initiate() is True


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


def test_making_something_discharges_the_creative_need(tmp_path, monkeypatch):
    """Only !art did, so creative sat at 1.0 and every chat turn said 'it itches'."""
    from utils.core import kaia_desires, kaia_expression
    engine = kaia_desires.DesireEngine(path=str(tmp_path / "desires.json"))
    engine.state.creative = 1.0
    monkeypatch.setattr(kaia_desires, "desire_engine", engine)
    monkeypatch.setattr(kaia_expression, "telemetry_path", lambda p: str(tmp_path / "growth.jsonl"))
    kaia_expression.remember("music", "[i played a trance set]")
    assert engine.state.creative < 0.5
