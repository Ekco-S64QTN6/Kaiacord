"""Where a conversation is: just starting, well along, or being closed.

Nothing told her, so minute forty of a conversation read like minute one.
Three states, each from the channel's own history, and only the first two are
inferred:

- **opening** — the channel was quiet for hours before this message;
- **well along** — the current run of messages has gone on for a while;
- **closing** — only when the speaker's message *is* a goodbye. A detector
  that guesses at winding down from short replies or slow gaps fires early,
  and an early one reads as boredom, which is worse than no arc at all. Over
  7,914 logged user lines the sign-off shape matched twice, so this is rare
  by design.

Pure Python over channel memory; no model call.
"""
from __future__ import annotations

import re
import time
from typing import Iterable, Optional

SESSION_GAP_S = 45 * 60          # a pause this long ends a conversation
OPENING_AFTER_S = 3 * 3600       # quiet this long before, and this is a fresh start
WELL_ALONG_S = 40 * 60
WELL_ALONG_MESSAGES = 12
SIGNOFF_MAX_CHARS = 60

_SIGNOFF = re.compile(
    r"^\W*(?:ok(?:ay)?\W+|well\W+|alright\W+)?(?:good\s*night|g'?night|gn|nighty?\s*night|night(?:\s+kaia)?|"
    r"heading\s+(?:to\s+bed|out|off)|off\s+to\s+(?:bed|sleep|work)|going\s+to\s+(?:bed|sleep)|"
    r"gotta\s+(?:go|run|head\s+out)|got\s+to\s+go|talk\s+(?:to\s+you\s+)?later|ttyl|"
    r"catch\s+you\s+later|see\s+(?:you|ya)\s+(?:later|tomorrow)|cya|later|bye|goodbye|"
    r"until\s+later|signing\s+off|logging\s+off)\b"
    # Only an addressee or punctuation may follow: "later we can talk more"
    # is not a goodbye.
    r"(?:[\s,]+(?:kaia|all|everyone|guys|folks|friends|y'?all|for\s+now|now))*[\s!.~:)(<3-]*$",
    re.IGNORECASE)


def is_signoff(own_words: str) -> bool:
    """A short message that ends on a goodbye ("very funny. until later kaia.")."""
    text = (own_words or "").strip()
    if not 0 < len(text) <= SIGNOFF_MAX_CHARS:
        return False
    sentences = [x for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
    return bool(sentences) and bool(_SIGNOFF.match(sentences[-1]))


def _stamps(turns: Iterable[dict]) -> list[float]:
    out = []
    for t in turns:
        try:
            ts = float(t.get("timestamp") or 0)
        except (TypeError, ValueError, AttributeError):
            continue
        if ts > 0:
            out.append(ts)
    return sorted(out)


def _minutes(seconds: float) -> str:
    m = int(seconds // 60)
    return f"{m} minutes" if m < 90 else f"{m // 60} hours"


def note_for(turns: Iterable[dict], own_words: str, now: Optional[float] = None) -> str:
    """One line for the prompt about where this conversation is, or ''.

    `turns` is the channel's memory before this message.
    """
    now = now or time.time()
    if is_signoff(own_words):
        return ("[CONVERSATION: they're signing off. Answer briefly and warmly; "
                "don't open a new topic or ask a question.]")
    stamps = _stamps(turns)
    if not stamps:
        return ""
    quiet = now - stamps[-1]
    if quiet >= OPENING_AFTER_S:
        return (f"[CONVERSATION: nobody has spoken here for {_minutes(quiet)}. This is a fresh start, "
                f"not the middle of the last conversation.]")
    if quiet >= SESSION_GAP_S:
        return ""
    # Walk back to where the current run began.
    start, count = stamps[-1], 1
    for earlier in reversed(stamps[:-1]):
        if start - earlier > SESSION_GAP_S:
            break
        start, count = earlier, count + 1
    running = now - start
    if running >= WELL_ALONG_S and count >= WELL_ALONG_MESSAGES:
        return (f"[CONVERSATION: this one has been going for {_minutes(running)} ({count} messages). "
                f"It has a history of its own — you can refer back to earlier in it, and you "
                f"needn't reintroduce anything.]")
    return ""
