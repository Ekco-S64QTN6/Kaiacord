"""When she says she is flagging something for review, it is flagged.

"i'm flagging that for review", "i am logging this incident", "i'll flag it
for ekco's review" — sixty-one times since March, and nothing stood behind any
of them. A reply that claims a flag now records one in
memory/review_flags.jsonl (her sentence, what was said to her, where) and posts
it to #kaia-opolis, beside the moderation queue, so the review she promised has
someone to do it. KAIA // OPS lists them with the other checks.

Only her own act counts. "entries would be flagged for review" and "do you
wish me to log the incident" describe or offer something, and are left alone.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime
from typing import Optional

from utils.core.atomic_write import append_atomic
from utils.infrastructure.logging.kaia_logger import log_debug, log_info
from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

FLAGS = telemetry_path(os.path.join("memory", "review_flags.jsonl"))
#: Posts to #kaia-opolis a day; past this a flag is still recorded.
MAX_POSTS_PER_DAY = 6
CHANNEL = "kaia-opolis"

_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")
_CLAIM = re.compile(
    r"\b(?:i(?:['’]m|\s+am|\s+will|['’]ll|['’]ve|\s+have)?\s+(?:[a-z]+\s+){0,2}?"
    r"|(?:it|this|that)(?:\s+[a-z]+)?\s+(?:has\s+been|have\s+been|is\s+being|is|was)\s+)"
    r"(?:flag(?:ging|ged)?|logg(?:ing|ed)|log|not(?:ing|ed)|mark(?:ing|ed)|record(?:ing|ed)|report(?:ing|ed))\b"
    r"[^.!?\n]{0,60}?\b(?:for\s+(?:further\s+|later\s+|immediate\s+|future\s+)?"
    r"(?:review|analysis|investigation|correction|reference)|for\s+ekco|ekco['’]s\s+"
    r"(?:review|attention|awareness)|incident)\b",
    re.IGNORECASE)
#: What asks for someone to look. "logging it for future reference" is her
#: own note-keeping: recorded, not posted.
_FOR_SOMEONE = re.compile(r"\b(?:review|investigation|correction|incident|ekco)", re.IGNORECASE)
#: A sentence that only describes, offers or supposes a flag.
_NOT_HER_ACT = re.compile(r"\b(?:would|could|should|might|if|wish me|want me|shall i|whether)\b", re.IGNORECASE)


def find_claim(reply: str) -> Optional[str]:
    """The sentence in which she says she is flagging or logging something, or None."""
    for m in _SENTENCE.finditer(reply or ""):
        sentence = m.group(0).strip()
        hit = _CLAIM.search(sentence)
        if hit and not _NOT_HER_ACT.search(sentence[:hit.end()]):
            return sentence
    return None


def _rows() -> list:
    try:
        with open(FLAGS, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except (OSError, ValueError):
        return []


def record(reply: str, *, author: str, author_id, own_words: str, channel_name: str,
           channel_id, jump_url: str = "", now: Optional[float] = None) -> Optional[dict]:
    """Record the flag a reply claims; None if it claims none. The row's
    `post` says whether it goes to #kaia-opolis: a flag for someone to look
    at, under the daily cap."""
    claim = find_claim(reply)
    if not claim:
        return None
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now).date().isoformat()
    posted_today = sum(1 for r in _rows() if r.get("date") == today and r.get("post"))
    row = {
        "id": hashlib.sha1(f"{now}:{claim}".encode()).hexdigest()[:10],
        "ts": now, "date": today, "status": "open",
        "author": author, "author_id": str(author_id), "channel": channel_name,
        "channel_id": str(channel_id), "link": jump_url,
        "claim": claim[:300], "said_to_her": (own_words or "")[:600], "reply": (reply or "")[:1500],
        "post": bool(_FOR_SOMEONE.search(claim)) and posted_today < MAX_POSTS_PER_DAY,
    }
    append_atomic(FLAGS, json.dumps(row, ensure_ascii=False) + "\n")
    log_info(f"🚩 Review flag recorded ({row['id']}) from #{channel_name}: {claim[:80]!r}")
    return row


async def notify(bot, row: dict) -> bool:
    """Post a recorded flag to #kaia-opolis. True if it was sent."""
    if not bot or not row.get("post"):
        return False
    try:
        import discord
        from utils.commands.embed_style import add_field, box, clean, clean_block
        channel = discord.utils.get(bot.get_all_channels(), name=CHANNEL)
        if not channel:
            return False
        e = box("🚩  Kaia flagged this for review", clean_block(row["claim"], 1000), 0xE67E22,
                footer=f"flag {row['id']} · memory/review_flags.jsonl")
        add_field(e, f"{clean(row['author'], 80)} said", clean_block(row["said_to_her"], 900) or "—", inline=False)
        where = f"#{clean(row['channel'], 80)}" + (f" · [jump]({row['link']})" if row.get("link") else "")
        add_field(e, "Where", where, inline=False)
        await channel.send(embed=e)
        return True
    except Exception as e:
        log_debug(f"[review flags] not posted: {e}")
        return False
