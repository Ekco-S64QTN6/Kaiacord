"""Bounded DJ skill catalog, phrase scheduler and manual-ownership tests."""
from types import SimpleNamespace

import numpy as np
import pytest

from utils.audio import dj_skills as S


def _phrase(start, end, section, *, aligned=True, bars=4, strength=0.8):
    return SimpleNamespace(
        start=float(start), end=float(end), section=section,
        aligned=aligned, bars=bars if aligned else None,
        section_strength=strength,
    )


def _profile(*phrases, aligned=True, duration=None):
    end = max((p.end for p in phrases), default=0.0)
    return SimpleNamespace(
        duration=float(duration if duration is not None else end),
        phrase_bars=4, aligned=aligned, phrases=tuple(phrases),
    )


def test_catalog_defines_only_real_engine_capabilities_and_complete_contracts():
    S.validate_catalog()
    assert set(S.SKILL_CATALOG) == {
        "solo_build_pressure", "solo_drop_reveal", "solo_breakdown_breathe",
        "solo_groove_hold", "solo_legacy_phrase_eq", "blend_headroom_ride",
        "blend_upper_exchange", "blend_air_handoff", "echo_out",
    }
    for spec in S.SKILL_CATALOG.values():
        assert spec.purpose and spec.preconditions and spec.capabilities
        assert spec.timing and spec.cancel_release and spec.fallback
        assert spec.explanation and spec.renderer


def test_action_validation_rejects_unsupported_lanes_and_out_of_range_parameters():
    scheduler = S.SkillScheduler()
    with pytest.raises(ValueError, match="does not own"):
        scheduler._action(
            "solo_build_pressure", "solo.mid", 0, 1, 1, 2, 0.95, "invalid"
        )
    with pytest.raises(ValueError, match="out-of-bounds"):
        scheduler._action(
            "solo_build_pressure", "solo.low", 0, 1, 1, 2, 1.30, "too large"
        )
    with pytest.raises(ValueError, match="invalid action timing"):
        scheduler._action(
            "solo_build_pressure", "solo.low", 2, 1, 1, 3, 0.94, "time reversal"
        )


def test_profile_compiler_schedules_build_pressure_and_drop_reveal_on_counted_phrases():
    scheduler = S.SkillScheduler()
    scheduler.set_solo_profile(_profile(
        _phrase(0, 8, "build_candidate"),
        _phrase(8, 16, "drop_candidate"),
        _phrase(16, 24, "breakdown_candidate"),
        _phrase(24, 32, "groove_candidate"),
    ), fingerprint=1234)

    build, build_label, build_id, handled = scheduler.render_solo(
        np.array([6.49, 6.51], dtype=np.float32), slot=1
    )
    assert handled and build_id == "solo_build_pressure"
    assert "build candidate" in build_label
    assert build[0][-1] == pytest.approx(0.94, abs=0.01)
    assert build[2][-1] == pytest.approx(1.04, abs=0.01)

    drop, drop_label, drop_id, handled = scheduler.render_solo(
        np.array([9.0, 9.01], dtype=np.float32), slot=1
    )
    assert handled and drop_id == "solo_drop_reveal"
    assert "drop candidate" in drop_label
    assert drop[0][-1] == pytest.approx(1.05, abs=0.01)
    assert drop[2][-1] == pytest.approx(0.98, abs=0.01)


def test_breakdown_and_groove_are_explicit_no_op_skills_not_timer_gestures():
    scheduler = S.SkillScheduler()
    scheduler.set_solo_profile(_profile(
        _phrase(0, 8, "breakdown_candidate"),
        _phrase(8, 16, "groove_candidate"),
    ), fingerprint=5)

    breakdown, label, skill_id, handled = scheduler.render_solo(
        np.array([2.0, 2.02], dtype=np.float32), slot=1
    )
    assert handled and skill_id == "solo_breakdown_breathe"
    assert "breakdown breathe" in label
    assert all(np.allclose(f, 1.0) for f in breakdown)

    groove, label, skill_id, handled = scheduler.render_solo(
        np.array([10.0, 10.02], dtype=np.float32), slot=1
    )
    assert handled and skill_id == "solo_groove_hold"
    assert "groove carry" in label
    assert all(np.allclose(f, 1.0) for f in groove)


def test_unaligned_profiles_never_promote_section_labels_to_phrase_skills():
    scheduler = S.SkillScheduler()
    scheduler.set_solo_profile(_profile(
        _phrase(0, 8, "drop_candidate", aligned=False),
        aligned=False,
    ), fingerprint=5)
    factors, label, skill_id, handled = scheduler.render_solo(
        np.array([2.0, 2.02], dtype=np.float32), slot=1
    )
    assert not handled
    assert label == "" and skill_id == ""
    assert all(np.allclose(f, 1.0) for f in factors)
    assert scheduler.snapshot()["profile_aligned"] is False


def test_profile_action_plan_is_bounded_even_for_long_records():
    phrases = tuple(
        _phrase(i * 8, (i + 1) * 8, "build_candidate")
        for i in range(100)
    )
    scheduler = S.SkillScheduler()
    scheduler.set_solo_profile(_profile(*phrases, duration=800), fingerprint=9)
    assert scheduler.snapshot()["solo_actions"] == S.MAX_PROFILE_ACTIONS


def test_overlapping_actions_require_explicit_composition_declarations():
    build = S.SkillScheduler._action(
        "solo_build_pressure", "solo.low", 0, 1, 2, 3, 0.94, "build"
    )
    drop = S.SkillScheduler._action(
        "solo_drop_reveal", "solo.low", 1, 1.5, 2, 3, 1.05, "drop"
    )
    S._validate_action_set([build, drop], 8)  # reciprocal declaration permits this handoff
    legacy = S.SkillScheduler._action(
        "solo_legacy_phrase_eq", "solo.low", 1, 1.5, 2, 3, 0.90, "legacy"
    )
    with pytest.raises(ValueError, match="do not declare composition"):
        S._validate_action_set([build, legacy], 8)


def _blend_plan(kind="blend"):
    return SimpleNamespace(
        kind=kind, drop=30.0, length=64.0, beat=0.5, done=100.0,
    )


def test_blend_compiler_retains_headroom_exchange_and_outgoing_air_skills():
    scheduler = S.SkillScheduler()
    plan = _blend_plan()
    scheduler.plan_blend(plan, energy=0.8, ramp_s=8.0, tail_s=16.0)
    assert scheduler.snapshot()["blend_actions"] == 4

    factors, label, skill_id = scheduler.render_blend(
        plan, np.array([50.0, 50.02], dtype=np.float32), out_slot=1, in_slot=2
    )
    assert skill_id == "blend_upper_exchange"
    assert "soft limiter" in label
    assert "upper-band" in label
    # The stage is the existing 0.84 multiplier. The upper bands trade in
    # opposite directions: outgoing rises slightly while incoming steps back.
    assert factors[0][-1] == pytest.approx(S.STAGE_MULTIPLIER, abs=0.01)
    assert factors[2][-1] > factors[5][-1]
    assert factors[2][-1] == pytest.approx(S.STAGE_MULTIPLIER * 1.108, abs=0.02)


def test_blend_manual_override_eases_owned_lane_and_explicit_handback_restores_skill():
    scheduler = S.SkillScheduler()
    plan = _blend_plan()
    scheduler.plan_blend(plan, energy=0.8, ramp_s=8.0, tail_s=16.0)
    times = np.array([51.0, 51.02], dtype=np.float32)
    baseline, _, _ = scheduler.render_blend(plan, times, out_slot=1, in_slot=2)

    scheduler.manual_override(1, "high", at=50.0, bar_s=2.0)
    during, _, _ = scheduler.render_blend(plan, times, out_slot=1, in_slot=2)
    assert abs(float(during[2][-1]) - S.STAGE_MULTIPLIER) < abs(float(baseline[2][-1]) - S.STAGE_MULTIPLIER)
    assert during[5][-1] == pytest.approx(baseline[5][-1])
    assert scheduler.snapshot()["manual_overrides"]

    scheduler.hand_back_all()
    after, _, _ = scheduler.render_blend(plan, times, out_slot=1, in_slot=2)
    assert after[2][-1] == pytest.approx(baseline[2][-1])
    assert scheduler.snapshot()["manual_overrides"] == []


def test_manual_override_releases_solo_legacy_fallback_lane_over_a_bar():
    scheduler = S.SkillScheduler()
    values = (
        np.array([0.90, 0.90], dtype=np.float32),
        np.array([1.0, 1.0], dtype=np.float32),
        np.array([1.0, 1.0], dtype=np.float32),
    )
    scheduler.manual_override(2, "low", at=0.0, bar_s=2.0)
    masked = scheduler.mask_solo_fallback(values, np.array([1.0, 1.02]), slot=2)
    assert masked[0][-1] > values[0][-1]
    assert masked[0][-1] < 1.0
    assert np.array_equal(masked[1], values[1])
    scheduler.hand_back_all()
    restored = scheduler.mask_solo_fallback(values, np.array([1.0, 1.02]), slot=2)
    assert np.array_equal(restored[0], values[0])


def test_cancelled_blend_actions_are_discarded_and_echo_label_uses_existing_echo_engine():
    scheduler = S.SkillScheduler()
    plan = _blend_plan()
    scheduler.plan_blend(plan, energy=0.8, ramp_s=8.0, tail_s=16.0)
    scheduler.cancel_blend()
    factors, label, skill_id = scheduler.render_blend(
        plan, np.array([50.0, 50.02], dtype=np.float32), out_slot=1, in_slot=2
    )
    assert skill_id == "" and label == ""
    assert all(np.allclose(f, 1.0) for f in factors)

    echo = _blend_plan("echo")
    scheduler.plan_blend(echo, energy=0.5, ramp_s=2.0, tail_s=4.0)
    factors, label, skill_id = scheduler.render_blend(
        echo, np.array([40.0, 40.02], dtype=np.float32), out_slot=1, in_slot=2
    )
    assert skill_id == "echo_out" and "bounded echo-out" in label
    assert all(np.allclose(f, 1.0) for f in factors)


def test_profile_missing_falls_back_without_claiming_structure():
    scheduler = S.SkillScheduler()
    scheduler.set_solo_profile(None, fingerprint=0)
    factors, label, skill_id, handled = scheduler.render_solo(
        np.array([2.0, 2.02], dtype=np.float32), slot=1
    )
    assert not handled and label == "" and skill_id == ""
    assert all(np.allclose(f, 1.0) for f in factors)
