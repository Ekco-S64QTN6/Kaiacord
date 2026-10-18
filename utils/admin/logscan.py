"""Kaiacord's log, read into dated events.

`logs/kaiacord.log` stamps each line with a time of day only. Dates are
recovered by walking a file backwards from its last line, anchored at the file's
modification time: going back, a clock that jumps forward by more than twelve
hours has crossed a midnight. That holds while the bot writes something every
day; a gap of more than a day without a line would shift what is before it by a
day. The rotated `kaiacord.log.1` is read the same way, anchored at its own time.

A boot is the "Unified logging system initialized" marker followed by the VRAM
flush line; the marker alone also fires when a tool reconfigures logging
mid-run (CLAUDE.md §9). Test runs log elsewhere, but a segment carrying test
fixtures (MagicMock, test-model, "(case test)") is flagged anyway.
"""
from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

LINE = re.compile(r"^\[(\d\d):(\d\d):(\d\d)\] ([A-Z]+): ?(.*)$")
LEVELS = ("DEBUG", "INFO", "SUCCESS", "ACTION", "WARNING", "ERROR", "CRITICAL")

TOKEN = re.compile(r"\[TOKEN_DEBUG\] prompt_eval_count=(\d+) eval_count=(\d+) num_ctx=(\d+)")
LATENCY = re.compile(r"TOTAL processing for (.+?): ([\d.]+)s")
RETRIEVAL = re.compile(r"Retrieval confidence: ([\d.]+) \((\d+) nodes\)")
GPU = re.compile(r"\[([a-z][a-z_]*?)_[0-9a-f]{8}\] Finished in ([\d.]+)s")
RSS = re.compile(r"Memory Audit: RSS ([\d.]+) MB(?: \(malloc_trim gave back (\d+) MB)?")
UNPROMPTED = re.compile(r"\[unprompted\] (\w+) posted as (.+?)(?::\*\*| \+|$)")
SLOW = re.compile(r"Slow response: on_message took ([\d.]+)s")
GUARD = re.compile(r"\[([A-Z][A-Z_ ]{2,}(?:GUARD|COLLAPSE|WATCHDOG|REPLAY|FILTER))\]")
RECORDS_PLAN = re.compile(r"\[records\] planned: (\w+) into")
VOICE_LATE = re.compile(r"\[records\] voice thread (\d+) ms")
SCANNER = re.compile(r"\[scanner\] (voice|data|carrier|noise) on ([\d.]+) MHz")
INTENT = re.compile(r"Fast-path intent: (\w+) \((\w+)\)")
BOOT = "Unified logging system initialized"
BOOT_CONFIRM = "Ensuring all models are flushed from VRAM"
SHUTDOWN = "Shutting down..."
FIXTURE = re.compile(r"MagicMock|test-model|\(case test\)")

#: Raw lines kept for the log viewer.
TAIL_LINES = 40000


def shape(text: str) -> str:
    """A message with its numbers and quoted payloads taken out, so repeats group."""
    s = re.sub(r"0x[0-9a-f]+", "X", text)
    s = re.sub(r"(['\"]).{0,400}?\1", "'…'", s)
    s = re.sub(r"\d+(?:\.\d+)?", "N", s)
    return s[:160]


@dataclass
class Scan:
    """What has been read, as plain lists the server serialises."""
    lines: deque = field(default_factory=lambda: deque(maxlen=TAIL_LINES))   # (seq, ts, level, text)
    seq: int = 0
    levels_hour: dict = field(default_factory=dict)       # hour epoch -> {level: n}
    tokens: list = field(default_factory=list)            # (ts, prompt, eval, ctx)
    latency: list = field(default_factory=list)           # (ts, who, seconds)
    retrieval: list = field(default_factory=list)         # (ts, confidence, nodes)
    gpu: list = field(default_factory=list)               # (ts, task, seconds)
    rss: list = field(default_factory=list)               # (ts, mb, trimmed_mb)
    unprompted: list = field(default_factory=list)        # (ts, source, label)
    slow: list = field(default_factory=list)              # (ts, seconds)
    guards: list = field(default_factory=list)            # (ts, tag)
    records: list = field(default_factory=list)           # (ts, kind)
    voice_late: list = field(default_factory=list)        # (ts, ms)
    scanner: list = field(default_factory=list)           # (ts, kind, mhz)
    intents: list = field(default_factory=list)           # (ts, strategy, category)
    errors: list = field(default_factory=list)            # (ts, level, shape, text)
    boots: list = field(default_factory=list)             # (ts, real, fixtures)
    shutdowns: list = field(default_factory=list)         # ts
    first_ts: Optional[float] = None
    last_ts: Optional[float] = None


def date_lines(raw_lines: list, anchor: float) -> list:
    """[(ts or None, level, text)] for each line; continuation lines (tracebacks)
    carry the stamp of the line they belong to and level "".

    `anchor` is when the file was last written: the last stamped line is on
    that date, or the day before when its time of day is later than the anchor's."""
    stamped = []
    for i, ln in enumerate(raw_lines):
        m = LINE.match(ln)
        if m:
            secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            stamped.append((i, secs, m.group(4), m.group(5)))
    out: list = [None] * len(raw_lines)
    if not stamped:
        return [(None, "", ln) for ln in raw_lines]
    a = datetime.fromtimestamp(anchor)
    anchor_secs = a.hour * 3600 + a.minute * 60 + a.second
    day = datetime(a.year, a.month, a.day)
    if stamped[-1][1] > anchor_secs + 60:
        day -= timedelta(days=1)
    nxt = stamped[-1][1]
    for i, secs, level, text in reversed(stamped):
        if secs - nxt > 12 * 3600:            # going back, the clock jumped forward: a midnight
            day -= timedelta(days=1)
        nxt = secs
        out[i] = ((day + timedelta(seconds=secs)).timestamp(), level, text)
    cur = None
    for i, ln in enumerate(raw_lines):
        if out[i] is None:
            out[i] = (cur, "", ln)
        else:
            cur = out[i][0]
    return out


def extract(scan: Scan, dated: list) -> None:
    """Fold dated lines into the scan's event lists."""
    pending_boot = None
    for idx, (ts, level, text) in enumerate(dated):
        scan.seq += 1
        scan.lines.append((scan.seq, ts, level, text))
        if ts is None:
            continue
        if scan.first_ts is None or ts < scan.first_ts:
            scan.first_ts = ts
        if scan.last_ts is None or ts > scan.last_ts:
            scan.last_ts = ts
        if level:
            h = int(ts // 3600 * 3600)
            bucket = scan.levels_hour.setdefault(h, {})
            bucket[level] = bucket.get(level, 0) + 1
        if pending_boot is not None:
            if BOOT_CONFIRM in text:
                scan.boots[pending_boot] = (scan.boots[pending_boot][0], True, scan.boots[pending_boot][2])
                pending_boot = None
            elif idx - pending_boot_idx > 4:
                pending_boot = None
        if FIXTURE.search(text) and scan.boots:
            b = scan.boots[-1]
            scan.boots[-1] = (b[0], b[1], True)
        if not level:
            continue
        if BOOT in text:
            scan.boots.append((ts, False, False))
            pending_boot, pending_boot_idx = len(scan.boots) - 1, idx
            continue
        if SHUTDOWN in text:
            scan.shutdowns.append(ts)
        if level in ("ERROR", "CRITICAL"):
            scan.errors.append((ts, level, shape(text), text[:400]))
        # Cheap substring checks before each regex: most lines match nothing.
        if "TOKEN_DEBUG" in text and (m := TOKEN.search(text)):
            scan.tokens.append((ts, int(m.group(1)), int(m.group(2)), int(m.group(3))))
        elif "TOTAL processing" in text and (m := LATENCY.search(text)):
            scan.latency.append((ts, m.group(1), float(m.group(2))))
        elif "Retrieval confidence" in text and (m := RETRIEVAL.search(text)):
            scan.retrieval.append((ts, float(m.group(1)), int(m.group(2))))
        elif "Finished in" in text and (m := GPU.search(text)):
            scan.gpu.append((ts, m.group(1), float(m.group(2))))
        elif "Memory Audit" in text and (m := RSS.search(text)):
            scan.rss.append((ts, float(m.group(1)), int(m.group(2) or 0)))
        elif "[unprompted]" in text and " posted as " in text and (m := UNPROMPTED.search(text)):
            label = re.sub(r"[*]", "", m.group(2)).strip()
            scan.unprompted.append((ts, m.group(1), "(no label)" if label.startswith("(no label)") else label))
        elif "Slow response" in text and (m := SLOW.search(text)):
            scan.slow.append((ts, float(m.group(1))))
        elif "[records]" in text:
            if (m := RECORDS_PLAN.search(text)):
                scan.records.append((ts, m.group(1)))
            elif (m := VOICE_LATE.search(text)):
                scan.voice_late.append((ts, int(m.group(1))))
        elif "[scanner]" in text and (m := SCANNER.search(text)):
            scan.scanner.append((ts, m.group(1), float(m.group(2))))
        elif "Fast-path intent" in text and (m := INTENT.search(text)):
            scan.intents.append((ts, m.group(1), m.group(2)))
        if "[" in text and (m := GUARD.search(text)):
            scan.guards.append((ts, m.group(1)))


class LogScanner:
    """Reads the rotated log once and the live log incrementally."""

    def __init__(self, log_dir: Path):
        self.log_dir = Path(log_dir)
        self.scan = Scan()
        self._lock = threading.Lock()
        self._live: Optional[tuple] = None        # (inode, offset, last ts) of kaiacord.log
        self.read_seconds = 0.0

    @property
    def live_path(self) -> Path:
        return self.log_dir / "kaiacord.log"

    def files(self) -> list:
        return [p for p in (self.log_dir / "kaiacord.log.1", self.live_path) if p.exists()]

    def full_scan(self) -> Scan:
        started = time.time()
        scan = Scan()
        live = None
        for p in self.files():
            st = p.stat()
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                raw = fh.read().split("\n")
            if raw and raw[-1] == "":
                raw.pop()
            dated = date_lines(raw, st.st_mtime)
            extract(scan, dated)
            if p == self.live_path:
                last = next((d[0] for d in reversed(dated) if d[0] is not None), None)
                live = (st.st_ino, st.st_size, last)
        with self._lock:
            self.scan, self._live = scan, live
        self.read_seconds = time.time() - started
        return scan

    def poll(self) -> int:
        """Read what was appended to the live log; rescan everything on rotation.
        Returns the number of new lines."""
        p = self.live_path
        if not p.exists():
            return 0
        st = p.stat()
        if self._live is None or st.st_ino != self._live[0] or st.st_size < self._live[1]:
            before = self.scan.seq
            self.full_scan()
            return self.scan.seq - before
        ino, offset, last = self._live
        if st.st_size == offset:
            return 0
        with open(p, "rb") as fh:
            fh.seek(offset)
            chunk = fh.read()
        cut = chunk.rfind(b"\n")
        if cut < 0:
            return 0
        text = chunk[:cut].decode("utf-8", errors="replace")
        raw = text.split("\n")
        dated = []
        day_anchor = last
        for ln in raw:
            m = LINE.match(ln)
            if not m:
                dated.append((day_anchor, "", ln))
                continue
            secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            if day_anchor is None:
                d = datetime.fromtimestamp(st.st_mtime)
                base = datetime(d.year, d.month, d.day)
            else:
                d = datetime.fromtimestamp(day_anchor)
                base = datetime(d.year, d.month, d.day)
                prev_secs = d.hour * 3600 + d.minute * 60 + d.second
                if prev_secs - secs > 12 * 3600:      # the clock went back: past midnight
                    base += timedelta(days=1)
            ts = (base + timedelta(seconds=secs)).timestamp()
            day_anchor = ts
            dated.append((ts, m.group(4), m.group(5)))
        with self._lock:
            extract(self.scan, dated)
            self._live = (ino, offset + cut + 1, day_anchor)
        return len(raw)
