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


def test_a_denial_is_an_answer_not_an_echo():
    user = ("53-year-old Canadian man warns ChatGPT had him lose his grip on reality. "
            "Kaia, should I apply to be the next pope?")
    reply = ("no, you should not apply to be the next pope. that story is a cautionary "
             "one about what sycophantic models do to people.")
    assert P.strip_restatements(reply, user) == reply


def test_a_first_person_answer_is_not_an_echo():
    user = ("are you willing to explore some imagery that is outside the standard "
            "deviation of completely neutral or emotional banality")
    reply = ("i am willing to explore imagery outside the standard deviation of "
             "completely neutral or emotional banality. send it over and we'll see.")
    assert P.strip_restatements(reply, user) == reply


def test_short_shared_phrasing_is_left_alone():
    user = "what do you make of the heat death of the universe"
    reply = ("the heat death of the universe is a long way off. entropy wins eventually, "
             "but 'eventually' is doing a lot of work in that sentence.")
    assert P.strip_restatements(reply, user) == reply


def test_a_reply_that_is_mostly_restatement_is_left_intact_rather_than_gutted():
    # Bounding the damage: if most of the turn is echo that is a generation
    # problem, and deleting most of a reply is worse than shipping a lazy one.
    user = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet. "
            "kilo lima mike november oscar papa quebec romeo sierra tango.")
    reply = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet. "
             "kilo lima mike november oscar papa quebec romeo sierra tango.")
    assert P.strip_restatements(reply, user) == reply


def test_guard_never_empties_a_turn():
    user = "the quick brown fox jumps over the lazy dog every single morning"
    reply = "the quick brown fox jumps over the lazy dog every single morning."
    assert P.strip_restatements(reply, user) == reply


def test_no_query_is_a_no_op():
    assert P.strip_restatements("anything at all", "") == "anything at all"
    assert P.strip_restatements("", "something") == ""
