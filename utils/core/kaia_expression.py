"""What Kaia makes, remembered as something she did.

A piece of art or a music set used to leave no trace in her: the image was
saved to disk and the set was logged, but neither reached anything she reads.
Asked about it a minute later, she had no idea she had made anything.

`remember` writes a first-person line into the channel's conversation memory
(so it is in her history on the next turn) and an event into the growth log
(the long-term ledger the presence status and dream prompts read).
"""
from __future__ import annotations

import json
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
            from collections import deque
            from utils.infrastructure.system.bot_state import bot_state
            from utils.infrastructure.system.yaml_config import config
            memory = bot_state.channel_memory
            if channel_id not in memory:
                memory[channel_id] = deque(maxlen=config.max_memory_messages)
            memory[channel_id].append({"role": "assistant", "content": line,
                                       "timestamp": time.time()})
        except Exception as e:
            log_debug(f"[expression] channel memory not updated: {e}")

    try:
        event = {"type": "creation", "kind": kind, "title": title,
                 "summary": line[:300], "ts": time.time()}
        if detail:
            event["detail"] = detail
        with open(telemetry_path("memory/growth_log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        log_debug(f"[expression] growth log not updated: {e}")
