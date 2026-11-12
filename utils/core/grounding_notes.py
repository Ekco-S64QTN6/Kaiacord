"""Notes beside the message for two things she would otherwise make up.

Asked about a picture that never came with the message, she described one: a
violet-and-apricot sunset, three times out of three, with the CORE RULES block's
"do NOT invent or hallucinate visual details" in the prompt. Asked who said a
line nobody said, she named someone (Charles Simic, Heraclitus, a Snow Crash
character). The rules sit at the end of an eleven-thousand-token system prompt;
a short note beside the message is what she reads. Replayed against the live
model (`tools/maintenance/replay_turns.py --probes`, three seeds), these notes
took both from 0/3 to 3/3, and she still named Gibson and Shakespeare for
their lines.

Each note is written only from what the turn actually carries: whether a
picture reached the model, and whether the quoted line is anywhere in what she
was given. Pure Python, no model call. Read the speaker's own words.
"""
from __future__ import annotations

import re

_PICTURE = re.compile(
    r"\b(?:this|my|the|these)\s+(?:pic|picture|photo|image|screenshot|selfie|meme)s?\b"
    r"|\blook\s+at\s+(?:this|my|lucky|nala|marley)\b",
    re.IGNORECASE,
)
_QUOTE_ASK = re.compile(
    r"\bwho\s+(?:said|wrote|says)\b|\bwhere(?:'s|’s|\s+is|\s+does)\s+(?:this|that)\b.*\bfrom\b"
    r"|\bsource\s+of\s+(?:this|that)\b|\bwhose\s+(?:line|quote|words)\b",
    re.IGNORECASE,
)
_QUOTED = re.compile(r"[\"“‘']([^\"“”‘’']{12,}?)[\"”’']")

PICTURE_NOTE = ("[no picture came with this message, so you can't see one now. if they mean one from earlier, "
                "go by what you said about it then; otherwise tell them you can't see it.]")
QUOTE_NOTE = ("[this line isn't in anything you've read. if it's one everyone knows, say whose it is; "
              "if you can't place it, say so and don't guess.]")


def _flat(text: str) -> str:
    return " ".join((text or "").lower().replace("’", "'").replace("‘", "'").split())


def picture_note(own_words: str, has_picture: bool) -> str:
    """The note for a picture spoken of when none reached her, or ""."""
    if has_picture or "http" in (own_words or "") or not _PICTURE.search(own_words or ""):
        return ""
    return PICTURE_NOTE


def quote_note(own_words: str, given: str) -> str:
    """The note for a quoted line she is asked to attribute and was given nothing about, or ""."""
    if not _QUOTE_ASK.search(own_words or ""):
        return ""
    quoted = _QUOTED.search(own_words or "")
    if not quoted or _flat(quoted.group(1)) in _flat(given):
        return ""
    return QUOTE_NOTE


def notes_for(own_words: str, *, has_picture: bool, tried_pictures: bool, given: str) -> str:
    """Every note this turn needs, joined, or "".

    `tried_pictures`: the pipeline found a picture to load; whether it loaded is
    then the vision path's own note to give.
    """
    notes = [quote_note(own_words, given)]
    if not tried_pictures:
        notes.append(picture_note(own_words, has_picture))
    return "\n".join(n for n in notes if n)
