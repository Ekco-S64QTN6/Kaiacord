"""What is worth a look in the scanner's ledger, and why.

A night is hundreds of catches, most of them the same telemetry. This ranks
what the ledger holds by what makes a catch worth playing — words, a channel
heard for the first time, a rarely active one, someone talking at an hour that
channel is usually silent, words that sound like an emergency — and says which
of those it was. Channels are sorted into what they do, from their record:
people talk on it, it sends data, it keys up on a timer, or it carries bare
carriers. Nothing here hides anything; it orders and labels.
"""
from __future__ import annotations

import json
import re
import time
from typing import Optional

from utils.radio import ledger

#: Words that make a transcript worth hearing first.
URGENT = re.compile(r"\b(mayday|emergency|help|injur\w*|unconscious|not breathing|cpr|shots?|gun\w*|fire|smoke|"
                    r"crash|collision|accident|rollover|pursuit|tornado|flood\w*|evacuat\w*|missing|"
                    r"structure fire|medic|ambulance|trauma|overdose)\b", re.I)
NEW_S = 48 * 3600                 # a channel first heard this recently is new
RARE_HITS = 5


def score(e: dict) -> tuple[float, list[str]]:
    """(score, reasons) for one event row from `ledger.events_since`."""
    kind = e.get("kind")
    if kind in ("noise", "seen"):
        return 0.0, []
    s, why = 0.0, []
    tr = (e.get("transcript") or "").strip()
    if kind == "voice":
        s += 5
        why.append("voice")
        words = len(tr.split())
        if words >= 12:
            s += 2
            why.append(f"{words} words")
        if URGENT.search(tr):
            s += 4
            why.append("urgent words: " + URGENT.search(tr).group(0).lower())
    elif e.get("clip"):
        s += 1.5
        why.append("kept: sounded like speech")
    else:
        return 0.0, []                          # a bare carrier or a data burst: new ones are in new_channels()
    first = e.get("first_seen")
    if first and e["ts"] - first <= NEW_S:
        s += 3
        why.append(f"new channel, first heard {_ago(e['ts'] - first, 'before')}" if e["ts"] - first > 60
                   else "first time heard")
    hits = e.get("ch_hits") or 0
    if 0 < hits <= RARE_HITS:
        s += 2
        why.append(f"rarely active ({hits}×)")
    try:
        hours = json.loads(e.get("hours") or "[]")
    except ValueError:
        hours = []
    if hours and sum(hours) >= 20 and kind == "voice":
        h = time.localtime(e["ts"]).tm_hour
        if hours[h] <= 1:
            s += 1.5
            why.append(f"unusual hour ({h:02d}h)")
    if (e.get("seconds") or 0) >= 30 and kind == "voice":
        s += 1
        why.append(f"{round(e['seconds'])} s")
    return s, sorted(why, key=_telling)


_ORDER = ("urgent", "first time", "new channel", "rarely", "unusual hour", "kept", "words", " s", "voice")


def _telling(reason: str) -> int:
    """Reasons most worth saying first: an urgent word before a word count."""
    return next((i for i, k in enumerate(_ORDER) if k in reason), len(_ORDER))


def _ago(sec: float, word: str = "ago") -> str:
    if sec < 3600:
        return f"{round(sec / 60)} min {word}"
    if sec < 172800:
        return f"{sec / 3600:.0f} h {word}"
    return f"{sec / 86400:.0f} days {word}"


def highlights(hours: float = 48.0, limit: int = 30) -> list[dict]:
    """The best of the last `hours`, best first, with the reasons."""
    out = []
    for e in ledger.events_since(time.time() - hours * 3600):
        s, why = score(e)
        if s >= 3:
            out.append({"id": e["id"], "ts": e["ts"], "freq": e["freq_hz"], "kind": e["kind"],
                        "seconds": e.get("seconds"), "clip": e.get("clip"), "transcript": e.get("transcript") or "",
                        "label": e.get("label") or e.get("service") or "", "score": round(s, 1), "why": why,
                        "peak_db": e.get("peak_db")})
    out.sort(key=lambda r: (-r["score"], -r["ts"]))
    return out[:limit]


def classify_channel(ch: dict, habits: dict, period: Optional[tuple] = None) -> tuple[str, str]:
    """(class, description) of a ledger channel: 'talk', 'timer', 'data',
    'carrier' or 'quiet' (listed, not heard)."""
    if ch.get("voice"):
        return "talk", f"voice {ch['voice']}× of {ch['hits']}"
    if not ch.get("hits"):
        return "quiet", "listed, not heard yet"
    if period and period[0] and period[1] >= 0.5:
        return "timer", f"keys up every {period[0]:.0f} s"
    held = any(abs(f - ch["freq_hz"]) <= 3000 for f in habits)
    said = ch.get("last_transcript") or ""
    if said.startswith("[") and "]" in said:
        return "data", f"{said[1:said.index(']')]} decoded · data {ch.get('data', 0)}×"
    if ch.get("data") or held:
        return "data", ("habitual: noted, held only when it runs long" if held else f"data {ch.get('data', 0)}×")
    return "carrier", f"{ch['hits']} carriers, no voice"


def channels(habits: dict, with_periods: int = 40) -> list[dict]:
    """Every heard or listed channel with its class; periods are worked out
    for the `with_periods` busiest (the rest are too sparse to show one)."""
    rows = [c for c in ledger.channels() if c["hits"] or c.get("source") == "listed"]
    busiest = {c["freq_hz"] for c in sorted(rows, key=lambda c: -c["hits"])[:with_periods] if not c["voice"]}
    since = time.time() - 3 * 86400
    out = []
    for c in rows:
        period = ledger.period_of(ledger.heard_at(c["freq_hz"], since)) if c["freq_hz"] in busiest else None
        cls, desc = classify_channel(c, habits, period)
        out.append({"freq": c["freq_hz"], "label": c.get("label") or "", "service": c.get("service") or "",
                    "hits": c["hits"], "voice": c["voice"], "data": c.get("data", 0), "last": c.get("last_seen"),
                    "first": c.get("first_seen"), "hours": ledger.active_hours(c), "hist": _hours(c),
                    "transcript": c.get("last_transcript") or "", "class": cls, "desc": desc,
                    "period": round(period[0], 1) if period and period[1] >= 0.5 else None,
                    "habit": next((s for f, s in habits.items() if abs(f - c["freq_hz"]) <= 3000), None)})
    order = {"talk": 0, "timer": 3, "data": 2, "carrier": 1, "quiet": 4}
    out.sort(key=lambda r: (order[r["class"]], -r["voice"], -r["hits"]))
    return out


def _hours(c: dict) -> list:
    try:
        h = json.loads(c.get("hours") or "[]")
    except ValueError:
        h = []
    return h if len(h) == 24 else [0] * 24


def new_channels(hours: float = 72.0) -> list[dict]:
    now = time.time()
    return sorted(({"freq": c["freq_hz"], "first": c["first_seen"], "hits": c["hits"], "voice": c["voice"],
                    "label": c.get("label") or c.get("service") or ""}
                   for c in ledger.channels()
                   if c.get("source") == "found" and c.get("first_seen") and now - c["first_seen"] <= hours * 3600),
                  key=lambda r: -r["first"])
