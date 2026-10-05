"""Whether Kaia is playing something in a voice channel right now.

discord.py's voice thread has to hand over a frame every 20 ms, and anything
in the bot's process that holds the GIL for tens of milliseconds makes it late
— which listeners hear as the music lagging out. The dream cycle is the worst
of it: each reflection it writes is indexed and the index persisted, and on
5 Oct a records set ran into it and the voice thread came back 60–170 ms late
fifteen times in five minutes. Background work that can wait asks this first
and waits.
"""
from __future__ import annotations


def playing() -> str:
    """What is playing ("records in General"), or "" if nothing is."""
    try:
        from utils.audio import records
        for s in list(records._sessions.values()):
            if not getattr(s, "_closing", False):
                return f"records in {s.channel_name}"
    except Exception:
        pass
    try:
        from utils.audio import strudel_session
        for s in strudel_session.active_sessions():
            ch = getattr(getattr(getattr(s, "vc", None), "channel", None), "name", "voice")
            return f"a live set in {ch}"
    except Exception:
        pass
    try:
        from utils.radio import live
        for s in live.active():
            ch = getattr(getattr(getattr(s, "vc", None), "channel", None), "name", "voice")
            return f"the radio in {ch}"
    except Exception:
        pass
    return ""


def music() -> str:
    """A records set or a live set playing ("records in General"), or "" —
    what the radio's own background listening yields to (the radio playing in
    voice is that listening itself)."""
    busy = playing()
    return "" if busy.startswith("the radio") else busy


async def wait_until_quiet(what: str, max_wait_s: float, poll_s: float = 120.0) -> bool:
    """Wait (polling) until nothing is playing; True when quiet, False if still
    playing after `max_wait_s`. Says once that it is waiting, and why."""
    import asyncio
    import time
    from utils.infrastructure.logging.kaia_logger import log_info
    busy = playing()
    if not busy:
        return True
    log_info(f"{what} waiting: {busy} is playing; it runs when the music stops")
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        await asyncio.sleep(poll_s)
        if not playing():
            log_info(f"{what}: the music stopped, starting now")
            return True
    log_info(f"{what} skipped: {playing() or 'music'} was still playing after {max_wait_s / 3600:.0f} h")
    return False
