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
import json
import time
import asyncio
from dataclasses import dataclass, field, asdict
from typing import List, Optional

from utils.infrastructure.logging.kaia_logger import log_debug, log_warning, log_error


RELATIONSHIPS_DIR = os.path.join("memory", "relationships")


@dataclass
class RelationshipEvent:
    timestamp: float
    event_type: str       # "positive", "friction", "neutral", "repair", "milestone"
    summary: str
    emotional_weight: float  # 0.0–1.0, higher = more significant
    topics: List[str] = field(default_factory=list)


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
        return [RelationshipEvent(**e) for e in raw]
    except Exception as e:
        log_warning(f"Failed to load relationship events for {user_id}: {e}")
        return []


def save_event(user_id: str, event: RelationshipEvent):
    """Append a relationship event and persist atomically."""
    events = load_events(user_id)
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

    path = _user_file(user_id)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump([asdict(e) for e in events], f, indent=2)
        os.replace(tmp_path, path)
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
            'milestone': '*', 'neutral': '·'
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


def detect_event_type(user_text: str, bot_text: str) -> Optional[str]:
    """Detect if the interaction contains a notable relationship event.
    Returns event_type string or None if unremarkable.
    """
    user_lower = user_text.lower()
    bot_lower = bot_text.lower()

    # Repair: user corrects Kaia
    correction_signals = ['actually', 'no that\'s wrong', 'that\'s not right',
                          'you\'re wrong', 'incorrect', 'not what i meant',
                          'i meant', 'correction']
    if any(sig in user_lower for sig in correction_signals):
        return 'repair'

    # Friction: user expresses frustration
    friction_signals = ['stop', 'enough', 'shut up', 'useless', 'broken',
                        'not helpful', 'wrong again', 'frustrated']
    if any(sig in user_lower for sig in friction_signals):
        return 'friction'

    # Positive: gratitude or praise
    positive_signals = ['thank you', 'thanks', 'awesome', 'perfect',
                        'love it', 'great job', 'well done', 'amazing',
                        'appreciate', 'exactly what i needed']
    if any(sig in user_lower for sig in positive_signals):
        return 'positive'

    return None  # Unremarkable interaction
