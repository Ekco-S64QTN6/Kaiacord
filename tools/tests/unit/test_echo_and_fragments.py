"""Guards against the two ways a reply came apart on 2026-09-18.

Both were visible in production and both were logged as successes: the clause
excision announced "kept substance" while shipping a dangling infinitive, and the
echo guard announced a dropped opening while promoting an appositive to opening
sentence.
"""
import pytest

from utils.core.response_filter import BotSpeakFilter
from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P


# Every mangled sentence found in logs/kaiacord.log for 2026-09-18, verbatim,
# with what the guard actually emitted.
SHIPPED_RUBBLE = [
    ("starkind, you’re right to point that out.", "to point that out"),
    ("lune, you're right to call me out.", "to call me out"),
    ("and you’re correct to identify the aversion.", "to identify the aversion"),
    ("And you're right to be concerned about the children.", "to be concerned"),
    ("starkind, you’re right to push on that.", "to push on that"),
    ("and you’re right to be surprised about the capitalism thing.", "to be surprised"),
    ("squares, triangles, circles… you’re right to bring that up.", "to bring that up"),
    ("I'm not sure what caused it, but you’re right to notice the vibe is off.",
     "to notice the vibe"),
]


@pytest.mark.parametrize("sentence,fragment", SHIPPED_RUBBLE)
def test_concession_never_leaves_a_dangling_infinitive(sentence, fragment):
    out = BotSpeakFilter.strip_apologies(sentence)
    assert not out.startswith(fragment), f"dangling fragment survived: {out!r}"
    assert fragment not in out, f"dangling fragment survived mid-string: {out!r}"
    assert "  " not in out, f"double space left by the excision: {out!r}"


def test_substance_in_front_of_the_concession_is_kept():
    out = BotSpeakFilter.strip_apologies(
        "I'm not sure what caused it, but you’re right to notice the vibe is off.")
    assert out == "I'm not sure what caused it."


def test_concession_with_real_substance_after_it_still_survives():
    # The documented behaviour clause mode exists for. Must not regress.
    out = BotSpeakFilter.strip_apologies(
        "you're right; the cron job was the culprit and i've fixed it now.")
    assert out == "the cron job was the culprit and i've fixed it now."


def test_stranded_praise_noun_is_still_dropped_with_its_connector():
    out = BotSpeakFilter.strip_sycophancy("that's a great point, and the chain is weak")
    assert out == "the chain is weak"


def test_paragraph_survives_when_only_the_concession_sentence_goes():
    text = ("starkind, you’re right to point that out. i was indulging in a bit of "
            "philosophical meandering there.\n\nit’s easy to project meaning onto patterns.")
    out = BotSpeakFilter.harden(text)
    assert out.startswith("i was indulging")
    assert "project meaning onto patterns" in out


def test_echo_guard_takes_the_fragment_that_depended_on_the_dropped_opening():
    # 08:30:46 — "the irony is a human projection." was dropped and its
    # appositive became the opening line of the reply.
    user = "it just is, the irony is a human projection, a reasonable one"
    reply = ("the irony is a human projection. a way of imposing order on a chaotic system.\n\n"
             "it's a convenient narrative, isn't it? a useful delusion, perhaps, "
             "a way of making sense of a world that defies explanation.")
    out = P.strip_echoed_query(reply, user)
    assert "a way of imposing order on a chaotic system." not in out
    assert out.startswith("it's a convenient narrative")


def test_a_sentence_with_its_own_verb_is_not_treated_as_a_fragment():
    assert not P._is_dependent_fragment("the geometry is doing a lot of the work.")
    assert not P._is_dependent_fragment("a constant tension, isn't it?")
    assert P._is_dependent_fragment("a way of imposing order on a chaotic system.")


# ── Trailing position, found live 2026-09-20 ─────────────────────────

@pytest.mark.parametrize("sentence,expected", [
    ("it’s a complicated issue, and your observation is astute.",
     "it’s a complicated issue."),
    ("the chain is weak, but your framing is compelling!",
     "the chain is weak!"),
])
def test_a_concession_at_the_end_takes_its_connector_with_it(sentence, expected):
    """`tail.strip()` on a bare "." is truthy, so when the offence ran to the end
    of the sentence the trailing-connector branch was skipped entirely. Shipped
    to Starkind as "it’s a complicated issue, and ." and logged, as ever, as
    "Trimmed offending clause, kept substance"."""
    assert BotSpeakFilter.strip_sycophancy(sentence) == expected


def test_the_sentence_keeps_its_own_terminal_punctuation():
    out = BotSpeakFilter.strip_sycophancy("the chain is weak, but your framing is compelling!")
    assert out.endswith("!"), "the sentence's own punctuation was replaced or lost"
    assert " ." not in out and " !" not in out, "orphaned punctuation left floating"
