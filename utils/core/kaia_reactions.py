"""
Kaia Reaction System
====================

Non-verbal communication via emoji reactions. Instead of always replying with
text, Kaia occasionally reacts with a contextually appropriate emoji, creating
a layered presence.

September 2026 rework. The previous version had four defects, all measured
against the 7,708 logged user messages:

  * **Substring matching.** `"peak" in content` matched "speaking", `"idea"`
    matched words containing it, `"love"` matched "glove". Sixteen keywords
    produced mid-word false positives. Matching is now anchored at a word
    *start*, which keeps stem matches ("thank" → "thanks") while rejecting
    interior ones.
  * **First category wins.** Categories were tried in dict order, so a message
    containing both "thanks" and "interesting" always drew from the affection
    pool. Every category is now scored and the strongest match wins.
  * **A dead pool.** `_DISAGREEMENT_REACTIONS` was defined and unreachable — no
    trigger referenced it.
  * **Nothing connected it to Kaia's state.** She has a persistent emotional
    arc; it did not influence what she reacted with. It does now, which is the
    point of having internal state at all.
"""

import re
import secrets
import time
from typing import Optional

import discord

from utils.infrastructure.logging.kaia_logger import log_debug, log_warning


# ── Reaction pools ───────────────────────────────────────────────────────────
# Dry, understated, never cutesy — the register the persona file describes.

_AMUSED = ["💀", "😭", "🫠", "😮‍💨", "🙃", "😅"]
_APPROVING = ["💯", "🫡", "✨", "🔥", "👌", "⭐"]
_CURIOUS = ["🤔", "👀", "💭", "🧐", "❓"]
_WARM = ["❤️", "🫂", "🩵", "🥺", "💗"]
_SKEPTICAL = ["🫤", "😐", "🤨", "😑", "🙄"]
_IMPRESSED = ["🤯", "😲", "👏", "🙌"]
_SYMPATHY = ["😔", "🫂", "💔", "😞"]
_TECHNICAL = ["🛠️", "⚙️", "🧠", "📉", "🐛"]
_AGREEMENT = ["✅", "💯", "🫡", "☝️"]
_NOCTURNAL = ["🌙", "☕", "🥱", "🕯️"]

# Every pool is reachable from at least one trigger; test_reactions asserts it.
ALL_POOLS = {
    "amused": _AMUSED, "approving": _APPROVING, "curious": _CURIOUS,
    "warm": _WARM, "skeptical": _SKEPTICAL, "impressed": _IMPRESSED,
    "sympathy": _SYMPATHY, "technical": _TECHNICAL, "agreement": _AGREEMENT,
    "nocturnal": _NOCTURNAL,
}


# ── Triggers ─────────────────────────────────────────────────────────────────
# Keywords are matched at a word start: "thank" catches "thanks" and "thanked",
# but "peak" no longer catches "speaking".

_TRIGGERS = {
    "amused": {
        "keywords": {"lol", "lmao", "lmfao", "haha", "hehe", "rofl", "funny",
                     "hilarious", "cursed", "unhinged", "chaos", "goblin"},
        "pool": _AMUSED,
    },
    "approving": {
        "keywords": {"based", "goated", "peak", "banger", "clean", "elegant",
                     "nailed", "shipped", "works now", "fixed it", "solved"},
        "pool": _APPROVING,
    },
    "curious": {
        "keywords": {"interesting", "hmm", "wonder", "curious", "what if",
                     "theory", "hypothesis", "why does", "how does", "weird"},
        "pool": _CURIOUS,
    },
    "warm": {
        "keywords": {"thank", "appreciate", "grateful", "love you", "missed you",
                     "glad", "proud of", "congrats", "congratulations"},
        "pool": _WARM,
    },
    "skeptical": {
        "keywords": {"allegedly", "supposedly", "sure buddy", "trust me bro",
                     "apparently", "doubt", "sceptical", "skeptical", "copium"},
        "pool": _SKEPTICAL,
    },
    "impressed": {
        "keywords": {"insane", "incredible", "unbelievable", "wild", "no way",
                     "holy", "actually works", "finally"},
        "pool": _IMPRESSED,
    },
    "sympathy": {
        "keywords": {"sorry", "rough", "exhausted", "burnt out", "burned out",
                     "sucks", "awful", "hospital", "passed away", "rip",
                     "stressed", "anxious"},
        "pool": _SYMPATHY,
    },
    "technical": {
        "keywords": {"segfault", "stack trace", "traceback", "regression",
                     "deadlock", "race condition", "memory leak", "compile",
                     "merge conflict", "rollback", "kernel panic", "oom"},
        "pool": _TECHNICAL,
    },
    "agreement": {
        # "this" is deliberately absent: as a keyword it fired on 437 of 7,708
        # messages — 85% of all agreement hits — because it is an ordinary
        # demonstrative pronoun. It only signals agreement as a whole message,
        # which _EXACT_TRIGGERS handles.
        "keywords": {"exactly", "agreed", "correct", "precisely",
                     "well put", "good point", "well said"},
        "pool": _AGREEMENT,
    },
    "nocturnal": {
        "keywords": {"cant sleep", "can't sleep", "insomnia", "3am", "4am",
                     "still up", "another coffee", "no sleep"},
        "pool": _NOCTURNAL,
    },
}

# Messages that are *entirely* one of these. Some tokens only carry meaning as
# a complete utterance: "this" alone is agreement, "this codebase" is not.
_EXACT_TRIGGERS = {
    "agreement": {"this", "this.", "^", "^^", "+1", "same", "fr", "facts"},
    "amused": {"lol", "lmao", "lmfao", "kek", "💀"},
    "curious": {"hm", "hmm", "huh", "wait what", "?"},
}

# Precomputed punctuation-stripped forms, empties removed.
_EXACT_TRIMMED = {
    name: {t for t in (e.rstrip("!.?").strip() for e in exacts) if t}
    for name, exacts in _EXACT_TRIGGERS.items()
}

# Compiled once. \b before the keyword only: a stem match is wanted, an
# interior match is not.
_COMPILED = {
    name: (re.compile("|".join(rf"\b{re.escape(k)}" for k in cfg["keywords"])), cfg["pool"])
    for name, cfg in _TRIGGERS.items()
}

# How Kaia's mood tilts the choice. Low valence makes her drier and less
# effusive; low social energy makes her react less at all.
_MOOD_AFFINITY = {
    "warm": "valence",          # only when she is feeling positive
    "impressed": "valence",
    "approving": "valence",
    "skeptical": "negative",    # more likely when valence is low
    "sympathy": "negative",
}


class KaiaReactions:
    """Manages Kaia's emoji reactions on Discord messages."""

    MAX_PER_HOUR = 6
    MIN_INTERVAL_SECONDS = 90
    BASE_REACT_CHANCE = 35      # percent, before mood adjustment

    def __init__(self):
        self._last_reaction_time: float = 0.0
        self._reaction_count_hour: int = 0
        self._hour_start: float = time.time()
        self._last_reacted_message_id: Optional[int] = None
        self._recent_emoji: list[str] = []

    def _reset_hourly_counter(self):
        now = time.time()
        if now - self._hour_start >= 3600:
            self._reaction_count_hour = 0
            self._hour_start = now

    def _mood(self):
        """Current (valence, social_energy), or a neutral default."""
        try:
            from utils.core.kaia_mood import emotional_arc
            return float(emotional_arc.valence), float(emotional_arc.social_energy)
        except Exception:
            return 0.1, 0.8

    def should_react(self, message: discord.Message) -> bool:
        """Rate limits: per-hour cap, minimum spacing, no bots, no repeats."""
        if message.author.bot:
            return False

        self._reset_hourly_counter()
        if self._reaction_count_hour >= self.MAX_PER_HOUR:
            return False
        if time.time() - self._last_reaction_time < self.MIN_INTERVAL_SECONDS:
            return False
        if message.id == self._last_reacted_message_id:
            return False
        return True

    def score_categories(self, content: str) -> dict:
        """Match count per category. Exposed so the behaviour is testable."""
        low = (content or "").lower().strip()
        scores = {}
        for name, (pattern, _pool) in _COMPILED.items():
            hits = len(pattern.findall(low))
            if hits:
                scores[name] = hits

        # A whole-message match is a stronger signal than a keyword buried in a
        # paragraph, so it is weighted accordingly.
        #
        # Trailing punctuation is ignored ("lol!!!" is "lol"), but the stripped
        # form must be non-empty: comparing rstripped values on both sides made
        # every punctuation-only message match the entry "?", which alone
        # accounted for 512 spurious hits.
        trimmed = low.rstrip("!.?").strip()
        for name, exacts in _EXACT_TRIGGERS.items():
            if low in exacts or (trimmed and trimmed in _EXACT_TRIMMED[name]):
                scores[name] = scores.get(name, 0) + 3
        return scores

    def pick_reaction(self, content: str) -> Optional[str]:
        """Pick an emoji for this message, or None.

        Kaia does not react to everything — returning None is the common and
        intended outcome.
        """
        scores = self.score_categories(content)
        if not scores:
            return None

        valence, _energy = self._mood()

        # Mood weighting: a category aligned with her current state is more
        # likely to win a tie than one that contradicts it.
        def weight(name):
            affinity = _MOOD_AFFINITY.get(name)
            if affinity == "valence":
                return 1.0 + max(0.0, valence)
            if affinity == "negative":
                return 1.0 + max(0.0, -valence)
            return 1.0

        best = max(scores, key=lambda n: (scores[n] * weight(n), secrets.randbelow(100)))
        pool = [e for e in _COMPILED[best][1] if e not in self._recent_emoji] or _COMPILED[best][1]
        return pool[secrets.randbelow(len(pool))]

    async def maybe_react(self, message: discord.Message) -> bool:
        """Add an emoji reaction to a message. Returns True if one was added."""
        if not self.should_react(message):
            return False

        emoji = self.pick_reaction(message.content)
        if not emoji:
            return False

        # Probabilistic gate, scaled by social energy: when she is depleted she
        # reacts less, which is the same signal the text pipeline already uses.
        _valence, energy = self._mood()
        chance = int(self.BASE_REACT_CHANCE * (0.5 + energy))
        if secrets.randbelow(100) >= max(10, min(80, chance)):
            return False

        try:
            await message.add_reaction(emoji)
            self._last_reaction_time = time.time()
            self._reaction_count_hour += 1
            self._last_reacted_message_id = message.id
            # Short memory so she does not use the same emoji twice running.
            self._recent_emoji.append(emoji)
            del self._recent_emoji[:-4]
            log_debug(f"Reacted with {emoji} to message from {message.author.name}")
            return True
        except discord.HTTPException as e:
            log_warning(f"Reaction failed: {e}")
            return False
        except Exception:
            return False
