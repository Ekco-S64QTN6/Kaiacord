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
import json
import hashlib
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
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

    # Path for persistent monologue logs
    LOG_PATH = Path("memory") / "monologue_log.jsonl"

    # Minimum interval between thought generation attempts
    COOLDOWN_SECONDS = 900  # 15 minutes

    # Maximum tokens for thought generation
    MAX_TOKENS = 100

    def __init__(self):
        self._buffer: deque[Thought] = deque(maxlen=5)
        self._last_generated: float = 0.0
        self._last_seen_message_count: int = 0
        # sha256 of the exact window last observed; see generate_thought.
        self._last_window_fingerprint: str = ""

    async def generate_thought(
        self,
        channel_memory: dict,
        bot_state,
        ollama_client,
        chat_model: str,
        is_discord_channel=None,
    ) -> Optional[str]:
        """Generate a private 1-sentence observation from recent channel activity.

        Returns the thought text if generated, None otherwise.
        Called by background_tasks every ~15 minutes.
        """
        now = time.time()

        # Cooldown guard
        if now - self._last_generated < self.COOLDOWN_SECONDS:
            return None

        # Collect recent messages across all channels.
        #
        # Two bugs lived here and together produced a monologue stuck on one
        # forum user for a day and a half:
        #
        # 1. `channel_memory` is shared, and forum threads are seeded into it
        #    by `forum_drafting.seed_thread_history` under a key from
        #    `conversation_channel_id` — a plain int, so a thread is not
        #    distinguishable from a channel by its key. Those turns are
        #    formatted exactly like Discord ones ("author: text", role "user").
        #    Live state held 24 Discord turns against 31 forum turns, so "your
        #    Discord server" was mostly the Project 1999 forum.
        # 2. The tail was taken from a concatenation in dict order with no
        #    sort, so whichever channel was inserted last supplied every one of
        #    the final 8 lines. Forum threads are seeded late, so they always
        #    won, and every thought came out about the same poster.
        collected = []
        for channel_id, messages in channel_memory.items():
            # Ground truth beats a marker. `seed_thread_history` now tags forum
            # turns `external`, but turns seeded *before* that was added are
            # still sitting in the persisted bot_state.json carrying no tag —
            # two of four forum channels, 19 turns, which is how a thought
            # about a forum poster reached the log hours after the fix landed.
            # If the caller can ask Discord whether a channel exists, that
            # answer covers legacy entries the marker cannot.
            if is_discord_channel is not None:
                try:
                    if not is_discord_channel(channel_id):
                        continue
                except Exception:
                    pass
            for msg in list(messages)[-5:]:
                if msg.get("external"):
                    continue  # a forum/social turn, not her Discord server
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user" and content:
                    # channel_memory content is prefixed with author name
                    # e.g. "Ekco: hey what's up" — extract the name
                    if ": " in content:
                        name = content.split(": ", 1)[0]
                        text = content.split(": ", 1)[1][:120]
                    else:
                        name = "someone"
                        text = content[:120]
                    try:
                        when = float(msg.get("timestamp") or 0.0)
                    except (TypeError, ValueError):
                        when = 0.0
                    collected.append((when, f"{name}: {text}"))

        # Genuinely most recent, across channels. Turns with no timestamp keep
        # their relative order behind the stamped ones rather than jumping the
        # queue, which is what a plain sort on a missing key would do.
        collected.sort(key=lambda pair: pair[0])
        recent_messages = [text for _, text in collected]

        if not recent_messages:
            return None

        # Has she already thought about exactly this? The guard used to compare
        # `len(recent_messages)` against the previous length — a count, not the
        # content. Two different conversations of the same size were treated as
        # "no new activity" and skipped, while one unchanged conversation whose
        # count shifted by a single message was re-observed as though it were
        # new. That is why the same stale window kept producing another thought
        # about it every fifteen minutes.
        window = recent_messages[-8:]
        fingerprint = hashlib.sha256("\n".join(window).encode("utf-8")).hexdigest()
        if fingerprint == self._last_window_fingerprint:
            return None
        self._last_window_fingerprint = fingerprint
        self._last_seen_message_count = len(recent_messages)

        # Build a minimal prompt for a 1-sentence internal thought
        if recent_messages:
            context_block = "\n".join(window)
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
                "- You MUST write in the first person ('i', 'my'). Never refer to yourself or Kaia in the third person ('she', 'her').\n"
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
                "- You MUST write in the first person ('i', 'my'). Never refer to yourself or Kaia in the third person ('she', 'her').\n"
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

            # Harden output to enforce persona consistency
            from utils.core.response_filter import BotSpeakFilter
            raw = BotSpeakFilter.harden(raw)

            # Plain English. The model reaches for curly quotes and em dashes,
            # nothing downstream folded them, and `json.dumps` escapes them —
            # which is why this log read "bradzax\u2019s".
            from utils.core.sanitizer import to_plain_english
            raw = to_plain_english(raw)

            if raw and len(raw) > 10:
                thought = Thought(
                    text=raw,
                    timestamp=now,
                    source="channel_observation" if recent_messages else "quiet_reflection",
                )
                self._buffer.append(thought)
                self._last_generated = now

                # Persist thought to monologue log file
                try:
                    def _write_log():
                        self.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
                        log_entry = {
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
                            "epoch": now,
                            "source": thought.source,
                            "thought": thought.text
                        }
                        with open(self.LOG_PATH, "a", encoding="utf-8") as f:
                            f.write(json.dumps(log_entry) + "\n")
                    await asyncio.to_thread(_write_log)
                except Exception as ex:
                    log_debug(f"Failed to persist inner monologue (non-fatal): {ex}")

                log_info(f"🧠 Inner monologue: {raw[:80]}...")
                # Delivery is the task's job, not this module's — everything
                # that reaches Discord goes through background_tasks. The text
                # is returned; the monologue task airs it in #kaia-opolis.
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
