"""Her own past shifts, recalled when a conversation touches them.

`memory/growth_log.jsonl` records how she changed: `identity_shift` entries
("i'm finding myself less inclined to…") and `belief_revised` ones. The chat
turn reads them here, so she can say "i'd have argued the opposite in June" —
with the date, because the date is what makes it a memory and not a pose.

Matching is on distinctive words: ones that appear in few shifts. Nearly every
shift says "systems", "noticing", "finding", so those match everything and are
ignored. A shift is offered only when the speaker's own words share at least
two distinctive words with it, and at most once per channel per cooldown, so
she does not narrate her development at every turn.
"""
import json
import math
import os
import re
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

GROWTH_LOG = os.path.join("memory", "growth_log.jsonl")
MIN_SHARED = 2
COOLDOWN_SECONDS = 6 * 3600
#: A word in more than this share of shifts is too common to identify one.
MAX_DOC_SHARE = 0.10

_WORD = re.compile(r"[a-z][a-z'’-]{4,}")
_STOP = frozenset("""
about after again being because before being could doesn't don't every first found going
isn't it's just kind know later least lately little maybe might more most much never other
really rather right should since something still their there these thing things think those
though through today under until using wasn't where which while would years yeah your
""".split())

_lock = threading.Lock()
_cache: Dict[str, object] = {"mtime": None, "shifts": [], "revisions": [], "df": {}}
_last_offered: Dict[object, float] = {}


def _words(text: str) -> set:
    return {w.strip("'’-") for w in _WORD.findall(text.lower())} - _STOP


def _load() -> None:
    """(Re)read the log when it has changed since the last read."""
    try:
        mtime = os.path.getmtime(GROWTH_LOG)
    except OSError:
        return
    if mtime == _cache["mtime"]:
        return
    shifts, revisions = [], []
    with open(GROWTH_LOG, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                evt = json.loads(line)
            except ValueError:
                continue
            kind = evt.get("type")
            if kind == "identity_shift" and evt.get("content"):
                shifts.append({"text": evt["content"], "ts": _ts(evt), "words": _words(evt["content"])})
            elif kind == "belief_revised" and evt.get("topic"):
                revisions.append(evt)
    df: Dict[str, int] = {}
    for s in shifts:
        for w in s["words"]:
            df[w] = df.get(w, 0) + 1
    _cache.update(mtime=mtime, shifts=shifts, revisions=revisions, df=df)


def _ts(evt: dict) -> float:
    try:
        return float(evt.get("ts") or evt.get("timestamp") or 0)
    except (TypeError, ValueError):
        return 0.0


def _when(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%B %-d") if ts else "a while back"


def identity_shift_for(own_words: str, channel_id=None, now: Optional[float] = None) -> str:
    """The prompt note for the newest shift this turn touches, or ""."""
    now = now or time.time()
    with _lock:
        if now - _last_offered.get(channel_id, 0) < COOLDOWN_SECONDS:
            return ""
        _load()
        shifts: List[dict] = _cache["shifts"]
        if not shifts:
            return ""
        limit = max(2, math.ceil(len(shifts) * MAX_DOC_SHARE))
        said = {w for w in _words(own_words) if _cache["df"].get(w, 0) <= limit}
        for shift in reversed(shifts):
            if len(said & shift["words"]) >= MIN_SHARED:
                _last_offered[channel_id] = now
                text = shift["text"][:220]
                return (f"[this touches something you noticed changing in yourself on "
                        f"{_when(shift['ts'])}: \"{text}\". if it fits, you may say how you "
                        f"used to see it and when that changed. don't bring it up otherwise.]")
    return ""


def belief_revision_for(matching: List[str]) -> str:
    """The prompt note for a revised belief among the ones this turn matched, or ""."""
    if not matching:
        return ""
    with _lock:
        _load()
        revisions = list(_cache["revisions"])
    lowered = [m.lower() for m in matching]
    for evt in reversed(revisions):
        topic = evt.get("topic", "")
        if topic and any(re.search(rf"\b{re.escape(topic.lower())}\b", m) for m in lowered):
            return (f"[your stance on \"{topic}\" has evolved since {_when(_ts(evt))}. "
                    f"you previously thought: \"{evt.get('old_position', '')[:80]}\". "
                    f"if natural, you may reference this shift.]")
    return ""
