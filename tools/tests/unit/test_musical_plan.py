"""Musical transition assessment: proxies, pacing and honest fallback."""
from utils.audio import musical_plan
from utils.audio.songmap import PhraseProfile, PhraseState
from utils.audio.library import Record


def _state(start, end, section, *, full=-12.0, bass=-12.0, lead=-12.0,
           upper=-12.0, transient=-12.0, aligned=True):
    return PhraseState(
        start=start, end=end, aligned=aligned, bars=4 if aligned else None,
        full_db=full, bass_db=bass, lead_db=lead, upper_db=upper,
        transient_db=transient, energy_change_db=0.0,
        section=section, section_strength=0.7 if section else 0.0,
    )


def _profile(*states, duration=64.0, aligned=True):
    return PhraseProfile(
        duration=duration, phrase_bars=4, grid_bpm=120.0,
        grid_contrast=8.0, aligned=aligned, phrases=tuple(states),
    )


def _records(current_genre="House", candidate_genre="Techno"):
    current = Record("/music/current.mp3", "Alpha", "Current", 120.0, "8A", current_genre)
    candidate = Record("/music/candidate.mp3", "Beta", "Candidate", 120.0, "8A", candidate_genre)
    return current, candidate


def test_build_to_drop_is_a_coherent_payoff_and_palette_change():
    current, candidate = _records()
    out = _profile(_state(0, 64, "build_candidate", full=-8, bass=-12, lead=-12))
    inc = _profile(_state(0, 64, "drop_candidate", full=-18, bass=-18, lead=-18))
    result = musical_plan.assess_transition(current, candidate, {"beats": 64, "back": 0, "cue": 0},
                                            out, inc)

    assert result.available
    assert result.preference == "prefer"
    assert "pay off" in result.purpose
    assert any("coherent palette change" in reason for reason in result.reasons)
    assert result.incoming_role == "peak"
    assert result.outgoing_aligned and result.incoming_aligned
    trace = result.trace()
    assert trace["outgoing_section"] == "build_candidate"
    assert trace["incoming_section"] == "drop_candidate"


def test_cluttered_measured_blend_is_deferred_not_mistaken_for_a_bad_lock():
    current, candidate = _records("House", "House")
    out = _profile(_state(0, 64, "build_candidate", full=-2, bass=-2, lead=-2,
                          upper=-2, transient=-2))
    inc = _profile(_state(0, 64, "drop_candidate", full=-2, bass=-2, lead=-2,
                          upper=-2, transient=-2))
    edge = {"beats": 64, "back": 0, "cue": 0, "agree": 16, "bars": 16, "ratio": 1.0}
    result = musical_plan.assess_transition(current, candidate, edge, out, inc)

    assert edge["agree"] == edge["bars"]  # the technical lock remains valid
    assert result.available and result.preference == "defer_if_alternative"
    assert any("midrange/presence" in reason for reason in result.reasons)
    assert "not vocal detection" in " ".join(result.reasons)


def test_missing_profiles_are_neutral_and_preserve_measured_rank():
    current, candidate = _records()
    result = musical_plan.assess_transition(current, candidate, {"beats": 64}, None, None)
    assert not result.available
    assert result.score == 0.0
    assert result.preference == "neutral"
    assert "unavailable" in result.purpose


def test_set_arc_prefers_a_breath_after_a_peak_and_spaces_repeated_peaks():
    after_peak, _ = musical_plan.arc_adjustment("breath", ["groove", "lift", "peak"])
    after_breath, _ = musical_plan.arc_adjustment("peak", ["groove", "lift", "breath"])
    repeated_peak, reasons = musical_plan.arc_adjustment("peak", ["peak", "groove", "peak"])
    first_peak, _ = musical_plan.arc_adjustment("peak", [])
    assert after_peak > 0
    assert after_breath > first_peak
    assert repeated_peak < first_peak
    assert any("stacking peaks" in reason for reason in reasons)


def test_unaligned_windows_are_used_as_time_local_evidence_without_phrase_claims():
    current, candidate = _records()
    out = _profile(_state(0, 64, "build_candidate", aligned=False), aligned=False)
    inc = _profile(_state(0, 64, "drop_candidate", aligned=False), aligned=False)
    result = musical_plan.assess_transition(current, candidate, {"beats": 64}, out, inc)
    assert result.available
    assert not result.outgoing_aligned and not result.incoming_aligned
    assert result.outgoing_section == "build_candidate"
    assert result.incoming_role == "peak"
