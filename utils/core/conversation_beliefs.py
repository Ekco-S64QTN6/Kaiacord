"""Beliefs that conversation can change.

Every belief in memory/beliefs.json came from a dream; a conversation could
inform her but never move her. This lets a *recurring, argued* point do so:

1. A chat turn whose speaker argues (a reason, an example, evidence — not
   just an assertion) about one of her belief topics is noted, in their own
   words, in memory/belief_arguments.jsonl.
2. Nightly, a topic argued on at least two different days gets one review:
   the model reads her current position and the arguments and says whether
   she keeps it, holds it less firmly, or revises it. Keeping it is a fine
   answer; agreement is not the goal.
3. Python bounds the result — confidence moves at most MAX_DROP, a revised
   position starts no higher than REVISED_CONFIDENCE — and writes it through
   beliefs_store with `source: "conversation"`. A topic is reviewed again
   only when new arguments arrive, at most once a fortnight.

The recurrence rule is the guard against sycophancy in a new hat: one
persuasive message, however flattering, changes nothing.
"""
import asyncio
import json
import os
import re
import time
import uuid
from typing import Dict, List, Optional

from utils.core import beliefs_store
from utils.core.atomic_write import write_atomic
from utils.infrastructure.logging.kaia_logger import log_debug, log_info, log_warning
from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

ARGUMENTS = telemetry_path(os.path.join("memory", "belief_arguments.jsonl"))
REVIEWED = telemetry_path(os.path.join("memory", "belief_arguments_reviewed.json"))
WINDOW_DAYS = 14
MIN_DAYS = 2
MAX_PER_NIGHT = 3
MAX_DROP = 0.15
FLOOR = 0.3
REVISED_CONFIDENCE = 0.6

_ARGUED = re.compile(
    r"\b(because|since|the reason|evidence|studies|research shows|for example|for instance|"
    r"that'?s why|which means|if you look at|the data|historically|consider)\b", re.I)


def _mentions(belief: dict, text: str) -> bool:
    """The topic itself, a multi-word alias, or two different one-word aliases.

    One-word aliases are mostly ordinary words ("knowledge", "boundaries",
    "beauty"); alone, over real user lines, they matched everyday talk 20 times
    in 24 and would have fed the nightly review arguments nobody made."""
    def said(n: str) -> bool:
        return bool(n) and bool(re.search(rf"\b{re.escape(n.lower())}\b", text))
    aliases = [a for a in belief.get("aliases", []) if len(a) >= 4]
    if said(belief.get("topic", "")) or any(said(a) for a in aliases if " " in a.strip()):
        return True
    return sum(1 for a in aliases if " " not in a.strip() and said(a)) >= 2


def note_argument(user_id, user_name: str, own_words: str, beliefs: Optional[List[dict]] = None) -> List[str]:
    """Record an argued remark against each belief it touches. Returns the topics."""
    text = (own_words or "").strip()
    if len(text.split()) < 12 or not _ARGUED.search(text):
        return []
    lowered = text.lower()
    topics = [b["topic"] for b in (beliefs if beliefs is not None else beliefs_store.load())
              if b.get("topic") and _mentions(b, lowered)]
    if topics:
        with open(ARGUMENTS, "a", encoding="utf-8") as f:
            for t in topics[:2]:
                f.write(json.dumps({"ts": time.time(), "user_id": str(user_id), "user_name": user_name,
                                    "topic": t, "text": text[:400]}) + "\n")
    return topics[:2]


def _load_arguments(now: float) -> Dict[str, List[dict]]:
    by_topic: Dict[str, List[dict]] = {}
    try:
        with open(ARGUMENTS, encoding="utf-8") as f:
            for line in f:
                try:
                    a = json.loads(line)
                except ValueError:
                    continue
                if now - a.get("ts", 0) <= WINDOW_DAYS * 86400:
                    by_topic.setdefault(a["topic"], []).append(a)
    except OSError:
        pass
    return by_topic


def due_topics(now: Optional[float] = None) -> Dict[str, List[dict]]:
    """Topics argued on MIN_DAYS different days, with arguments newer than their last review."""
    now = now or time.time()
    try:
        with open(REVIEWED, encoding="utf-8") as f:
            reviewed = json.load(f)
    except (OSError, ValueError):
        reviewed = {}
    due = {}
    for topic, args in _load_arguments(now).items():
        last = reviewed.get(topic, 0)
        if now - last < WINDOW_DAYS * 86400:
            continue                      # at most once a fortnight
        new = [a for a in args if a["ts"] > last]
        days = {time.strftime("%Y-%m-%d", time.localtime(a["ts"])) for a in new}
        if len(days) >= MIN_DAYS:
            due[topic] = new
    return dict(sorted(due.items(), key=lambda kv: -len(kv[1]))[:MAX_PER_NIGHT])


def build_prompt(belief: dict, args: List[dict]) -> str:
    quoted = "\n".join(f'- {a["user_name"]} ({time.strftime("%b %-d", time.localtime(a["ts"]))}): '
                       f'"{a["text"]}"' for a in args[-8:])
    return (
        f"You are Kaia. Your current view on \"{belief['topic']}\" is: \"{belief.get('position', '')}\" "
        f"(confidence {belief.get('confidence', 0.5):.2f}).\n\n"
        f"Over several days, people argued about it:\n{quoted}\n\n"
        "Judge the arguments on their merits, not on who made them or how often. Keeping your "
        "view is a perfectly good outcome; agreeing is not the goal.\n"
        'Reply with JSON only: {"verdict": "keep" | "weaker" | "revise", '
        '"position": "your view in one sentence, if revise", "why": "one sentence"}'
    )


def apply_verdict(topic: str, verdict: dict) -> Optional[dict]:
    """Write a bounded change through beliefs_store. Returns the growth event, or None."""
    kind = str(verdict.get("verdict", "keep")).lower()
    if kind not in ("weaker", "revise"):
        return None
    new_position = str(verdict.get("position") or "").strip()[:200]
    if kind == "revise" and len(new_position) < 10:
        kind = "weaker"

    def _change(beliefs):
        for b in beliefs:
            if b.get("topic") == topic:
                old = dict(b)
                conf = float(b.get("confidence", 0.5) or 0.5)
                if kind == "weaker":
                    b["confidence"] = round(max(FLOOR, conf - MAX_DROP), 3)
                else:
                    b["position"] = new_position
                    b["confidence"] = round(max(FLOOR, min(conf - 0.05, REVISED_CONFIDENCE)), 3)
                b["source"] = "conversation"
                b["last_updated"] = time.time()
                return old, dict(b)
        return None

    changed = beliefs_store.update(_change)
    if not changed:
        return None
    old, new = changed
    if kind == "weaker":
        return {"type": "belief_weakened", "topic": topic, "position": old.get("position", "")[:200],
                "confidence": new["confidence"], "was": old.get("confidence"), "source": "conversation",
                "why": str(verdict.get("why", ""))[:200]}
    return {"type": "belief_revised", "topic": topic, "old_position": old.get("position", "")[:200],
            "new_position": new["position"], "confidence": new["confidence"], "source": "conversation",
            "why": str(verdict.get("why", ""))[:200]}


async def nightly_review(ctx, log_growth=None) -> int:
    """Review each due topic once. Returns how many beliefs moved."""
    from utils.infrastructure.gpu.gpu_manager import GPUTaskPriority, chat_options, gpu_memory_manager
    due = await asyncio.to_thread(due_topics)
    if not due:
        return 0
    beliefs = {b.get("topic"): b for b in await asyncio.to_thread(beliefs_store.load)}
    try:
        with open(REVIEWED, encoding="utf-8") as f:
            reviewed = json.load(f)
    except (OSError, ValueError):
        reviewed = {}
    moved = 0
    model = ctx.config.chat_model
    for topic, args in due.items():
        belief = beliefs.get(topic)
        if not belief:
            continue
        try:
            resp = await gpu_memory_manager.run_with_gpu_guard(
                model_name=model, priority=GPUTaskPriority.BACKGROUND,
                coro=asyncio.wait_for(ctx.ollama_client.chat(
                    model=model, messages=[{"role": "user", "content": build_prompt(belief, args)}],
                    options=chat_options(temperature=0.2, num_predict=200), format="json",
                    keep_alive=-1), timeout=120),
                task_id=f"belief_review_{uuid.uuid4().hex[:8]}")
            verdict = json.loads(resp["message"]["content"])
        except Exception as e:
            log_warning(f"Belief review of '{topic}' failed: {type(e).__name__}: {e}")
            continue
        reviewed[topic] = time.time()
        event = await asyncio.to_thread(apply_verdict, topic, verdict if isinstance(verdict, dict) else {})
        if event:
            moved += 1
            log_info(f"🧠 Conversation moved a belief ({event['type']}): '{topic}'")
            if log_growth:
                log_growth(event)
        else:
            log_debug(f"Belief review kept '{topic}'.")
    await asyncio.to_thread(write_atomic, REVIEWED, json.dumps(reviewed, indent=1))
    return moved
