"""Bounded listener intent for records-mode next-pick preferences.

Intents steer the next autonomous candidate among records already being
considered by the records planner. They do not edit audio or promise a
technique the engine cannot perform. Feature/section evidence is heuristic;
vocal and percussion recognition are deliberately not inferred from these
curves.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional


INTENT_TTL_S = 15 * 60
MIN_PREFERENCE_SCORE = 0.20


@dataclass(frozen=True)
class ListenerIntent:
    request_id: int
    kind: str
    label: str
    requested_by: str
    created_at: float
    expires_at: float


@dataclass(frozen=True)
class RecordsRequestResult:
    understood: bool
    reply: str
    queued_after_current: bool = False


_LABELS = {
    "more_bass": "more bass",
    "less_bass": "less bass",
    "darker": "darker",
    "brighter": "brighter",
    "build": "a build",
    "drop": "a drop",
    "calmer": "a calmer passage",
    "harder": "a harder passage",
}
_UNSUPPORTED = {
    "vocal": "I can't identify vocals: the lead curve is only a midrange/presence proxy.",
    "voice": "I can't identify vocals: the lead curve is only a midrange/presence proxy.",
    "acapella": "I can't identify or separate vocals in these records.",
    "percussion": "I can't classify percussion from the transient curve; it is only spectral-change activity.",
    "drum": "I can't classify drums from the transient curve; it is only spectral-change activity.",
    "kick": "I can't identify kick drums from the transient curve; it is only spectral-change activity.",
    "snare": "I can't identify snares from the transient curve; it is only spectral-change activity.",
    "hihat": "I can't identify hi-hats from the transient curve; it is only spectral-change activity.",
    "cymbal": "I can't identify cymbals from the transient curve; it is only spectral-change activity.",
    "singer": "I can't identify singers: the lead curve is only a midrange/presence proxy.",
    "singing": "I can't identify singing: the lead curve is only a midrange/presence proxy.",
    "faster": "Records mode currently keeps the incoming deck matched to the playing tempo; I can't promise a faster set from a track request.",
    "slower": "Records mode currently keeps the incoming deck matched to the playing tempo; I can't promise a slower set from a track request.",
    "tempo": "Records mode currently keeps the incoming deck matched to the playing tempo; I can't promise a tempo change from this request.",
}


def create_request(text: str, requested_by: str, request_id: int,
                   now: Optional[float] = None) -> tuple[Optional[ListenerIntent], str]:
    """Parse one deliberately small, explainable set of supported intents."""
    raw = (text or "").strip().lower()
    words = re.findall(r"[a-z]+", raw)
    if not words:
        return None, "Tell me what musical direction you'd like."

    for word, explanation in _UNSUPPORTED.items():
        matched = word in words or (
            word in {"vocal", "drum", "voice", "percussion", "acapella"}
            and any(token.startswith(word) for token in words)
        )
        if matched:
            return None, explanation

    kind = None
    if re.search(r"\bmore\s+(?:bass|low(?:\s+end)?)\b", raw) or re.search(r"\badd\s+(?:some\s+)?bass\b", raw):
        kind = "more_bass"
    elif re.search(r"\b(?:less|no|remove|cut)\s+(?:the\s+)?(?:bass|low(?:\s+end)?)\b", raw):
        kind = "less_bass"
    elif any(w in words for w in ("darker", "dark", "deeper", "moodier")):
        kind = "darker"
    elif any(w in words for w in ("brighter", "bright", "lighter")):
        kind = "brighter"
    elif any(w in words for w in ("drop", "breakdown")):
        kind = "drop"
    elif any(w in words for w in ("build", "lift")):
        kind = "build"
    elif any(w in words for w in ("calmer", "calm", "chill", "chiller", "softer")):
        kind = "calmer"
    elif any(w in words for w in ("harder", "heavier", "driving")):
        kind = "harder"

    if kind is None:
        return None, "I can steer the next records pick toward more/less bass, darker/brighter, a build/drop, or calmer/harder. I can't promise vocal or percussion targeting."

    created = time.time() if now is None else float(now)
    return ListenerIntent(
        request_id=int(request_id),
        kind=kind,
        label=_LABELS[kind],
        requested_by=str(requested_by or "")[:80],
        created_at=created,
        expires_at=created + INTENT_TTL_S,
    ), ""


def entry_exit_windows(current_profile, candidate_profile, current_bpm: float,
                       candidate_bpm: float, edge: Optional[dict]) -> tuple:
    """Return approximate outgoing/incoming states for a measured graph edge."""
    if current_profile is None or candidate_profile is None:
        return None, None
    try:
        out_bpm = max(1.0, float(current_bpm or 120.0))
        in_bpm = max(1.0, float(candidate_bpm or 120.0))
        beats = max(1.0, float((edge or {}).get("beats", 64) or 64))
        back = max(0.0, float((edge or {}).get("back", 0) or 0))
        cue_bars = max(0.0, float((edge or {}).get("cue", 0) or 0))
        out_time = max(0.0, float(current_profile.duration)
                       - back * 32.0 * 60.0 / out_bpm
                       - beats * 30.0 / out_bpm)
        in_time = cue_bars * 4.0 * 60.0 / in_bpm + beats * 30.0 / in_bpm
    except (TypeError, ValueError, AttributeError):
        return None, None
    return _at(current_profile, out_time), _at(candidate_profile, in_time)


def _at(profile, seconds: float):
    phrases = getattr(profile, "phrases", ()) or ()
    if not phrases:
        return None
    for phrase in phrases:
        if phrase.start <= seconds < phrase.end:
            return phrase
    return min(phrases, key=lambda p: abs((p.start + p.end) / 2.0 - seconds))


def score_candidate(intent: ListenerIntent, current_profile, candidate_profile,
                    current_bpm: float, candidate_bpm: float,
                    edge: Optional[dict] = None) -> Optional[tuple[float, str]]:
    """Softly rank an incoming window against the current outgoing window.

    Scalar choices compare each record's own relative feature levels. Build/drop
    requests require a counted phrase-aligned candidate label. A score never
    changes whether a blend is technically measured or safe.
    """
    if time.time() >= intent.expires_at:
        return None
    out, incoming = entry_exit_windows(current_profile, candidate_profile,
                                       current_bpm, candidate_bpm, edge)
    if out is None or incoming is None:
        return None

    if intent.kind in {"build", "drop"}:
        if not incoming.aligned or not incoming.section:
            return None
        wanted = "build_candidate" if intent.kind == "build" else "drop_candidate"
        if incoming.section == wanted:
            return 0.85, f"incoming window is a phrase-aligned {intent.label} candidate"
        return -0.20, f"incoming window is a different phrase candidate ({incoming.section})"

    field, direction, description = {
        "more_bass": ("bass_db", 1.0, "relative low-end feature level"),
        "less_bass": ("bass_db", -1.0, "relative low-end feature level"),
        "darker": ("upper_db", -1.0, "relative upper-band feature level"),
        "brighter": ("upper_db", 1.0, "relative upper-band feature level"),
        "calmer": ("full_db", -1.0, "relative overall feature level"),
        "harder": ("full_db", 1.0, "relative overall feature level"),
    }.get(intent.kind, (None, 0.0, ""))
    if field is None:
        return None
    try:
        delta = float(getattr(incoming, field)) - float(getattr(out, field))
    except (TypeError, ValueError, AttributeError):
        return None
    score = max(-1.0, min(1.0, direction * delta / 8.0))
    score = round(score, 3)
    if score <= 0.0:
        return score, f"{description} does not move in the requested direction ({delta:+.1f} dB)"
    return score, f"{description} changes by {delta:+.1f} dB in the requested direction"


def pending_label(intent: Optional[ListenerIntent]) -> Optional[str]:
    if intent is None or time.time() >= intent.expires_at:
        return None
    minutes = max(1, int((intent.expires_at - time.time() + 59) // 60))
    return f"{intent.label} (next autonomous pick; expires in {minutes} min)"
