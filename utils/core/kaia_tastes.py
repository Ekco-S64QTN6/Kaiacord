"""Her real tastes, so a favourite is something she has.

Asked for a favourite album, book or film she has named titles that do not
exist. She has no store of tastes, but she has a record of what she keeps
coming back to: the books she has spent the most nights reflecting on
(`kaia_dreams/consolidated/books/`, "*43 reflections about a book*"), the
library she owns (`knowledge_base/books/`), the sets she has played and the
pieces she has made (`memory/growth_log.jsonl`). When the speaker asks for a
favourite or a recommendation, that record goes into the prompt.

Pure Python; read at most once an hour.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Optional

from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

KB = Path("knowledge_base")
CACHE_S = 3600
TOP_BOOKS = 6

# A request for *her* taste, not any sentence with "favourite" or "suggests" in
# it. Measured over 7,911 real user lines: the old any-mention pattern fired on
# 139, most of them "the image suggests…" or someone naming their own favourite.
_MEDIA = r"(?:book|novel|song|track|album|band|artist|film|movie|show|series|game|anime|genre|author|record)s?"
ASKS = re.compile(
    r"\byour\s+(?:(?:all[- ]time|absolute|second|least)\s+)?(?:most\s+)?(?:fav(?:ou?rite|e)s?|top|go-?to)\b"
    r"|\bfav(?:ou?rite|e)\b[^.!?\n]{0,40}\?"
    r"|\b(?:would|could|can|do|will)\s+you\s+recommend\b|(?:^|[.?!,:]\s*|\bkaia\s+)recommend\s+(?:me|us|a|an|some|any)\b"
    r"|\brecommendations?\b[^.!\n]{0,40}\?|\bany\s+(?:good\s+)?recommendations?\b"
    rf"|\bsuggest\s+(?:me\s+)?(?:a|an|some|any)\s+(?:good\s+)?{_MEDIA}\b"
    r"|\bwhat\s+(?:do|are)\s+you\s+(?:into|reading|listening\s+to|playing)\b"
    r"|\bwhat\s+(?:should|would|could)\s+i\s+(?:read|listen\s+to|watch|play)\b"
    r"|\byour\s+tastes?\b|\bwhat\s+have\s+you\s+been\s+(?:reading|listening\s+to|playing)\b",
    re.IGNORECASE)

_REFLECTIONS = re.compile(r"\*(\d+) reflections? about")
_WORD = re.compile(r"[a-z0-9]+")
_cache: tuple[float, Optional[dict]] = (0.0, None)


def asks_for_taste(own_words: str) -> bool:
    return bool(ASKS.search(own_words or ""))


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower())) - {"the", "of", "a", "an", "and", "by", "book", "md"}


def _library() -> dict[str, str]:
    """{word-set key: "Title by Author"} for every book she owns."""
    out = {}
    for p in (KB / "books").glob("Book - *.md"):
        title = p.stem[len("Book - "):]
        out[title] = title
    return out


def _title_for(stem: str, library: dict[str, str]) -> str:
    """A consolidated stem ("Phillip_K_Dick_Do_Androids_Dream...") as the
    library names it, when one clearly matches; the stem made readable if not."""
    want = _words(stem.replace("_", " "))
    best, score = None, 0.0
    for title in library:
        have = _words(title)
        overlap = len(want & have) / max(1, len(want))
        if overlap > score:
            best, score = title, overlap
    if best and score >= 0.6:
        return best
    return re.sub(r"\s+", " ", stem.replace("_", " ")).strip()


def _most_reflected(library: dict[str, str]) -> list[tuple[str, int]]:
    found = []
    for p in (KB / "kaia_dreams" / "consolidated" / "books").glob("*.md"):
        if p.stem.lower() in ("unattributed",) or re.match(r"\d{4}_", p.stem):
            continue
        try:
            head = p.read_text(encoding="utf-8")[:1200]
        except OSError:
            continue
        m = _REFLECTIONS.search(head)
        if m:
            found.append((_title_for(p.stem, library), int(m.group(1))))
    return sorted(found, key=lambda t: -t[1])[:TOP_BOOKS]


def _made() -> tuple[Counter, Counter, str]:
    """(genres played, art titles, the last set) from her growth log."""
    genres, pieces, last_set = Counter(), Counter(), ""
    try:
        lines = Path(telemetry_path("memory/growth_log.jsonl")).read_text(encoding="utf-8").splitlines()
    except OSError:
        return genres, pieces, last_set
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "creation":
            continue
        if e.get("kind") == "music":
            genre = (e.get("detail") or {}).get("genre")
            if genre:
                genres[genre] += 1
                last_set = e.get("summary", "").strip("[]")
        elif e.get("kind") == "art" and e.get("title"):
            pieces[e["title"]] += 1
    return genres, pieces, last_set


def tastes() -> dict:
    global _cache
    stamp, value = _cache
    if value is not None and time.time() - stamp < CACHE_S:
        return value
    library = _library()
    genres, pieces, last_set = _made()
    value = {"books": _most_reflected(library), "library_size": len(library),
             "genres": genres.most_common(5), "pieces": [t for t, _ in pieces.most_common(4)],
             "last_set": last_set}
    _cache = (time.time(), value)
    return value


def note_for(own_words: str) -> str:
    """The block for a turn that asks about her favourites, or ''."""
    if not asks_for_taste(own_words):
        return ""
    t = tastes()
    lines = []
    if t["books"]:
        lines.append("Books and works you keep coming back to (nights you've spent reflecting on each): "
                     + "; ".join(f"{title} ({n})" for title, n in t["books"]) + ".")
    if t["library_size"]:
        lines.append(f"You own {t['library_size']} books in your library.")
    if t["genres"]:
        lines.append("Music you've actually played live: "
                     + ", ".join(f"{g} ({n} set{'s' if n != 1 else ''})" for g, n in t["genres"]) + "."
                     + (f" Most recently: {t['last_set']}" if t["last_set"] else ""))
    if t["pieces"]:
        lines.append("Pieces you've made: " + ", ".join(f'"{p}"' for p in t["pieces"]) + ".")
    if not lines:
        return ""
    return ("[YOUR REAL TASTES — from what you have and have done. A favourite or a recommendation "
            "comes from here or from something you can name for certain. If the question is about "
            "something outside these, say you don't have a favourite there rather than naming a "
            "title you aren't sure exists.]\n" + "\n".join(f"- {l}" for l in lines))
