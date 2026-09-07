"""Emoji reactions and log payload compaction.

Both systems were reworked in September 2026 against measurements from the
production log (30,498 lines) and the interaction transcripts (7,708 user
messages). The numbers quoted in the assertions come from those.
"""
import re

import pytest

from utils.core.kaia_reactions import (
    ALL_POOLS,
    KaiaReactions,
    _COMPILED,
    _EXACT_TRIGGERS,
    _TRIGGERS,
)
from utils.infrastructure.logging.log_sanitize import (
    RepeatAggregator,
    compact,
    is_traceback,
    shorten_urls,
    summarize_payload,
)


# ── Reactions ────────────────────────────────────────────────────────

@pytest.fixture
def reactions():
    return KaiaReactions()


def test_every_pool_is_reachable_from_a_trigger():
    """_DISAGREEMENT_REACTIONS used to be defined and referenced by nothing."""
    reachable = {e for _pattern, pool in _COMPILED.values() for e in pool}
    defined = {e for pool in ALL_POOLS.values() for e in pool}
    assert defined == reachable, f"unreachable: {sorted(defined - reachable)}"


def test_pool_is_meaningfully_larger_than_before():
    assert sum(len(p) for p in ALL_POOLS.values()) >= 40   # was 14
    assert len(ALL_POOLS) >= 9                              # was 5


@pytest.mark.parametrize("text,expect_hit", [
    ("thanks for that", True),        # stem match must still work
    ("I appreciated it", True),
    ("speaking of which", False),     # 'peak' must not match inside 'speaking'
    ("put on a glove", False),        # 'love' must not match inside 'glove'
    ("check the database", False),    # 'based' must not match inside 'database'
    ("the coolant leaked", False),    # 'cool' must not match inside 'coolant'
])
def test_keywords_match_at_word_start_only(reactions, text, expect_hit):
    assert bool(reactions.score_categories(text)) is expect_hit


def test_standalone_this_is_agreement_but_the_pronoun_is_not(reactions):
    """As a keyword 'this' fired on 437 of 7,708 messages — 85% of agreement
    hits — because it is an ordinary demonstrative."""
    assert "agreement" in reactions.score_categories("this")
    assert reactions.score_categories("this codebase is fine") == {}


@pytest.mark.parametrize("text", ["", "   ", "...", "!!!", "?!"])
def test_punctuation_only_messages_do_not_trigger(reactions, text):
    """Comparing punctuation-stripped values on both sides made every such
    message match the exact entry '?'."""
    if text.strip() == "?":
        return
    assert reactions.score_categories(text) == {}


def test_literal_question_mark_still_triggers_curiosity(reactions):
    assert "curious" in reactions.score_categories("?")


def test_strongest_category_wins_not_declaration_order(reactions):
    """Categories were tried in dict order, so an earlier one always won."""
    text = "thanks — that is interesting, genuinely interesting, curious even"
    scores = reactions.score_categories(text)
    assert scores["curious"] > scores["warm"]
    assert max(scores, key=scores.get) == "curious"


def test_pick_reaction_returns_none_when_nothing_matches(reactions):
    assert reactions.pick_reaction("the build finished at 4pm") is None


def test_pick_reaction_returns_an_emoji_from_the_winning_pool(reactions):
    emoji = reactions.pick_reaction("lmao that is hilarious")
    assert emoji in ALL_POOLS["amused"]


def test_mood_biases_selection(reactions, monkeypatch):
    """Internal state should influence behaviour, not just be recorded."""
    text = "sorry, that sucks — but congrats on the fix"
    monkeypatch.setattr(reactions, "_mood", lambda: (-0.9, 0.8))
    negative = {reactions.pick_reaction(text) for _ in range(40)}
    monkeypatch.setattr(reactions, "_mood", lambda: (0.9, 0.8))
    positive = {reactions.pick_reaction(text) for _ in range(40)}
    assert negative & set(ALL_POOLS["sympathy"])
    assert positive & set(ALL_POOLS["warm"] + ALL_POOLS["approving"])


def test_rate_limits_are_stricter_than_the_pool_is_large(reactions):
    assert reactions.MAX_PER_HOUR <= 8
    assert reactions.MIN_INTERVAL_SECONDS >= 60


def test_recent_emoji_are_avoided(reactions):
    reactions._recent_emoji = list(ALL_POOLS["amused"][:-1])
    assert reactions.pick_reaction("lmao") == ALL_POOLS["amused"][-1]


def test_trigger_keywords_are_all_lowercase():
    """Matching lowercases the content, so an uppercase keyword is dead."""
    for cat, cfg in _TRIGGERS.items():
        for kw in cfg["keywords"]:
            assert kw == kw.lower(), f"{cat}: {kw!r}"
    for cat, exacts in _EXACT_TRIGGERS.items():
        for e in exacts:
            assert e == e.lower(), f"{cat}: {e!r}"


# ── Log compaction ───────────────────────────────────────────────────

def test_multiline_payload_becomes_one_line():
    """6,080 of 30,498 log lines (19.9%) were continuations of dumped
    documents; the constitution appeared in full 771 times."""
    payload = "PERSONA LOADED\n" + "a line of the persona\n" * 60
    out = compact(payload)
    assert "\n" not in out
    assert "+60 lines" in out


def test_tracebacks_are_never_collapsed():
    """Their line structure is the information."""
    tb = ('failed:\nTraceback (most recent call last):\n'
          '  File "x.py", line 1, in <module>\n    boom()\nValueError: boom')
    assert is_traceback(tb)
    assert compact(tb) == tb


def test_short_single_line_messages_pass_through_untouched():
    msg = "Retrieval confidence: 0.82 (6 nodes)"
    assert compact(msg) == msg


def test_long_single_line_is_truncated_with_a_count():
    out = compact("x" * 5000)
    assert len(out) < 600 and "[5000 chars]" in out


def test_long_urls_lose_their_query_string():
    """Discord CDN links carry ~150 characters of signing token that changes
    every request, which also defeats duplicate detection."""
    url = "https://cdn.discordapp.com/attachments/1/2/a.png?ex=" + "f" * 200
    out = shorten_urls(f"vision payload: {url}")
    assert "ex=fff" not in out
    assert "cdn.discordapp.com/attachments/1/2/a.png" in out


def test_short_urls_are_left_alone():
    msg = "see https://example.com/a"
    assert shorten_urls(msg) == msg


def test_summarize_payload_reports_size_not_content():
    """The point is that the document itself never reaches the log."""
    payload = "secret text\n" * 100
    out = summarize_payload("constitution", payload)
    assert "secret text" not in out
    assert "\n" not in out
    assert out.startswith("constitution:")
    assert str(len(payload)) in out.replace(",", "")     # 1200 chars
    assert "101 lines" in out                            # 100 newlines + 1


class TestRepeatAggregator:
    """`Pre-chunking large document (N chars)` ran 1,056 times, once in an
    unbroken run of 574. The exact-string duplicate check could not see it
    because the number varies."""

    def test_first_occurrences_pass_through(self):
        agg = RepeatAggregator(min_run=3)
        assert agg.feed("Pre-chunking large document (100 chars)")[0] is True
        assert agg.feed("Pre-chunking large document (200 chars)")[0] is True

    def test_run_is_suppressed_after_min_run(self):
        agg = RepeatAggregator(min_run=3)
        emitted = sum(agg.feed(f"Pre-chunking large document ({n} chars)")[0]
                      for n in range(20))
        assert emitted == 2

    def test_tally_accounts_for_every_message(self):
        agg = RepeatAggregator(min_run=3)
        shown = sum(agg.feed(f"doc ({n})")[0] for n in range(8))
        _emit, summary = agg.feed("something else")
        assert "6 more" in summary
        assert shown + 6 == 8

    def test_a_different_message_ends_the_run(self):
        agg = RepeatAggregator(min_run=3)
        for n in range(5):
            agg.feed(f"doc ({n})")
        emit, summary = agg.feed("unrelated")
        assert emit is True and summary is not None

    def test_flush_emits_a_pending_tally(self):
        agg = RepeatAggregator(min_run=3)
        for n in range(6):
            agg.feed(f"doc ({n})")
        assert "4 more" in agg.flush()

    def test_flush_is_silent_with_nothing_pending(self):
        assert RepeatAggregator().flush() is None
