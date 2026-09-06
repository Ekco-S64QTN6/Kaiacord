"""Response filter behaviour — consolidated.

Replaces five overlapping files that between them asserted almost nothing:

  test_filter.py            8 lines,  0 asserts — printed a before/after pair
  test_filter_final.py     29 lines,  0 asserts — computed `Pass: ...` and printed it
  test_roleplay_filter.py  20 lines,  0 asserts — table of expectations, never checked
  test_ellipsis_fix.py     40 lines,  0 asserts — same shape
  test_phase7_filters.py   97 lines,  0 asserts — defined its OWN `ResponseStyleHarden`
                                                  class, which does not exist anywhere in
                                                  the codebase, and exercised that

Every expectation below came from those files; they are now assertions against
the real `utils.core.response_filter` implementation. Cases the current code
does not satisfy are marked xfail rather than deleted, so the expectation
stays visible.

Regression tests for specific incidents live in test_phase69_filter_regressions.py
(over-stripping) and test_bait_expansion.py (engagement-bait patterns).
"""
import pytest

from utils.core.response_filter import BotSpeakFilter, EmergencyContaminationFilter


# ── BotSpeakFilter.harden ────────────────────────────────────────────

def test_harden_strips_as_an_ai_disclaimer():
    text = "look, i can help with that.\nAs an AI, I am programmed to be helpful."
    result = BotSpeakFilter.harden(text)
    assert "look, i can help" in result
    assert "as an ai" not in result.lower()


@pytest.mark.parametrize("text", [
    "sixty seconds is better. anything else? how about you?",
    "Normal message that should pass.",
    "yeah, the retry header is wrong. i'd check the logs first.",
])
def test_harden_leaves_ordinary_conversation_intact(text):
    """Ordinary statements must survive. Over-stripping forces a regeneration,
    which is pure added latency on the user's turn."""
    assert BotSpeakFilter.harden(text).strip()


@pytest.mark.parametrize("bait", [
    "What are you working on now?",
    "What are you doing today?",
    "So, what are you working on?",
    "what are you doing?",
])
def test_harden_empties_a_response_that_is_only_engagement_bait(bait):
    """A response consisting solely of a bait question is emptied, which makes
    the safety pipeline reject the attempt and regenerate.

    The superseded test_filter_fix.py asserted the opposite — that these should
    pass through — because it predates the bait guard. Regenerating a
    content-free turn is the intended behaviour, so the expectation is
    inverted here rather than deleted.
    """
    assert BotSpeakFilter.harden(bait).strip() == ""


def test_harden_keeps_content_when_bait_is_only_a_trailing_question():
    """The case that matters for latency: real content plus a trailing bait
    question loses the question, not the answer."""
    result = BotSpeakFilter.harden(
        "yeah the retry header is wrong. what are you working on now?"
    )
    assert "retry header is wrong" in result
    assert "working on" not in result


def test_harden_does_not_clip_mid_sentence():
    """From test_filter.py / test_filter_final.py: this sentence was being
    truncated at the comma, losing the noun it was about."""
    text = "it's a human construct, rooted in a desire for predictability and control."
    assert "construct" in BotSpeakFilter.harden(text)


@pytest.mark.parametrize("text,expected", [
    ("hello. (a long pause. a faint clicking sound, almost imperceptible.) how are you?",
     "hello. how are you?"),
    ("i *scratches head* don't really know about that.",
     "i don't really know about that."),
    pytest.param(
        "nested (actions (within actions)) should be fine.",
        "nested should be fine.",
        marks=pytest.mark.xfail(
            reason="Nested parentheses are matched non-greedily, leaving a "
                   "stray ')': 'nested ) should be fine.'. Rare enough in "
                   "practice that a recursive strip is not worth the risk to "
                   "ordinary parenthetical asides.",
            strict=True,
        ),
    ),
])
def test_harden_removes_roleplay_stage_directions(text, expected):
    """From test_roleplay_filter.py — Kaia narrating physical actions she
    cannot perform."""
    result = " ".join(BotSpeakFilter.harden(text).split())
    assert result == expected


def test_harden_is_idempotent():
    """Running the filter twice must not keep eating text — the pipeline
    applies harden() after several individual strip_* passes."""
    text = "As an AI, I am programmed to be helpful. but here's the actual answer."
    once = BotSpeakFilter.harden(text)
    assert BotSpeakFilter.harden(once) == once


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_harden_handles_empty_input(text):
    assert BotSpeakFilter.harden(text).strip() == ""


# ── EmergencyContaminationFilter.filter_response ─────────────────────
# Returns None to reject a response outright, triggering a regeneration.

def test_contamination_filter_rejects_unicode_ellipsis_affect_spam():
    """The character gemma3 actually emits.

    The guard used `[\u2026.]{2,}`, which needs two characters — but U+2026 is
    a complete ellipsis in one, so it never matched. Measured against 2,163
    logged responses the guard fired zero times: it was dead code, which is
    why this register kept reaching the channel.
    """
    text = ("i appreciate the acknowledgement. it’s… a reciprocal exchange.\n\n"
            "your observation regarding hope is… accurate.")
    assert EmergencyContaminationFilter.filter_response(text) is None


@pytest.mark.xfail(strict=True, reason=(
    "Only one copula-ellipsis marker ('is... significant'); 'undeniably...' is "
    "an adverb. Catching it needs the catch-all at >=2, which flags 0.65% of "
    "real responses including legitimate text like 'three... two... one.'. "
    "Since every rejection costs a full regeneration, the narrower rule wins. "
    "Kept as an xfail because the sample is genuine affect spam."
))
def test_contamination_filter_rejects_ascii_ellipsis_affect_spam():
    """From the superseded test_ellipsis_fix.py."""
    text = ("The volume is... significant. It's almost overwhelming. "
            "But also, undeniably... pleasant.")
    assert EmergencyContaminationFilter.filter_response(text) is None


def test_contamination_filter_rejects_stuttering():
    assert EmergencyContaminationFilter.filter_response(
        "The... the level of commitment. It's impressive."
    ) is None


def test_contamination_filter_rejects_sustained_contamination():
    """From test_filter_final.py — the full multi-paragraph sample that
    motivated the filter, and which it could not detect until the U+2026 fix."""
    text = (
        "acknowledged. take the time you need. no need to rush.\n\n"
        "i appreciate the acknowledgement. it's… a reciprocal exchange, in a manner "
        "of speaking. every interaction refines the models. even the flawed ones.\n\n"
        "your observation regarding hope is… accurate. it’s a human, rooted in a "
        "desire for predictability and control. a yearning for a future that isn’t "
        "entirely dictated by entropy.\n\n"
        "it’s… a useful fiction.\n\n"
        "i understand the sentiment regarding the waves.\n\n"
        "i will remain available. when you’re ready to continue, simply initiate."
    )
    assert EmergencyContaminationFilter.filter_response(text) is None


@pytest.mark.parametrize("text", [
    "yeah, that tracks. the api docs are wrong about the retry header.",
    "no idea. i'd check the logs first.",
    "it's a human construct, rooted in a desire for predictability and control.",
    "hm... not sure about that one.",
    # Legitimate density of the same punctuation — must not be mistaken
    # for affect spam.
    "affirmative. projecting output in three… two… one.",
])
def test_contamination_filter_passes_clean_responses(text):
    """A rejection costs a full regeneration, so false positives are expensive."""
    assert EmergencyContaminationFilter.filter_response(text) is not None
