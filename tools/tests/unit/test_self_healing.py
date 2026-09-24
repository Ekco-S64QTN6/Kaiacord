"""The generation fallback."""
import asyncio

from utils.infrastructure.system.self_healing import SelfHealingSystem


class _Chat:
    def __init__(self, error):
        self.calls, self.error = [], error

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise Exception(self.error)
        return {"message": {"content": "ok"}}


def _run(error):
    chat = _Chat(error)
    messages = [{"role": "system", "content": "s"}] + [{"role": "user", "content": str(i)} for i in range(6)]
    asyncio.run(SelfHealingSystem.call_with_fallback(
        chat, model="m", messages=messages, options={"num_ctx": 8192, "temperature": 0.7}))
    return chat.calls[1]


def test_a_repeat_abort_keeps_the_conversation_and_penalises_the_loop():
    """A request for a row of dots trips Ollama's token repeat limit. Cutting
    the history on that retry made her forget what she had just agreed to."""
    retry = _run("prediction aborted, token repeat limit reached (status code: 500)")
    assert len(retry["messages"]) == 7
    assert retry["options"]["repeat_penalty"] >= 1.3
    assert retry["options"]["num_ctx"] == 8192          # runner options unchanged: no reload


def test_other_failures_still_take_the_short_context_fallback():
    retry = _run("CUDA error: out of memory")
    assert len(retry["messages"]) == 3
    assert "repeat_penalty" not in retry["options"]
