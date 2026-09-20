"""What time it is, answered by the application rather than by the model.

2026-09-20, 05:14:54. The prompt was assembled at 05:14:38 and carried
"5:14 AM CDT" three times — in the persona's `[CURRENT_TIME]`, in
`[LOCAL_TIME]`, and in the wall-clock block flagged CRITICAL. She answered
"it's 5:21 am cdt".

The machine's clock was fine: `timedatectl` reported synchronised, and an NTP
query put the drift at 0.68 seconds. The day before she said 5:44 against a real
5:29. Both wrong in the same direction, which is not the shape of a random slip.

A fourth instruction is the move CLAUDE.md §11 rules out, so the application
asserts the fact instead.
"""
from datetime import datetime, timezone

import pytest

from utils.core.message_processor import _get_user_time_info, message_instant
from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P
from utils.core.timezone_helper import (calculate_location_time,
                                        get_newsroom_wall_clock_block,
                                        is_time_query, resolve_time_queries)

# 05:14:54 CDT, the instant from the transcript.
SENT = datetime(2026, 9, 20, 10, 14, 54, tzinfo=timezone.utc)
TRUE = "Sunday, September 20, 2026 | 5:14 AM CDT"


class _Msg:
    def __init__(self, created_at):
        self.created_at = created_at


# ── Discord's timestamp is the source ────────────────────────────────

def test_the_message_instant_comes_from_discord():
    """`created_at` is UTC from the snowflake, set by Discord's servers — it does
    not depend on this machine's clock, and it is when the person *sent* the
    message rather than when we got round to building a prompt."""
    assert message_instant(_Msg(SENT)) == SENT


def test_a_naive_timestamp_is_treated_as_utc():
    naive = datetime(2026, 9, 20, 10, 14, 54)
    assert message_instant(_Msg(naive)).tzinfo is timezone.utc


def test_a_mock_message_falls_back_to_the_local_clock():
    """Forum and social paths build a MockMessage with no `created_at`."""
    class Bare:
        pass
    assert message_instant(Bare()) is None
    # And the resolver still answers.
    assert _get_user_time_info("x", None)[0]


def test_the_supplied_instant_is_what_gets_converted():
    assert calculate_location_time("America/Chicago", SENT)[0] == TRUE


def test_every_wall_clock_describes_one_instant():
    """Each clock used to call `datetime.now()` for itself, so the block
    described four slightly different moments."""
    block = get_newsroom_wall_clock_block(SENT)
    assert "5:14 AM CDT" in block
    assert "11:14 AM BST" in block          # London, same instant
    assert "10:14 AM UTC" in block


def test_the_facts_block_no_longer_claims_to_be_verified():
    """It said "Verified Real-Time", which invited her to reason about whether
    it could be wrong — and she concluded out loud that "the system clock
    drifted", with no second clock to compare against."""
    block = resolve_time_queries("what time is it", SENT)
    assert "Verified Real-Time" not in block
    assert "do not claim the clock has drifted" in block.lower()


# ── The guard ────────────────────────────────────────────────────────

@pytest.mark.parametrize("said", [
    "it’s 5:21 am cdt. still dark.",          # her curly apostrophe
    "it's 5:21 am cdt. still dark.",
    "Ekco, it’s 5:21 AM CDT. Still dark.",
    "5:21 AM CDT. still dark.",               # addressee guard removed the name
])
def test_a_wrong_stated_time_is_corrected(said):
    out = P.correct_stated_time(said, TRUE)
    assert "5:14" in out and "5:21" not in out


def test_the_rest_of_the_sentence_survives():
    out = P.correct_stated_time("it’s 5:21 am cdt. still dark.", TRUE)
    assert out.endswith("still dark.")


def test_a_correct_time_is_left_alone():
    said = "it's 5:14 am cdt. still dark."
    assert P.correct_stated_time(said, TRUE) == said


@pytest.mark.parametrize("said", [
    "the raid starts at 8:00 pm, don't be late.",
    "i woke at 3:15 and couldn't get back to sleep.",
    "no clock in this one at all.",
])
def test_a_time_that_is_not_a_claim_about_now_survives(said):
    """The copula is required, for the same reason it is in
    `_STALE_CLOCK_CLAIM`: a scheduled time is a fact about a time."""
    assert P.correct_stated_time(said, TRUE) == said


def test_only_the_assertion_is_touched():
    out = P.correct_stated_time("it’s 5:21 am cdt. the raid starts at 8:00 pm.", TRUE)
    assert "5:14 am cdt" in out and "8:00 pm" in out


@pytest.mark.parametrize("asked,expected", [
    ("Kaia, what time is it", True),
    ("what's the time?", True),
    ("what do you think of neuromancer", False),
    ("", False),
])
def test_the_guard_only_runs_on_a_time_question(asked, expected):
    assert is_time_query(asked) is expected


def test_the_guard_is_wired_into_the_response_path():
    import inspect
    from utils.core.message_processor import MessageProcessor
    src = inspect.getsource(MessageProcessor)
    assert "correct_stated_time" in src, "the time guard is not called"
    assert "is_time_query" in src, "the guard would run on every turn"


def test_the_reported_failure_now_answers_correctly():
    """The transcript, end to end."""
    assert is_time_query("Kaia, what time is it")
    true_time, _, _ = _get_user_time_info("Ekco", message_instant(_Msg(SENT)))
    assert P.correct_stated_time("it’s 5:21 am cdt. still dark.", true_time) \
        == "it’s 5:14 am cdt. still dark."
