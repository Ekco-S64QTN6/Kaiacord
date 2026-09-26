"""What she keeps coming back to without having settled it.

An open thread is an idea she has wondered about on more than one day — in a
passing thought or at the end of a dream — or a belief someone is arguing
with her about. It survives restarts because its sources do
(`memory/monologue_log.jsonl`, `kaia_dreams/`, `memory/belief_arguments.jsonl`).

Two rules keep it from failing the way the spec warns:

- Wonderings about *people* are left out. Most of her monologue is "i wonder
  if starkind is subtly…"; feeding that back in would teach her to read
  motives into everyone, which is the fault that produced "a user named l".
- It is never an obligation. "I still owe you an answer on X" is the failed
  version; the prompt line says what she has been turning over and that it
  may colour what catches her interest, nothing more.

Pure Python; recomputed at most hourly.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

WINDOW_S = 14 * 86400
MAX_THREADS = 5
MIN_DAYS = 2
MIN_SHARED = 2
CACHE_S = 3600
KB = Path("knowledge_base")

_STOP = set("""a an the and or but if then so of to in on at by for with from as is are was were be been
being it its it's this that these those i me my mine you your we our they their them he she his her
what which who whom why how when where whether wonder wondering maybe perhaps really just about into
more most some any all not no nor too very can could would should will might must do does did done have
has had having there here than also still even ever only own same such each other one two something
anything nothing everything someone thing things way ways kind sort seem seems seemed feel feels felt
like being much many because while after before again once else entirely trying subtly subtle deeper
actually almost quite keep isn't it's can't don't didn't doesn't what's that's they're there's i'm i've
signal simply genuinely sort probably possibly rather somehow somewhere perhaps whole part""".split())
_WORD = re.compile(r"[a-z][a-z'’-]{3,}")
# "the data breaches are a constant, aren't they?" is a reaction, not a question.
_TAG = re.compile(r",\s*(?:is|are|was|were|do|does|did|has|have|can|could|would|will)n['’]?t\s+(?:it|they|there|that|he|she|we|you)\s*\?$", re.I)
_cache: tuple[float, Optional[list]] = (0.0, None)


def _content(text: str) -> set[str]:
    words = {w.strip("'-") for w in _WORD.findall(text.lower().replace("’", "'"))}
    return {w for w in words if w not in _STOP and w.removesuffix("'s") not in _STOP}


def _people() -> set[str]:
    names = set()
    try:
        for d in (KB / "user_logs").iterdir():
            if d.is_dir() and "_" in d.name and not d.name.startswith(("social_", "forum_", "Kaia", ".")):
                base = d.name.rsplit("_", 1)[0]
                names |= {base.lower(), base.lower().replace("_", " ")}
                names |= {p.lower() for p in base.split("_") if len(p) > 2}
    except OSError:
        pass
    # The names people go by, which the log folder may not carry: GuardNGnowm
    # logs under GnowmaticFlux.
    try:
        state = json.loads(Path(telemetry_path("memory/bot_state.json")).read_text(encoding="utf-8"))
        for rel in (state.get("relationships") or {}).values():
            n = (rel.get("display_name") or "").strip().lower()
            if len(n) > 2:
                names.add(n)
        for turns in (state.get("channel_memory") or {}).values():
            for t in turns:
                c = t.get("content") or ""
                if t.get("role") == "user" and ": " in c:
                    n = c.split(": ", 1)[0].strip().lower()
                    if 2 < len(n) < 40:
                        names.add(n)
    except (OSError, ValueError, AttributeError):
        pass
    return names


def _names_someone(text: str, people: set[str]) -> bool:
    low = text.lower()
    return any(re.search(r"\b" + re.escape(n) + r"(?:'s|’s)?\b", low) for n in people)


def _wonderings(now: float, people: set[str]) -> list[tuple[float, str]]:
    out = []
    try:
        with open(telemetry_path("memory/monologue_log.jsonl"), encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                t, when = e.get("thought") or "", float(e.get("epoch") or 0)
                if now - when <= WINDOW_S and "wonder" in t.lower() and not _names_someone(t, people):
                    out.append((when, t.strip()))
    except OSError:
        pass
    for f in (KB / "kaia_dreams").glob("*/dream_*.md"):
        try:
            when = f.stat().st_mtime
            if now - when > WINDOW_S:
                continue
            body = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "## Kaia's Reflection" not in body:
            continue
        refl = " ".join(body.split("## Kaia's Reflection", 1)[1].split())
        for s in re.split(r"(?<=[.!?])\s+", refl):
            s = s.strip()
            if 30 <= len(s) <= 240 and (s.endswith("?") or s.lower().startswith("i wonder")) \
                    and not _TAG.search(s) and not _names_someone(s, people):
                out.append((when, s))
    return out


def _argued(now: float) -> list[dict]:
    try:
        lines = open(telemetry_path("memory/belief_arguments.jsonl"), encoding="utf-8").read().splitlines()
    except OSError:
        return []
    topics: dict[str, set[str]] = {}
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if now - float(e.get("ts") or 0) <= WINDOW_S and e.get("topic"):
            topics.setdefault(e["topic"], set()).add(time.strftime("%Y-%m-%d", time.localtime(e["ts"])))
    return [{"kind": "argument", "text": f"what you think about {t}, which someone has been arguing with you",
             "words": _content(t), "days": len(d)} for t, d in topics.items()]


def threads(now: Optional[float] = None) -> list[dict]:
    """[{kind, text, words, days}], strongest first."""
    global _cache
    now = now or time.time()
    stamp, value = _cache
    if value is not None and now - stamp < CACHE_S:
        return value
    items = [(when, text, _content(text)) for when, text in _wonderings(now, _people())]
    items = [i for i in items if len(i[2]) >= MIN_SHARED]
    found, used = [], set()
    for i, (when, text, words) in enumerate(items):
        if i in used:
            continue
        group = [j for j, (_, _, w) in enumerate(items) if j != i and len(words & w) >= MIN_SHARED]
        days = {time.strftime("%Y-%m-%d", time.localtime(items[j][0])) for j in group + [i]}
        if len(days) >= MIN_DAYS:
            used |= set(group) | {i}
            latest = max(group + [i], key=lambda j: items[j][0])
            found.append({"kind": "wondering", "text": items[latest][1], "words": words, "days": len(days)})
    found += [a for a in _argued(now) if a["days"] >= 1]
    value = sorted(found, key=lambda t: -t["days"])[:MAX_THREADS]
    _cache = (now, value)
    return value


def note_for(own_words: str) -> str:
    """A line for a chat turn that touches one of her open threads, or ''."""
    words = _content(own_words or "")
    if len(words) < 2:
        return ""
    for t in threads():
        if len(words & t["words"]) >= MIN_SHARED:
            return (f"[STILL OPEN FOR YOU: something you've kept turning over on {t['days']} different days — "
                    f"\"{t['text']}\". It can shape what catches your interest here. It is not an answer "
                    f"you owe anyone; don't announce it.]")
    return ""


def for_monologue() -> str:
    """One thread for a passing thought to return to, or ''."""
    ts = threads()
    if not ts:
        return ""
    t = ts[int(time.time() // 900) % len(ts)]
    return f"Something you keep coming back to, unsettled: \"{t['text']}\""
