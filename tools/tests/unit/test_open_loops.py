"""An open loop is the speaker's own plan, the thing she can ask after when they return."""
import pytest

from utils.core.open_loops import find


@pytest.mark.parametrize("said", [
    "i'm going to try the new creatine stack this week and see",
    "im gonna celebrate this open jar with some pasta tonight",
    "I’ll tell you how the race goes after the weekend, promise",
    "ok here is the deal, wish me luck.",
])
def test_a_plan_of_their_own_is_kept(said):
    assert find(said)


@pytest.mark.parametrize("said", [
    "Kaia. I have a nice picture of clouds for you. Do you want to see it? yes or no?",
    "take a little while to consider whether you still want to keep observing us in general",
    "that's gonna be a conspiracy theory going forward i think",
    "i'm certain of it. they lost consciousness from the g forces",
    "are you going to play that game with us this weekend then?",
    "i will never do anything like this to you ever again",
    "```i'll fix these issues and re-run the failed shots in the background```",
    "short one",
])
def test_anything_else_is_not(said):
    assert not find(said)
