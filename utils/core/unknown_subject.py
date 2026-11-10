"""When she is asked what she knows about something nothing she has mentions,
she is told so, as a fact about this turn.

Asked "what do you know about the russian hacker empress", with nothing on
Empress in retrieval, her history or the message, she answered with a dossier:
a made-up name, attacks "in 2045", "a transcript from a 2041 conference". The
persona already says not to invent people, years or sources, three times over;
one more rule is the stacking §11 rules out. This is not a rule: it tells her
that, this turn, the subject appears nowhere in what she was given, so whatever
she says of it is general knowledge or nothing.

Pure Python, no model. A subject counts as present when its last word (the
head: "empress") and at least half its words appear in the prompt outside the
question itself. A scene she is playing is in her history, so its names are
present and this stays quiet.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# The ways a turn asks what she knows of a thing. The subject runs to the end
# of the clause.
_ASKS = re.compile(
    r"\b(?:"
    r"what\s+(?:do|did)\s+you\s+(?:know|remember|recall)\s+(?:about|of|regarding)"
    r"|what\s+can\s+you\s+tell\s+(?:me|us)\s+about"
    r"|(?:can|could|would)\s+you\s+tell\s+(?:me|us)\s+(?:anything\s+)?about"
    r"|tell\s+(?:me|us)\s+(?:what\s+you\s+know\s+)?about"
    r"|(?:have|had)\s+you\s+(?:ever\s+)?heard\s+(?:of|about)"
    r"|do\s+you\s+know\s+(?:anything\s+)?(?:about|of)"
    r"|are\s+you\s+familiar\s+with"
    r"|who\s+(?:is|was|are|were)"
    r")\s+(?P<subject>[^?.!,;\n]{2,80})",
    re.IGNORECASE)

# Not a subject she could look up: herself, the speaker, the conversation.
_DEICTIC = {
    "you", "yourself", "me", "myself", "us", "we", "i", "he", "she", "they", "him", "her", "them",
    "it", "this", "that",
    "these", "those", "there", "here", "everyone", "anyone", "someone", "everything",
    "anything", "something", "kaia", "today", "now",
}
_POSSESSIVE = {"your", "my", "our", "his", "her", "their", "its"}
_STOP = {
    "the", "a", "an", "of", "and", "or", "in", "on", "at", "to", "for", "with", "from", "by",
    "about", "is", "was", "are", "were", "be", "that", "this", "who", "what", "any", "some",
    "all", "lol", "lmao", "btw", "though", "anyway", "really", "actually", "exactly", "called",
    "named", "guy", "girl", "person", "people", "thing", "stuff", "one", "ones",
}
_WORD = re.compile(r"[a-z0-9]+")
MAX_WORDS = 6


def _words(text: str) -> list[str]:
    return _WORD.findall(re.sub(r"['’]s\b", "", (text or "").lower()))


def subject_of(own_words: str) -> Optional[tuple[str, list[str]]]:
    """(the subject as asked, its content words), or None when the turn does
    not ask what she knows of a nameable thing."""
    m = _ASKS.search(own_words or "")
    if not m:
        return None
    subject = m.group("subject").strip(" \t\"'`*_()[]“”‘’")
    subject = re.sub(r"\s+(?:at all|again|lately|then|now|kaia)$", "", subject, flags=re.IGNORECASE)
    tokens = _words(subject)
    if not tokens or tokens[0] in _DEICTIC or tokens[0] in _POSSESSIVE:
        return None
    if re.search(r"https?://|\.\w{2,4}\b", subject):
        return None
    content = [t for t in tokens if t not in _STOP and t not in _DEICTIC and len(t) > 2]
    if not content or len(content) > MAX_WORDS:
        return None
    return subject, content


def mentioned(content: list[str], texts: Iterable[str]) -> bool:
    """The head word and at least half the words appear in what she was given."""
    seen = set()
    for text in texts:
        seen.update(_words(text))
    if content[-1] not in seen:
        return False
    return sum(1 for w in content if w in seen) * 2 >= len(content)


def note_for(own_words: str, given: Iterable[str]) -> str:
    """The fact for this turn, or "" when the subject is in front of her or
    the turn asks nothing of the kind. `given` is everything in her prompt
    except the question itself."""
    found = subject_of(own_words)
    if not found:
        return ""
    subject, content = found
    if mentioned(content, given):
        return ""
    subject = re.sub(r"[\[\]\"]", "", subject)[:80]
    return (f"[nothing you have read, kept or been told mentions \"{subject}\". what you say about "
            "it can only be general knowledge you already had. if you don't know, or only hazily, "
            "say so plainly; never supply names, dates, events or sources to fill the gap.]")
