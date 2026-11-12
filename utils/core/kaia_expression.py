"""What Kaia makes, remembered as something she did.

A piece of art or a music set used to leave no trace in her: the image was
saved to disk and the set was logged, but neither reached anything she reads.
Asked about it a minute later, she had no idea she had made anything.

`remember` writes a first-person line into the channel's conversation memory
(so it is in her history on the next turn), an event into the growth log
(the long-term ledger the presence status and dream prompts read), and
discharges her creative need.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from utils.infrastructure.logging.kaia_logger import log_debug
from utils.infrastructure.monitoring.telemetry_paths import telemetry_path


def remember(kind: str, line: str, *, channel_id: Optional[int] = None,
             title: str = "", detail: Optional[dict] = None) -> None:
    """Record something she made. Never raises.

    `line` is written as she would say it ("i made a piece called ..."); it is
    what appears in her conversation history.
    """
    if channel_id is not None:
        try:
            from utils.infrastructure.system.bot_state import bot_state
            from utils.infrastructure.system.yaml_config import config
            # Marked as an event: the prompt shows it as a note of what she
            # did, not as a turn of hers to copy (`events_as_notes`).
            bot_state.append_channel_turn(channel_id, {"role": "assistant", "content": line,
                                       "event": True, "timestamp": time.time()},
                                       maxlen=config.max_memory_messages)
        except Exception as e:
            log_debug(f"[expression] channel memory not updated: {e}")

    try:
        from utils.core.kaia_desires import desire_engine
        desire_engine.observe_creation()
    except Exception as e:
        log_debug(f"[expression] creative need not discharged: {e}")

    try:
        event = {"type": "creation", "kind": kind, "title": title,
                 "summary": line[:300], "ts": time.time()}
        if detail:
            event["detail"] = detail
        from utils.core.growth_log import append_growth_event
        append_growth_event(event, telemetry_path("memory/growth_log.jsonl"))
    except Exception as e:
        log_debug(f"[expression] growth log not updated: {e}")


async def remember_async(kind: str, line: str, *, channel_id: Optional[int] = None,
                         title: str = "", detail: Optional[dict] = None) -> None:
    """Record a creation from an async caller without blocking its event loop."""
    await asyncio.to_thread(
        remember, kind, line, channel_id=channel_id, title=title, detail=detail
    )
