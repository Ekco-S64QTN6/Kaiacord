"""A clipped "do me next" is tied to the speaker's last question and to who "me" is."""
import json

import pytest

from utils.core import followup_note as f

HISTORY = [
    {"role": "user", "content": "Cara: oh ok. You remember Tom? What did you find distinctive about his way of talking?"},
    {"role": "assistant", "content": "long stories, mostly, and a lot of certainty."},
]


@pytest.mark.parametrize("words", [
    "do me next", "Do me next.", "ok now do me", "and me?", "what about me?", "How about me", "me next",
    "my turn", "kaia do me next", "now analyze me",
])
def test_a_clipped_handover_gets_the_note(words):
    note = f.note(words, "Cara", HISTORY)
    assert '"What did you find distinctive about his way of talking?"' in note
    assert note.endswith('"me" is Cara, not you.]')


@pytest.mark.parametrize("words", [
    "What questions do you have for me?",            # says what it means
    "I tell you things, you tell me things",
    "do it next",
    "do me a favour and look at this log",
    "tell me more",
    "that reminds me",
    "",
])
def test_ordinary_first_person_talk_gets_none(words):
    assert f.note(words, "Cara", HISTORY) == ""


def test_no_note_when_their_last_message_asked_nothing():
    history = [{"role": "user", "content": "Cara: Tom was a strange one."},
               {"role": "assistant", "content": "he was."}]
    assert f.note("do me next", "Cara", history) == ""


def test_no_note_when_someone_else_asked_the_last_question():
    history = [{"role": "user", "content": "Dev: what did you make of Tom?"},
               {"role": "assistant", "content": "long stories."}]
    assert f.note("do me next", "Cara", history) == ""
    assert f.note("do me next", "Cara", []) == ""


def test_a_quote_in_the_question_cannot_close_the_note():
    history = [{"role": "user", "content": 'Cara: what did he mean by "the long way"?'}]
    note = f.note("and me?", "Cara", history)
    assert note.count('"') == 4 and "'the long way'" in note
    json.dumps(note)


def test_a_very_long_question_is_not_quoted():
    history = [{"role": "user", "content": "Cara: " + "why " * 100 + "?"}]
    assert f.note("do me next", "Cara", history) == ""
