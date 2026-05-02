"""
Kaia Presence Manager
=====================

Maps Kaia's internal mood state to visible Discord presence.
Users see a status dot (online/idle/dnd) and a custom activity
message under Kaia's name in the member list.

Update cadence: every 5 minutes via background task, plus
immediate updates on significant state changes (dream start/end,
first message after long idle).
"""

import asyncio
import secrets
import time
from datetime import datetime
from typing import Optional

import discord
from discord.ext import tasks

from utils.infrastructure.logging.kaia_logger import log_action, log_debug, log_info, log_warning
from utils.infrastructure.system.yaml_config import config


# ── Activity Text Pools ─────────────────────────────────────────────────────
# Curated in Kaia's voice: lowercase, blunt, no emoji spam.

_IDLE_TEXTS = [
    "quiet day. thinking.",
    "letting things settle.",
    "listening to the hum.",
    "nothing urgent. just here.",
    "still. not gone.",
    "sitting with it.",
    "not much to say right now.",
]

_ACTIVE_TEXTS = [
    "in conversation.",
    "busy day.",
    "people are talking.",
    "active.",
    "present.",
]

_POST_DREAM_TEXTS = [
    "just woke up. processing.",
    "fresh from dreaming.",
    "still sorting through last night.",
    "memories settling.",
]

_DEGRADED_TEXTS = [
    "memory's patchy today.",
    "index needs work.",
    "something's off. working on it.",
    "fuzzy.",
]

_DREAMING_TEXTS = [
    "dreaming...",
    "sleeping.",
    "processing. don't wait up.",
    "nightly cycle.",
]

_BOOTING_TEXTS = [
    "waking up...",
    "booting.",
    "getting my bearings.",
]


class KaiaPresenceManager:
    """Manages Kaia's Discord presence based on internal mood state."""

    def __init__(self, bot: discord.Client, bot_state):
        self.bot = bot
        self.bot_state = bot_state
        self._last_status_text: str = ""
        self._last_status_type: discord.Status = discord.Status.online
        self._last_update_time: float = 0.0
        self._force_update: bool = False
        self._override_text: Optional[str] = None
        self._override_status: Optional[discord.Status] = None
        self._override_until: float = 0.0

    def _pick_random(self, pool: list) -> str:
        """Pick a random item from a pool using secrets for consistency with project standards."""
        return pool[secrets.randbelow(len(pool))]

    def get_mood_activity(self) -> tuple[discord.Status, str]:
        """Determine the appropriate status dot and activity text from current mood state.
        
        Returns:
            (discord.Status, activity_text_string)
        """
        now = time.time()

        # 1. Check for active overrides (dream cycle, boot, etc.)
        if self._override_text and now < self._override_until:
            return (
                self._override_status or discord.Status.idle,
                self._override_text
            )

        # 2. Dream hours — force sleeping status
        current_hour = datetime.now().hour
        dream_start = config.get('dream_mode.schedule_start_hour', 3)
        dream_end = config.get('dream_mode.schedule_end_hour', 5)
        if dream_start <= current_hour < dream_end:
            return discord.Status.idle, self._pick_random(_DREAMING_TEXTS)

        # 3. Read mood floats from bot_state
        engagement = getattr(self.bot_state, 'kaia_engagement', 0.5)
        coherence = getattr(self.bot_state, 'kaia_coherence', 0.85)
        dream_freshness = getattr(self.bot_state, 'kaia_dream_freshness', 1.0)

        # 4. Determine status dot color
        if coherence < 0.4:
            status = discord.Status.dnd
        elif engagement < 0.3:
            status = discord.Status.idle
        else:
            status = discord.Status.online

        # 5. Determine activity text
        if coherence < 0.4:
            text = self._pick_random(_DEGRADED_TEXTS)
        elif dream_freshness > 0.9 and engagement < 0.4:
            # Just dreamed recently but quiet day
            text = self._pick_random(_POST_DREAM_TEXTS)
        elif engagement >= 0.7:
            text = self._pick_random(_ACTIVE_TEXTS)
        elif engagement <= 0.3:
            text = self._pick_random(_IDLE_TEXTS)
        else:
            # Moderate — mix of idle and active
            pool = _IDLE_TEXTS + _ACTIVE_TEXTS
            text = self._pick_random(pool)

        return status, text

    async def update_presence(self):
        """Push the current mood state to Discord as a presence update.
        
        Rate-limited: won't update more than once per 60 seconds unless forced.
        """
        if not config.get('features.presence_enabled', True):
            return

        now = time.time()
        # Rate limit: min 60s between updates unless forced
        if not self._force_update and (now - self._last_update_time) < 60:
            return

        try:
            status, text = self.get_mood_activity()

            # Skip if nothing changed
            if not self._force_update and text == self._last_status_text and status == self._last_status_type:
                return

            activity = discord.CustomActivity(name=text)
            await self.bot.change_presence(status=status, activity=activity)

            self._last_status_text = text
            self._last_status_type = status
            self._last_update_time = now
            self._force_update = False

            log_debug(f"Presence updated: {status.name} | {text}")
        except Exception as e:
            log_warning(f"Presence update failed: {e}")

    def set_override(self, text: str, status: discord.Status = discord.Status.idle, duration_seconds: float = 300):
        """Set a temporary presence override (e.g., during dream cycle).
        
        Args:
            text: The activity text to display
            status: The status dot color
            duration_seconds: How long the override lasts before reverting to mood-based
        """
        self._override_text = text
        self._override_status = status
        self._override_until = time.time() + duration_seconds
        self._force_update = True

    def clear_override(self):
        """Clear any active override and revert to mood-based presence."""
        self._override_text = None
        self._override_status = None
        self._override_until = 0.0
        self._force_update = True

    def force_update(self):
        """Force the next update_presence() call to push regardless of rate limit."""
        self._force_update = True


def make_presence_task(presence_manager: KaiaPresenceManager):
    """Create the background task loop for periodic presence updates."""

    @tasks.loop(minutes=5)
    async def presence_update_task():
        try:
            await presence_manager.update_presence()
        except Exception as e:
            log_warning(f"Presence task error: {e}")

    @presence_update_task.before_loop
    async def before_presence():
        await presence_manager.bot.wait_until_ready()
        # Brief delay to let boot complete
        await asyncio.sleep(10)

    @presence_update_task.error
    async def presence_error(error):
        log_warning(f"Presence task died: {type(error).__name__}: {error}")

    return presence_update_task
