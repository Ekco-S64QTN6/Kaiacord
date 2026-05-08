"""
Episodic Memory Anchors
=======================

Thematic tags extracted from dream processing that enable deep associative
callbacks. When a future conversation touches the same theme, the anchor
is injected as a system prompt hint — creating the illusion of deep
associative memory beyond raw keyword RAG retrieval.

Storage: memory/anchors.json — list of anchor dicts
Cap: 100 anchors max, oldest pruned first
Decay: weight reduces by 0.1 per 30 days
Writes: atomic (tmp → os.replace)
"""

import json
import os
import time
from typing import Optional, List, Dict
from datetime import datetime

from utils.infrastructure.logging.kaia_logger import log_debug, log_info, log_warning

ANCHORS_PATH = os.path.join("memory", "anchors.json")
MAX_ANCHORS = 100
DECAY_RATE = 0.1        # weight reduction per 30-day period
DECAY_PERIOD = 30 * 86400  # 30 days in seconds
MATCH_THRESHOLD = 0.15  # minimum overlap score to trigger injection

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
        os.makedirs(os.path.dirname(ANCHORS_PATH), exist_ok=True)
        tmp_path = ANCHORS_PATH + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(anchors, f, indent=2)
        os.replace(tmp_path, ANCHORS_PATH)
    except Exception as e:
        log_warning(f"Failed to save anchors: {e}")


def _tokenize(text: str) -> set:
    """Extract meaningful words from text, stripping stop words."""
    words = set(text.lower().split())
    return words - _STOP_WORDS


def _apply_decay(anchors: List[Dict]) -> List[Dict]:
    """Apply time-based weight decay and prune dead anchors."""
    now = time.time()
    live = []
    for a in anchors:
        created = a.get('created_at', now)
        age_periods = (now - created) / DECAY_PERIOD
        decayed_weight = a.get('weight', 0.5) - (DECAY_RATE * age_periods)
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
) -> None:
    """Save a new thematic anchor extracted from dream processing.

    Args:
        user_id: The user this anchor is associated with (or None for general).
        theme: Short thematic label (e.g., "career_frustration", "ai_ethics").
        anchor_text: The concrete memory snippet (e.g., "feeling stuck at work").
        weight: Initial importance weight (0.0-1.0).
        user_name: Human-readable name for prompt injection.
    """
    if not theme or not anchor_text:
        return

    anchors = _load_anchors()

    # Deduplicate: if an anchor with the same theme+user exists, update it
    for existing in anchors:
        if (existing.get('theme', '').lower() == theme.lower()
                and existing.get('user_id') == user_id):
            existing['anchor_text'] = anchor_text
            existing['weight'] = weight
            existing['updated_at'] = time.time()
            if user_name:
                existing['user_name'] = user_name
            log_debug(f"Updated existing anchor: {theme} for user {user_name or user_id}")
            _save_anchors(anchors)
            return

    # New anchor
    new_anchor = {
        'theme': theme.lower().strip(),
        'anchor_text': anchor_text.strip()[:200],
        'user_id': user_id,
        'user_name': user_name,
        'weight': weight,
        'created_at': time.time(),
        'updated_at': time.time(),
        'keywords': list(_tokenize(f"{theme} {anchor_text}"))[:20],
    }
    anchors.append(new_anchor)

    # Cap enforcement — prune oldest first
    if len(anchors) > MAX_ANCHORS:
        anchors.sort(key=lambda a: a.get('created_at', 0))
        anchors = anchors[-MAX_ANCHORS:]

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
    anchors = _load_anchors()
    if not anchors:
        return []

    # Apply decay
    anchors = _apply_decay(anchors)

    message_words = _tokenize(message_text)
    if len(message_words) < 2:
        return []

    scored = []
    for anchor in anchors:
        anchor_keywords = set(anchor.get('keywords', []))
        if not anchor_keywords:
            anchor_keywords = _tokenize(
                f"{anchor.get('theme', '')} {anchor.get('anchor_text', '')}"
            )

        # Jaccard-like overlap score
        overlap = message_words & anchor_keywords
        if not overlap:
            continue

        # Score = overlap proportion relative to anchor keywords
        score = len(overlap) / max(len(anchor_keywords), 1)

        # Boost for user-specific anchors
        if user_id and anchor.get('user_id') == str(user_id):
            score *= 1.5

        # Weight by anchor importance
        effective_weight = anchor.get('effective_weight', anchor.get('weight', 0.5))
        score *= effective_weight

        if score >= MATCH_THRESHOLD:
            scored.append((score, anchor))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    return [anchor for _, anchor in scored[:max_results]]


def format_anchor_injection(anchor: Dict) -> str:
    """Format an anchor match for system prompt injection.

    Returns a bracketed directive that guides Kaia to make an
    associative callback without forcing it.
    """
    theme = anchor.get('theme', 'something')
    text = anchor.get('anchor_text', '')
    user_name = anchor.get('user_name', 'someone')
    created = anchor.get('created_at', time.time())

    # Human-readable time delta
    days_ago = int((time.time() - created) / 86400)
    if days_ago < 1:
        time_ref = "earlier today"
    elif days_ago == 1:
        time_ref = "yesterday"
    elif days_ago < 7:
        time_ref = f"a few days ago"
    elif days_ago < 30:
        time_ref = f"a couple weeks ago"
    else:
        time_ref = f"about {days_ago // 30} month{'s' if days_ago > 60 else ''} ago"

    return (
        f"[memory anchor: you remember {user_name} talking about {theme} "
        f"{time_ref} — \"{text}\". if it connects to what they're saying now, "
        f"reference it naturally. don't force it.]"
    )
