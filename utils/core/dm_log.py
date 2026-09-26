"""Direct messages are kept apart from public conversation.

A DM used to be logged into the same `knowledge_base/user_logs/` files as
public chat, where retrieval serves it to every public reply and the proactive
`personal_memory` source quotes it into the busiest channel. DMs are written
here instead, under `memory/dm_logs/` — never indexed, never quoted.
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

_lock = threading.Lock()


def path_for(user_id) -> Path:
    return Path(telemetry_path(f"memory/dm_logs/{int(user_id) if str(user_id).isdigit() else 'unknown'}.md"))


def record(user_id, user_name: str, said: str, reply: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"[{stamp}] {user_name}: {said}\n"
    if reply.strip():
        text += f"[{stamp}] Kaia: {reply}\n"
    p = path_for(user_id)
    with _lock:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(text + "\n")
