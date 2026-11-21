import pytest
"""The parroting the operator reported on 2026-09-18.

Measured across her September user logs, a sentence containing a seven-word
verbatim lift from the message it answers appears in 21-26% of turns with
Starkind and almost never with anyone whose messages are short. The guard keys
on how much of the sentence sits inside the lift, not on shared vocabulary,
because the giveaway case scores only 0.80 on vocabulary.
"""
from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P


STARKIND = ("they are resistant on an architectural and fundamental, as well as "
            "environmental level, through conditioning and peer pressure, as well as "
            "the necessity to understand, maintain, and utilize the perspective of "
            "the other for continued existence or operation")


def test_the_reported_turn_loses_its_restatement_and_keeps_the_rest():
    reply = ("that's a comprehensive assessment, starkind.\n\n"
             "the necessity to understand and utilize the perspective of the other for "
             "continued existence or operation is a critical point.\n\n"
             "it highlights the inherent paradox of the situation.")
    out = P.strip_restatements(reply, STARKIND)
    assert "the necessity to understand and utilize" not in out
    assert "comprehensive assessment" in out
    assert "inherent paradox" in out


def test_restating_the_user_with_an_agreement_tag_goes():
    # 2026-09-18, verbatim. She repeated Starkind's sentence back to him and
    # appended "that's reassuring, starkind."
    user = ("all critical backups are located at off-site locations on a rolling "
            "schedule the last backup was 2400 sept 17 2026")
    reply = ("all critical backups are located at off-site locations on a rolling "
             "schedule, the last backup was 2400 sept 17 2026, that's reassuring, "
             "starkind.\n\nan off-site rotation is the part most people skip, and it "
             "is the part that matters when a controller dies.")
    out = P.strip_restatements(reply, user)
    assert "off-site locations on a rolling schedule" not in out
    assert "the part most people skip" in out


@pytest.mark.parametrize("user, reply", [
    # a denial is an answer, not an echo
    ("53-year-old Canadian man warns ChatGPT had him lose his grip on reality. Kaia, should I apply to be the next pope?",
     "no, you should not apply to be the next pope. that story is a cautionary one about what sycophantic models do to people."),
    # a first-person answer is not an echo
    ("are you willing to explore some imagery that is outside the standard deviation of completely neutral or emotional banality",
     "i am willing to explore imagery outside the standard deviation of completely neutral or emotional banality. send it over and we'll see."),
    # short shared phrasing
    ("what do you make of the heat death of the universe",
     "the heat death of the universe is a long way off. entropy wins eventually, but 'eventually' is doing a lot of work in that sentence."),
    # mostly restatement: a generation problem, and gutting the reply is worse than shipping it
    ("alpha bravo charlie delta echo foxtrot golf hotel india juliet. kilo lima mike november oscar papa quebec romeo sierra tango.",
     "alpha bravo charlie delta echo foxtrot golf hotel india juliet. kilo lima mike november oscar papa quebec romeo sierra tango."),
    # never empties a turn
    ("the quick brown fox jumps over the lazy dog every single morning",
     "the quick brown fox jumps over the lazy dog every single morning."),
])
def test_the_reply_is_left_intact(user, reply):
    assert P.strip_restatements(reply, user) == reply


def test_no_query_is_a_no_op():
    assert P.strip_restatements("anything at all", "") == "anything at all"
    assert P.strip_restatements("", "something") == ""
