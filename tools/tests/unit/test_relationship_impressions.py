"""A prose impression per person, rewritten from the events."""
import asyncio
import json
import time
from types import SimpleNamespace

from utils.core import relationship_impressions as ri
from utils.core import relationship_manager as rm


def _event(kind, summary, ago_days=1):
    return rm.RelationshipEvent(timestamp=time.time() - ago_days * 86400, event_type=kind,
                                summary=summary, emotional_weight=0.6)


def test_an_impression_is_written_from_new_events_and_injected(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "RELATIONSHIPS_DIR", str(tmp_path))
    rm.save_event("42", _event("disagreement", 'they said "vim is worse"; you held "modal is the point"'))
    rm.save_event("99", _event("positive", "thanks", ago_days=200))     # inactive
    prompts = []

    async def chat(model, messages, options, keep_alive):
        prompts.append(messages[0]["content"])
        return {"message": {"content": "the one who argues with me properly, and means it kindly."}}

    async def guard(model_name, priority, coro, task_id):
        return await coro
    from utils.infrastructure.gpu import gpu_manager
    monkeypatch.setattr(gpu_manager.gpu_memory_manager, "run_with_gpu_guard", guard)
    ctx = SimpleNamespace(
        config=SimpleNamespace(chat_model="m"), ollama_client=SimpleNamespace(chat=chat),
        bot_state=SimpleNamespace(relationships={"42": {"display_name": "Ekco"}},
                                  get_relationship_stage=lambda uid: "familiar"))
    assert asyncio.run(ri.refresh_all(ctx)) == 1
    assert "≠ disagreement" in prompts[0] and "Ekco" in prompts[0]
    assert ri.impression_note("42", "Ekco") == \
        "[how you see Ekco: the one who argues with me properly, and means it kindly.]"
    # Nothing new since: not rewritten.
    assert asyncio.run(ri.refresh_all(ctx)) == 0
    assert json.loads((tmp_path / "42.impression.json").read_text())["events_used"] == 1
    assert rm.load_events("42")                    # the impression file is not read as events
