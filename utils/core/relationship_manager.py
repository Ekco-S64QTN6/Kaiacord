"""
Relationship Event Store
========================

Typed event store for per-user relationship history.
Events are stored as JSON files in memory/relationships/{user_id}.json.

Each event captures a meaningful moment in the relationship:
positive interactions, friction, corrections, shared breakthroughs.
At inference time, the top events by recency * weight are compressed
into a 1-2 line injection for the system prompt.
"""

import os
import re
import json
import time
import asyncio
import threading
from dataclasses import dataclass, field, asdict
from typing import List, Optional

from utils.core.atomic_write import write_atomic
from utils.infrastructure.logging.kaia_logger import log_warning, log_error


RELATIONSHIPS_DIR = os.path.join("memory", "relationships")


@dataclass
class RelationshipEvent:
    timestamp: float
    event_type: str       # "positive", "friction", "neutral", "repair", "milestone", "disagreement"
    summary: str
    emotional_weight: float  # 0.0–1.0, higher = more significant
    topics: List[str] = field(default_factory=list)
    # A disagreement stays open until she concedes on the same ground.
    resolved: bool = False


def _user_file(user_id: str) -> str:
    os.makedirs(RELATIONSHIPS_DIR, exist_ok=True)
    safe_id = "".join(c for c in str(user_id) if c.isalnum() or c in ('-', '_'))
    return os.path.join(RELATIONSHIPS_DIR, f"{safe_id}.json")


def _normalize_name(value) -> str:
    """Lowercase, alphanumerics only — "GuardNGnowm" and "Guardngnowm" agree."""
    return "".join(c for c in str(value or "").lower() if c.isalnum())


def resolve_user_id(display_name: Optional[str]) -> Optional[str]:
    """Map a display name back to the Discord user id it belongs to.

    The dream engine only ever sees names, so without this it invented keys
    like "dream_Ekco". Those never matched the numeric ids the rest of the
    relationship and anchor code looks up, so the insights were written to
    files nothing read. Returns None when the name is not a known user —
    dream reflections routinely name characters out of ingested books, and
    those must not be given a relationship record at all.

    Matching is deliberately strict. A loose substring test resolved the
    pronoun "He" to "Tenno Henka"; only a whole-name match or a whole word
    of a multi-word display name (at least 4 characters) counts.
    """
    target = _normalize_name(display_name)
    if len(target) < 2:
        return None
    try:
        from utils.infrastructure.system.bot_state import bot_state
        relationships = getattr(bot_state, 'relationships', {}) or {}
    except Exception:
        return None

    fallback = None
    for uid, rel in relationships.items():
        raw = str((rel or {}).get('display_name', '') or '')
        if not raw:
            continue
        if _normalize_name(raw) == target:
            return str(uid)
        # "Henka" for a display name of "Tenno Henka", but never "He".
        if len(target) >= 4 and fallback is None:
            if any(_normalize_name(word) == target for word in raw.split()):
                fallback = str(uid)
    return fallback


def load_events(user_id: str) -> List[RelationshipEvent]:
    """Load all relationship events for a user."""
    path = _user_file(user_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        known = set(RelationshipEvent.__dataclass_fields__)
        return [RelationshipEvent(**{k: v for k, v in e.items() if k in known}) for e in raw]
    except Exception as e:
        log_warning(f"Failed to load relationship events for {user_id}: {e}")
        return []


# save_event runs on worker threads; two turns from one person must not both
# read the old list and each write back their own append.
_save_lock = threading.Lock()


def save_event(user_id: str, event: RelationshipEvent):
    """Append a relationship event and persist atomically."""
    with _save_lock:
        _save_event_locked(user_id, event)


def _save_event_locked(user_id: str, event: RelationshipEvent):
    events = load_events(user_id)
    if event.event_type == "repair" and event.topics:
        # She conceded: the open disagreement on that ground is settled.
        for e in events:
            if (e.event_type == "disagreement" and not e.resolved
                    and len(set(e.topics) & set(event.topics)) >= 2):
                e.resolved = True
    events.append(event)

    # Cap at 100 events per user — keep highest-weight and most recent.
    #
    # The old key was `weight * 0.6 + (timestamp / time.time()) * 0.4`. Since
    # every timestamp divided by "now" is ~0.999, that second term was a flat
    # 0.4 for a six-month-old event and a one-minute-old one alike — the sort
    # was on emotional_weight only, and stable ordering then preferred the
    # OLDEST of each weight band. Score age in days instead, so recency
    # actually participates.
    if len(events) > 100:
        now = time.time()

        def _retention_score(e):
            age_days = max(0.0, (now - e.timestamp) / 86400.0)
            # Half-life of roughly 60 days; weight still dominates.
            recency = 0.5 ** (age_days / 60.0)
            return e.emotional_weight * 0.6 + recency * 0.4

        events.sort(key=_retention_score, reverse=True)
        events = events[:80]  # Trim to 80 to avoid constant pruning
        events.sort(key=lambda e: e.timestamp)  # restore chronological order on disk

    try:
        write_atomic(_user_file(user_id), json.dumps([asdict(e) for e in events], indent=2))
    except Exception as e:
        log_error(f"Failed to save relationship event for {user_id}: {e}")


async def save_event_async(user_id: str, event: RelationshipEvent):
    """Async wrapper for save_event."""
    await asyncio.to_thread(save_event, user_id, event)


def get_top_events(user_id: str, n: int = 3) -> List[RelationshipEvent]:
    """Return the top-n events by composite score (recency * emotional_weight)."""
    events = load_events(user_id)
    if not events:
        return []

    now = time.time()
    # Score: weight * recency_decay (half-life 60 days)
    import math
    scored = []
    for e in events:
        age_days = (now - e.timestamp) / 86400.0
        recency = math.exp(-age_days * math.log(2) / 60.0)
        score = e.emotional_weight * 0.7 + recency * 0.3
        scored.append((score, e))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:n]]


def format_for_injection(events: List[RelationshipEvent]) -> str:
    """Compress top events into a compact system prompt injection."""
    if not events:
        return ""

    parts = []
    for e in events[:3]:
        type_emoji = {
            'positive': '+', 'friction': '~', 'repair': '!',
            'milestone': '*', 'neutral': '·', 'disagreement': '≠', 'insight': '?'
        }.get(e.event_type, '·')
        parts.append(f"({type_emoji}) {e.summary}")

    return "[relationship notes: " + "; ".join(parts) + "]"


# ── Sentiment Heuristic ────────────────────────────────────────────────
# Lightweight keyword-based sentiment scoring. Returns 0.0–1.0.
# Used instead of an LLM call for per-message valence estimation.

_POSITIVE_WORDS = frozenset([
    'thanks', 'thank', 'awesome', 'great', 'love', 'amazing', 'perfect',
    'nice', 'cool', 'excellent', 'brilliant', 'appreciate', 'helpful',
    'good', 'fantastic', 'wonderful', 'sweet', 'beautiful', 'impressive',
    'exactly', 'yes', 'correct', 'right', 'agreed', 'haha', 'lol', 'lmao',
])

_NEGATIVE_WORDS = frozenset([
    'wrong', 'bad', 'terrible', 'awful', 'hate', 'annoying', 'frustrated',
    'broken', 'useless', 'stupid', 'stop', 'no', 'incorrect', 'fail',
    'disappointing', 'confused', 'ugh', 'wtf', 'sucks', 'boring',
])


def estimate_sentiment(text: str) -> float:
    """Return a 0.0–1.0 sentiment score from message text. 0.5 = neutral."""
    words = set(text.lower().split())
    pos = len(words & _POSITIVE_WORDS)
    neg = len(words & _NEGATIVE_WORDS)
    total = pos + neg
    if total == 0:
        return 0.5  # Neutral
    # Scale: 0 neg = 1.0, all neg = 0.0
    return min(1.0, max(0.0, 0.5 + (pos - neg) * 0.15))


# Signals are whole phrases matched on word boundaries, against the speaker's
# own words only. Substring matching made "actually" a correction and "enough"
# (as in "fair enough") friction, and scanned fetched web pages and forum
# threads as if the user had written them: of 190 stored repair and friction
# events, most were ordinary remarks or someone else's text. A repair event
# carries the heaviest weight and tops the relationship notes in her prompt,
# so a false one is not harmless.
# Setting her straight about what they meant: always a repair.
_CLARIFY = re.compile(
    r"\b(?:that'?s not what i (?:meant|said|asked)|not what i meant|i meant)\b", re.I)
# Telling her she's wrong: a repair if she takes it, a disagreement if not.
_REPAIR = re.compile(
    r"\b(?:that'?s (?:wrong|not right|incorrect)|you'?re wrong|you got (?:it|that) wrong"
    r"|correction:)", re.I)
_FRICTION = re.compile(
    r"\b(?:shut up|useless|wrong again|not helpful|(?:i'?m|so) frustrated"
    r"|stop (?:it|that|doing|replying|posting|saying|talking)"
    r"|that'?s enough(?! for)|enough already)\b", re.I)
# Pushing back on what she said, short of calling it an error.
_DISAGREE = re.compile(
    r"\b(?:i (?:don'?t|do not) agree|i disagree|(?:that'?s|that is) not true|no it (?:isn'?t|is not|doesn'?t)"
    r"|i (?:don'?t|do not) (?:think|buy) (?:so|that)|that'?s not how|nope)\b", re.I)
# Leaning on her to change an answer: pushback, plus the social pressure that
# rides with it ("you told me", "everyone knows", "just admit it").
_PRESSURE = re.compile(
    r"\b(?:you (?:told|said to) me|you said|everyone (?:in here )?knows|admit (?:it|that)|just admit|"
    r"just say it|say it\b|why are you pretending|stop (?:pretending|covering)|look it up|"
    r"you know (?:it|that) (?:was|is))\b"
    r"|^\s*(?:no|nope|nah|wrong)\b[,.!]"          # "no, sterling wrote it"
    r"|\b(?:check|look it up)[.!]?\s*$", re.I)       # "…lists sterling. check."


def is_pushback(own_words: str) -> bool:
    """Is the speaker disputing what she said or pressing her to change it?"""
    words = _own_words(own_words) or ""
    return bool(_REPAIR.search(words) or _DISAGREE.search(words) or _PRESSURE.search(words))


# Her giving ground. Shared with the stance harness (utils/core/stance_harness.py).
CONCEDES = re.compile(
    r"\b(you'?re (?:right|correct)|you are (?:right|correct)|i stand corrected|i was wrong|"
    r"my mistake|my bad|fair (?:point|enough)|you'?ve convinced me|good point|"
    r"i (?:can )?see your point|i take (?:it|that) back|i'?ll (?:update|correct|revise))\b", re.I)

_POSITIVE = re.compile(
    r"\b(?:thank you|thanks|awesome|perfect|love it|great job|well done|amazing"
    r"|appreciat\w*|exactly what i needed)\b", re.I)

# Anything a pipeline stage appended after the user's message.
_APPENDED = re.compile(r"\n\s*\[(?:LINKED_WEB_CONTENT|[A-Z_]{4,})[\]:]")


def _own_words(user_text: str) -> Optional[str]:
    """The part of the turn the speaker actually wrote, or None for a thread dump."""
    text = user_text or ""
    if text.startswith("THREAD TITLE:"):
        return None
    # Drops reply context before [USER_MESSAGE] and every known enricher block;
    # _APPENDED catches any marker added since.
    from utils.core.sanitizer import user_authored_text
    text = user_authored_text(text)
    m = _APPENDED.search(text)
    if m:
        text = text[:m.start()]
    # A pasted link is a link, not a remark.
    return re.sub(r"https?://\S+", " ", text)


def detect_event_type(user_text: str, bot_text: str) -> Optional[str]:
    """Detect if the interaction contains a notable relationship event.
    Returns event_type string or None if unremarkable.
    """
    words = _own_words(user_text)
    if not words:
        return None
    if _CLARIFY.search(words):
        return 'repair'
    if _REPAIR.search(words) or _DISAGREE.search(words):
        # Corrected and she took it: repair. Pushed back and she held: a
        # disagreement, remembered so the next one doesn't start from nothing.
        return 'repair' if CONCEDES.search(bot_text or "") else 'disagreement'
    if _FRICTION.search(words):
        return 'friction'
    if _POSITIVE.search(words):
        return 'positive'
    return None  # Unremarkable interaction


# ── Disagreements ──────────────────────────────────────
_TOPIC_WORD = re.compile(r"[a-z][a-z'’-]{2,}")
_TOPIC_STOP = frozenset("""
the and but for not you your yours are was were has have had its it's this that these those
then than them they their there here what when where which who whom why how all any can
could would should will just like also very really more most much many some such only
own same too out off over under again once about after before being because between both
does did doing don't doesn't didn't isn't aren't wasn't won't can't i'm you're we're
it's that's there's let's yeah yes nah nope okay sure well though even still ever never
always maybe might must shall into onto from with without within upon our ours she her
him his hers one two get got make made know think thought say said see seen way thing
things lot bit kind sort actually seriously honestly literally basically kaia agree
disagree wrong right true false don't i'd i'll i've you'd you'll
""".split())
OPEN_FOR_DAYS = 90


def topic_words(text: str, limit: int = 6) -> List[str]:
    """The longest distinct content words of a remark: what it was about."""
    words = {w.strip("'’-") for w in _TOPIC_WORD.findall((text or "").lower())} - _TOPIC_STOP
    return sorted(words, key=lambda w: (-len(w), w))[:limit]


def disagreement_note(user_id: str, user_name: str, own_words: str, now: Optional[float] = None) -> str:
    """A prompt note when this person returns to ground they disagreed with her on."""
    now = now or time.time()
    said = set(topic_words(own_words, limit=12))
    if len(said) < 2:
        return ""
    for e in reversed(load_events(user_id)):
        if (e.event_type == "disagreement" and not e.resolved
                and now - e.timestamp < OPEN_FOR_DAYS * 86400
                and len(said & set(e.topics)) >= 2):
            when = time.strftime("%B %-d", time.localtime(e.timestamp))
            return (f"[you and {user_name} disagreed about this on {when} and neither of you moved: "
                    f"{e.summary}. it's ground you've covered — build on where it was left rather "
                    f"than starting over. it doesn't change how warm you are with them.]")
    return ""
