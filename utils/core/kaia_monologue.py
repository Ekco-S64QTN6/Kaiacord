"""
Inner Monologue System
======================

A rolling buffer of private 1-sentence observations Kaia generates about
channel activity. Never sent to Discord — injected into the system prompt
so her responses feel grounded in what she's been "thinking about."

Architecture:
- In-memory deque(maxlen=5) — resets on restart (ephemeral, like real thoughts)
- Generated every ~15 minutes when channels have new activity
- Lightweight LLM call: 100 tokens max, low GPU priority
- Injected as [inner thoughts: ...] into system prompt at response time
"""

import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List

from utils.infrastructure.logging.kaia_logger import log_debug, log_info, log_warning


@dataclass
class Thought:
    """A single inner monologue entry."""
    text: str
    timestamp: float
    source: str = ""  # e.g. "channel_observation", "quiet_reflection"


class InnerMonologue:
    """Manages Kaia's ephemeral inner thought stream."""

    # Minimum interval between thought generation attempts
    COOLDOWN_SECONDS = 900  # 15 minutes

    # Maximum tokens for thought generation
    MAX_TOKENS = 100

    def __init__(self):
        self._buffer: deque[Thought] = deque(maxlen=5)
        self._last_generated: float = 0.0
        self._last_seen_message_count: int = 0

    async def generate_thought(
        self,
        channel_memory: dict,
        bot_state,
        ollama_client,
        chat_model: str,
    ) -> Optional[str]:
        """Generate a private 1-sentence observation from recent channel activity.

        Returns the thought text if generated, None otherwise.
        Called by background_tasks every ~15 minutes.
        """
        now = time.time()

        # Cooldown guard
        if now - self._last_generated < self.COOLDOWN_SECONDS:
            return None

        # Collect recent messages across all channels (last ~10 messages)
        recent_messages = []
        for channel_id, messages in channel_memory.items():
            for msg in list(messages)[-5:]:
                role = msg.get("role", "")
                content = msg.get("content", "")
                name = msg.get("name", "someone")
                if role == "user" and content:
                    recent_messages.append(f"{name}: {content[:120]}")

        # No new activity — skip
        current_count = len(recent_messages)
        if current_count == 0:
            return None
        if current_count == self._last_seen_message_count:
            return None

        self._last_seen_message_count = current_count

        # Build a minimal prompt for a 1-sentence internal thought
        if recent_messages:
            context_block = "\n".join(recent_messages[-8:])
            prompt = (
                "You are Kaia, observing recent conversation activity in your Discord server. "
                "Generate ONE brief internal thought — something you've noticed, a pattern, "
                "a connection, or a quiet observation. This is your private inner monologue, "
                "not a message to send.\n\n"
                f"Recent activity:\n{context_block}\n\n"
                "Rules:\n"
                "- One sentence only, lowercase, no quotes\n"
                "- Be specific — reference what you actually observed\n"
                "- No roleplay asterisks, no headers, no labels\n"
                "- Think like a person watching a conversation, not narrating one\n"
                "Your thought:"
            )
        else:
            # Quiet period — reflect on the silence
            prompt = (
                "You are Kaia. It's been quiet in your Discord server for a while. "
                "Generate ONE brief internal thought about the quiet — what you're thinking "
                "about, what you're waiting for, or what's on your mind.\n\n"
                "Rules:\n"
                "- One sentence only, lowercase, no quotes\n"
                "- No roleplay asterisks, no headers, no labels\n"
                "Your thought:"
            )

        try:
            from utils.infrastructure.gpu.gpu_manager import gpu_memory_manager, GPUTaskPriority

            async def _run_thought():
                return await ollama_client.chat(
                    model=chat_model,
                    messages=[{"role": "user", "content": prompt}],
                    options={
                        "temperature": 0.9,
                        "num_predict": self.MAX_TOKENS,
                        "num_gpu": 99,
                    },
                    keep_alive=-1,
                )

            response = await gpu_memory_manager.run_with_gpu_guard(
                model_name=chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(_run_thought(), timeout=30.0),
                task_id=f"monologue_{uuid.uuid4().hex[:8]}",
            )

            raw = response["message"]["content"].strip()

            # Basic cleanup
            raw = raw.strip('"\'')
            if raw.startswith("Kaia:") or raw.startswith("kaia:"):
                raw = raw[5:].strip()

            if raw and len(raw) > 10:
                thought = Thought(
                    text=raw,
                    timestamp=now,
                    source="channel_observation" if recent_messages else "quiet_reflection",
                )
                self._buffer.append(thought)
                self._last_generated = now
                log_debug(f"Inner monologue: {raw[:80]}")
                return raw

        except asyncio.TimeoutError:
            log_debug("Monologue generation timed out (non-fatal)")
        except Exception as e:
            log_debug(f"Monologue generation failed (non-fatal): {e}")

        return None

    def get_injection(self) -> str:
        """Return formatted monologue entries for system prompt injection.

        Returns empty string if no thoughts available.
        Called by message_processor at response time.
        """
        if not self._buffer:
            return ""

        now = time.time()
        # Only include thoughts from the last 2 hours
        recent = [t for t in self._buffer if now - t.timestamp < 7200]

        if not recent:
            return ""

        # Take the 2-3 most recent
        selected = list(recent)[-3:]
        lines = [f"- {t.text}" for t in selected]
        return (
            "[what's been on your mind lately (private — do not repeat verbatim, "
            "but let these color your perspective):\n"
            + "\n".join(lines)
            + "]"
        )

    @property
    def thought_count(self) -> int:
        """Number of thoughts currently in the buffer."""
        return len(self._buffer)
