"""Emergency Action Messages from eam.watch.

eam.watch is a volunteer log of the USAF High Frequency Global Communications
System (8992 / 11175 kHz USB and friends). Its front end reads two public JSON
endpoints; nothing here is documented by the site, so a response that does not
look as expected raises FeedError rather than being read as "no traffic".

    /api/messages?page=N   newest first, 15 per page — current traffic
    /api/skykings?page=N   the Skyking archive, 2007–2022; Skyking is defunct

Messages are encrypted. Nothing here, and nothing Kaia says about them, may
claim to decode one.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from utils.radio.fetch import FeedError, get_json, is_stale, read_cache, write_cache

BASE = "https://eam.watch"
MESSAGES_CACHE = "eam_messages"
ARCHIVE_CACHE = "eam_skyking_archive"

#: The ordinary EAM. The rest are the net's housekeeping.
EAM_TYPE = "ALLSTATIONS"
TYPE_LABELS = {
    "ALLSTATIONS": "EAM",
    "RADIOCHECK": "radio check",
    "DISREGARDED": "disregard",
    "SKYKING": "Skyking",
    "OTHER": "net traffic",
}

NATO = {
    "A": "ALFA", "B": "BRAVO", "C": "CHARLIE", "D": "DELTA", "E": "ECHO", "F": "FOXTROT",
    "G": "GOLF", "H": "HOTEL", "I": "INDIA", "J": "JULIETT", "K": "KILO", "L": "LIMA",
    "M": "MIKE", "N": "NOVEMBER", "O": "OSCAR", "P": "PAPA", "Q": "QUEBEC", "R": "ROMEO",
    "S": "SIERRA", "T": "TANGO", "U": "UNIFORM", "V": "VICTOR", "W": "WHISKEY",
    "X": "X-RAY", "Y": "YANKEE", "Z": "ZULU",
}


@dataclass
class Message:
    id: str
    type: str
    sender: str
    receiver: str
    text: str
    time: Optional[datetime]
    repeats: int = 0
    comments: int = 0
    recordings: list = field(default_factory=list)

    @property
    def label(self) -> str:
        return TYPE_LABELS.get(self.type, self.type.lower())

    @property
    def preamble(self) -> str:
        """The six-character preamble, when the message opens with it."""
        if self.receiver and self.text.startswith(self.receiver):
            return self.receiver
        return ""

    @property
    def body(self) -> str:
        return self.text[len(self.preamble):] if self.preamble else self.text

    @property
    def url(self) -> str:
        return f"{BASE}/view/{self.id}"


def _parse_time(value) -> Optional[datetime]:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def parse(item: dict) -> Message:
    if not isinstance(item, dict) or "message" not in item or "sender" not in item:
        raise FeedError("eam.watch returned a message without the expected fields")
    recordings = [r.get("link") for r in (item.get("recordings") or []) + (item.get("automated_recordings") or [])
                  if isinstance(r, dict) and r.get("link")]
    return Message(
        id=str(item.get("id", "")),
        type=str(item.get("type") or "OTHER").upper(),
        sender=str(item.get("sender") or "").strip() or "UNKNOWN",
        receiver=str(item.get("receiver") or "").strip(),
        text=" ".join(str(item.get("message") or "").split()),
        time=_parse_time(item.get("time")),
        repeats=int(item.get("repeats") or 0),
        comments=int(item.get("comment_count") or 0),
        recordings=recordings,
    )


def _page_items(payload) -> list:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise FeedError("eam.watch's API no longer answers in the expected shape")
    return payload["data"]


# ── current traffic ─────────────────────────────────────────────────────────

async def refresh(max_age_s: float, force: bool = False) -> dict:
    """The cached first page of traffic, fetched again only when it is older than max_age_s."""
    cache = read_cache(MESSAGES_CACHE)
    if not force and cache.get("messages") and not is_stale(cache, max_age_s):
        return cache
    items = _page_items(await get_json(f"{BASE}/api/messages", {"page": 1}))
    for item in items:           # validate before anything is written
        parse(item)
    # Every callsign ever seen, so a transcription can be matched to a name
    # that is no longer on the first page.
    known = set(cache.get("callsigns") or []) | {parse(i).sender for i in items}
    write_cache(MESSAGES_CACHE, {"messages": items, "callsigns": sorted(known)})
    return read_cache(MESSAGES_CACHE)


def messages(cache: dict) -> list[Message]:
    out = [parse(i) for i in cache.get("messages") or []]
    out.sort(key=lambda m: m.time or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return out


def latest_eams(msgs: list[Message], n: int = 5) -> list[Message]:
    return [m for m in msgs if m.type == EAM_TYPE][:n]


def net_traffic(msgs: list[Message], n: int = 3) -> list[Message]:
    return [m for m in msgs if m.type != EAM_TYPE][:n]


def observation(msgs: list[Message], now: Optional[datetime] = None) -> str:
    """One line about the pattern — counts and gaps, never content."""
    now = now or datetime.now(timezone.utc)
    eams = [m for m in msgs if m.type == EAM_TYPE and m.time]
    if not eams:
        return "nothing logged on the net lately."
    week = [m for m in eams if now - m.time <= timedelta(days=7)]
    if not week:
        days = (now - eams[0].time).days
        return f"quiet week on the net — the last logged EAM was {days} days ago, from {eams[0].sender}."
    senders = {}
    for m in week:
        senders[m.sender] = senders.get(m.sender, 0) + 1
    top, count = max(senders.items(), key=lambda kv: kv[1])
    span = week[0].time - week[-1].time
    if len(week) > 1 and count == len(week) and span <= timedelta(hours=1):
        return (f"{len(week)} EAMs this week, all from {top} inside "
                f"{max(1, int(span.total_seconds() // 60))} minutes.")
    if len(week) == 1:
        return f"one EAM logged this week, from {top}."
    return f"{len(week)} EAMs logged this week; {top} sent {count} of them."


# ── the Skyking archive ─────────────────────────────────────────────────────

_SKYKING = re.compile(r"^\s*(?P<code>.+?)\s+TIME\s+(?P<time>\d{1,2})\s+AUTH(?:ENTICATION)?\s+(?P<auth>[A-Z]{1,3})\s*$",
                      re.IGNORECASE)


def skyking_broadcast(m: Message) -> str:
    """How a Skyking message sounded on the air, from its logged shorthand."""
    hit = _SKYKING.match(m.text)
    if not hit:
        return f"SKYKING, SKYKING, DO NOT ANSWER. {m.text}"
    auth = " ".join(NATO.get(c, c) for c in hit["auth"].upper())
    return (f"SKYKING, SKYKING, DO NOT ANSWER. {hit['code'].upper()}, "
            f"TIME {int(hit['time']):02d}, AUTHENTICATION {auth}.")


async def classic(rng: Optional[random.Random] = None) -> Message:
    """A random message from the Skyking archive. The archive does not change,
    so each page is fetched at most once, ever."""
    rng = rng or random.Random()
    archive = read_cache(ARCHIVE_CACHE)
    pages = archive.get("pages") or {}
    last = int(archive.get("last_page") or 0)
    if not last:
        payload = await get_json(f"{BASE}/api/skykings", {"page": 1})
        pages["1"] = _page_items(payload)
        last = int((payload.get("meta") or {}).get("last_page") or 1)
    page = str(rng.randint(1, last))
    if page not in pages:
        pages[page] = _page_items(await get_json(f"{BASE}/api/skykings", {"page": int(page)}))
    write_cache(ARCHIVE_CACHE, {"pages": pages, "last_page": last})
    items = pages[page]
    if not items:
        raise FeedError("the Skyking archive page came back empty")
    return parse(rng.choice(items))
