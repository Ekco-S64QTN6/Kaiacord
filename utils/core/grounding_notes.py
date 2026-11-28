"""Notes beside the message for things she would otherwise make up.

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


#: User turns back that a picture shared earlier is still what "the picture"
#: means. Starkind asked for "anything unrelated to the picture" two minutes
#: after sending one, and the note had her answer "i don't see a photo".
RECENT_PICTURE_TURNS = 6


def shared_recently(history: list) -> bool:
    """A picture is among the last RECENT_PICTURE_TURNS user turns of `history`."""
    users = [m for m in (history or []) if isinstance(m, dict) and m.get("role") == "user"]
    return any("[shared image]" in str(m.get("content", "")) for m in users[-RECENT_PICTURE_TURNS:])


def picture_note(own_words: str, has_picture: bool, shown_earlier: bool = False) -> str:
    """The note for a picture spoken of when none reached her, or ""."""
    if has_picture or shown_earlier or "http" in (own_words or "") or not _PICTURE.search(own_words or ""):
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


# "when was the last message from jimjam?" She answered "about an hour ago,
# regarding a philosophical discussion on survival" (25 Nov); he had last
# talked to her on 6 October. What she does know is when each person last
# spoke to her (BotState.relationships), so that is the note.
_NAME = (r"@?(?!(?:the|a|an|that|this|it|he|she|they|you|i|we|someone|anyone|anybody|everyone|kaia)\b)"
         r"([^\W\d_][\w.\-]{1,31})")
_LAST_SEEN_ASK = re.compile(
    r"\b(?:last|latest|most\s+recent)\s+(?:message|msg|post|word)s?\s+(?:from|of|by)\s+" + _NAME
    + r"|\bwhen\s+(?:did|was|has)\s+" + _NAME + r"\s+(?:last\b|(?:here|on|online|around)\s+last\b)"
    + r"|\bwhen\s+(?:did|was)\s+(?:the\s+)?last\s+time\s+" + _NAME + r"\b"
    + r"|\b(?:have|has)\s+(?:you|anyone|anybody)\s+(?:seen|heard\s+from)\s+" + _NAME
    + r"|\bwhere(?:['’]s|\s+is|\s+has)\s+" + _NAME + r"\s+(?:been|gone)\b",
    re.IGNORECASE,
)


def last_seen_note(own_words: str, last_seen: dict, now: float) -> str:
    """The note for a question about when someone she knows last spoke, or "".

    `last_seen`: display name -> the last time that person spoke to her. Only a
    name she knows gets a note, so an unrelated word cannot be taken for one.
    """
    import datetime
    m = _LAST_SEEN_ASK.search(own_words or "")
    if not m or not last_seen:
        return ""
    asked = next(g for g in m.groups() if g).lower()
    known = {name.lower(): (name, ts) for name, ts in last_seen.items() if name}
    hit = known.get(asked) or next(
        (v for k, v in known.items() if len(asked) >= 4 and k.startswith(asked)), None)
    if hit is None:
        return ""
    name, ts = hit
    days = int((now - ts) // 86400)
    when = datetime.datetime.fromtimestamp(ts).strftime("%A %d %B").replace(" 0", " ")
    ago = "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"
    return (f"[what you know: {name} last spoke to you on {when} ({ago}). you don't have "
            f"what they said then, so don't make it up.]")


def notes_for(own_words: str, *, has_picture: bool, tried_pictures: bool, given: str,
              history: list = None, last_seen: dict = None, now: float = None) -> str:
    """Every note this turn needs, joined, or "".

    `tried_pictures`: the pipeline found a picture to load; whether it loaded is
    then the vision path's own note to give. `history`: the turns before this one.
    `last_seen`: display name -> when that person last spoke to her.
    """
    import time
    notes = [quote_note(own_words, given)]
    if not tried_pictures:
        notes.append(picture_note(own_words, has_picture, shared_recently(history)))
    notes.append(last_seen_note(own_words, last_seen or {}, time.time() if now is None else now))
    return "\n".join(n for n in notes if n)
