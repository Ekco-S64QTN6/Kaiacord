"""Reading a filed news brief as headlines and stories, for `!news`.

A brief is Markdown the generator writes daily: an executive summary, then one
`## SECTION` per beat with `- ` items and a `- QUOTE:` line. `!news` lists the
lead items as numbered headlines and `!news N` opens one, so the numbering has
to come out the same on both calls — `headlines()` is the single source of it.

Pure functions over text; the handler does the file I/O off the event loop.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

NEWS_DIR = Path("knowledge_base/news")

#: Lead items per section in the headline list.
PER_SECTION = 2

_EMPTY = re.compile(r"no verified developments", re.I)
_BRIEF_NAME = re.compile(r"news_brief_(\d{8})\.md$")


@dataclass
class Brief:
    date: Optional[datetime]
    summary: str = ""
    sections: Dict[str, List[str]] = field(default_factory=dict)
    quotes: Dict[str, str] = field(default_factory=dict)


@dataclass
class Story:
    number: int
    section: str
    text: str


def section_title(key: str) -> str:
    """"GLOBAL_GEOPOLITICS" → "Global Geopolitics", keeping "US" and "AI" upper."""
    words = key.replace("_", " ").split()
    return " ".join(w if w in ("US", "UK", "EU", "AI", "UN") else w.capitalize() for w in words)


def parse(text: str, date: Optional[datetime] = None) -> Brief:
    """A brief's summary, its items by section, and each section's quote."""
    from utils.core.frontmatter import parse_frontmatter
    try:
        _, body = parse_frontmatter(text)
    except Exception:
        body = text.split("---\n", 2)[-1] if text.startswith("---\n") else text

    brief = Brief(date=date)
    current = None
    summary_lines: List[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            current = line[3:].strip()
            continue
        if not line or line.startswith("# ") or line.startswith(">"):
            continue
        if current == "EXECUTIVE_SUMMARY":
            summary_lines.append(line)
            continue
        if current is None:
            continue
        item = line[2:].strip() if line.startswith("- ") else line
        if _EMPTY.search(item):
            continue
        if item.upper().startswith("QUOTE:"):
            brief.quotes.setdefault(current, item.split(":", 1)[1].strip())
            continue
        brief.sections.setdefault(current, []).append(item)
    brief.summary = " ".join(summary_lines)
    return brief


def headlines(brief: Brief, per_section: int = PER_SECTION) -> List[Story]:
    """The numbered lead stories, in section order. `!news N` indexes this list."""
    stories: List[Story] = []
    for section, items in brief.sections.items():
        for text in items[:per_section]:
            stories.append(Story(len(stories) + 1, section, text))
    return stories


def headline(text: str, limit: int = 110) -> str:
    """The first sentence of an item, cut at a word if it runs long."""
    first = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
    if len(first) <= limit:
        return first.rstrip(".")
    cut = first[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:—-")
    return cut + "…"


def brief_files(news_dir: Path = NEWS_DIR) -> List[Tuple[datetime, Path]]:
    """Every filed brief under news/, newest first."""
    found = []
    for path in news_dir.rglob("news_brief_*.md"):
        m = _BRIEF_NAME.search(path.name)
        if m:
            try:
                found.append((datetime.strptime(m.group(1), "%Y%m%d"), path))
            except ValueError:
                continue
    return sorted(found, reverse=True)


def load_latest(news_dir: Path = NEWS_DIR) -> Optional[Brief]:
    files = brief_files(news_dir)
    if not files:
        return None
    date, path = files[0]
    return parse(path.read_text(encoding="utf-8", errors="replace"), date)


_STOP = frozenset("""
about after again against also among amid being between could during first from
have into more most other over said says some their there these they this those
through under until were what when where which while with would year years
president minister officials government announced reported stated according
approximately billion million percent including following national international
united states country countries today week monday tuesday wednesday thursday
friday saturday sunday january february march april june july august september
october november december
""".split())


def _salient(text: str) -> set:
    """Names and substantive words: what two items about one story share."""
    words = re.findall(r"[A-Za-z][A-Za-z'-]{3,}", text)
    return {w.lower() for w in words if w.lower() not in _STOP and (w[0].isupper() or len(w) >= 7)}


def related(story: Story, brief: Brief, earlier: List[Brief], limit: int = 3,
            min_shared: int = 2, common: float = 0.04
            ) -> Tuple[List[str], List[Tuple[datetime, str]]]:
    """Other items on the same story: in today's brief, and in earlier ones.

    Two items match when they share at least `min_shared` salient words that
    are not common across the briefs searched. Without the rarity test every
    item naming "Donald Trump" or "General Assembly" was the same story.
    """
    pool = [(None, t) for items in brief.sections.values() for t in items]
    for other in earlier:
        pool += [(other.date, t) for items in other.sections.values() for t in items]
    words = {t: _salient(t) for _, t in pool}
    df: Dict[str, int] = {}
    for ws in words.values():
        for w in ws:
            df[w] = df.get(w, 0) + 1
    ceiling = max(3, int(len(words) * common))
    rare = lambda ws: {w for w in ws if df.get(w, 0) <= ceiling}

    key = rare(_salient(story.text))
    names = {w.lower() for w in re.findall(r"\b[A-Z][a-zA-Z'-]{2,}", story.text)} & key
    if len(key) < min_shared or not names:
        return [], []

    same_day, before, seen = [], [], {story.text}
    for date, text in pool:
        if text in seen:
            continue
        overlap = key & rare(words[text])
        shared = len(overlap)
        # At least one shared name: two items that merely share vocabulary
        # ("funding", "security") are not the same story.
        if shared < min_shared or not (overlap & names):
            continue
        seen.add(text)
        if date is None:
            same_day.append(text)
        else:
            before.append((shared, date, text))
    # Strongest overlap first, then newest.
    before.sort(key=lambda t: (-t[0], -t[1].timestamp()))
    return same_day[:limit], [(d, t) for _, d, t in before[:limit]]
