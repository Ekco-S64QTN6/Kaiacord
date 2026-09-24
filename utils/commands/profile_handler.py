"""'kaia, who do you know?' — the people she has logs for, by name only.

Profiles are her internal notes on people and are never posted; this answers
with names. Forum users are counted rather than listed: there are hundreds.
"""
import asyncio
import re
from pathlib import Path
from typing import List, Tuple

from utils.infrastructure.logging.kaia_logger import log_info

LOGS_DIR = Path("./knowledge_base/user_logs")

_PATTERNS = [re.compile(p) for p in (
    r"kaia\s+(list|show|display)\s+(all\s+)?(users?|profiles?|known users?)",
    r"kaia\s+who\s+do\s+you\s+know",
    r"kaia\s+who\s+is\s+(on\s+this\s+server|here)",
)]


def _name(folder: str) -> str:
    """`Tenno_Henka_919782120308752425` -> `Tenno Henka`."""
    head, _, tail = folder.rpartition("_")
    return (head if tail.isdigit() else folder).replace("_", " ")


def get_known_users() -> Tuple[List[str], int]:
    """(Discord names, number of forum users) from the user_logs folders."""
    if not LOGS_DIR.exists():
        return [], 0
    names, forum = set(), 0
    for d in LOGS_DIR.iterdir():
        if not d.is_dir() or d.name.startswith((".", "_")):
            continue
        if d.name.startswith("forum_"):
            forum += 1
        elif not d.name.startswith("Kaia-"):      # her own channel log, not a person
            names.add(_name(d.name))
    return sorted(names, key=str.lower), forum


def is_user_list_query(text: str) -> bool:
    q = text.lower().strip()
    return len(q) < 100 and any(p.search(q) for p in _PATTERNS)


async def handle_profile_query(msg, sanitized_content, send_kaia_response, run_rag, rag):
    """Answer an explicit 'who do you know' with names. True if handled."""
    if not is_user_list_query(sanitized_content):
        return False
    names, forum = await asyncio.to_thread(get_known_users)
    log_info(f"User list query: {len(names)} Discord users, {forum} forum users")
    if names:
        response_text = f"people i know here: {', '.join(names)}."
        if forum:
            response_text += f" and {forum} from the project 1999 forums."
    else:
        response_text = "i don't have logs for anyone yet."
    await send_kaia_response(msg.channel, response_text)
    if run_rag and rag:
        await run_rag(rag.log_user_interaction, msg.author.id, msg.author.display_name,
                      sanitized_content, response_text)
    return True
