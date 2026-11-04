"""Structured diagnostics for partial RPG record-directory scans."""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class ScanFailure:
    path: str
    owner_id: str | None
    reason: str


@dataclass
class ScanReport:
    records: list[dict]
    failures: list[ScanFailure]

    @property
    def complete(self) -> bool:
        return not self.failures


_logged_failures: set[tuple[str, str, str, int | None, int | None]] = set()
_log_lock = threading.Lock()


def log_scan_failures(store_name: str, report: ScanReport) -> None:
    """Warn once per distinct damaged-file version while preserving scan results."""
    if not report.failures:
        return

    fresh = []
    with _log_lock:
        for failure in report.failures:
            try:
                stat = os.stat(failure.path)
                mtime_ns, size = stat.st_mtime_ns, stat.st_size
            except OSError:
                mtime_ns, size = None, None
            key = (store_name, failure.path, failure.reason, mtime_ns, size)
            if key not in _logged_failures:
                _logged_failures.add(key)
                fresh.append(failure)

    if fresh:
        from utils.infrastructure.logging.kaia_logger import log_warning
        details = "; ".join(
            f"{failure.path} ({failure.reason})" for failure in fresh[:10]
        )
        remaining = len(fresh) - 10
        if remaining > 0:
            details += f"; and {remaining} more"
        log_warning(
            f"[rpg storage] {store_name} scan incomplete: "
            f"{len(report.failures)} record(s) skipped; {details}"
        )
