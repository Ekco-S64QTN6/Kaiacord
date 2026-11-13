"""How much this turn asks of her.

A person answers in proportion: a remark made in passing gets a line back, a
quick question gets its answer, and room is taken when room is offered. Her
replies had stopped doing that. The median reply to a message of twelve words
or fewer went from 40 words in early September to 69 in early November, and
44% of those replies ran past 80 words.

Nothing in the prompt read the message for its size. Length advice came from
the hour ("willing to go longer"), from the average of the speaker's last five
messages, and from how long the conversation had run, each appended on its own
and free to disagree. This module is the one place a turn's shape is read, from
the speaker's own words, and its note goes beside the message, where a note is
actually followed.

Pure Python, no model call. A turn it does not recognise gets no note.
"""
from __future__ import annotations

import re

#: A message this short, with no question and no request in it, is a passing remark.
ASIDE_WORDS = 14
#: A question this short is a quick one.
QUICK_QUESTION_WORDS = 14
#: From here the speaker has written at length and set the scale themselves.
LONG_WORDS = 40

_URL = re.compile(r"https?://\S+")
_MENTION = re.compile(r"<[@#!&][^>]*>")
_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")

# Words that offer her room: a request for depth, an opinion, a story, a
# continuation. Matched on word boundaries, in the speaker's own words only.
_INVITATION = re.compile(
    r"\b(?:"
    r"explain|describe|elaborate|expand|continue|proceed|go\s+on|keep\s+going|carry\s+on"
    r"|tell\s+me|talk\s+me\s+through|walk\s+me\s+through|show\s+me"
    r"|what\s+do\s+you\s+(?:think|make|see|feel|know|remember)"
    r"|what\s+are\s+your\s+thoughts|your\s+(?:thoughts|take|opinion|view|read)"
    r"|thoughts|opinions?"
    r"|how\s+do\s+you\s+feel|how\s+does\s+(?:it|that)\s+feel"
    r"|what(?:['’]s|\s+is|\s+was)\s+(?:it|that)\s+like"
    r"|in\s+(?:detail|depth)|deep\s+dive|break\s+(?:it|this|that)\s+down"
    r"|summar\w+|analy[sz]\w+|compare|review|critique"
    r"|write|draft|compose|imagine|pretend|picture\s+this|let['’]?s\s+(?:play|say|imagine)"
    r"|story|scene|narrat\w+|roleplay|rp"
    r"|discuss|talk\s+about|let['’]?s\s+talk|go\s+ahead|take\s+it\s+away|surprise\s+me"
    r"|open\s+(?:direction|floor|topic|ended)|free\s+(?:direction|rein|form)|your\s+(?:choice|call|turn|move)"
    r"|whatever\s+you\s+(?:want|like|wish)|anything\s+you\s+(?:want|like|wish)|up\s+to\s+you"
    r"|more\s+about|what\s+else|and\s+then|what\s+happens"
    r"|why\s+do\s+you|why\s+is|why\s+are|why\s+does|how\s+does|how\s+do|how\s+would|how\s+did"
    r")\b",
    re.IGNORECASE,
)
_QUESTION_OPENER = re.compile(
    r"^(?:who|what|when|where|which|whose|is|are|was|were|do|does|did|can|could|"
    r"would|will|should|have|has|had|any|ever)\b",
    re.IGNORECASE,
)


def typed_words(own_words: str) -> list:
    """The words the speaker typed: no links, no mentions, not her name used to call her."""
    text = _MENTION.sub(" ", _URL.sub(" ", own_words or ""))
    words = _WORD.findall(text)
    if words and words[0].lower() == "kaia":
        words = words[1:]
    elif words and words[-1].lower() == "kaia":
        words = words[:-1]
    return words


def kind_of(own_words: str) -> str:
    """"invitation", "long", "question", "aside", "statement" or "empty"."""
    words = typed_words(own_words)
    if not words:
        return "empty"
    text = _URL.sub(" ", own_words or "")
    if _INVITATION.search(text):
        return "invitation"
    if len(words) >= LONG_WORDS:
        return "long"
    if "?" in text or _QUESTION_OPENER.match(" ".join(words)):
        return "question" if len(words) <= QUICK_QUESTION_WORDS else "statement"
    if len(words) <= ASIDE_WORDS:
        return "aside"
    return "statement"


def note_for(own_words: str, shared: bool = False) -> str:
    """The note that goes beside the message, or "" when the turn sets no scale.

    Only a passing remark in plain text gets one. Replayed on real turns against
    the live model, that note took asides from a median of 52 words to 16 with
    her voice intact. The same treatment of short questions cost her voice
    (capitalised, "can you clarify") and flattened scene play, and a message
    that shares a link, file or picture (`shared`) is an invitation to look at
    it, so neither gets a note.
    """
    if shared or kind_of(own_words) != "aside":
        return ""
    return ("[a passing remark, not a prompt for an essay. answer it at its own size: "
            "a line or two, then stop. no closing reflection.]")
