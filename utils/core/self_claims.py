"""A self-model that can be wrong (DECISIONS K1).

Ten to twenty things she believes about her own character ("i get terse when
someone pushes me on facts"), each with a confidence and the lines of hers it
rests on. Nightly, a handful are held up against what she actually said that
day: a quote of hers that bears one out raises it, one that goes against it
lowers it, and a claim that falls below RETIRE_BELOW is retired rather than
deleted. Every quote is checked against her real turns before it counts — a
self-model that only ever flatters is the failure this exists to avoid.

Seeded once from two weeks of her turns when the store is empty. Shown to her
only when someone asks what she is like, and in `!memory self`.
"""
import asyncio
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from utils.core.atomic_write import write_atomic
from utils.infrastructure.logging.kaia_logger import log_info, log_warning
from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

STORE = telemetry_path(os.path.join("memory", "self_claims.json"))
LOGS = Path("knowledge_base/user_logs")
SEED_DAYS = 14
TARGET = 12
MAX_CLAIMS = 20
REVIEW_PER_NIGHT = 6
UP, DOWN = 0.05, 0.12
RETIRE_BELOW = 0.25

_KAIA_TURN = re.compile(r"^\[(\d{4}-\d\d-\d\d) [\d:]{8}\] Kaia: (.+)$")
ABOUT_HER = re.compile(
    r"\b(what are you like|are you (?:always|usually|ever)|you (?:always|never|tend to|usually)|"
    r"do you (?:usually|ever|always)|how would you describe yourself|what kind of person)\b", re.I)


def her_turns(days: int, now: Optional[datetime] = None, limit: int = 80) -> List[str]:
    """Her own lines from people's logs over the last `days` days, newest last."""
    now = now or datetime.now()
    wanted = {(now - timedelta(days=d)).strftime("%Y%m%d") for d in range(days)}
    lines = []
    if not LOGS.is_dir():
        return lines
    for folder in LOGS.iterdir():
        if not folder.is_dir() or folder.name.startswith(("forum_", "Kaia-", ".", "_")):
            continue
        for day in wanted:
            f = folder / f"interactions_{day}.md"
            if not f.exists():
                continue
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                m = _KAIA_TURN.match(line.strip())
                if m and len(m.group(2)) > 30:
                    lines.append((m.group(1), m.group(2)[:400]))
    lines.sort()
    return [text for _, text in lines[-limit:]]


def load() -> List[dict]:
    try:
        with open(STORE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save(claims: List[dict]) -> None:
    write_atomic(STORE, json.dumps(claims, indent=1, ensure_ascii=False))


def _verified(quotes, turns: List[str]) -> List[str]:
    """Quotes that really are words of hers from `turns`."""
    joined = "\n".join(" ".join(t.lower().split()) for t in turns)
    out = []
    for q in quotes or []:
        q = " ".join(str(q).split()).strip(' "')
        if len(q) >= 12 and q.lower() in joined:
            out.append(q[:200])
    return out


def seed_prompt(turns: List[str]) -> str:
    sample = "\n".join(f"- {t}" for t in turns)
    return (
        "These are things you, Kaia, said in conversations over the last two weeks:\n\n"
        f"{sample}\n\n"
        f"Name {TARGET} things these show about how you actually behave — habits, tendencies, "
        "weaknesses as well as strengths. Each must be something a quote here demonstrates. "
        "Write each claim in first person, lowercase, one short sentence.\n"
        'Reply with JSON only: {"claims": [{"claim": "...", "quote": "exact words copied from one line above"}]}'
    )


def review_prompt(claims: List[dict], turns: List[str]) -> str:
    listed = "\n".join(f"{i}. {c['claim']}" for i, c in enumerate(claims))
    sample = "\n".join(f"- {t}" for t in turns)
    return (
        f"Things you, Kaia, believe about yourself:\n{listed}\n\n"
        f"What you actually said today:\n{sample}\n\n"
        "For each belief, find lines that bear it out and lines that go against it. Be as ready "
        "to find it wrong as right; if today says nothing about it, give neither.\n"
        'Reply with JSON only: {"results": [{"i": 0, "supports": ["exact words"], '
        '"contradicts": ["exact words"]}]}'
    )


def apply_seed(reply: dict, turns: List[str], now: float) -> List[dict]:
    claims = []
    for item in (reply or {}).get("claims", [])[:TARGET]:
        text = " ".join(str(item.get("claim", "")).split()).lower()[:160]
        quotes = _verified([item.get("quote")], turns)
        if len(text) >= 12 and quotes:
            claims.append({"claim": text, "confidence": 0.6, "created": now, "last_checked": now,
                           "evidence": [{"ts": now, "for": True, "quote": quotes[0]}]})
    return claims


def apply_review(claims: List[dict], chosen: List[int], reply: dict, turns: List[str], now: float) -> List[dict]:
    """Move confidence by verified quotes. Returns growth events for claims that fell."""
    events = []
    results = {r.get("i"): r for r in (reply or {}).get("results", []) if isinstance(r, dict)}
    for pos, idx in enumerate(chosen):
        c = claims[idx]
        c["last_checked"] = now
        r = results.get(pos) or {}
        up, down = _verified(r.get("supports"), turns), _verified(r.get("contradicts"), turns)
        before = c["confidence"]
        c["confidence"] = round(min(0.95, max(0.0, before + UP * min(len(up), 2) - DOWN * min(len(down), 2))), 3)
        c["evidence"] = (c.get("evidence", []) + [{"ts": now, "for": True, "quote": q} for q in up[:1]]
                         + [{"ts": now, "for": False, "quote": q} for q in down[:1]])[-8:]
        if c["confidence"] < RETIRE_BELOW:
            c["retired"] = now
        if c["confidence"] < before:
            events.append({"type": "self_claim_weakened", "claim": c["claim"], "was": before,
                           "confidence": c["confidence"], "against": down[0] if down else ""})
    return events


def note(own_words: str) -> str:
    """Her self-model, with confidences, when someone asks what she is like."""
    if not ABOUT_HER.search(own_words or ""):
        return ""
    live = sorted((c for c in load() if not c.get("retired")), key=lambda c: -c["confidence"])[:6]
    if not live:
        return ""
    return ("[what you believe about yourself, and how sure you are — you may be wrong: "
            + "; ".join(f"{c['claim']} ({c['confidence']:.1f})" for c in live) + "]")


async def nightly(ctx, log_growth=None) -> int:
    """Seed when empty, else review the least recently checked claims. Returns claims touched."""
    from utils.infrastructure.gpu.gpu_manager import GPUTaskPriority, chat_options, gpu_memory_manager
    now = time.time()
    claims = await asyncio.to_thread(load)
    live = [i for i, c in enumerate(claims) if not c.get("retired")]
    seeding = len(live) < TARGET // 2
    turns = await asyncio.to_thread(her_turns, SEED_DAYS if seeding else 1)
    if len(turns) < (20 if seeding else 5):
        return 0
    if seeding:
        prompt, chosen = seed_prompt(turns), []
    else:
        chosen = sorted(live, key=lambda i: claims[i].get("last_checked", 0))[:REVIEW_PER_NIGHT]
        prompt = review_prompt([claims[i] for i in chosen], turns)
    model = ctx.config.chat_model
    try:
        resp = await gpu_memory_manager.run_with_gpu_guard(
            model_name=model, priority=GPUTaskPriority.BACKGROUND,
            coro=asyncio.wait_for(ctx.ollama_client.chat(
                model=model, messages=[{"role": "user", "content": prompt}],
                options=chat_options(temperature=0.3, num_predict=900), format="json",
                keep_alive=-1), timeout=240),
            task_id=f"self_claims_{uuid.uuid4().hex[:8]}")
        reply = json.loads(resp["message"]["content"])
    except Exception as e:
        log_warning(f"Self-model review failed: {type(e).__name__}: {e}")
        return 0
    if seeding:
        new = apply_seed(reply, turns, now)
        claims = (claims + new)[-MAX_CLAIMS:]
        touched = len(new)
        log_info(f"🪞 Self-model seeded with {touched} claims")
    else:
        events = apply_review(claims, chosen, reply, turns, now)
        touched = len(chosen)
        for e in events:
            log_info(f"🪞 Self-claim weakened: '{e['claim'][:60]}' {e['was']} → {e['confidence']}")
            if log_growth:
                log_growth(e)
    await asyncio.to_thread(save, claims)
    return touched
