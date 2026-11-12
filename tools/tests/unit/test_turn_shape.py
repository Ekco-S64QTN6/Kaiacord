"""A turn is read for how much it asks of her, from the speaker's own words."""
import pytest

from utils.core import turn_shape


@pytest.mark.parametrize("text", [
    "thanks", "lol", "status kaia", "it's a waiting room in a children's hospital",
    "I dare say they will perhaps find a bit here and a word there.",
])
def test_a_passing_remark_is_an_aside(text):
    assert turn_shape.kind_of(text) == "aside"
    assert "a line or two" in turn_shape.note_for(text)


@pytest.mark.parametrize("text", [
    "kaia what day is it", "is there anything to output?", "who wrote neuromancer?",
])
def test_a_short_question_is_recognised_and_left_alone(text):
    assert turn_shape.kind_of(text) == "question"
    assert turn_shape.note_for(text) == ""       # the note cost her voice on questions


@pytest.mark.parametrize("text", [
    "open direction", "kaia you may continue, stop, or we can choose something else",
    "Kaia. \"What is it like?\"", "what do you think of this?", "tell me about the boat",
    "lets discuss my motivation Kaia. I'm open to that.", "explain", "Please continue with the appraisals",
    "why do you keep the tank?",
])
def test_an_invitation_sets_no_limit(text):
    """A scene's "continue" and a request for her view offer room; nothing here shortens them."""
    assert turn_shape.kind_of(text) == "invitation"
    assert turn_shape.note_for(text) == ""


def test_someone_who_wrote_at_length_set_the_scale_themselves():
    text = " ".join(["word"] * 45)
    assert turn_shape.kind_of(text) == "long"
    assert turn_shape.note_for(text) == ""


def test_a_longer_statement_or_question_gets_no_note():
    statement = "i put psychology firmly in the soft sciences because it rests on subjective models, not measurement"
    assert turn_shape.kind_of(statement) == "statement"
    assert turn_shape.note_for(statement) == ""


def test_a_link_and_her_name_are_not_words_typed():
    assert turn_shape.typed_words("Kaia https://x.com/some/long/path <@123>") == []
    assert turn_shape.typed_words("here kaia") == ["here"]
    assert turn_shape.kind_of("kaia") == "empty"
    assert turn_shape.note_for("kaia") == ""             # a bare name has its own handling


def test_something_shared_gets_no_note():
    assert turn_shape.note_for("here's the main feed https://x.com/a", shared=True) == ""
    assert turn_shape.note_for("", shared=True) == ""


def test_the_notes_carry_no_example_reply_and_no_dash():
    """A prompt's example is the output, and the persona forbids the em dash."""
    for note in (turn_shape.note_for("thanks"),):
        assert "—" not in note and "'" not in note.replace("they're", "").replace("doesn't", "")
        assert "e.g." not in note and "like:" not in note


def test_the_note_sits_beside_the_message_not_in_the_system_prompt():
    from unittest.mock import MagicMock
    from utils.core.message_context import MessageContext
    from utils.core.message_processor import MessageProcessor
    from utils.infrastructure.system.yaml_config import config

    def turn(text):
        author = MagicMock()
        author.display_name = author.name = "Ekco"
        author.id = 1
        msg = MagicMock()
        msg.platform, msg.author, msg.content = "discord", author, text
        msg.attachments, msg.embeds, msg.stickers = [], [], []
        msg.channel.id = 1
        ctx = MessageContext(message=msg, sanitized_content=text, is_social=False, is_mention=True,
                             is_dm=False, start_time=0.0)
        p = MessageProcessor.__new__(MessageProcessor)
        p.config = config
        return p._construct_messages(ctx, {"persona": "P", "rag": "", "history": []})

    messages = turn("thanks")
    assert "a line or two" in messages[-1]["content"]
    assert "a line or two" not in messages[0]["content"]
    assert "a line or two" not in turn("tell me about the boat")[-1]["content"]
