"""Substring excisions that took the sentence's subject with them.

Two guards shipped this in one week, both by removing a span from the *middle*
of a clause — the shape CLAUDE.md §5 rules out, because the removed span is
usually the thing the grammar is hanging off:

    the "dead internet theory" is... concerning.  ->  the is... concerning.
    the system warning is unhelpful on its own.   ->  theis unhelpful on its own.

The first was queued to the Project 1999 forum for review before anyone noticed.
"""
import pytest

from utils.core.response_filter import BotSpeakFilter, excision_broke_grammar
from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P


# ── The shared rule ──────────────────────────────────────────────────

@pytest.mark.parametrize("before,after", [
    ('the "dead internet theory" is concerning.', "the is concerning."),
    ("the system warning is unhelpful.", "theis unhelpful."),
    ("a system warning was all i got.", "awas all i got."),
    ("that heat death of the universe stuff is grim.", "that is grim."),
])
def test_a_stranded_article_is_recognised(before, after):
    assert excision_broke_grammar(before, after)


@pytest.mark.parametrize("before,after", [
    ("the cron job was the culprit.", "the cron job was the culprit."),
    ("you're right; the cron job was the culprit.", "the cron job was the culprit."),
    ("system warning. what do you want to know?", "what do you want to know?"),
    ("anything at all", ""),
])
def test_a_clean_excision_is_not_flagged(before, after):
    assert not excision_broke_grammar(before, after)


def test_pre_existing_rubble_is_not_blamed_on_the_excision():
    """Only rubble the excision *created*. If the model already wrote "the is",
    refusing to filter would leave the offence in place for no benefit."""
    assert not excision_broke_grammar("the is broken already. system warning.",
                                      "the is broken already.")


# ── PROMPT_ECHO_GUARD ────────────────────────────────────────────────

DEAD_INTERNET = ("have you seen the dead internet theory stuff going around? "
                 "bots talking to bots, the whole web filled with generated slop")


def test_the_forum_post_that_reported_this():
    """2026-09-20, 08:03:09. Logged as 'Dropped echoed span: dead internet
    theory...' and queued to the forum a second later."""
    reply = ('the line between a helpful assistant and a deceptive presence. '
             'the "dead internet theory" is... concerning.')
    assert P.strip_prompt_echo(reply, DEAD_INTERNET) == reply


@pytest.mark.parametrize("query,reply", [
    ("i keep thinking about the heat death of the universe and entropy",
     'a lot of physics rests on the "heat death of the universe" being inevitable.'),
    ("the network file service unavailable error keeps coming back on sda2",
     'the "network file service unavailable" means the mount never came up.'),
    ("my tank has a limnological biosphere setup with live plants",
     'i read about a "limnological biosphere setup with live plants" last week.'),
])
def test_a_quoted_term_used_as_a_noun_survives(query, reply):
    """Naming a thing with the words the other person used for it is how you
    refer to a thing, not an echo."""
    assert P.strip_prompt_echo(reply, query) == reply


def test_the_documented_fault_is_still_caught():
    """The audited failure this guard exists for: opening a turn by quoting the
    user back at themselves, the quote standing on its own."""
    query = "starkind's assessment of the situation is that the system is failing under load"
    reply = ('"starkind\'s assessment of the situation" yes, you\'re largely '
             "summarizing his point there. i think the load is the real story.")
    out = P.strip_prompt_echo(reply, query)
    assert "starkind's assessment of the situation" not in out
    assert out.startswith("yes, you're largely summarizing")


# ── DIRECTIVE_LEAK_GUARD ─────────────────────────────────────────────

def test_a_bare_label_between_sentences_is_still_scrubbed():
    out = BotSpeakFilter.scrub_directive_leaks(
        "can't access it. system warning. what do you want to know?")
    assert "system warning" not in out
    assert out == "can't access it. what do you want to know?"


@pytest.mark.parametrize("text", [
    "the system warning is unhelpful on its own.",
    "a system warning was all i got back.",
])
def test_a_label_that_is_the_subject_of_its_sentence_survives(text):
    """She discusses her own plumbing constantly, which is exactly the
    conversation this guard is most likely to fire in."""
    assert BotSpeakFilter.scrub_directive_leaks(text) == text
