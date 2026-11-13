"""Structured diagnostics for partial RPG record-directory scans."""
from __future__ import annotations

import os
import re
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
            f"{failure.path} [owner={failure.owner_id or 'unknown'}] ({failure.reason})"
            for failure in fresh[:10]
        )
        remaining = len(fresh) - 10
        if remaining > 0:
            details += f"; and {remaining} more"
        log_warning(
            f"[rpg storage] {store_name} scan incomplete: "
            f"{len(fresh)} new failure(s) reported; {details}"
        )


_RECORD_ID = re.compile(r"[A-Za-z0-9_\-]{1,64}")


def safe_record_id(value) -> str:
    """An id that is safe to put in a record's file name.

    Per-player records are named `<id>.json`. Ids come from Discord, but one
    command passed typed text straight through, and `../../x` read any `.json`
    file the bot could open. No separator or dot is ever part of an id."""
    text = str(value)
    if not _RECORD_ID.fullmatch(text):
        raise ValueError(f"not a valid record id: {text[:40]!r}")
    return text
