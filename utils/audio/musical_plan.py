"""Explainable musical preference layered on top of measured transition feasibility.

This module never decides whether an audio blend is technically safe. The set
graph is the authority for that: only transitions measured by mixcheck appear
as candidates. Profiles contribute a soft, time-local preference and an
explanation. Missing evidence is neutral, and weak choices are deferred when
a better measured alternative exists rather than becoming a new hard gate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class MusicalAssessment:
    available: bool
    score: float
    preference: str
    purpose: str
    outgoing_section: Optional[str]
    incoming_section: Optional[str]
    incoming_role: str
    outgoing_aligned: bool
    incoming_aligned: bool
    overlaps: dict[str, float]
    reasons: tuple[str, ...]

    def trace(self) -> dict:
        """JSON-safe explanation, deliberately separate from technical facts."""
        return asdict(self)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _level(db: float) -> float:
    """Coarse within-track feature prominence, not calibrated loudness."""
    return _clamp((float(db) + 24.0) / 24.0)


def _at(profile, seconds: float):
    phrases = getattr(profile, "phrases", ()) or ()
    if not phrases:
        return None
    for phrase in phrases:
        if phrase.start <= seconds < phrase.end:
            return phrase
    return min(phrases, key=lambda p: abs((p.start + p.end) / 2.0 - seconds))


def _role(section: Optional[str]) -> str:
    return {
        "intro_candidate": "settle",
        "groove_candidate": "groove",
        "build_candidate": "lift",
        "breakdown_candidate": "breath",
        "drop_candidate": "peak",
        "outro_candidate": "release",
    }.get(section or "", "unknown")


def _purpose(outgoing: Optional[str], incoming: Optional[str]) -> str:
    pairs = {
        ("build_candidate", "drop_candidate"): "pay off the outgoing build with an incoming drop",
        ("breakdown_candidate", "drop_candidate"): "return from a breathing space into an incoming drop",
        ("outro_candidate", "intro_candidate"): "make a fresh handoff from the outgoing outro",
        ("drop_candidate", "breakdown_candidate"): "release the outgoing peak into an incoming breakdown",
        ("drop_candidate", "groove_candidate"): "let the outgoing peak resolve into a steadier groove",
        ("breakdown_candidate", "groove_candidate"): "move from the outgoing breakdown into a grounded groove",
        ("groove_candidate", "build_candidate"): "introduce a gradual lift after the outgoing groove",
    }
    return pairs.get((outgoing, incoming), "complement the current passage where the available evidence allows")


def assess_transition(current, candidate, edge: Optional[dict],
                      current_profile=None, candidate_profile=None) -> MusicalAssessment:
    """Compare approximate exit/entry moments using cached phrase evidence.

    The edge is already a measured graph edge. Its back, cue and beats values
    locate the approximate windows being compared; they do not replace the
    live planner's final measurement.
    """
    if not edge or current_profile is None or candidate_profile is None:
        return MusicalAssessment(
            available=False, score=0.0, preference="neutral",
            purpose="use existing measured-transition ranking; phrase evidence unavailable",
            outgoing_section=None, incoming_section=None, incoming_role="unknown",
            outgoing_aligned=False, incoming_aligned=False, overlaps={},
            reasons=("one or both phrase profiles are unavailable",),
        )

    try:
        out_bpm = max(1.0, float(getattr(current, "bpm", 0.0) or 120.0))
        in_bpm = max(1.0, float(getattr(candidate, "bpm", 0.0) or 120.0))
        beats = max(1.0, float(edge.get("beats", 64) or 64))
        back = max(0.0, float(edge.get("back", 0) or 0))
        cue_bars = max(0.0, float(edge.get("cue", 0) or 0))
        out_time = max(0.0, float(current_profile.duration)
                       - back * 32.0 * 60.0 / out_bpm
                       - beats * 30.0 / out_bpm)
        in_time = cue_bars * 4.0 * 60.0 / in_bpm + beats * 30.0 / in_bpm
    except (TypeError, ValueError, AttributeError):
        return MusicalAssessment(
            available=False, score=0.0, preference="neutral",
            purpose="use existing measured-transition ranking; timing metadata unavailable",
            outgoing_section=None, incoming_section=None, incoming_role="unknown",
            outgoing_aligned=False, incoming_aligned=False, overlaps={},
            reasons=("profile timing could not be resolved",),
        )

    out = _at(current_profile, out_time)
    inc = _at(candidate_profile, in_time)
    if out is None or inc is None:
        return MusicalAssessment(
            available=False, score=0.0, preference="neutral",
            purpose="use existing measured-transition ranking; profiles contain no usable windows",
            outgoing_section=None, incoming_section=None, incoming_role="unknown",
            outgoing_aligned=False, incoming_aligned=False, overlaps={},
            reasons=("one or both profiles contain no usable windows",),
        )

    fields = ("bass", "lead", "upper", "transient")
    overlaps = {
        name: round(min(_level(getattr(out, f"{name}_db")),
                        _level(getattr(inc, f"{name}_db"))), 3)
        for name in fields
    }
    score = 0.0
    reasons: list[str] = []
    penalties = {
        "bass": (0.24, "both passages carry prominent low-end material"),
        "lead": (0.28, "both passages carry prominent sustained midrange/presence material (a proxy, not vocal detection)"),
        "upper": (0.10, "both passages carry prominent upper-band material"),
        "transient": (0.12, "both passages show high spectral-change activity (not a drum classification)"),
    }
    for name, (weight, explanation) in penalties.items():
        amount = overlaps[name]
        if amount >= 0.55:
            penalty = weight * _clamp((amount - 0.45) / 0.55)
            score -= penalty
            if penalty >= 0.035:
                reasons.append(explanation)

    section_pairs = {
        ("build_candidate", "drop_candidate"): (0.28, "the incoming drop can answer the outgoing build"),
        ("breakdown_candidate", "drop_candidate"): (0.24, "the incoming drop can restore energy after a breathing space"),
        ("outro_candidate", "intro_candidate"): (0.18, "the incoming intro offers a clean new chapter"),
        ("drop_candidate", "breakdown_candidate"): (0.18, "the incoming breakdown can make room after a peak"),
        ("drop_candidate", "groove_candidate"): (0.12, "the incoming groove can release pressure after a peak"),
        ("breakdown_candidate", "groove_candidate"): (0.12, "the incoming groove can refill a sparse moment"),
        ("groove_candidate", "build_candidate"): (0.12, "the incoming build can add tension without forcing an immediate peak"),
    }
    out_section, in_section = out.section, inc.section
    reward, reason = section_pairs.get((out_section, in_section), (0.0, ""))
    score += reward
    if reason:
        reasons.append(reason)

    out_full, in_full = _level(out.full_db), _level(inc.full_db)
    if out_full >= 0.78 and in_full >= 0.78:
        score -= 0.10
        reasons.append("both passages are dense relative to their own tracks")
    elif abs(out_full - in_full) >= 0.22:
        score += 0.04
        reasons.append("the passages offer a useful relative-density contrast")

    coherent_change = bool(
        reward >= 0.12 and getattr(current, "genre", None)
        and getattr(candidate, "genre", None)
        and str(current.genre).casefold() != str(candidate.genre).casefold()
    )
    if coherent_change:
        score += 0.06
        reasons.append("the section handoff supports a coherent palette change")

    score = round(_clamp(score, -1.0, 1.0), 3)
    preference = "defer_if_alternative" if score <= -0.16 else "prefer" if score >= 0.14 else "neutral"
    purpose = _purpose(out_section, in_section)
    if not reasons:
        reasons.append("no strong complement or conflict is visible in these proxies")

    return MusicalAssessment(
        available=True, score=score, preference=preference, purpose=purpose,
        outgoing_section=out_section, incoming_section=in_section,
        incoming_role=_role(in_section),
        outgoing_aligned=bool(out.aligned), incoming_aligned=bool(inc.aligned),
        overlaps=overlaps, reasons=tuple(reasons),
    )


def arc_adjustment(incoming_role: str, recent_roles: tuple[str, ...] | list[str]) -> tuple[float, tuple[str, ...]]:
    """Softly vary pacing based on the recent set arc, without a fixed BPM ramp."""
    roles = [r for r in recent_roles if r and r != "unknown"][-4:]
    score = 0.0
    reasons: list[str] = []
    if incoming_role == "peak":
        recent_peaks = roles.count("peak")
        if recent_peaks:
            score -= min(0.28, 0.14 * recent_peaks)
            reasons.append("avoid stacking peaks without room between them")
        if roles and roles[-1] == "breath":
            score += 0.16
            reasons.append("a peak can provide release after the recent breathing space")
        elif roles and roles[-1] == "lift":
            score += 0.10
            reasons.append("the recent lift gives the peak a musical lead-in")
    elif incoming_role == "breath":
        if roles and roles[-1] == "peak":
            score += 0.18
            reasons.append("make room after the recent peak")
        elif roles.count("breath") >= 2:
            score -= 0.12
            reasons.append("avoid making the set feel persistently low-energy")
    elif incoming_role == "lift":
        if roles and roles[-1] == "breath":
            score += 0.12
            reasons.append("rebuild tension after the breathing space")
        elif roles.count("lift") >= 2:
            score -= 0.10
            reasons.append("vary the repeated build pattern")
    if len(roles) >= 3 and len(set(roles[-3:])) == 1 and incoming_role == roles[-1]:
        score -= 0.12
        reasons.append("vary a role that has repeated for three transitions")
    return round(_clamp(score, -0.5, 0.5), 3), tuple(reasons)


def contextual_score(assessment: MusicalAssessment,
                     recent_roles: tuple[str, ...] | list[str]) -> tuple[float, tuple[str, ...]]:
    """Profile preference plus the current set-arc context; technical rank is separate."""
    if not assessment.available:
        return 0.0, ()
    adjustment, reasons = arc_adjustment(assessment.incoming_role, recent_roles)
    return round(assessment.score + adjustment, 3), reasons
