"""Low-overhead process-local metrics for long-lived asyncio lock registries."""

from __future__ import annotations

import asyncio
import threading
import time

_guard = threading.Lock()
_metrics: dict[str, dict[str, float | int]] = {}


def _entry(registry: str) -> dict[str, float | int]:
    return _metrics.setdefault(
        registry,
        {
            "created": 0,
            "current": 0,
            "peak": 0,
            "acquisitions": 0,
            "contended": 0,
            "wait_ms_total": 0.0,
            "wait_ms_max": 0.0,
        },
    )


def record_registry_lock_created(registry: str, current_size: int) -> None:
    """Record one lock insertion and the registry's resulting size."""
    with _guard:
        metric = _entry(registry)
        metric["created"] = int(metric["created"]) + 1
        metric["current"] = int(current_size)
        metric["peak"] = max(int(metric["peak"]), int(current_size))


def _record_acquisition(registry: str, contended: bool, wait_ms: float) -> None:
    with _guard:
        metric = _entry(registry)
        metric["acquisitions"] = int(metric["acquisitions"]) + 1
        if contended:
            metric["contended"] = int(metric["contended"]) + 1
            metric["wait_ms_total"] = float(metric["wait_ms_total"]) + wait_ms
            metric["wait_ms_max"] = max(float(metric["wait_ms_max"]), wait_ms)


class MeasuredAsyncLock(asyncio.Lock):
    """An asyncio lock that records acquisition contention without changing semantics."""

    def __init__(self, registry: str):
        super().__init__()
        self._metric_registry = registry

    async def acquire(self) -> bool:
        contended = self.locked()
        started = time.perf_counter()
        acquired = await super().acquire()
        if acquired:
            _record_acquisition(
                self._metric_registry,
                contended,
                (time.perf_counter() - started) * 1000.0 if contended else 0.0,
            )
        return acquired


def lock_registry_snapshot() -> dict[str, dict[str, float | int]]:
    """Return a detached snapshot; callers cannot mutate the live counters."""
    with _guard:
        return {name: dict(values) for name, values in _metrics.items()}


def format_lock_registry_metrics() -> str:
    """Small, identity-free report suitable for the owner-only !sysmon output."""
    snapshot = lock_registry_snapshot()
    if not snapshot:
        return "No RPG lock-registry activity recorded in this process."

    labels = {
        "rpg_action": "Action locks",
        "rpg_session": "Session I/O locks",
        "rpg_character": "Character locks",
    }
    rows = []
    for name in ("rpg_action", "rpg_session", "rpg_character"):
        metric = snapshot.get(name)
        if metric is None:
            continue
        rows.append(
            f"• **{labels[name]}:** current {metric['current']} / peak {metric['peak']} "
            f"({metric['created']} created); {metric['contended']} contended acquisitions, "
            f"max wait {float(metric['wait_ms_max']):.1f} ms"
        )
    return "\n".join(rows) if rows else "No RPG lock-registry activity recorded in this process."
