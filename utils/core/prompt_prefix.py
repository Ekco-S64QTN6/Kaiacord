"""Keeps the start of her prompt in the model's cache.

Every reply reprocessed its whole prompt, about 16,000 tokens and 12 of the 22
seconds of a turn, though the persona at the front of it never changes.
gemma3 has sliding-window attention, so llama-server can only resume from a
context checkpoint, and it writes those at the end of a prompt, never partway
through. A request that is the persona alone leaves a checkpoint where every
later prompt can pick up. Measured on a 10,783-token prompt: 9.7 s, then 6.4 s
on each turn after one of these, other calls in between or not.

Two things keep it working. Nothing in the persona changes from turn to turn:
the time went in at token 1,231 and cost the whole prefix, so it lives in the
metadata block now. And the warm-up is repeated when a turn comes back cold, as
one does after the model is reloaded or the cache rolls over.
"""
from __future__ import annotations

import asyncio
import time
import uuid

from utils.infrastructure.logging.kaia_logger import log_debug

#: Cut from the end of the persona, so the checkpoint falls inside what every
#: prompt shares: one written just past the shared text cannot be resumed from.
TRIM_CHARS = 200
#: Per token of a prompt nothing was reused for: 0.85–0.90 ms. A 16,000-token
#: turn that picked up the persona averages about 0.63.
COLD_S_PER_TOKEN = 0.00075
#: Too short to tell, and not worth a warm-up: a monologue, a short task.
MIN_TOKENS = 6000
MIN_GAP_S = 600

_last_warm = 0.0
_warming = False


def warm_messages(persona: str) -> list:
    return [{"role": "system", "content": persona[:-TRIM_CHARS]}]


def looks_cold(prompt_eval_count, prompt_eval_duration_ns) -> bool:
    if not prompt_eval_count or not prompt_eval_duration_ns or prompt_eval_count < MIN_TOKENS:
        return False
    return prompt_eval_duration_ns / 1e9 / prompt_eval_count > COLD_S_PER_TOKEN


async def warm(ollama_client, chat_model: str) -> bool:
    """One request that is the persona alone. Never raises: a missed warm-up costs
    one slow turn, not a reply."""
    global _last_warm, _warming
    if _warming:
        return False
    _warming = True
    _last_warm = time.time()
    try:
        from utils.infrastructure.gpu.gpu_manager import GPUTaskPriority, chat_options, gpu_memory_manager
        from utils.social.kaia_social_responder import load_persona_async
        persona = await load_persona_async()
        if not persona or len(persona) <= TRIM_CHARS:
            return False
        await gpu_memory_manager.run_with_gpu_guard(
            model_name=chat_model, priority=GPUTaskPriority.BACKGROUND,
            coro=lambda: asyncio.wait_for(
                ollama_client.chat(model=chat_model, messages=warm_messages(persona),
                                   options=chat_options(num_predict=1, temperature=0.0), keep_alive=-1),
                timeout=120),
            task_id=f"prefix_warm_{uuid.uuid4().hex[:8]}")
        log_debug("[prompt_prefix] persona warmed into the model's cache")
        return True
    except Exception as e:
        log_debug(f"[prompt_prefix] warm-up skipped: {type(e).__name__}: {e}")
        return False
    finally:
        _warming = False


def note_turn(response, ollama_client, chat_model: str, now=None):
    """After a generation: if nothing was reused, warm again for the next turn.
    Returns the task it started, if any."""
    get = response.get if hasattr(response, "get") else lambda k, d=None: getattr(response, k, d)
    if not looks_cold(get("prompt_eval_count"), get("prompt_eval_duration")):
        return None
    now = time.time() if now is None else now
    if _warming or now - _last_warm < MIN_GAP_S:
        return None
    from utils.infrastructure.monitoring.async_task_registry import task_registry
    task = asyncio.create_task(warm(ollama_client, chat_model))
    task_registry.register(f"prefix_warm_{uuid.uuid4().hex[:6]}", task)
    return task
