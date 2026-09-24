"""The read on a user's state matches whole words, not substrings."""
import pytest

from utils.infrastructure.system.bot_state import BotState


@pytest.mark.parametrize("text, key, not_expected", [
    ("whatever you think is fine", "apparent_mood", "frustrated"),     # h-a-t-e
    ("talk to you later", "apparent_mood", "tired"),                   # l-a-t-e
    ("definitely going tonight", "likely_intent", "troubleshooting"),  # d-e-f
    ("you should see this", "likely_intent", "greeting"),              # y-o
    ("his sword broke in half lol", "likely_intent", "greeting"),      # h-i
    ("OK", "energy", "high"),                                          # two capitals
])
def test_substrings_do_not_decide_the_read(text, key, not_expected):
    assert BotState().update_user_state("1", text)[key] != not_expected


def test_real_signals_still_register():
    s = BotState()
    assert s.update_user_state("1", "ugh this is broken")["apparent_mood"] == "frustrated"
    assert s.update_user_state("1", "hey kaia")["likely_intent"] == "greeting"
    assert s.update_user_state("1", "THIS IS AMAZING!!")["energy"] == "high"
