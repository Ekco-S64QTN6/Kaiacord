"""Asked what she knows of something nothing in front of her mentions, she is
told so. Asked about "the russian hacker empress" with nothing on Empress in
her prompt, she invented Elena Volkova and attacks in 2045 (9 Nov)."""
from unittest.mock import MagicMock

import pytest

from utils.core import unknown_subject as U

EMPRESS = "kaia what do you know about the russian hacker empress"


def test_the_empress_question_with_nothing_on_her_gets_the_note():
    given = ["# persona\nyou are kaia.", "Cecily: lol", "a russian hacker group was in the news."]
    note = U.note_for(EMPRESS, given)
    assert '"the russian hacker empress"' in note
    assert "say so plainly" in note


def test_a_subject_in_front_of_her_is_left_alone():
    given = ["Ekco: the cracker EMPRESS, famous for bypassing Denuvo, was a russian hacker"]
    assert U.note_for(EMPRESS, given) == ""


def test_the_head_word_has_to_be_there():
    """"russian" and "hacker" are everywhere; "empress" is the subject."""
    assert U.note_for(EMPRESS, ["a russian hacker leaked it"]) != ""


def test_a_scene_she_is_playing_is_in_her_history():
    given = ["Starkind: the shadow syndicate wants the codes", "Kaia: the syndicate can wait."]
    assert U.note_for("what do you know about the shadow syndicate", given) == ""


@pytest.mark.parametrize("text", [
    "who are you", "tell me about your day", "what do you remember about me", "tell me about it",
    "kaia, who was that", "who is they", "can you tell me about https://example.com/a",
    "hey kaia how's it going", "what is the time",
])
def test_turns_that_ask_nothing_nameable_get_nothing(text):
    assert U.note_for(text, []) == ""


@pytest.mark.parametrize("text,subject", [
    ("who is starkind", "starkind"),
    ("have you ever heard of Neuromancer?", "Neuromancer"),
    ("do you know anything about the Denuvo DRM", "the Denuvo DRM"),
])
def test_her_phrasings_are_recognised(text, subject):
    assert U.subject_of(text)[0] == subject


def _construct(text, history=(), rag=""):
    from utils.core.message_context import MessageContext
    from utils.core.message_processor import MessageProcessor
    from utils.infrastructure.system.yaml_config import config
    author = MagicMock()
    author.display_name = author.name = "Cecily"
    author.id = 1415184297744404482
    msg = MagicMock()
    msg.platform, msg.author, msg.content, msg.attachments = "discord", author, text, []
    msg.channel.id = 1
    ctx = MessageContext(message=msg, sanitized_content=text, is_social=False, is_mention=True,
                         is_dm=False, start_time=0.0)
    ctx.category = "general"
    p = MessageProcessor.__new__(MessageProcessor)
    p.config = config
    return p._construct_messages(ctx, {"persona": "P", "rag": rag, "history": list(history)})


def test_the_note_goes_beside_the_question():
    user_turn = _construct(EMPRESS)[-1]["content"]
    assert "nothing you have read, kept or been told mentions" in user_turn


def test_the_question_itself_does_not_count_as_knowing():
    """The question is in the user turn; only what else is there counts."""
    assert "mentions" in _construct(EMPRESS)[-1]["content"]
    told = _construct(EMPRESS, rag="Empress is a cracker known for breaking Denuvo; russian hacker.")
    assert "nothing you have read" not in told[-1]["content"]
