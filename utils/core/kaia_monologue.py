"""
Inner Monologue System
======================

A rolling buffer of private one-sentence observations Kaia makes about
channel activity. They are injected into her system prompt, so her replies are
coloured by what she has been thinking about, and are also offered to the
shared unprompted system (utils/core/unprompted.py), which posts them to
#kaia-opolis when `unprompted.sources.monologue` is on.

- In-memory deque(maxlen=5): resets on restart, like real thoughts
- At most one every 15 minutes, and only when the conversation has changed
- A short model call (100 tokens) through the GPU guard
- Every thought is appended to memory/monologue_log.jsonl
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
    source: str = ""  # "channel_observation"


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
        # sha256 of the window last thought about; see generate_thought.
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

        # Collect recent messages across all channels. Two properties matter:
        #
        # 1. Forum threads must be filtered out. `channel_memory` is shared and
        #    `forum_drafting.seed_thread_history` seeds threads into it under an
        #    int key, indistinguishable from a channel id, with turns formatted
        #    exactly like Discord ones — so unfiltered, "your Discord server" is
        #    mostly the forum.
        # 2. The tail must be sorted by time. Taken from a concatenation in dict
        #    order, whichever channel was inserted last supplies every line, and
        #    every thought comes out about the same person.
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

        # Has she already thought about exactly this? Compared on content, not
        # on `len(recent_messages)`: a count treats two different conversations
        # of the same size as unchanged, and one unchanged conversation as new
        # the moment a single message shifts the total.
        window = recent_messages[-8:]
        fingerprint = hashlib.sha256("\n".join(window).encode("utf-8")).hexdigest()
        if fingerprint == self._last_window_fingerprint:
            return None

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

        try:
            from utils.infrastructure.gpu.gpu_manager import gpu_memory_manager, GPUTaskPriority, chat_options

            async def _run_thought():
                return await ollama_client.chat(
                    model=chat_model,
                    messages=[{"role": "user", "content": prompt}],
                    options=chat_options(temperature=0.9, num_predict=self.MAX_TOKENS),
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
                thought = Thought(text=raw, timestamp=now, source="channel_observation")
                self._buffer.append(thought)
                self._last_generated = now
                # Marked as thought about only once there is a thought. Set
                # before the call, a timeout meant the same conversation was
                # never tried again.
                self._last_window_fingerprint = fingerprint

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
