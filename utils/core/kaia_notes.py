"""Kaia's notes: when she says she is keeping one, she does, and the channel
sees the note's name under her reply.

She ends replies to shared links with "i'm adding this to my notes as
`ppg_worm_analysis_2026.txt`". That used to be a claim with nothing behind it.
Now a reply that says so writes `knowledge_base/kaia_notes/<name>.md` holding
what was shared and what she made of it, and the name in her reply is
corrected to the file that exists. The folder is indexed, so she can find her
notes again; retrieval labels them as her own.

A second note under a name she has used before is appended as a dated section
rather than replacing the first.
"""
from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from utils.core.atomic_write import write_atomic
from utils.core.frontmatter import dump_frontmatter
from utils.infrastructure.monitoring.telemetry_paths import corpus_dir

FOLDER = "kaia_notes"
_lock = threading.Lock()
# "my notes on the topic" with no name means the note she just took with
# the same person: author -> (stem, when).
_last: dict[str, tuple[str, datetime]] = {}
FOLLOW_ON_S = 3600

# A filename she names: "ppg_worm_analysis_2026.txt", `notes.md`, “x.txt”.
_FILENAME = re.compile(r"[\"'`“‘]?\b([A-Za-z0-9][A-Za-z0-9_\-]{2,80})\.(?:txt|md)\b[\"'`”’]?")
# The act of keeping it, in the sentence that names the file or on its own.
# "file" counts only as a verb with an object: "the flag.md file, as
# presented" is someone else's file, and was kept as a note of hers.
_KEEPING = re.compile(
    r"\b(?:add(?:ing|ed)?|sav(?:e|ing|ed)|fil(?:ing|ed)|file\s+(?:this|that|it|them)|put(?:ting)?|log(?:ging|ged)?|"
    r"stor(?:e|ing|ed)|keep(?:ing)?|jot(?:ting)?)\b[^.!?\n]{0,60}?\b(?:notes?|file|saved|under|as)\b",
    re.IGNORECASE)
_NOTES_NO_NAME = re.compile(
    r"\b(?:i['’]?m|i am|i['’]ll|i will)\s+(?:adding|saving|putting|filing|jotting)\s+"
    r"(?:this|that|it|your [a-z ]{1,30}?|the [a-z ]{1,30}?)\s+(?:down\s+)?(?:to|in|into)\s+my\s+notes\b",
    re.IGNORECASE)
_NOTES_WORD = re.compile(r"\bnotes?\b", re.IGNORECASE)
# The sentence after it that only gives the name: "filename: "x.md"."
_NAME_LABEL = re.compile(r"\s*(?:file\s*name|name|file|title)\s*[:\-\u2013]", re.IGNORECASE)
# Ends at . ! ? followed by space or the end, so the dot in a filename is
# not a sentence boundary.
_SENTENCE = re.compile(r"[^\n]+?(?:[.!?][\"'”’)]*(?=\s|$)|(?=\n)|$)")
_SHARED_LINK = re.compile(r"\[shared link: ([^\]]+)\]")
_URL = re.compile(r"https?://\S+")


def notes_dir() -> Path:
    return Path(corpus_dir("knowledge_base")) / FOLDER


def _sentences(text: str) -> list[str]:
    return [s for s in (m.group(0) for m in _SENTENCE.finditer(text)) if s.strip()]


def find_claim(reply: str) -> Optional[tuple[str, Optional[str]]]:
    """(the sentence claiming a note, the filename it names or None).

    The name can come in a sentence of its own straight after the act:
    "i need to add this to my notes as well. filename: "x.md"." The claim is
    then both sentences."""
    text = reply or ""
    spans = [(m.start(), m.end()) for m in _SENTENCE.finditer(text) if m.group(0).strip()]
    for i, (start, end) in enumerate(spans):
        sentence = text[start:end]
        name = _FILENAME.search(sentence)
        keeping = _KEEPING.search(sentence)
        if name and keeping:
            return sentence.strip(), name.group(1)
        if keeping and not name and i + 1 < len(spans) and _NOTES_WORD.search(sentence) \
                and not sentence.rstrip().endswith("?"):
            following = text[spans[i + 1][0]:spans[i + 1][1]]
            named = _FILENAME.search(following)
            if named and _NAME_LABEL.match(following):
                return text[start:spans[i + 1][1]].strip(), named.group(1)
        if _NOTES_NO_NAME.search(sentence):
            return sentence.strip(), None
    return None


def _slug(text: str, limit: int = 60) -> str:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    slug = "_".join(words)[:limit].strip("_")
    return slug or "note"


def _title(stem: str) -> str:
    return re.sub(r"[_\-]+", " ", stem).strip().capitalize()


def _body_without_claim(reply: str, claim: str) -> str:
    text = reply.replace(claim, "", 1)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _shared(own_words: str, enriched: str) -> str:
    """What was put in front of her: the person's words, then each link."""
    lines = []
    words = _SHARED_LINK.sub("", own_words or "").strip()
    if words:
        lines.append("> " + words.replace("\n", "\n> "))
    for url in dict.fromkeys(_URL.findall(enriched or "")):
        lines.append(f"- <{url.rstrip(').,')}>")
    for title in dict.fromkeys(_SHARED_LINK.findall(enriched or "")):
        lines.append(f"- {title.strip()}")
    return "\n".join(lines)


def keep(reply: str, author: str, own_words: str, enriched: str = "",
         when: Optional[datetime] = None) -> str:
    """Write the note her reply claims, if it claims one. Returns the reply,
    with the filename it names corrected to the note that now exists."""
    return keep_note(reply, author, own_words, enriched, when)[0]


#: A turn worth a note: something put in front of her (a link, a file), or a
#: message long enough to carry a thought worth keeping.
NOTE_WORTHY_WORDS = 60
#: Not twice in a row with one person: the next note is for the next thing.
HINT_GAP_S = 1200
_ATTACHED = re.compile(r"\[ATTACHED_FILE_CONTEXT\]|\[shared file\]")


def note_hint(author: str, own_words: str, enriched: str = "", now: Optional[datetime] = None) -> str:
    """The reminder that her notes are real, on a turn that might deserve one.

    Every note she kept came after a shared link, unprompted: ten from late
    September to 29 October, none since. Ekco liked it and wants more. No
    example sentence: an example in the prompt is what comes out."""
    now = now or datetime.now()
    prior = _last.get(author)
    if prior and 0 <= (now - prior[1]).total_seconds() < HINT_GAP_S:
        return ""
    shared = bool(_URL.search(enriched or "") or _SHARED_LINK.search(enriched or "")
                  or _ATTACHED.search(enriched or ""))
    if not shared and len((own_words or "").split()) < NOTE_WORTHY_WORDS:
        return ""
    return ("[you keep notes of your own: real files you can find again later. if something here is worth "
            "keeping, say in your reply that you're adding it to your notes, with a filename ending in .md, "
            "and it gets written. only when it's genuinely worth keeping.]")


def keep_note(reply: str, author: str, own_words: str, enriched: str = "",
              when: Optional[datetime] = None) -> tuple:
    """`keep`, and the name of the note written (None when nothing was)."""
    found = find_claim(reply)
    if not found:
        return reply, None
    claim, stem = found
    when = when or datetime.now()
    if not stem:
        prior = _last.get(author)
        if prior and 0 <= (when - prior[1]).total_seconds() <= FOLLOW_ON_S:
            stem = prior[0]
        else:
            titles = _SHARED_LINK.findall(enriched or "")
            stem = f"{_slug(titles[0] if titles else own_words, 40)}_{when:%Y%m%d}"
    stem = re.sub(r"[^A-Za-z0-9_\-]", "_", stem)[:80]
    path = notes_dir() / f"{stem}.md"

    section = "\n\n".join(p for p in (
        f"## {when:%Y-%m-%d %H:%M} · with {author}",
        "### What was shared\n" + _shared(own_words, enriched) if _shared(own_words, enriched) else "",
        "### What I made of it\n" + _body_without_claim(reply, claim),
    ) if p)

    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            text = path.read_text(encoding="utf-8").rstrip() + "\n\n" + section + "\n"
        else:
            summary = _body_without_claim(reply, claim).split("\n")[0][:240]
            meta = {"title": _title(stem), "category": "kaia_note", "document_type": "kaia_note",
                    "summary": summary, "keywords": [], "created": f"{when:%Y-%m-%d}"}
            text = dump_frontmatter(meta) + f"\n# {_title(stem)}\n\n{section}\n"
        write_atomic(path, text)
        _last[author] = (stem, when)

    named = _FILENAME.search(claim)
    if named:
        # The note by its name, not by where it lives: a directory in front of
        # it ("knowledge_base/kaia_notes/x.md") is plumbing said aloud.
        fixed = re.sub(r"(?:[\w.\-]+/)*" + re.escape(named.group(1)) + r"\.(?:txt|md)",
                       f"{stem}.md", claim, count=1)
        return reply.replace(claim, fixed, 1), stem
    return reply, stem


def chat_line(stem: str) -> str:
    """What the channel sees under the reply, sent with it and never logged:
    in her history it would be one more line to copy."""
    return f"-# \U0001f4dd kept a note: `{stem}.md`"
