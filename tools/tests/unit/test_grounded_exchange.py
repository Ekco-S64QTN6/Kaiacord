"""A reply drafted from reference documents is marked grounded on the turn,
where the desire engine reads it afterwards."""
import asyncio
import types
from unittest.mock import patch

from utils.core.message_context import MessageContext
from utils.core.message_processor import MessageProcessor
from utils.infrastructure.system.yaml_config import config


def _generate(raw_nodes):
    class Client:
        async def chat(self, **kw):
            return {"message": {"content": "the book says the harbour froze in 1709, and the fleet stayed in."}}

    async def guard(model_name, coro, task_id=None, priority=None):
        return await (coro() if callable(coro) else coro)

    p = MessageProcessor.__new__(MessageProcessor)
    p.config, p.ollama_client = config, Client()
    p.bot_state = types.SimpleNamespace(first_chat_done=False)
    msg = types.SimpleNamespace(platform="discord", content="when did the harbour freeze?")
    ctx = MessageContext(message=msg, sanitized_content=msg.content, is_social=False, is_mention=True,
                         is_dm=False, start_time=0.0)
    ctx.raw_nodes = raw_nodes
    with patch("utils.infrastructure.gpu.gpu_manager.gpu_memory_manager.run_with_gpu_guard", guard), \
         patch("utils.core.prompt_prefix.note_turn", lambda *a, **k: None), \
         patch("utils.core.kaia_telemetry.record_prompt", lambda *a, **k: None):
        reply = asyncio.run(p._call_ollama_with_retries(ctx, [{"role": "user", "content": msg.content}]))
    return ctx, reply


def test_a_reply_from_a_book_is_grounded():
    book = {"content": "…", "metadata": {"source_type": "book", "file_path": "knowledge_base/books/x.md"}}
    ctx, reply = _generate([book])
    assert reply and ctx.is_grounded is True


def test_ordinary_conversation_is_not():
    log = {"content": "…", "metadata": {"source_type": "user_log", "retrieval_method": "hybrid"}}
    ctx, _ = _generate([log])
    assert ctx.is_grounded is False
