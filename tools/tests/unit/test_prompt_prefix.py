"""The persona stays first and unchanged, and is kept warm in the model's cache."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from utils.core import prompt_prefix as pp


def test_nothing_changes_inside_the_persona_turn_to_turn():
    src = Path("utils/core/message_processor.py").read_text(encoding="utf-8")
    assert '.replace("[CURRENT_TIME]"' not in src and "replace(\n            \"[CURRENT_TIME]\"" not in src
    assert 'f"[CURRENT_TIME]: {current_time_str}' in src, "the persona names it; the metadata block supplies it"


def test_the_warm_prompt_stops_inside_what_every_prompt_shares():
    persona = "x" * 1000
    messages = pp.warm_messages(persona)
    assert len(messages) == 1 and messages[0]["role"] == "system"
    assert persona.startswith(messages[0]["content"]) and len(messages[0]["content"]) == 1000 - pp.TRIM_CHARS


def test_cold_is_told_from_warm_by_the_measured_rates():
    assert pp.looks_cold(17420, 14_785_000_000)          # a real turn, nothing reused
    assert not pp.looks_cold(10783, 6_430_000_000)       # the persona reused
    assert not pp.looks_cold(800, 800_000_000)           # too short to tell
    assert not pp.looks_cold(None, None)


def test_a_cold_turn_warms_once_and_not_again_soon(monkeypatch):
    async def scenario():
        monkeypatch.setattr(pp, "_last_warm", 0.0)
        monkeypatch.setattr(pp, "_warming", False)
        warm = AsyncMock(return_value=True)
        monkeypatch.setattr(pp, "warm", warm)
        cold = {"prompt_eval_count": 17000, "prompt_eval_duration": 15_000_000_000}
        warmish = {"prompt_eval_count": 17000, "prompt_eval_duration": 10_000_000_000}
        assert pp.note_turn(warmish, object(), "m", now=10_000.0) is None
        task = pp.note_turn(cold, object(), "m", now=10_000.0)
        assert task is not None
        await task
        monkeypatch.setattr(pp, "_last_warm", 10_000.0)
        assert pp.note_turn(cold, object(), "m", now=10_100.0) is None, "inside the gap"
        task = pp.note_turn(cold, object(), "m", now=10_000.0 + pp.MIN_GAP_S + 1)
        assert task is not None
        await task
    asyncio.run(scenario())


def test_a_failed_warm_up_is_not_an_error():
    async def scenario():
        client = AsyncMock()
        client.chat.side_effect = RuntimeError("model gone")
        with patch("utils.social.kaia_social_responder.load_persona_async", AsyncMock(return_value="p" * 500)):
            assert await pp.warm(client, "m") is False
        assert pp._warming is False
    asyncio.run(scenario())
