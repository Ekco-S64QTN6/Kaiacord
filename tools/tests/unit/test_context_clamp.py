"""The reply must always have room to exist.

`optimize_context` budgets with `performance.token_multiplier` (1.6), a
constant calibrated to the *median*. Measured over 147 real prompts the true
ratio is 1.55 median, 1.66 at p90, 2.04 at worst — so a median used as a bound
underestimates about half of all prompts, and dense ones badly.

Over 154 production generations, 4 broke the response reserve and the reply
shrank in lockstep with the headroom left:

    prompt 15484  headroom 900  reply 58 tokens
    prompt 15487  headroom 897  reply 55
    prompt 15840  headroom 544  reply 29
    prompt 16363  headroom  21  reply 21

against a median of 87 tokens when the reserve held. She got terser on exactly
the turns carrying the most context.
"""
from unittest.mock import MagicMock

import pytest

from utils.core.message_processor import MessageProcessor

WINDOW, RESERVE = 16384, 1024
WORST = 2.05


@pytest.fixture
def processor():
    proc = MessageProcessor.__new__(MessageProcessor)
    proc.config = MagicMock()
    proc.config.max_context_tokens = WINDOW
    proc.config.max_response_tokens = RESERVE
    return proc


def _tokens(messages):
    return sum(int(len(str(m["content"]).split()) * WORST) for m in messages)


def _build(history_turns, words_each=400, system_words=5000):
    messages = [{"role": "system", "content": "sys " * system_words}]
    for i in range(history_turns):
        messages.append({"role": "user" if i % 2 == 0 else "assistant",
                         "content": f"turn{i} " * words_each})
    messages.append({"role": "user", "content": "the actual question " * 20})
    return messages


def test_an_oversized_prompt_is_trimmed_to_leave_the_reserve(processor):
    messages = _build(history_turns=12)
    assert _tokens(messages) > WINDOW - RESERVE, "fixture is not actually oversized"

    clamped = processor._clamp_to_context_window(messages)
    assert _tokens(clamped) <= WINDOW - RESERVE


def test_a_prompt_that_already_fits_is_untouched(processor):
    messages = _build(history_turns=4)
    before = list(messages)
    clamped = processor._clamp_to_context_window(messages)
    assert clamped == before, "trimmed a prompt that was already within budget"


def test_the_system_prompt_and_user_message_are_never_dropped(processor):
    """Trimming either would cost her persona or the question itself; history
    is what optimize_context would have dropped had it known the real size."""
    clamped = processor._clamp_to_context_window(_build(history_turns=40))
    assert clamped[0]["role"] == "system"
    assert clamped[-1]["content"].startswith("the actual question")
    assert len(clamped) >= 2


def test_it_degrades_rather_than_raising_on_a_broken_config(processor):
    processor.config.max_context_tokens = "not a number"
    messages = _build(history_turns=12)
    assert processor._clamp_to_context_window(messages) is messages
