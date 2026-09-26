"""Kaia's notes: when she says she is keeping one, she does.

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
_KEEPING = re.compile(
    r"\b(?:add(?:ing|ed)?|sav(?:e|ing|ed)|fil(?:e|ing|ed)|put(?:ting)?|log(?:ging|ged)?|"
    r"stor(?:e|ing|ed)|keep(?:ing)?|jot(?:ting)?)\b[^.!?\n]{0,60}?\b(?:notes?|file|saved|under|as)\b",
    re.IGNORECASE)
_NOTES_NO_NAME = re.compile(
    r"\b(?:i['’]?m|i am|i['’]ll|i will)\s+(?:adding|saving|putting|filing|jotting)\s+"
    r"(?:this|that|it|your [a-z ]{1,30}?|the [a-z ]{1,30}?)\s+(?:down\s+)?(?:to|in|into)\s+my\s+notes\b",
    re.IGNORECASE)
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
    """(the sentence claiming a note, the filename it names or None)."""
    for sentence in _sentences(reply or ""):
        name = _FILENAME.search(sentence)
        if name and _KEEPING.search(sentence):
            return sentence.strip(), name.group(1)
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
    found = find_claim(reply)
    if not found:
        return reply
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
        fixed = re.sub(re.escape(named.group(1)) + r"\.(?:txt|md)", f"{stem}.md", claim, count=1)
        return reply.replace(claim, fixed, 1)
    return reply
