"""Something a person said they are about to do, for her to ask after when they return."""
from __future__ import annotations

import re

_FIRST_PERSON_FUTURE = re.compile(
    r"\b(?:(?:i'?m|i\s+am)\s+(?:(?:about|going|planning|trying|hoping)\s+to|gonna)"
    r"|i\s+gonna"
    r"|i(?:'ll|\s+will|\s+might)(?!\s+(?:never|not|always|be\b)))\s+\S.{8,80}",
    re.IGNORECASE)
_LUCK = re.compile(r"\b(?:wish me luck|fingers crossed)\b.{0,80}", re.IGNORECASE)
MIN_MESSAGE_CHARS = 30
#: Pasted text is someone else's plan: "```i'll fix these issues…```" was a coding agent.
_QUOTED = re.compile(r"```.*?(?:```|\Z)|^>[^\n]*$", re.DOTALL | re.MULTILINE)


def find(own_words: str) -> str:
    """The first plan in what they typed, or "". A plan has "i" for its subject:
    "want to see it?" was kept as Starkind's own intention, and "gonna be a
    conspiracy theory" as Ekco's. A question is not one."""
    text = _QUOTED.sub(" ", (own_words or "").replace("\u2019", "'"))
    if len(text.strip()) <= MIN_MESSAGE_CHARS:
        return ""
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        if sentence.rstrip().endswith("?"):
            continue
        m = _FIRST_PERSON_FUTURE.search(sentence) or _LUCK.search(sentence)
        if m:
            return m.group(0).strip().lower()[:120]
    return ""
