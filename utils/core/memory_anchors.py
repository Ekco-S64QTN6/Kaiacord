"""
Episodic Memory Anchors
=======================

Thematic tags extracted from dream processing that enable deep associative
callbacks. When a future conversation touches the same theme, the anchor
is injected as a system prompt hint — creating the illusion of deep
associative memory beyond raw keyword RAG retrieval.

Storage: memory/anchors.json — list of anchor dicts
Cap: 100 anchors max, the weakest (after decay) evicted first
Decay: weight reduces by 0.1 per 30 days
Writes: atomic, and every read-modify-write holds one lock — the dream engine
saves anchors on a worker thread while chat turns update access counts.
"""

import json
import os
import re
import threading
import time
from typing import Optional, List, Dict

from utils.core.atomic_write import write_atomic
from utils.infrastructure.logging.kaia_logger import log_debug, log_warning

ANCHORS_PATH = os.path.join("memory", "anchors.json")
MAX_ANCHORS = 100
DECAY_RATE = 0.1        # weight reduction per 30-day period
DECAY_PERIOD = 30 * 86400  # 30 days in seconds
MATCH_THRESHOLD = 0.15  # minimum overlap score to trigger injection
MIN_OVERLAP = 2         # distinct content words the message and anchor share

_lock = threading.RLock()

# Common stop words stripped before overlap matching
_STOP_WORDS = frozenset({
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'do', 'does', 'did',
    'i', 'you', 'we', 'they', 'it', 'to', 'of', 'in', 'for', 'on',
    'with', 'at', 'by', 'and', 'or', 'but', 'not', 'what', 'how',
    'why', 'when', 'where', 'who', 'that', 'this', 'my', 'your', 'me',
    'be', 'have', 'has', 'had', 'about', 'just', 'like', 'think',
    'know', 'really', 'so', 'can', 'been', 'some', 'would', 'could',
    'should', 'will', 'if', 'then', 'than', 'too', 'very', 'much',
})


def _load_anchors() -> List[Dict]:
    """Load anchors from disk. Returns empty list on failure."""
    try:
        if os.path.exists(ANCHORS_PATH) and os.path.getsize(ANCHORS_PATH) > 0:
            with open(ANCHORS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except Exception as e:
        log_warning(f"Failed to load anchors: {e}")
    return []


def _save_anchors(anchors: List[Dict]) -> None:
    """Atomically save anchors to disk."""
    try:
        write_atomic(ANCHORS_PATH, json.dumps(anchors, indent=2))
    except Exception as e:
        log_warning(f"Failed to save anchors: {e}")


_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def _tokenize(text: str) -> set:
    """Meaningful words, stop words removed.

    Words, not whitespace runs: splitting on spaces kept the punctuation, so
    "points." in an anchor never met "points" in a message, and a theme like
    "systems_awareness" was one token nothing could match.
    """
    words = _WORD.findall((text or "").lower().replace("\u2019", "'").replace("_", " "))
    # Contractions and short words are function words whatever the list says.
    return {w for w in words if len(w) >= 4 and "'" not in w} - _STOP_WORDS


def _anchor_words(anchor: Dict) -> set:
    return _tokenize(f"{anchor.get('theme', '')} {anchor.get('anchor_text', '')}")


def _apply_decay(anchors: List[Dict]) -> List[Dict]:
    """Apply time-based weight decay and prune dead anchors.
    
    Salient anchors decay slower to preserve important relational memories.
    Includes access-reinforcement heuristics (Item 8).
    """
    now = time.time()
    live = []
    for a in anchors:
        created = a.get('created_at', now)
        age_periods = (now - created) / DECAY_PERIOD
        
        # Access count reinforcement: each access boosts weight by +0.05 (capped at 1.0)
        access_count = a.get('access_count', 0)
        base_weight = min(1.0, a.get('weight', 0.5) + (0.05 * access_count))
        
        # Double decay if anchor is older than 30 days and has never been accessed
        age_seconds = now - created
        if access_count == 0 and age_seconds > 30 * 86400:
            decay_rate = DECAY_RATE * 2.0
        else:
            decay_rate = DECAY_RATE
            
        # Salience-modulated decay multiplier: high salience = slower decay
        salience = a.get('salience', 0.5)
        decay_mult = max(0.2, 1.5 - salience)
        
        decayed_weight = base_weight - (decay_rate * age_periods * decay_mult)
        if decayed_weight > 0:
            a['effective_weight'] = max(0.05, decayed_weight)
            live.append(a)
    return live


def save_anchor(
    user_id: Optional[str],
    theme: str,
    anchor_text: str,
    weight: float = 0.7,
    user_name: Optional[str] = None,
    salience: float = 0.5,
) -> None:
    """Save a new thematic anchor extracted from dream processing.

    Args:
        user_id: The user this anchor is associated with (or None for general).
        theme: Short thematic label (e.g., "career_frustration", "ai_ethics").
        anchor_text: The concrete memory snippet (e.g., "feeling stuck at work").
        weight: Initial importance weight (0.0-1.0).
        user_name: Human-readable name for prompt injection.
        salience: Emotional importance factor (0.0-1.0) to modulate decay speed.
    """
    if not theme or not anchor_text:
        return

    # The dream engine's salience is an open-ended triage score (0.5 for
    # reading, 1.0 and up for user logs); decay wants 0–1.
    salience = max(0.0, min(1.0, float(salience)))
    theme = theme.lower().strip()
    anchor_text = anchor_text.strip()[:200]

    with _lock:
        anchors = _load_anchors()

        # Deduplicate: if an anchor with the same theme+user exists, update it
        for existing in anchors:
            if (existing.get('theme', '').lower() == theme
                    and existing.get('user_id') == user_id):
                existing['anchor_text'] = anchor_text
                existing['weight'] = weight
                existing['salience'] = salience
                existing['updated_at'] = time.time()
                existing['keywords'] = sorted(_tokenize(f"{theme} {anchor_text}"))
                if user_name:
                    existing['user_name'] = user_name
                _save_anchors(anchors)
                log_debug(f"Updated existing anchor: {theme} for user {user_name or user_id}")
                return

        now = time.time()
        anchors.append({
            'theme': theme,
            'anchor_text': anchor_text,
            'user_id': user_id,
            'user_name': user_name,
            'weight': weight,
            'salience': salience,
            'created_at': now,
            'updated_at': now,
            'keywords': sorted(_tokenize(f"{theme} {anchor_text}")),
        })

        # Cap enforcement — evict the weakest after decay, not the oldest: an
        # old anchor she keeps recalling outranks last night's passing one.
        if len(anchors) > MAX_ANCHORS:
            anchors = sorted(_apply_decay(anchors), key=lambda a: a.get('effective_weight', 0),
                             reverse=True)[:MAX_ANCHORS]

        _save_anchors(anchors)
    log_debug(f"Saved new anchor: {theme} for user {user_name or user_id}")


def find_matching_anchors(
    message_text: str,
    user_id: Optional[str] = None,
    max_results: int = 2,
) -> List[Dict]:
    """Find anchors that thematically match the current message.

    Uses keyword overlap scoring with stop-word filtering.
    Boosts score for anchors tied to the current user.

    Args:
        message_text: The user's current message content.
        user_id: The current user's ID (for user-specific boosting).
        max_results: Maximum number of matching anchors to return.

    Returns:
        List of matching anchor dicts, sorted by score descending.
    """
    message_words = _tokenize(message_text)
    if len(message_words) < 2:
        return []

    with _lock:
        anchors = _load_anchors()
        if not anchors:
            return []
        anchors = _apply_decay(anchors)

        scored = []
        for anchor in anchors:
            # Always from the text: stored keyword lists predate the tokenizer
            # fix and were an arbitrary 20 of a set, punctuation included.
            anchor_keywords = _anchor_words(anchor)
            overlap = message_words & anchor_keywords
            # One shared word is coincidence: against a six-word anchor it
            # cleared the threshold alone. And the message has to touch what
            # the anchor is *about* — two filler words ("being", "little")
            # shared with its text matched a tenth of all chat.
            if len(overlap) < MIN_OVERLAP or not (overlap & _tokenize(anchor.get('theme', ''))):
                continue

            # Share of the anchor's words the message touches
            score = len(overlap) / max(len(anchor_keywords), 1)
            if user_id and anchor.get('user_id') == str(user_id):
                score *= 1.5
            score *= anchor.get('effective_weight', anchor.get('weight', 0.5))

            if score >= MATCH_THRESHOLD:
                scored.append((score, anchor))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [anchor for _, anchor in scored[:max_results]]
        if results:
            # The matched dicts are elements of `anchors`, so this updates
            # what is saved. Decay has also dropped anchors whose weight ran
            # out; saving here is what prunes them.
            for matched in results:
                matched['access_count'] = matched.get('access_count', 0) + 1
            _save_anchors(anchors)

    return results


def format_anchor_injection(anchor: Dict) -> str:
    """Format an anchor match for system prompt injection.

    Returns a bracketed directive that guides Kaia to make an
    associative callback without forcing it.
    """
    theme = (anchor.get('theme') or 'something').replace('_', ' ')
    text = anchor.get('anchor_text', '')
    user_name = anchor.get('user_name')
    # When its text was last written: an updated anchor carries new words.
    created = anchor.get('updated_at') or anchor.get('created_at', time.time())

    # Human-readable time delta
    days_ago = int((time.time() - created) / 86400)
    if days_ago < 1:
        time_ref = "earlier today"
    elif days_ago == 1:
        time_ref = "yesterday"
    elif days_ago < 7:
        time_ref = "a few days ago"
    elif days_ago < 30:
        time_ref = "a couple weeks ago"
    else:
        time_ref = f"about {days_ago // 30} month{'s' if days_ago > 60 else ''} ago"

    # Most anchors come from dreams about reading, not about a person, and
    # have no user. Those printed "you remember None talking about ...".
    if user_name:
        return (
            f"[memory anchor: you remember {user_name} talking about {theme} "
            f"{time_ref} — \"{text}\". if it connects to what they're saying now, "
            f"reference it naturally. don't force it.]"
        )
    return (
        f"[memory anchor: {time_ref} you were thinking about {theme} — "
        f"\"{text}\". if it connects to what they're saying now, "
        f"reference it naturally. don't force it.]"
    )
