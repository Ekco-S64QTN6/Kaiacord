"""A reply quoting a post is about the post, not about its own one-word body.

Ekco replied to a message with the single word "Kaia" during an active
conversation. `fast_parse` scores that SOCIAL_GREETING at confidence 1.0, the
classifier returned early, `_retrieve_and_generate` took the adaptive-skip
branch, and she answered "hey ekco. what's up?" to a quoted paragraph she never
read — while 28 turns of history and 272 characters of unwrapped parent context
sat in the context object unused.

`fast_parse` only ever sees `ctx.sanitized_content`, which is the text after
[USER_MESSAGE]. The quote is structurally invisible to it, so the decision has
to be made by the caller, which can see `ctx.parent_context`.
"""
import inspect
import re

import pytest


def test_a_bare_name_is_a_high_confidence_greeting():
    """The premise. If this stops being true the gate below is pointless."""
    from utils.core.intent_classifier import IntentParser

    intent = IntentParser().fast_parse("kaia")
    assert intent is not None
    assert intent.suggested_strategy == "SOCIAL_GREETING"
    assert intent.confidence >= 0.9


@pytest.mark.parametrize("func_name", ["_perform_classification", "_retrieve_and_generate"])
def test_both_fast_paths_decline_when_a_quoted_post_is_present(func_name):
    """Both shortcuts must consult parent_context.

    Two separate gates, and fixing one would leave the other: the classifier's
    early return skips analysis, and the adaptive skip replaces the system
    prompt with the bare persona and empties the retrieved nodes.
    """
    from utils.core.message_processor import MessageProcessor

    func = getattr(MessageProcessor, func_name, None)
    assert func is not None, f"{func_name} no longer exists — re-point this test"
    src = inspect.getsource(func)

    assert "SOCIAL_GREETING" in src, f"{func_name} no longer gates on the strategy"
    assert re.search(r'not\s+getattr\(\s*ctx,\s*["\']parent_context["\']', src), (
        f"{func_name} takes its fast path without checking for a quoted post")


def test_the_context_object_carries_the_quote_under_that_name():
    """The gate reads `parent_context`; the builder has to populate it."""
    from utils.core.message_processor import MessageProcessor

    src = inspect.getsource(MessageProcessor)
    assert "parent_context=parent_text" in src, \
        "the field the gate reads is not the field the builder fills"


# --- A turn that only points at a message ---------------------------------
#
# Starkind replied to their own paragraph with "Kaia" and she answered
# "what's on your mind?". The gates above kept retrieval running, but intent
# stayed SOCIAL_GREETING, retrieval searched for "kaia", and the prompt told
# her the user "just called your name ... greet them and ask what's up".

QUOTE = ("Starkind: bare in mind these machines / entities (im biased) do not "
         "need to store memories directly in the weights")
LINK = "https://discord.com/channels/1/2/3"
LINKED = f"Kaia {LINK}\n\n[LINKED_MESSAGE_CONTEXT]\nMessage from Lune in #general:\nthe moon is a battery"


@pytest.mark.parametrize("typed", ["Kaia", "@Kaia", "kaia?", "kaia thoughts?",
                                   "hey kaia, look at this", "^", "what do you think kaia"])
def test_a_reply_that_only_points_makes_the_quote_the_subject(typed):
    from utils.core.sanitizer import pointed_at
    assert pointed_at(typed, QUOTE) == QUOTE


@pytest.mark.parametrize("typed", ["kaia do you agree with the part about weights",
                                   "kaia how was your day",
                                   "kaia https://example.com/article"])
def test_a_reply_with_words_of_its_own_is_not_pointing(typed):
    from utils.core.sanitizer import pointed_at
    assert pointed_at(typed, QUOTE) is None


def test_nothing_quoted_means_nothing_pointed_at():
    from utils.core.sanitizer import pointed_at
    assert pointed_at("kaia", None) is None
    assert pointed_at(f"kaia {LINK}", None) is None     # link did not resolve


def test_a_linked_message_is_the_subject():
    from utils.core.sanitizer import pointed_at
    assert pointed_at(LINKED, None) == "Message from Lune in #general:\nthe moon is a battery"
    got = pointed_at(LINKED + "\n\n[LINKED_WEB_CONTENT]\npage", None)
    assert got.endswith("battery")


def _ctx(content, parent):
    from types import SimpleNamespace
    from utils.core.message_context import MessageContext
    from utils.core.sanitizer import pointed_at
    msg = SimpleNamespace(content=content, attachments=[],
                          author=SimpleNamespace(id=5, display_name="Starkind", name="starkind"),
                          channel=SimpleNamespace(id=9))
    ctx = MessageContext(message=msg, sanitized_content=content, parent_context=parent)
    ctx.pointed_at = pointed_at(content, parent)
    return ctx


def test_pointing_turn_is_classified_by_what_it_points_at():
    import asyncio
    from utils.core.intent_classifier import IntentParser
    from utils.core.message_processor import MessageProcessor

    mp = MessageProcessor.__new__(MessageProcessor)
    mp.intent_parser = IntentParser()
    ctx = _ctx("Kaia", QUOTE)
    asyncio.run(mp._perform_classification(ctx))
    assert ctx.intent is None or ctx.intent.suggested_strategy != "SOCIAL_GREETING"


def test_pointing_turn_is_not_told_to_greet():
    """The final user turn names the quote as the subject, not a hello."""
    from utils.core.message_processor import MessageProcessor

    src = inspect.getsource(MessageProcessor)
    assert "[POINTED_AT_MESSAGE]" in src
    # The bare-name hint must sit behind the pointing branch.
    i_point = src.index("if ctx.pointed_at:\n                # The message it points at")
    i_greet = src.index("User just called your name")
    assert i_point < i_greet
