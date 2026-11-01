"""The local radio ledger: every frequency the scanner has found or been told
about, what is on it, and when it is active.

SQLite at memory/radio/local_ledger.sqlite3 (a test file under pytest). Two
tables: `channels`, one row per frequency with running counts and a 24-hour
activity histogram in local time, and `events`, one row per catch — and one
per burst on a habitual data channel the watch noted without holding
(kind 'seen', no audio), so that channel's timing and hours stay measured.

Connections are kept per thread (the dashboard's stream asks ten times a
second; each call used to open the file and run the schema).
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
    kind        TEXT,              -- 'voice' | 'data' | 'carrier' | 'noise' (hiss that tripped the trigger) | 'seen'
    rms         REAL,
    hf_ratio    REAL,
    clip        TEXT,
    transcript  TEXT
);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
"""
#: Columns added since the first schema: (name, type). Added in place, never dropped.
EVENT_COLUMNS = (("peak_db", "REAL"),       # dB over the slice's floor when it triggered
                 ("carrier_s", "REAL"))     # seconds of the recording with a carrier under them
_local = threading.local()


def path() -> Path:
    return Path(telemetry_path("memory/radio/local_ledger.sqlite3"))


def _db() -> sqlite3.Connection:
    p = str(path())
    cons = getattr(_local, "cons", None)
    if cons is None:
        cons = _local.cons = {}
    con = cons.get(p)
    if con is None:
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(p, timeout=10)
        con.row_factory = sqlite3.Row
        # The bot writes catches while KAIA // OPS and KAIA//RX query this
        # database from independent processes. WAL lets those readers retain
        # snapshots without holding up scanner commits.
        mode = con.execute("PRAGMA journal_mode").fetchone()[0].lower()
        if mode != "wal":
            con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA busy_timeout = 10000")
        con.executescript(SCHEMA)
        have = {r[1] for r in con.execute("PRAGMA table_info(events)")}
        for name, typ in EVENT_COLUMNS:
            if name not in have:
                con.execute(f"ALTER TABLE events ADD COLUMN {name} {typ}")
        con.execute("CREATE INDEX IF NOT EXISTS events_freq_ts ON events(freq_hz, ts)")
        con.commit()
        cons[p] = con
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
           when: Optional[float] = None, peak_db: Optional[float] = None,
           carrier_s: Optional[float] = None) -> None:
    when = when or time.time()
    hour = time.localtime(when).tm_hour
    with _lock, _db() as con:
        if kind == "noise":
            # Hiss is not a channel: it's kept as an event, for counting how
            # often the trigger trips, and never adds a row or a hit.
            con.execute("INSERT INTO events (freq_hz, ts, seconds, kind, rms, hf_ratio, clip, transcript, "
                        "peak_db, carrier_s) VALUES (?, ?, ?, ?, ?, ?, NULL, '', ?, ?)",
                        (int(freq_hz), when, seconds, kind, rms, hf_ratio, peak_db, carrier_s))
            return
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
        con.execute("INSERT INTO events (freq_hz, ts, seconds, kind, rms, hf_ratio, clip, transcript, "
                    "peak_db, carrier_s) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (int(freq_hz), when, seconds, kind, rms, hf_ratio, clip, transcript, peak_db, carrier_s))


def catches_since(ts: float) -> list[dict]:
    """Every catch since `ts` (frequency and kind), uncapped: `recent()` is for
    display and stops at its limit, which a busy night passes."""
    with _lock, _db() as con:
        return [dict(r) for r in con.execute(
            "SELECT freq_hz, kind, ts FROM events WHERE ts >= ? AND kind NOT IN ('noise', 'seen') ORDER BY ts",
            (float(ts),))]


def forget_clips(names: list[str]) -> None:
    """Rows whose clip has been rotated off disk stop naming it."""
    if not names:
        return
    with _lock, _db() as con:
        con.executemany("UPDATE events SET clip = NULL WHERE clip = ?", [(n,) for n in names])


def relabel_voice(event_id: int, transcript: str) -> bool:
    """A carrier catch found to hold words: the event becomes voice and its
    channel counts it. False if the event is gone or already voice."""
    with _lock, _db() as con:
        e = con.execute("SELECT freq_hz, ts, kind FROM events WHERE id = ?", (int(event_id),)).fetchone()
        if not e or e["kind"] == "voice":
            return False
        con.execute("UPDATE events SET kind = 'voice', transcript = ? WHERE id = ?", (transcript, int(event_id)))
        con.execute("UPDATE channels SET voice = voice + 1, data = data - ?, "
                    "last_transcript = CASE WHEN COALESCE(last_transcribed, 0) <= ? THEN ? ELSE last_transcript END, "
                    "last_transcribed = MAX(COALESCE(last_transcribed, 0), ?) WHERE freq_hz = ?",
                    (1 if e["kind"] == "data" else 0, e["ts"], transcript, e["ts"], e["freq_hz"]))
        return True


def set_transcript(event_id: int, transcript: str) -> bool:
    """Replace one event's transcript (a correction), and its channel's last
    transcript if that was this one."""
    with _lock, _db() as con:
        e = con.execute("SELECT freq_hz, transcript FROM events WHERE id = ?", (int(event_id),)).fetchone()
        if not e or e["transcript"] == transcript:
            return False
        con.execute("UPDATE events SET transcript = ? WHERE id = ?", (transcript, int(event_id)))
        con.execute("UPDATE channels SET last_transcript = ? WHERE freq_hz = ? AND last_transcript = ?",
                    (transcript, e["freq_hz"], e["transcript"]))
        return True


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


# ── What the ledger says about a channel's habits ───────────────────────────

#: A channel is habitual data once it has keyed up this often in HABIT_DAYS,
#: never with a voice catch, with at least HABIT_HELD recordings to measure its
#: bursts from.
HABIT_MIN_HITS = 30
HABIT_DAYS = 7.0
HABIT_HELD = 10
HABIT_MIN_BURST_S = 4.0


def habitual(now: Optional[float] = None) -> dict:
    """{freq: longest usual burst in seconds} for channels that only ever send
    short bursts with no voice — telemetry, polled data, trunking. The burst is
    the 90th percentile of what was recorded (which includes the silence the
    hold waited out), so a transmission longer than that is something else."""
    import numpy as np
    since = (now or time.time()) - HABIT_DAYS * 86400
    with _lock, _db() as con:
        counts = {r[0]: r[1] for r in con.execute(
            "SELECT freq_hz, COUNT(*) FROM events WHERE ts >= ? AND kind IN ('carrier', 'data', 'seen') "
            "GROUP BY freq_hz", (since,))}
        # A voice catch, or a decoded data catch ("[APRS] …"), means the bursts say something.
        voiced = [r[0] for r in con.execute(
            "SELECT freq_hz FROM channels WHERE voice > 0 OR last_transcript LIKE '[%'")]
        out = {}
        for f, n in counts.items():
            if n < HABIT_MIN_HITS or any(abs(f - v) <= 3000 for v in voiced):
                continue
            secs = [r[0] for r in con.execute(
                "SELECT seconds FROM events WHERE freq_hz = ? AND kind IN ('carrier', 'data') "
                "ORDER BY ts DESC LIMIT 200", (f,))]
            if len(secs) >= HABIT_HELD:
                out[int(f)] = round(max(HABIT_MIN_BURST_S, float(np.percentile(secs, 90))), 1)
    return out


def period_of(ts: list, tol_s: float = 2.6, pmin: float = 15.0, pmax: float = 900.0,
              kmax: int = 12) -> tuple:
    """(period in seconds, confidence 0..1) of a channel that keys up on a
    timer, from when it was heard. Each gap between catches is tested against
    whole multiples of a candidate period (the sweep misses most bursts, so a
    gap is usually several periods), within `tol_s` — a pass of the sweep, the
    jitter in when a burst is first seen. Confidence is the share of gaps that
    fit, above what chance alone would fit at that period: 0.5 and up is a
    timer. (None, 0.0) when there are too few gaps to say."""
    import numpy as np
    t = np.sort(np.asarray(ts, dtype=float))
    gaps = np.diff(t)
    gaps = gaps[(gaps > 3) & (gaps < pmax * kmax)]
    if len(gaps) < 12:
        return None, 0.0
    P = np.exp(np.arange(np.log(pmin), np.log(pmax), 0.002))
    k = np.round(gaps[None, :] / P[:, None])
    ok = (k >= 1) & (k <= kmax)
    tol = np.maximum(tol_s, 0.015 * P)[:, None]
    fit = ((np.abs(gaps[None, :] - k * P[:, None]) <= tol) & ok).sum(axis=1) / np.maximum(ok.sum(axis=1), 1)
    chance = np.minimum(1.0, 2 * tol[:, 0] / P)
    score = (fit - chance) / (1 - chance + 1e-9) * (ok.sum(axis=1) / len(gaps))
    i = int(np.argmax(score))
    return float(P[i]), float(max(0.0, score[i]))


def heard_at(freq_hz: int, since: float) -> list:
    """When a channel keyed up since `since` (every kind but noise)."""
    with _lock, _db() as con:
        return [r[0] for r in con.execute(
            "SELECT ts FROM events WHERE freq_hz = ? AND ts >= ? AND kind != 'noise' ORDER BY ts",
            (int(freq_hz), float(since)))]


def events_since(ts: float, kinds: Optional[tuple] = None) -> list:
    """Every event since `ts` with its channel's label, oldest first."""
    q, args = "", [float(ts)]
    if kinds:
        q = f" AND e.kind IN ({','.join('?' * len(kinds))})"
        args += list(kinds)
    with _lock, _db() as con:
        return [dict(r) for r in con.execute(
            "SELECT e.*, c.label, c.service, c.first_seen, c.hits AS ch_hits, c.voice AS ch_voice, c.hours "
            f"FROM events e LEFT JOIN channels c USING (freq_hz) WHERE e.ts >= ?{q} ORDER BY e.ts", args)]
