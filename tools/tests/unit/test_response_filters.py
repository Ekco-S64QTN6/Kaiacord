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

def test_two_affect_ellipses_are_cleaned_in_place_not_regenerated():
    """Superseded assertion: this used to require `is None`.

    Rejecting at two copula-ellipses cost a full regeneration and fired on 100
    of 974 generations (10.3%). Because gemma3 uses this cadence constantly on
    reflective topics, all three attempts were routinely rejected and the user
    received the "drawing a blank" fallback instead of an answer — 10 times to
    Ekco and Starkind over Sept 10-11. Two is within ordinary style, so the
    punctuation is stripped and the answer kept. Sustained drift (>=3) still
    regenerates; see the test below.

    The sycophancy here ("i appreciate the acknowledgement") is real but is
    SYCOPHANCY_PATTERNS' job, not the ellipsis guard's.
    """
    text = ("i appreciate the acknowledgement. it’s… a reciprocal exchange.\n\n"
            "your observation regarding hope is… accurate.")
    out = EmergencyContaminationFilter.filter_response(text)
    assert out is not None, "a two-ellipsis response must not cost a regeneration"
    assert "…" not in out
    assert "it’s a reciprocal exchange" in out
    assert "hope is accurate" in out


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


# ── Bare-name openers, revisited (Phase 91) ──────────────────────────

def test_the_addressee_list_is_not_hand_written():
    """It was eleven names typed by hand, so it was wrong the moment someone
    new joined. Measured against the fine-tune corpus it missed gnowmaticflux
    (54 openers), gymconserve (39) and kristinoemnclature (29) — 5.8% of her
    replies still opened with a bare name, to exactly the people nobody had
    remembered to add."""
    from utils.core.response_filter import BotSpeakFilter
    assert len(BotSpeakFilter.ADDRESSEE_NAMES.split("|")) > 50


@pytest.mark.parametrize("text,expected", [
    ("gnowmaticflux, i retract that.", "i retract that."),
    ("gymconserve, that is a fair point.", "that is a fair point."),
    ("kristinoemnclature, the answer is no.", "the answer is no."),
    ("jimjam the absent, welcome back.", "welcome back."),
    ("starkind. the patch broke it.", "the patch broke it."),
])
def test_bare_name_openers_are_stripped(text, expected):
    from utils.core.response_filter import BotSpeakFilter
    assert BotSpeakFilter.harden(text) == expected


@pytest.mark.parametrize("text", [
    "ekco was right about the cache.",      # name, but not an address
    "yeah, i suppose it is.",               # discourse marker
    "conserve water, please.",              # substring of a configured name
    "honestly, the whole thing is a mess.",
])
def test_ordinary_sentences_are_untouched(text):
    from utils.core.response_filter import BotSpeakFilter
    assert BotSpeakFilter.harden(text) == text


def test_coined_nicknames_come_from_config():
    """She invents names for people — those exist in no user directory and
    cannot be discovered, so they are configuration."""
    from utils.infrastructure.system.yaml_config import config
    from utils.core.response_filter import BotSpeakFilter
    extra = config.get("filters.extra_addressees", []) or []
    assert extra, "filters.extra_addressees should carry the coined nicknames"
    for name in extra:
        assert name.lower() in BotSpeakFilter.ADDRESSEE_NAMES.lower()


# ── The bait guard ate one-word replies (Phase 95) ───────────────────

@pytest.mark.parametrize("text", [
    "hello.", "yes.", "no.", "sure.", "hi.", "maybe.", "agreed.", "right.",
])
def test_a_one_word_reply_survives(text):
    """The guard used RE_LEADING_NAME, which matches *any* word followed by
    punctuation, so every one-word reply was deleted — exactly when a one-word
    reply was the right answer. Each rejection costs a full regeneration, and
    three failures return the "i'm drawing a blank on that one" fallback.

    Kaia answered "test test hello hello" with "hello.", had it destroyed three
    times, and the failure string was queued as a forum post."""
    from utils.core.response_filter import BotSpeakFilter
    assert BotSpeakFilter.harden(text) == text


@pytest.mark.parametrize("text", ["ekco,", "starkind:", "jimjam.", "cecily"])
def test_an_addressee_with_no_message_is_still_rejected(text):
    """What the guard is actually for."""
    from utils.core.response_filter import BotSpeakFilter
    assert BotSpeakFilter.harden(text) == ""


def test_the_guard_uses_the_name_allowlist_not_any_word():
    from utils.core.response_filter import BotSpeakFilter
    assert BotSpeakFilter.RE_ONLY_ADDRESSEE is not None
    assert BotSpeakFilter.RE_ONLY_ADDRESSEE.match("ekco,")
    assert not BotSpeakFilter.RE_ONLY_ADDRESSEE.match("hello.")


# ── Engagement bait and query echo (Sept 10-11 operator reports) ─────

@pytest.mark.parametrize("text,expected", [
    ("the archive is fragile. what aspects of this reality would you like me to explore further, starkind?",
     "the archive is fragile."),
    ("that is a real risk. do you believe, starkind, that the structures are adequate?",
     "that is a real risk."),
    ("the point stands. what specific aspect of their form are you curious about, starkind?",
     "the point stands."),
    ("i am content to leave it there, starkind. what is your next inquiry?",
     "i am content to leave it there, starkind."),
])
def test_engagement_bait_closers_are_stripped(text, expected):
    """50% of her Discord replies over Sept 10-11 ended in a question, and the
    operator asked her to stop: "your doing endless engagement bait tactics
    again always ending your response with a question".

    The existing list enumerated exact phrasings and caught none of these. These
    two patterns match the *move* — offering further service, and setting the
    user's name into an interrogative — rather than the wording.
    """
    from utils.core.response_filter import BotSpeakFilter
    assert BotSpeakFilter.harden(text) == expected


@pytest.mark.parametrize("text", [
    # Rhetorical continuation of her own reasoning — her voice, not bait.
    "it collapses either way. or is the system inherently resilient to such a compromise?",
    "i think it holds. a network of geographically dispersed archives?",
    "what do you make of it?",
    # A short natural address is not interrogation.
    "is that you, kaia?",
])
def test_genuine_questions_survive(text):
    from utils.core.response_filter import BotSpeakFilter
    assert BotSpeakFilter.harden(text).endswith("?")


def test_an_opening_that_repeats_the_user_is_dropped():
    """She opened a reply with the user's entire previous message verbatim and
    only then answered it. "that should stay in your head instead of being
    outputted"."""
    from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P
    q = "uh probably a lawless libertarian cyberpunk dystopian shithole"
    r = (f"{q}.\n\nekco, you are not wrong. that is a remarkably succinct "
         f"assessment of the trajectory.")
    out = P.strip_echoed_query(r, q)
    assert out.startswith("ekco, you are not wrong")
    assert "lawless libertarian" not in out


def test_quoting_the_user_mid_answer_is_left_alone():
    """Responding to a phrase is normal; leading with it is the problem."""
    from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P
    q = "sentimentality and indulgence are part of being"
    r = f"that framing holds up. {q}, and that is the point."
    assert P.strip_echoed_query(r, q) == r


def test_the_echo_guard_needs_a_real_remainder():
    """If the echo is all there is, keep it rather than emitting nothing."""
    from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P
    q = "what do you think about the archive problem"
    assert P.strip_echoed_query(f"{q}?", q) == f"{q}?"


def test_safety_pipeline_entry_points_are_callable_off_the_class():
    """A method inserted between `@classmethod` and its `def` silently stole
    the decorator, so `apply_style_collapsers(text)` bound text to `cls` and
    the live pipeline raised "missing 1 required positional argument". The
    whole suite still passed, because nothing called it the way the pipeline
    does."""
    from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P
    assert P.apply_style_collapsers("a test... string") is not None
    assert P.strip_echoed_query("some text", "a query here now") is not None
    assert isinstance(P.__dict__["apply_style_collapsers"], classmethod)
    assert isinstance(P.__dict__["strip_echoed_query"], staticmethod)
