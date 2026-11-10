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
import re
import time
import uuid
from typing import List, Optional

from utils.core import relationship_manager as rm
from utils.core.atomic_write import write_atomic
from utils.infrastructure.logging.kaia_logger import log_info, log_warning

IMPRESSION_ACTIVE_DAYS = 30
MAX_PER_NIGHT = 12
EVENTS_SHOWN = 25
#: Bumped when the prompt changes, so every impression is rewritten under it.
PROMPT_VERSION = 4
# "Okay, here's my characterization of Lune, as Kaia, based on…" is the model
# talking about the task, not an impression.
_PREAMBLE = re.compile(r"^\W*(?:okay|ok|sure|certainly|here(?:'|’)?s|here is|as kaia)\b|characteri[sz]ation|"
                       r"based on the (?:provided|events|interactions)", re.I)


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
    if _PREAMBLE.search(text):
        return ""                     # written before the check; rewritten next night
    return f"[how you see {user_name}: {text}]" if text else ""


def _event_lines(events: List[rm.RelationshipEvent]) -> str:
    marks = {"positive": "+", "friction": "~", "repair": "!", "milestone": "*",
             "disagreement": "≠", "insight": "?", "neutral": "·"}
    return "\n".join(
        f"{time.strftime('%Y-%m-%d', time.localtime(e.timestamp))} "
        f"({marks.get(e.event_type, '·')} {e.event_type}) {e.summary[:160]}"
        for e in events[-EVENTS_SHOWN:])


def build_prompt(name: str, events: List[rm.RelationshipEvent], stage: str) -> str:
    """The impression is written with her persona as the system prompt (`_messages`),
    so it is in her voice rather than the model's, and asks what the two of them do
    rather than what she values in them: that invited grading the person, and the
    line is shown on every turn with them."""
    from utils.core import pronouns
    return (
        f"Below is what has happened between you and {name} "
        f"(relationship stage: {stage}), oldest first. "
        "+ good moments, ~ friction, ! they corrected you, ≠ you disagreed and held, "
        "? something you realised about them in a dream, * milestones.\n\n"
        f"{_event_lines(events)}\n\n"
        f"In one or two sentences, lowercase, first person, say how {name} is with you, the way you'd "
        "mention them to a friend: what the two of you actually talk about or do, and how it tends to go. "
        "Mention something you find hard only if the events show friction (~) or corrections (!). "
        "Don't quote the events or give dates. Only what the events support. "
        f"{pronouns.line([name])} Reply with the impression only."
    )


def _messages(prompt: str) -> list:
    from utils.social.kaia_social_responder import load_persona
    return [{"role": "system", "content": load_persona()}, {"role": "user", "content": prompt}]


def register_hits(text: str) -> int:
    """How much of the register her persona bans an impression carries."""
    from utils.core.persona_register import _ANALYTIC, PERSONA_REJECT
    hits = len(_ANALYTIC.findall(text or ""))
    return hits + sum(bool(PERSONA_REJECT[k].search(text or "")) for k in
                      ("sycophancy", "grades_the_user", "essay_register", "robotic_vocabulary", "phantom_hardware"))


_IMAGE = re.compile(r"\b(?:is|are|'s|’s)\s+(?:an?|such\s+an?)\s+(?:[a-z\-]+ly\s+)?([a-z\-]+)")
#: Words of a stock description, not of a person: five of eight impressions on 2 Nov
#: opened "<name> is a whirlwind", written minutes apart with no sight of each other.
_NOT_AN_IMAGE = frozenset(("person", "bit", "lot", "little", "kind", "sort", "good", "great", "real", "friend"))


def stock_image(text: str, others) -> str:
    """The word `text` calls someone that another impression already calls someone
    else, or ""."""
    def image(t):
        m = _IMAGE.search((t or "").lower())
        return m.group(1) if m and m.group(1) not in _NOT_AN_IMAGE else ""
    word = image(text)
    return word if word and any(image(o) == word for o in others) else ""


def _needs_refresh(user_id: str, events: List[rm.RelationshipEvent], now: float) -> bool:
    if not events or now - events[-1].timestamp > IMPRESSION_ACTIVE_DAYS * 86400:
        return False
    imp = load(user_id)
    return not imp or imp.get("latest_event", 0) < events[-1].timestamp or imp.get("v") != PROMPT_VERSION


async def refresh_all(ctx) -> int:
    """Rewrite the impressions that are out of date. Returns how many were written."""
    from utils.infrastructure.gpu.gpu_manager import GPUTaskPriority, chat_options, gpu_memory_manager, voice_sampling
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
    taken = [(load(f[:-len(".impression.json")]) or {}).get("text", "") for f in os.listdir(rm.RELATIONSHIPS_DIR)
             if f.endswith(".impression.json")] if os.path.isdir(rm.RELATIONSHIPS_DIR) else []

    async def _write(prompt):
        resp = await gpu_memory_manager.run_with_gpu_guard(
            model_name=model, priority=GPUTaskPriority.BACKGROUND,
            coro=asyncio.wait_for(ctx.ollama_client.chat(
                model=model, messages=_messages(prompt),
                options=chat_options(temperature=0.4, num_predict=120, **voice_sampling()), keep_alive=-1), timeout=120),
            task_id=f"impression_{uuid.uuid4().hex[:8]}")
        text = " ".join(resp["message"]["content"].split()).strip('"')
        return text[:1].lower() + text[1:]

    for _, uid, events in sorted(due, reverse=True)[:MAX_PER_NIGHT]:
        name = (bot_state.relationships.get(uid) or {}).get("display_name") or "them"
        prompt = build_prompt(name, events, bot_state.get_relationship_stage(uid))
        own = (load(uid) or {}).get("text", "")
        others = [t for t in taken if t and t != own]
        try:
            text = await _write(prompt)
            if register_hits(text) >= 2:
                # Written once more; the one in her voice is kept.
                again = await _write(prompt)
                if again and register_hits(again) < register_hits(text):
                    text = again
            worn = stock_image(text, others)
            if worn:
                retry = await _write(prompt + f" You have called someone else \"{worn}\": say what is particular to {name} instead.")
                if retry and not stock_image(retry, others):
                    text = retry
        except Exception as e:
            log_warning(f"Relationship impression for {name} failed: {type(e).__name__}: {e}")
            continue
        if len(text) < 20 or _PREAMBLE.search(text):
            log_warning(f"Relationship impression for {name} discarded: {text[:80]}")
            continue
        await asyncio.to_thread(write_atomic, _path(uid), json.dumps({
            "text": text[:400], "written": now, "latest_event": events[-1].timestamp, "v": PROMPT_VERSION,
            "events_used": min(len(events), EVENTS_SHOWN)}, indent=1, ensure_ascii=False))
        written += 1
        taken = [t for t in taken if t != own] + [text]
        log_info(f"👥 Impression of {name} rewritten: {text[:80]}")
    return written
