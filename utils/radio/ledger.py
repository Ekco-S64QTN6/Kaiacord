"""The local radio ledger: every frequency the scanner has found or been told
about, what is on it, and when it is active.

SQLite at memory/radio/local_ledger.sqlite3 (a test file under pytest). Two
tables: `channels`, one row per frequency with running counts and a 24-hour
activity histogram in local time, and `events`, one row per catch.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

_lock = threading.Lock()
SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    freq_hz     INTEGER PRIMARY KEY,
    band        TEXT,
    service     TEXT,
    label       TEXT,
    source      TEXT,              -- 'listed' (seeded) or 'found' (by the scanner)
    mode        TEXT DEFAULT 'fm',
    first_seen  REAL,
    last_seen   REAL,
    probes      INTEGER DEFAULT 0,
    hits        INTEGER DEFAULT 0,
    voice       INTEGER DEFAULT 0,
    data        INTEGER DEFAULT 0,
    hours       TEXT DEFAULT '[]', -- 24 counts of hits by local hour
    last_transcript TEXT,
    last_transcribed REAL
);
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    freq_hz     INTEGER,
    ts          REAL,
    seconds     REAL,
    kind        TEXT,              -- 'voice' | 'data' | 'carrier'
    rms         REAL,
    hf_ratio    REAL,
    clip        TEXT,
    transcript  TEXT
);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
"""


def path() -> Path:
    return Path(telemetry_path("memory/radio/local_ledger.sqlite3"))


def _db() -> sqlite3.Connection:
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def seed(channels: list[dict]) -> None:
    """Listed channels (repeaters, NOAA, FRS/GMRS…); existing rows keep their counts."""
    with _lock, _db() as con:
        for c in channels:
            con.execute("INSERT OR IGNORE INTO channels (freq_hz, band, service, label, source, mode) "
                        "VALUES (?, ?, ?, ?, 'listed', ?)",
                        (int(c["freq_hz"]), c.get("band", ""), c.get("service", ""), c.get("label", ""),
                         c.get("mode", "fm")))


def note_probe(freq_hz: int, band: str = "", service: str = "") -> None:
    with _lock, _db() as con:
        con.execute("INSERT OR IGNORE INTO channels (freq_hz, band, service, label, source, first_seen) "
                    "VALUES (?, ?, ?, '', 'found', ?)", (int(freq_hz), band, service, time.time()))
        con.execute("UPDATE channels SET probes = probes + 1 WHERE freq_hz = ?", (int(freq_hz),))


def record(freq_hz: int, kind: str, seconds: float, rms: float, hf_ratio: float,
           clip: Optional[str] = None, transcript: str = "", band: str = "", service: str = "",
           when: Optional[float] = None) -> None:
    when = when or time.time()
    hour = time.localtime(when).tm_hour
    with _lock, _db() as con:
        con.execute("INSERT OR IGNORE INTO channels (freq_hz, band, service, label, source, first_seen) "
                    "VALUES (?, ?, ?, '', 'found', ?)", (int(freq_hz), band, service, when))
        row = con.execute("SELECT hours, first_seen FROM channels WHERE freq_hz = ?", (int(freq_hz),)).fetchone()
        hours = json.loads(row["hours"] or "[]") or [0] * 24
        hours[hour] += 1
        con.execute(
            "UPDATE channels SET hits = hits + 1, voice = voice + ?, data = data + ?, hours = ?, "
            "last_seen = ?, first_seen = COALESCE(first_seen, ?), "
            "last_transcript = COALESCE(NULLIF(?, ''), last_transcript), "
            "last_transcribed = CASE WHEN ? != '' THEN ? ELSE last_transcribed END WHERE freq_hz = ?",
            (1 if kind == "voice" else 0, 1 if kind == "data" else 0, json.dumps(hours), when, when,
             transcript, transcript, when, int(freq_hz)))
        con.execute("INSERT INTO events (freq_hz, ts, seconds, kind, rms, hf_ratio, clip, transcript) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (int(freq_hz), when, seconds, kind, rms, hf_ratio, clip, transcript))


def channel(freq_hz: int) -> Optional[dict]:
    with _lock, _db() as con:
        row = con.execute("SELECT * FROM channels WHERE freq_hz = ?", (int(freq_hz),)).fetchone()
    return dict(row) if row else None


def channels() -> list[dict]:
    with _lock, _db() as con:
        return [dict(r) for r in con.execute("SELECT * FROM channels ORDER BY freq_hz")]


def presets(limit: int = 25) -> list[dict]:
    """The dropdown: channels with voice first, then any activity, then listed ones."""
    with _lock, _db() as con:
        rows = con.execute(
            "SELECT * FROM channels ORDER BY (voice > 0) DESC, voice DESC, hits DESC, "
            "(source = 'listed') DESC, freq_hz LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def recent(limit: int = 10, kinds: tuple = ("voice", "data", "carrier")) -> list[dict]:
    q = ",".join("?" * len(kinds))
    with _lock, _db() as con:
        rows = con.execute(
            f"SELECT e.*, c.label, c.service FROM events e LEFT JOIN channels c USING (freq_hz) "
            f"WHERE e.kind IN ({q}) ORDER BY e.ts DESC LIMIT ?", (*kinds, limit)).fetchall()
    return [dict(r) for r in rows]


def active_hours(ch: dict) -> str:
    """'01–03h' style summary of when a channel is heard."""
    hours = json.loads(ch.get("hours") or "[]")
    busy = [h for h, n in enumerate(hours) if n]
    if not busy:
        return "not heard yet"
    return ", ".join(f"{h:02d}h" for h in busy[:6]) + ("…" if len(busy) > 6 else "")


def merge(src_hz: int, dst_hz: int) -> None:
    """Fold one channel's counts and events into another — for rows a rounding
    split (462.2775 and 462.275 are one transmitter)."""
    if int(src_hz) == int(dst_hz):
        return
    with _lock, _db() as con:
        src = con.execute("SELECT * FROM channels WHERE freq_hz = ?", (int(src_hz),)).fetchone()
        if not src:
            return
        con.execute("INSERT OR IGNORE INTO channels (freq_hz, band, service, label, source, first_seen) "
                    "VALUES (?, ?, ?, '', 'found', ?)", (int(dst_hz), src["band"], src["service"], src["first_seen"]))
        dst = con.execute("SELECT * FROM channels WHERE freq_hz = ?", (int(dst_hz),)).fetchone()
        hs, hd = json.loads(src["hours"] or "[]") or [0] * 24, json.loads(dst["hours"] or "[]") or [0] * 24
        con.execute(
            "UPDATE channels SET probes = probes + ?, hits = hits + ?, voice = voice + ?, data = data + ?, "
            "hours = ?, first_seen = MIN(COALESCE(first_seen, ?), ?), last_seen = MAX(COALESCE(last_seen, 0), ?), "
            "last_transcript = COALESCE(last_transcript, ?) WHERE freq_hz = ?",
            (src["probes"], src["hits"], src["voice"], src["data"], json.dumps([a + b for a, b in zip(hd, hs)]),
             src["first_seen"] or 0, src["first_seen"] or 1e12, src["last_seen"] or 0, src["last_transcript"],
             int(dst_hz)))
        con.execute("UPDATE events SET freq_hz = ? WHERE freq_hz = ?", (int(dst_hz), int(src_hz)))
        if src["source"] != "listed":
            con.execute("DELETE FROM channels WHERE freq_hz = ?", (int(src_hz),))
