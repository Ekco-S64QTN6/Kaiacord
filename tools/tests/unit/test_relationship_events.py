"""Relationship events come from what the speaker said to her.

They are injected into her prompt as relationship notes, repair weighted
highest, so a false event misrepresents the relationship every turn.
"""
import pytest

from utils.core.relationship_manager import detect_event_type


@pytest.mark.parametrize("text", [
    "that's actually pretty good advice",
    "fair enough, it's a global mass extinction event",
    "an old motorcycle with points ignition still works when everything's broken",
    "THREAD TITLE: AI\n\nTHREAD CONTEXT:\n#1 bob: you're wrong, shut up",
    "Kaia, look at this\n\n[LINKED_WEB_CONTENT]\nCorrection: the article was wrong. Thanks!",
    "https://example.com/stop-it-thanks",
])
def test_ordinary_remarks_and_other_peoples_text_are_not_events(text):
    assert detect_event_type(text, "") is None


@pytest.mark.parametrize("text,kind", [
    ("erm i meant to say obrigado", "repair"),
    ("no, that's not right, it was 1999", "repair"),
    ("Kaia, stop replying to Brad in the commodore64 thread", "friction"),
    ("thank you, that helped", "positive"),
    ("really appreciated that", "positive"),
])
def test_real_events_are_still_found(text, kind):
    assert detect_event_type(text, "") == kind
