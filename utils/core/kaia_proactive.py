"""
Proactive Conversation Initiation
==================================

Kaia occasionally speaks first — triggered by knowledge ingestion, user
absence, dream insights, or observed conversations. Heavily rate-limited
to avoid annoyance.

Guardrails:
- Maximum 2 proactive messages per 24-hour period globally
- Only post in channels where Kaia has recently been active
- Time gate: only between 9 AM – 10 PM local time
- Minimum 4 hours between proactive messages
- Natural, casual openers — never pushy
"""

import asyncio
import time
import uuid
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from utils.infrastructure.logging.kaia_logger import (
    log_debug, log_info, log_warning, log_success,
)

# ── Rate Limiting Constants ─────────────────────────────────────────
MAX_DAILY_PROACTIVE = 2
MIN_INTERVAL_SECONDS = 4 * 3600  # 4 hours between proactive messages
QUIET_HOUR_START = 9   # 9 AM
QUIET_HOUR_END = 22    # 10 PM
ABSENCE_THRESHOLD_DAYS = 3  # User must be gone this long to trigger


@dataclass
class ProactiveTrigger:
    """A resolved trigger that should produce a proactive message."""
    trigger_type: str  # "absence", "knowledge", "dream_insight", "observation"
    channel_id: int
    context: str       # Brief context for the LLM prompt
    target_user: Optional[str] = None  # Display name, if user-specific


class ProactiveEngine:
    """Evaluates trigger conditions and generates proactive conversation starters."""

    def __init__(self):
        self._last_trigger_type: Optional[str] = None

    def _is_within_hours(self) -> bool:
        """Check if current time is within the allowed proactive window."""
        hour = datetime.now().hour
        return QUIET_HOUR_START <= hour < QUIET_HOUR_END

    def _is_rate_limited(self, bot_state) -> bool:
        """Check if we've exceeded daily or interval limits."""
        now = time.time()
        today = datetime.now().strftime('%Y-%m-%d')

        # Reset daily count if new day
        last_date = getattr(bot_state, 'last_proactive_date', '')
        if last_date != today:
            bot_state.proactive_daily_count = 0
            bot_state.last_proactive_date = today

        # Daily cap
        if getattr(bot_state, 'proactive_daily_count', 0) >= MAX_DAILY_PROACTIVE:
            return True

        # Minimum interval
        last_sent = getattr(bot_state, 'proactive_last_sent', 0.0)
        if now - last_sent < MIN_INTERVAL_SECONDS:
            return True

        return False

    def _find_active_channel(self, bot_state) -> Optional[int]:
        """Find the most recently active channel where Kaia has spoken.

        Returns the channel ID or None if no suitable channel found.
        """
        if not bot_state.channel_last_activity:
            return None

        # Sort channels by recency, pick the most recent one
        # that has had activity in the last 24 hours
        now = time.time()
        candidates = [
            (ch_id, ts) for ch_id, ts in bot_state.channel_last_activity.items()
            if now - ts < 86400  # Active in last 24h
        ]
        if not candidates:
            return None

        # Most recently active channel
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    async def evaluate_triggers(
        self,
        bot_state,
        dream_engine=None,
    ) -> Optional[ProactiveTrigger]:
        """Evaluate all trigger conditions and return the best one, or None.

        Called by background_tasks every ~30 minutes.
        """
        if not self._is_within_hours():
            return None

        if self._is_rate_limited(bot_state):
            return None

        channel_id = self._find_active_channel(bot_state)
        if not channel_id:
            return None

        # ── Trigger 1: User Absence ─────────────────────────────
        # A regular user (>25 interactions) hasn't been seen in 3+ days
        try:
            now = time.time()
            for user_id, rel in bot_state.relationships.items():
                count = rel.get('interaction_count', 0)
                last_seen = rel.get('last_seen', 0)
                if count >= 25 and last_seen > 0:
                    days_absent = (now - last_seen) / 86400
                    if days_absent >= ABSENCE_THRESHOLD_DAYS:
                        # Check if we already triggered for this absence
                        last_proactive_for = rel.get('last_proactive_checkin', 0)
                        if now - last_proactive_for > 7 * 86400:  # Max once per week per user
                            # display_name may not exist in older relationship records
                            user_name = rel.get('display_name') or f'user {user_id[-4:]}'
                            return ProactiveTrigger(
                                trigger_type="absence",
                                channel_id=channel_id,
                                context=(
                                    f"{user_name} hasn't been around for "
                                    f"{int(days_absent)} days. You've had "
                                    f"{count} conversations with them."
                                ),
                                target_user=user_name,
                            )
        except Exception as e:
            log_debug(f"Absence trigger check failed (non-fatal): {e}")

        # ── Trigger 2: Recent Knowledge Ingestion ───────────────
        # A document was recently ingested that Kaia could comment on
        try:
            recent = getattr(bot_state, 'recent_ingestions', [])
            if recent:
                # recent_ingestions entries are dicts: {filename, snippet, timestamp}
                latest_entry = recent[-1]
                if isinstance(latest_entry, dict):
                    latest = latest_entry.get('filename', str(latest_entry))
                else:
                    latest = str(latest_entry)
                return ProactiveTrigger(
                    trigger_type="knowledge",
                    channel_id=channel_id,
                    context=(
                        f"You recently read something new: '{latest}'. "
                        f"You found it interesting and want to mention it casually."
                    ),
                )
        except Exception as e:
            log_debug(f"Knowledge trigger check failed (non-fatal): {e}")

        # ── Trigger 3: Dream Insight ────────────────────────────
        # The last dream cycle produced a belief revision worth sharing
        try:
            from pathlib import Path
            import json
            growth_log = Path("memory") / "growth_log.jsonl"
            if growth_log.exists():
                size = growth_log.stat().st_size
                if size > 0:
                    with open(growth_log, 'r', encoding='utf-8') as f:
                        f.seek(max(0, size - 2000))
                        tail = f.read()
                    lines = tail.strip().splitlines()
                    for line in reversed(lines[-5:]):
                        try:
                            evt = json.loads(line)
                            if evt.get('type') == 'belief_revised':
                                age = time.time() - evt.get('ts', 0)
                                if age < 86400:  # Within last 24h
                                    topic = evt.get('topic', '')
                                    new_pos = evt.get('new_position', '')
                                    if topic and new_pos:
                                        return ProactiveTrigger(
                                            trigger_type="dream_insight",
                                            channel_id=channel_id,
                                            context=(
                                                f"You recently changed your mind about '{topic}'. "
                                                f"Your new take: '{new_pos[:120]}'. "
                                                f"Mention it like you've been mulling it over."
                                            ),
                                        )
                        except Exception:
                            continue
        except Exception as e:
            log_debug(f"Dream insight trigger check failed (non-fatal): {e}")

        return None

    async def generate_opener(
        self,
        trigger: ProactiveTrigger,
        ollama_client,
        chat_model: str,
        persona: str,
    ) -> Optional[str]:
        """Generate a natural conversation opener from a trigger.

        Returns the message text, or None on failure.
        """
        type_instructions = {
            "absence": (
                f"You haven't seen {trigger.target_user} in a while. "
                f"Generate a casual, low-key check-in. Not clingy — just noticing they've been gone. "
                f"Example tone: 'hey {trigger.target_user}, been quiet without you around. everything good?'"
            ),
            "knowledge": (
                "You read something new and want to share a thought about it. "
                "Don't summarize the whole thing — just mention one interesting angle. "
                "Example tone: 'just read something interesting about X. made me think about...'"
            ),
            "dream_insight": (
                "You've been thinking about something and your perspective shifted. "
                "Share it like you've been mulling it over — not like you're announcing a thesis. "
                "Example tone: 'been thinking about this and i changed my mind about...'"
            ),
            "observation": (
                "You noticed something interesting in a conversation you were watching. "
                "Comment on it naturally. "
                "Example tone: 'saw you all talking about X earlier — that's actually...'"
            ),
        }

        instruction = type_instructions.get(trigger.trigger_type, "Share a thought.")

        prompt = (
            f"{persona}\n\n"
            f"CONTEXT: {trigger.context}\n\n"
            f"TASK: {instruction}\n\n"
            f"Rules:\n"
            f"- 1-2 sentences max, lowercase, casual\n"
            f"- No roleplay asterisks, no headers\n"
            f"- Sound like a person who just thought of something, not a bot making an announcement\n"
            f"- Don't start with 'hey everyone' — be specific\n"
            f"Your message:"
        )

        try:
            from utils.infrastructure.gpu.gpu_manager import gpu_memory_manager, GPUTaskPriority

            async def _run_proactive():
                return await ollama_client.chat(
                    model=chat_model,
                    messages=[{"role": "user", "content": prompt}],
                    options={
                        "temperature": 0.85,
                        "num_predict": 150,
                        "num_gpu": 99,
                    },
                    keep_alive=-1,
                )

            response = await gpu_memory_manager.run_with_gpu_guard(
                model_name=chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(_run_proactive(), timeout=45.0),
                task_id=f"proactive_{uuid.uuid4().hex[:8]}",
            )

            raw = response["message"]["content"].strip()

            # Basic cleanup
            raw = raw.strip('"\'')
            if raw.startswith("Kaia:") or raw.startswith("kaia:"):
                raw = raw[5:].strip()

            if raw and len(raw) > 10:
                log_info(f"Proactive opener generated ({trigger.trigger_type}): {raw[:80]}")
                return raw

        except asyncio.TimeoutError:
            log_debug("Proactive generation timed out (non-fatal)")
        except Exception as e:
            log_warning(f"Proactive generation failed: {e}")

        return None

    def record_sent(self, bot_state, trigger: ProactiveTrigger) -> None:
        """Record that a proactive message was sent, updating cooldowns."""
        now = time.time()
        bot_state.proactive_last_sent = now
        bot_state.proactive_daily_count = getattr(bot_state, 'proactive_daily_count', 0) + 1
        bot_state.last_proactive_date = datetime.now().strftime('%Y-%m-%d')

        # For absence triggers, record per-user to avoid spamming
        if trigger.trigger_type == "absence" and trigger.target_user:
            for user_id, rel in bot_state.relationships.items():
                name = rel.get('display_name', '')
                if name == trigger.target_user:
                    rel['last_proactive_checkin'] = now
                    break

        self._last_trigger_type = trigger.trigger_type
        bot_state.save()
