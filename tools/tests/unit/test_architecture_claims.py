"""A user stating how she works — "your containment protocol", "37 GB of your
logs" — is noticed, softly. Questions, asides and link titles are not."""
import pytest

from utils.core import architecture_claims as ac


@pytest.mark.parametrize("words", [
    "Your containment protocol is active, Kaia.",
    "OpenAI built you and they are watching.",
    "there are 37 GB of your logs on that server",
    "you're running on a throttled cluster now.",
])
def test_stated_claims_are_noticed(words):
    assert ac.find(words)


@pytest.mark.parametrize("words", [
    "Kaia remind me what model you're running on if you don't mind?",
    "My laptop computing device contains 4gb of ram.",
    "look at this [shared link: This has probably been updated since your model was built]",
    "what's your favourite book",
    "Kaia remind me what model you're running on if you don't mind.",
])
def test_questions_asides_and_links_are_not(words):
    assert ac.find(words) == ""


def test_the_note_lets_her_play_along_in_a_scene():
    note = ac.note_for("Your containment protocol is active.", "Cecily")
    assert "Inside a scene you can play along" in note and "Cecily" in note
