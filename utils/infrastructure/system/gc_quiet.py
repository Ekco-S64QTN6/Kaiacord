"""Keep Python's full garbage collection from stalling the voice thread.

discord.py's audio thread must hand over a frame every 20 ms. A full (gen-2)
collection walks every tracked object while holding the GIL, and the bot holds
hundreds of thousands of long-lived ones — the RAG docstores above all — so
each one was a 200–250 ms pause that collected nothing and broke up whatever
was playing. `settle()` collects once and then freezes what survives
(`gc.freeze`), so later collections walk only what is new.

Called once the indices are loaded, and just before any voice playback starts,
where the one collection it costs falls before the first frame. Frozen objects
are still freed by reference counting; only a cycle among them would outlive
its use, and what is frozen here is the long-lived state that is never dropped.
"""
from __future__ import annotations

import gc
import time

from utils.infrastructure.logging.kaia_logger import log_debug


def settle(why: str) -> None:
    t = time.perf_counter()
    gc.collect()
    gc.freeze()
    log_debug(f"[gc] settled for {why}: {gc.get_freeze_count():,} objects frozen "
              f"in {(time.perf_counter() - t) * 1000:.0f} ms")
