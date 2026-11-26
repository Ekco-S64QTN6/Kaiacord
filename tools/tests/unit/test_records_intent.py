"""Listener intent parsing and soft preference scoring for records mode."""
import time
from types import SimpleNamespace

from utils.audio import records_intent


def _profile(*, section="groove_candidate", bass=-12.0, upper=-12.0,
             full=-12.0, aligned=True):
    state = SimpleNamespace(
        start=0.0, end=64.0, aligned=aligned, section=section if aligned else None,
        bass_db=bass, upper_db=upper, full_db=full,
    )
    return SimpleNamespace(duration=64.0, phrases=(state,))


def _request(text):
    intent, error = records_intent.create_request(text, "listener", 1)
    assert intent is not None, error
    return intent


def test_supported_records_directions_are_typed_and_bounded():
    for text, kind in (
        ("more bass", "more_bass"), ("less low end", "less_bass"),
        ("darker", "darker"), ("brighter please", "brighter"),
        ("build", "build"), ("drop", "drop"),
        ("calmer", "calmer"), ("harder", "harder"),
    ):
        intent = _request(text)
        assert intent.kind == kind
        assert intent.requested_by == "listener"
        assert intent.expires_at - intent.created_at == records_intent.INTENT_TTL_S


def test_vocal_and_percussion_requests_are_rejected_honestly():
    for text, expected in (
        ("more vocals", "midrange/presence proxy"),
        ("vocal forward", "midrange/presence proxy"),
        ("more percussion", "spectral-change activity"),
        ("more drums", "spectral-change activity"),
        ("faster", "matched to the playing tempo"),
    ):
        intent, reason = records_intent.create_request(text, "listener", 1)
        assert intent is None
        assert expected in reason


def test_more_and_less_bass_compare_relative_incoming_and_outgoing_evidence():
    more = _request("more bass")
    less = _request("less bass")
    outgoing = _profile(bass=-18.0)
    bassy = _profile(bass=-4.0)
    thin = _profile(bass=-22.0)

    plus = records_intent.score_candidate(more, outgoing, bassy, 120, 120, {"beats": 64})
    minus = records_intent.score_candidate(less, outgoing, thin, 120, 120, {"beats": 64})
    assert plus and plus[0] > 0.8 and "relative low-end" in plus[1]
    assert minus and minus[0] > 0.4


def test_darker_brighter_and_energy_directions_use_their_own_feature_proxies():
    outgoing = _profile(upper=-4.0, full=-4.0)
    incoming = _profile(upper=-20.0, full=-18.0)
    dark = records_intent.score_candidate(_request("darker"), outgoing, incoming, 120, 120, {"beats": 64})
    calm = records_intent.score_candidate(_request("calmer"), outgoing, incoming, 120, 120, {"beats": 64})
    bright = records_intent.score_candidate(_request("brighter"), incoming, outgoing, 120, 120, {"beats": 64})
    assert dark and dark[0] > 0
    assert calm and calm[0] > 0
    assert bright and bright[0] > 0


def test_build_and_drop_require_counted_phrase_alignment():
    build = _request("build")
    drop = _request("drop")
    outgoing = _profile(section="groove_candidate")
    aligned_drop = _profile(section="drop_candidate")
    unaligned_drop = _profile(section="drop_candidate", aligned=False)

    result = records_intent.score_candidate(drop, outgoing, aligned_drop, 120, 120, {"beats": 64})
    no_result = records_intent.score_candidate(drop, outgoing, unaligned_drop, 120, 120, {"beats": 64})
    build_result = records_intent.score_candidate(build, outgoing, _profile(section="build_candidate"),
                                                 120, 120, {"beats": 64})
    assert result and result[0] > 0.8 and "phrase-aligned" in result[1]
    assert no_result is None
    assert build_result and build_result[0] > 0.8


def test_expired_intent_is_not_applied():
    intent, error = records_intent.create_request(
        "more bass", "listener", 2, now=time.time() - records_intent.INTENT_TTL_S - 1
    )
    assert intent is not None and not error
    scored = records_intent.score_candidate(
        intent, _profile(bass=-20), _profile(bass=-2), 120, 120, {"beats": 64}
    )
    assert scored is None
