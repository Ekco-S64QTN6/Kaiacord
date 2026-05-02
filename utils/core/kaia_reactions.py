"""
Kaia Reaction System
====================

Non-verbal communication via emoji reactions. Instead of always
replying with text, Kaia occasionally reacts to messages with a
contextually appropriate emoji — creating a layered presence.

Rate-limited: max 4 reactions per hour, never on consecutive messages.
"""

import secrets
import time
from typing import Optional

import discord

from utils.infrastructure.logging.kaia_logger import log_debug, log_warning


# ── Reaction Pools ───────────────────────────────────────────────────────────
# Curated for Kaia's personality: dry, understated, never cutesy.

_POSITIVE_REACTIONS = ["👀", "💯", "🫡", "✨"]
_FUNNY_REACTIONS = ["💀", "😭", "🫠"]
_THOUGHTFUL_REACTIONS = ["🤔", "👀", "💭"]
_AFFIRMATION_REACTIONS = ["❤️", "🫂", "🩵"]
_DISAGREEMENT_REACTIONS = ["🫤", "😐"]

# Keyword → reaction pool mapping (lightweight, no LLM)
_REACTION_TRIGGERS = {
    "positive": {
        "keywords": {"lol", "lmao", "haha", "funny", "nice", "cool", "awesome",
                     "love", "based", "goated", "fire", "peak"},
        "pool": _FUNNY_REACTIONS + _POSITIVE_REACTIONS,
    },
    "affection": {
        "keywords": {"thank", "thanks", "appreciate", "grateful", "love you",
                     "missed you", "glad", "happy"},
        "pool": _AFFIRMATION_REACTIONS,
    },
    "thinking": {
        "keywords": {"interesting", "hmm", "wonder", "curious", "what if",
                     "theory", "idea", "hypothesis"},
        "pool": _THOUGHTFUL_REACTIONS,
    },
}


class KaiaReactions:
    """Manages Kaia's emoji reactions on Discord messages."""

    def __init__(self):
        self._last_reaction_time: float = 0.0
        self._reaction_count_hour: int = 0
        self._hour_start: float = time.time()
        self._last_reacted_message_id: Optional[int] = None

    def _reset_hourly_counter(self):
        """Reset the hourly counter if an hour has passed."""
        now = time.time()
        if now - self._hour_start >= 3600:
            self._reaction_count_hour = 0
            self._hour_start = now

    def should_react(self, message: discord.Message) -> bool:
        """Determine if Kaia should react to this message.
        
        Rate limits:
        - Max 4 reactions per hour
        - Min 120 seconds between reactions  
        - Never on consecutive messages (same author, same channel)
        - Never on bot messages
        """
        if message.author.bot:
            return False

        self._reset_hourly_counter()

        if self._reaction_count_hour >= 4:
            return False

        now = time.time()
        if now - self._last_reaction_time < 120:
            return False

        # Never react to consecutive messages from the same interaction
        if message.id == self._last_reacted_message_id:
            return False

        return True

    def pick_reaction(self, content: str) -> Optional[str]:
        """Pick a contextually appropriate emoji for the message content.
        
        Returns None if no good match is found (Kaia doesn't force reactions).
        """
        content_lower = content.lower()

        # Check each trigger category
        for category, config in _REACTION_TRIGGERS.items():
            for keyword in config["keywords"]:
                if keyword in content_lower:
                    return config["pool"][secrets.randbelow(len(config["pool"]))]

        # No match — Kaia doesn't react to everything. That's the point.
        return None

    async def maybe_react(self, message: discord.Message) -> bool:
        """Attempt to add an emoji reaction to a message.
        
        Returns True if a reaction was added.
        """
        if not self.should_react(message):
            return False

        emoji = self.pick_reaction(message.content)
        if not emoji:
            return False

        # Probabilistic gate — only react ~30% of the time even when triggered
        if secrets.randbelow(100) >= 30:
            return False

        try:
            await message.add_reaction(emoji)
            self._last_reaction_time = time.time()
            self._reaction_count_hour += 1
            self._last_reacted_message_id = message.id
            log_debug(f"Reacted with {emoji} to message from {message.author.name}")
            return True
        except discord.HTTPException as e:
            log_warning(f"Reaction failed: {e}")
            return False
        except Exception:
            return False
