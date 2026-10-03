"""Where the bot's memory goes over a session: a leak, or a heap that won't shrink.

RSS rose ~80 MB an hour across a long session, in steps that line up with RAG
refreshes, and spiked to ~5 GB whenever Whisper was loaded for the scanner.
Two causes look the same from RSS alone and need different fixes:

- **Python objects kept alive** — the traced total grows with RSS, and
  `tracemalloc` names the lines that allocated them.
- **glibc not handing freed memory back** after big transient allocations
  (a 3 GB model loaded and released, an index rebuilt) — RSS grows while the
  traced total does not, and `malloc_trim(0)` returns it.

Every audit (15 min) takes RSS, trims the heap and records what the trim gave
back, so fragmentation is both measured and undone. With
`diagnostics.memory_trace` on, `tracemalloc` also runs from boot and each
audit records the traced total and the sites that grew most since the first
sample. A snapshot holds the GIL for as long as it takes to walk every traced
block, so it is skipped while anything is playing in voice. Samples go to
`memory/diagnostics/mem_probe.jsonl`; `tools/maintenance/mem_report.py` reads
them.
"""
from __future__ import annotations

import ctypes
import json
import time
from typing import Callable, Optional

from utils.infrastructure.logging.kaia_logger import log_debug, log_info

TRACE_FRAMES = 3
TOP_SITES = 12
_baseline = None
_libc = None


def _rss_mb() -> float:
    import psutil
    return psutil.Process().memory_info().rss / 1024 / 1024


def start_trace(enabled: Optional[bool] = None) -> bool:
    """Start tracemalloc if `diagnostics.memory_trace` (or `enabled`) says so."""
    import tracemalloc
    if enabled is None:
        try:
            from utils.infrastructure.system.yaml_config import config
            enabled = bool(config.get("diagnostics.memory_trace", False))
        except Exception:
            enabled = False
    if enabled and not tracemalloc.is_tracing():
        tracemalloc.start(TRACE_FRAMES)
        log_info(f"[mem] tracemalloc on ({TRACE_FRAMES} frames): the audit will name what grows")
    return tracemalloc.is_tracing()


def trim() -> float:
    """glibc malloc_trim(0): hand freed heap back to the system. MB returned;
    0 where there is no glibc."""
    global _libc
    try:
        if _libc is None:
            _libc = ctypes.CDLL("libc.so.6")
        before = _rss_mb()
        _libc.malloc_trim(0)                # ctypes releases the GIL for the call
        return max(0.0, before - _rss_mb())
    except (OSError, AttributeError):
        return 0.0


def _sites(snapshot) -> list:
    global _baseline
    if _baseline is None:
        _baseline = snapshot
        return []
    stats = snapshot.compare_to(_baseline, "traceback")
    out = []
    for s in stats[:TOP_SITES]:
        if s.size_diff <= 0:
            continue
        frame = s.traceback[-1] if len(s.traceback) else None
        where = f"{frame.filename.split('Kaiacord/')[-1].split('site-packages/')[-1]}:{frame.lineno}" if frame else "?"
        out.append({"site": where, "mb": round(s.size_diff / 1048576, 1), "blocks": s.count_diff})
    return out


def sample(busy: Callable[[], bool] = lambda: False) -> dict:
    """One audit: RSS, the trim, and (tracing) Python's total and growth sites.
    Blocking: run it off the event loop."""
    import tracemalloc
    row = {"ts": time.time(), "rss_mb": round(_rss_mb(), 1)}
    row["trimmed_mb"] = round(trim(), 1)
    row["rss_after_trim_mb"] = round(row["rss_mb"] - row["trimmed_mb"], 1)
    if tracemalloc.is_tracing():
        cur, peak = tracemalloc.get_traced_memory()
        row["traced_mb"] = round(cur / 1048576, 1)
        row["traced_peak_mb"] = round(peak / 1048576, 1)
        if busy():
            row["sites"] = "skipped: voice playing"
        else:
            t = time.perf_counter()
            row["sites"] = _sites(tracemalloc.take_snapshot())
            row["snapshot_ms"] = round((time.perf_counter() - t) * 1000)
    try:
        from utils.infrastructure.monitoring.telemetry_paths import telemetry_path
        from pathlib import Path
        path = Path(telemetry_path("memory/diagnostics/mem_probe.jsonl"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception as e:
        log_debug(f"[mem] sample not written: {e}")
    return row


def describe(row: dict) -> str:
    text = f"Memory Audit: RSS {row['rss_mb']:.1f} MB"
    if row.get("trimmed_mb", 0) >= 1:
        text += f" (malloc_trim gave back {row['trimmed_mb']:.0f} MB → {row['rss_after_trim_mb']:.0f} MB)"
    if "traced_mb" in row:
        text += f"; Python traced {row['traced_mb']:.0f} MB"
        sites = row.get("sites")
        if isinstance(sites, list) and sites:
            text += "; grew most: " + ", ".join(f"{s['site']} +{s['mb']:g} MB" for s in sites[:3])
    return text
