"""A note beside a short follow-up that turns the last question on the speaker.

Cecily asked what was distinctive about someone's way of talking, got the
answer, and said "do me next". She analysed herself. Replayed against the live
model the turn was misread on every seed ("do you what?", "be the subject of
analysis?"), with the persona alone and on the code of a week earlier: the
model takes the "me" in a clipped request as its own. Saying who "me" is did
not help, and neither did the previous question alone. Both together did,
five seeds of five.

Pure Python, no model call. The note is written only when the message is a few
words that hand the last question to the speaker ("do me next", "what about
me?", "and me?", "my turn") and that speaker's own previous message was a
question; anything longer says what it means on its own.
"""
from __future__ import annotations

import re

MAX_WORDS = 6
MAX_QUESTION_CHARS = 240

_ME = r"(?:me|myself|mine)"
_HANDOVER = re.compile(
    rf"^(?:(?:ok(?:ay)?|now|and|so|then|alright)[\s,]+)*"
    rf"(?:(?:do|try|analy[sz]e|read|rate|describe)\s+{_ME}(?:\s+(?:next|now|too|as\s+well|then))?"
    rf"|(?:what|how)\s+about\s+{_ME}"
    rf"|{_ME}(?:\s+(?:next|now|too|as\s+well))?"
    rf"|my\s+turn(?:\s+(?:next|now))?)$",
    re.IGNORECASE,
)
_LEADING_NAME = re.compile(r"^\s*(?:hey\s+)?@?kaia\b[\s,:]*|[\s,]*\bkaia\s*$", re.IGNORECASE)
_SENTENCE = re.compile(r"[^.!?\n]*\?")


def hands_over(own_words: str) -> bool:
    """Whether the message is only a clipped request to be the next subject."""
    text = _LEADING_NAME.sub("", own_words or "").strip().strip(".!?… ").strip()
    if not text or len(text.split()) > MAX_WORDS:
        return False
    return bool(_HANDOVER.match(text))


def last_question(history, speaker: str) -> str:
    """The speaker's previous message, if it was the last one before this and asked something."""
    prefix = f"{speaker}:".lower()
    for turn in reversed(list(history or [])):
        if turn.get("role") != "user":
            continue
        content = str(turn.get("content", "")).strip()
        if not content.lower().startswith(prefix):
            return ""                              # someone else spoke last: not theirs to continue
        body = content[len(prefix):].strip()
        asked = [s.strip() for s in _SENTENCE.findall(body) if s.strip()]
        if not asked:
            return ""
        question = " ".join(asked[-1].split())
        return question if len(question) <= MAX_QUESTION_CHARS else ""
    return ""


def note(own_words: str, speaker: str, history) -> str:
    """The note for this turn, or an empty string."""
    if not speaker or not hands_over(own_words):
        return ""
    question = last_question(history, speaker)
    if not question:
        return ""
    question = question.replace('"', "'")
    return (f'[{speaker} is asking the same thing they just asked ("{question}"), '
            f'this time about {speaker}. "me" is {speaker}, not you.]')
