"""A proactive opener that opens like her recent posts in that channel is drafted again."""
import asyncio
from unittest.mock import patch

from utils.core import kaia_proactive as kp

CHANNEL = 1462239450691145924
WORN = ["it's funny how the light shifts in the morning.", "it's funny, i was just thinking about cecily.",
        "the tank light is steady tonight.", "it's funny how much effort people put into blame."]


def _opener(drafts, recent=WORN):
    class Client:
        async def chat(self, **kw):
            return {"message": {"content": drafts.pop(0)}}

    async def guard(model_name, coro, task_id=None, priority=None):
        return await (coro() if callable(coro) else coro)

    engine = kp.ProactiveEngine.__new__(kp.ProactiveEngine)
    trigger = kp.ProactiveTrigger(trigger_type="knowledge", channel_id=CHANNEL, context="the croissant shop")
    with patch.object(kp.ProactiveEngine, "_load_diversity_log",
                      lambda self: [{"channel_id": CHANNEL, "summary": s} for s in recent]), \
         patch("utils.infrastructure.gpu.gpu_manager.gpu_memory_manager.run_with_gpu_guard", guard):
        return asyncio.run(engine.generate_opener(trigger, Client(), "gemma3:12b", "persona"))


def test_a_worn_opening_is_drafted_again():
    out = _opener(["it's funny, i was just thinking about the croissant shop on fifth.",
                   "the croissant shop on fifth closed early again, the line went round the block."])
    assert out and out.startswith("the croissant shop")


def test_a_second_worn_draft_is_not_posted():
    assert _opener(["it's funny how croissants work.", "it's funny, croissants again, apparently."]) is None


def test_a_fresh_opening_goes_first_time():
    drafts = ["the croissant shop on fifth closed early again today.", "unused"]
    assert _opener(drafts).startswith("the croissant shop") and drafts == ["unused"]
