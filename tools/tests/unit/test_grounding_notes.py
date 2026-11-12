"""She is told when a picture never reached her and when a quoted line is in nothing she was given."""
import asyncio
import types

import pytest

from utils.core import grounding_notes as g
from utils.core.message_processor import MessageProcessor


@pytest.mark.parametrize("words", [
    "what do you think of this picture i took of the sunset",
    "rate my selfie",
    "look at lucky right now lol",
    "the image was picked for the composition",
])
def test_a_picture_spoken_of_that_did_not_reach_her_gets_the_note(words):
    assert g.picture_note(words, has_picture=False) == g.PICTURE_NOTE


@pytest.mark.parametrize("words, has_picture", [
    ("what do you think of this picture", True),                     # it reached her
    ("look at this picture https://example.com/a.jpg", False),       # a link: the enricher's
    ("look at that, you were right", False),                         # ordinary talk
    ("i painted the fence today", False),
])
def test_no_picture_note_when_one_is_there_or_none_is_meant(words, has_picture):
    assert g.picture_note(words, has_picture) == ""


def test_a_line_she_was_given_nothing_about_gets_the_quote_note():
    ask = "who said 'the quiet mind hears the river before the rain'"
    assert g.quote_note(ask, "persona text. retrieved: a passage about rivers.") == g.QUOTE_NOTE


def test_a_line_that_is_in_what_she_was_given_gets_none():
    ask = "who wrote “The sky above the port was the color of television”?"
    given = "Book - Neuromancer: The sky above the port was the color of television, tuned to a dead channel."
    assert g.quote_note(ask, given) == ""


@pytest.mark.parametrize("words", [
    "the quiet mind hears the river before the rain",                # no question
    "who said that?",                                                # nothing quoted
    "who said 'hi'",                                                 # too short to be a line
])
def test_no_quote_note_without_an_ask_and_a_quoted_line(words):
    assert g.quote_note(words, "") == ""


def test_a_tried_picture_is_left_to_the_vision_note():
    words = "what do you think of this picture, who said 'the quiet mind hears the river before the rain'"
    assert g.notes_for(words, has_picture=False, tried_pictures=True, given="") == g.QUOTE_NOTE
    both = g.notes_for(words, has_picture=False, tried_pictures=False, given="")
    assert g.QUOTE_NOTE in both and g.PICTURE_NOTE in both


class _Stop(BaseException):
    pass


def _run_stage(words, attachments=()):
    p = MessageProcessor.__new__(MessageProcessor)
    p.bot_state = types.SimpleNamespace(channel_memory={}, is_generating=False)
    p.context_optimizer = types.SimpleNamespace(optimize_context=lambda **k: {})
    p._construct_messages = lambda ctx, opt: [{"role": "system", "content": "persona"},
                                              {"role": "user", "content": f"Ekco: {words}"}]
    seen = {}

    async def call(ctx, messages):
        seen["messages"] = messages
        raise _Stop

    async def fetch(url, is_gif=False):
        return None                                                  # the picture fails to load
    p._call_ollama_with_retries = call
    p._fetch_image_as_base64 = fetch
    msg = types.SimpleNamespace(attachments=list(attachments), embeds=[], reference=None, content=words,
                                channel=types.SimpleNamespace(), platform="discord")
    ctx = types.SimpleNamespace(message=msg, own_words=words, channel_id=1, category="GENERAL", system_prompt="",
                                context_nodes=[], intent=None, sanitized_content=words, author_id=1)
    with pytest.raises(_Stop):
        asyncio.run(p._generate_response_stage(ctx))
    return seen["messages"]


def test_the_generation_stage_puts_the_note_beside_the_message():
    messages = _run_stage("what do you think of this picture i took")
    assert messages[-1]["content"].endswith(g.PICTURE_NOTE)
    assert g.PICTURE_NOTE not in messages[0]["content"]


def test_a_picture_that_failed_to_load_gets_only_the_vision_note():
    upload = types.SimpleNamespace(filename="sunset.jpg", url="https://cdn.discordapp.com/a/sunset.jpg",
                                   content_type="image/jpeg", size=1000)
    messages = _run_stage("what do you think of this picture i took", [upload])
    assert g.PICTURE_NOTE not in messages[-1]["content"]
    assert "could not be loaded" in messages[0]["content"]
