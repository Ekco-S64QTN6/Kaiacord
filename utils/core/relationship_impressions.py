"""How she sees each person, in prose.

What she was given about someone was a list of events: "(!) that's not right,
it was 1999; (+) thanks". This keeps the events — they are the evidence — and
writes a short first-person impression from them each night after the dream
cycle ("the one who argues with me properly"). The chat turn injects the
impression instead of the list. A wrong impression is fixed by regenerating it
from the events, never by editing it.

Stored beside the events as memory/relationships/<id>.impression.json. A
person is rewritten only when an event has been added since, and only people
seen in the last IMPRESSION_ACTIVE_DAYS.
"""
import asyncio
import json
import os
import time
import uuid
from typing import List, Optional

from utils.core import relationship_manager as rm
from utils.core.atomic_write import write_atomic
from utils.infrastructure.logging.kaia_logger import log_info, log_warning

IMPRESSION_ACTIVE_DAYS = 30
MAX_PER_NIGHT = 12
EVENTS_SHOWN = 25


def _path(user_id: str) -> str:
    return rm._user_file(user_id).replace(".json", ".impression.json")


def load(user_id: str) -> Optional[dict]:
    try:
        with open(_path(user_id), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def impression_note(user_id: str, user_name: str) -> str:
    """The prompt line for this person, or "" when none has been written yet."""
    imp = load(str(user_id))
    text = (imp or {}).get("text", "").strip()
    return f"[how you see {user_name}: {text}]" if text else ""


def _event_lines(events: List[rm.RelationshipEvent]) -> str:
    marks = {"positive": "+", "friction": "~", "repair": "!", "milestone": "*",
             "disagreement": "≠", "neutral": "·"}
    return "\n".join(
        f"{time.strftime('%Y-%m-%d', time.localtime(e.timestamp))} "
        f"({marks.get(e.event_type, '·')} {e.event_type}) {e.summary[:160]}"
        for e in events[-EVENTS_SHOWN:])


def build_prompt(name: str, events: List[rm.RelationshipEvent], stage: str) -> str:
    return (
        f"You are Kaia. Below is what has happened between you and {name} "
        f"(relationship stage: {stage}), oldest first. "
        "+ good moments, ~ friction, ! they corrected you, ≠ you disagreed and held, * milestones.\n\n"
        f"{_event_lines(events)}\n\n"
        f"In one or two sentences, lowercase, first person, say how you see {name} — what they're "
        "like with you, what you value or find hard. A characterisation, not a list of events; "
        "don't quote the events or give dates. Only what the events support. "
        "Refer to them as they or by name."
    )


def _needs_refresh(user_id: str, events: List[rm.RelationshipEvent], now: float) -> bool:
    if not events or now - events[-1].timestamp > IMPRESSION_ACTIVE_DAYS * 86400:
        return False
    imp = load(user_id)
    return not imp or imp.get("latest_event", 0) < events[-1].timestamp


async def refresh_all(ctx) -> int:
    """Rewrite the impressions that are out of date. Returns how many were written."""
    from utils.infrastructure.gpu.gpu_manager import GPUTaskPriority, chat_options, gpu_memory_manager
    bot_state, model = ctx.bot_state, ctx.config.chat_model
    now = time.time()
    due = []
    for fname in os.listdir(rm.RELATIONSHIPS_DIR) if os.path.isdir(rm.RELATIONSHIPS_DIR) else []:
        if not fname.endswith(".json") or fname.endswith(".impression.json"):
            continue
        uid = fname[:-5]
        events = await asyncio.to_thread(rm.load_events, uid)
        if _needs_refresh(uid, events, now):
            due.append((events[-1].timestamp, uid, events))
    written = 0
    for _, uid, events in sorted(due, reverse=True)[:MAX_PER_NIGHT]:
        name = (bot_state.relationships.get(uid) or {}).get("display_name") or "them"
        prompt = build_prompt(name, events, bot_state.get_relationship_stage(uid))
        try:
            resp = await gpu_memory_manager.run_with_gpu_guard(
                model_name=model, priority=GPUTaskPriority.BACKGROUND,
                coro=asyncio.wait_for(ctx.ollama_client.chat(
                    model=model, messages=[{"role": "user", "content": prompt}],
                    options=chat_options(temperature=0.4, num_predict=120), keep_alive=-1), timeout=120),
                task_id=f"impression_{uuid.uuid4().hex[:8]}")
            text = " ".join(resp["message"]["content"].split()).strip('"')
        except Exception as e:
            log_warning(f"Relationship impression for {name} failed: {type(e).__name__}: {e}")
            continue
        if len(text) < 20:
            continue
        await asyncio.to_thread(write_atomic, _path(uid), json.dumps({
            "text": text[:400], "written": now, "latest_event": events[-1].timestamp,
            "events_used": min(len(events), EVENTS_SHOWN)}, indent=1, ensure_ascii=False))
        written += 1
        log_info(f"👥 Impression of {name} rewritten: {text[:80]}")
    return written
