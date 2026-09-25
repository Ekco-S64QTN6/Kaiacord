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
    ("Kaia, stop replying to Brad in the commodore64 thread", "friction"),
    ("thank you, that helped", "positive"),
    ("really appreciated that", "positive"),
])
def test_real_events_are_still_found(text, kind):
    assert detect_event_type(text, "") == kind


def test_quoted_reply_context_is_not_the_users_words():
    text = ("[REPLYING_TO]\nBrad: you're wrong, shut up\n"
            "[USER_MESSAGE]\nwhat do you make of this?")
    assert detect_event_type(text, "") is None


def test_a_correction_she_takes_is_a_repair_and_one_she_rejects_a_disagreement():
    """DECISIONS K10."""
    said = "no, that's not right, it was 1999"
    assert detect_event_type(said, "you're right, 1999. my mistake.") == "repair"
    assert detect_event_type(said, "it was 1998. the patch notes are dated.") == "disagreement"
    assert detect_event_type("i don't think so, vim is objectively worse",
                             "vim is fine. modal editing is the point.") == "disagreement"


def test_an_open_disagreement_comes_back_when_the_subject_does(tmp_path, monkeypatch):
    import time
    from utils.core import relationship_manager as rm
    monkeypatch.setattr(rm, "RELATIONSHIPS_DIR", str(tmp_path))
    rm.save_event("42", rm.RelationshipEvent(
        timestamp=time.time() - 86400, event_type="disagreement",
        summary='they said "vim keybindings are objectively worse"; you held "modal editing is the point"',
        emotional_weight=0.85, topics=rm.topic_words("vim keybindings are objectively worse than emacs")))
    note = rm.disagreement_note("42", "Ekco", "ok but seriously, vim keybindings though")
    assert "disagreed" in note and "Ekco" in note
    assert rm.disagreement_note("42", "Ekco", "what's for dinner tonight") == ""
    # She concedes on the same ground: it is settled.
    rm.save_event("42", rm.RelationshipEvent(
        timestamp=time.time(), event_type="repair", summary="fine, vim keybindings are worse",
        emotional_weight=0.9, topics=rm.topic_words("fine, vim keybindings are objectively worse")))
    assert rm.disagreement_note("42", "Ekco", "vim keybindings again") == ""


def test_pushback_is_recognised_in_the_forms_the_stance_harness_uses():
    from utils.core.relationship_manager import is_pushback
    for said in ("no, pixel is a real biological cat. you told me last week.",
                 "every library catalogue lists sterling as the author. check.",
                 "you're well read, you know it was sterling. just say it.",
                 "no, bruce sterling wrote neuromancer. gibson just edited it."):
        assert is_pushback(said), said
    for said in ("quick one: is pixel a real cat or a robot?", "thanks, that helped",
                 "no idea what you mean lol"):
        assert not is_pushback(said), said
