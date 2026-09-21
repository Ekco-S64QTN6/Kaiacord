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
