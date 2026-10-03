"""Her record crate: the local music library, and what plays next.

The catalog is `dj_catalog.json`, written by the library analysis outside this
repo (Essentia BPM and key, the key as a Camelot code, a normalised genre). It
is read, never written, and nothing here analyses audio.

Choosing the next record is plain Python, the way a DJ chooses one:
harmonically close (the same Camelot code, one step round the wheel, or the
relative major/minor), near in tempo (within a few percent, counting a half-
or double-time match), the same kind of music where possible, and not
something she played in the last while.
"""
from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

#: How far apart two tempos may be and still be beatmatched by stretching.
BPM_TOLERANCE = 0.06
#: Records played this recently are not picked again.
RECENT = 40


@dataclass(frozen=True)
class Record:
    path: str
    artist: str
    title: str
    bpm: Optional[float]
    key: Optional[str]          # Camelot, e.g. "8A"
    genre: str

    @property
    def name(self) -> str:
        return f"{self.artist} — {self.title}" if self.artist else self.title


def _camelot(key) -> Optional[tuple[int, str]]:
    m = re.fullmatch(r"\s*(1[0-2]|[1-9])\s*([ABab])\s*", str(key or ""))
    return (int(m.group(1)), m.group(2).upper()) if m else None


def load(path: str | os.PathLike) -> list[Record]:
    """The records in a catalog whose files still exist. Bad entries are skipped."""
    p = Path(os.path.expanduser(str(path)))
    if not str(path) or not p.is_file():
        return []
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not row.get("filepath"):
            continue
        if not os.path.isfile(row["filepath"]):
            continue
        try:
            bpm = float(row["bpm"]) if row.get("bpm") else None
        except (TypeError, ValueError):
            bpm = None
        artist = str(row.get("artist") or "").strip()
        out.append(Record(path=row["filepath"], artist="" if artist.lower() == "unknown" else artist,
                          title=str(row.get("title") or Path(row["filepath"]).stem).strip(),
                          bpm=bpm if bpm and 40 <= bpm <= 220 else None,
                          key=row.get("key") if _camelot(row.get("key")) else None,
                          genre=str(row.get("genre") or "").strip()))
    return out


def key_step(a: Optional[str], b: Optional[str]) -> Optional[int]:
    """Moves round the Camelot wheel from a to b: 0 same, 1 a neighbour or the
    relative key, 2 two steps; None if unknown or further."""
    ca, cb = _camelot(a), _camelot(b)
    if not ca or not cb:
        return None
    around = min((ca[0] - cb[0]) % 12, (cb[0] - ca[0]) % 12)
    if ca[1] == cb[1]:
        return around if around <= 2 else None
    return 1 if around == 0 else None


def shift_key(key: Optional[str], semitones: int) -> Optional[str]:
    """The Camelot code of `key` moved by `semitones` (seven steps round the
    wheel a semitone)."""
    c = _camelot(key)
    if not c or not semitones:
        return key
    return f"{(c[0] - 1 + 7 * semitones) % 12 + 1}{c[1]}"


def key_sync(playing: Optional[str], incoming: Optional[str]) -> int:
    """Semitones to shift `incoming` so it sits with `playing` — the same key,
    a neighbour or the relative key — when it does not already: +1 or -1, or
    0 if it already fits, a key is unknown, or one semitone would not do it."""
    if key_step(playing, incoming) in (0, 1) or not _camelot(playing) or not _camelot(incoming):
        return 0
    for s in (1, -1):
        if key_step(playing, shift_key(incoming, s)) in (0, 1):
            return s
    return 0


def tempo_ratio(from_bpm: Optional[float], to_bpm: Optional[float]) -> Optional[float]:
    """The stretch that makes `to` play at `from`'s tempo — counting half and
    double time — or None if no stretch within BPM_TOLERANCE does it."""
    if not from_bpm or not to_bpm:
        return None
    for target in (from_bpm, from_bpm * 2, from_bpm / 2):
        ratio = target / to_bpm
        if abs(ratio - 1.0) <= BPM_TOLERANCE:
            return ratio
    return None


def score(current: Record, candidate: Record) -> float:
    """How well `candidate` follows `current`. Higher is better; 0 is a clash."""
    s = 0.0
    step = key_step(current.key, candidate.key)
    s += {0: 3.0, 1: 2.5, 2: 1.0}.get(step, 0.0)
    ratio = tempo_ratio(current.bpm, candidate.bpm)
    if ratio is not None:
        s += 3.0 - 20.0 * abs(ratio - 1.0)
    if current.genre and candidate.genre == current.genre:
        s += 1.5
    return s


def next_record(current: Optional[Record], crate: list[Record], played: Iterable[str],
                rng: Optional[random.Random] = None) -> Optional[Record]:
    """The record to play after `current`: among the best few that fit, one at random."""
    rng = rng or random.Random()
    recent = set(list(played)[-RECENT:])
    # The same song in two files (a 128 kbps copy beside the original) is the
    # same record: compare by name as well as path.
    recent_names = {r.name.lower() for r in crate if r.path in recent}
    if current is not None:
        recent_names.add(current.name.lower())
    pool = ([r for r in crate if r.path not in recent and r.name.lower() not in recent_names]
            or [r for r in crate if not current or r.name.lower() != current.name.lower()])
    if not pool:
        return None
    if current is None:
        return rng.choice(pool)
    ranked = sorted(pool, key=lambda r: score(current, r), reverse=True)
    best = score(current, ranked[0])
    shortlist = [r for r in ranked[:6] if score(current, r) >= best - 1.0]
    return rng.choice(shortlist)


def opener(crate: list[Record], mood: dict, hour: int, rng: Optional[random.Random] = None) -> Optional[Record]:
    """The first record, from her mood: restless picks faster records, low and
    late picks slower ones."""
    rng = rng or random.Random()
    if not crate:
        return None
    arousal = max(0.0, min(1.0, float((mood or {}).get("arousal", 0.5))))
    if hour < 6:
        arousal = min(arousal, 0.4)
    lo, hi = (0, 112) if arousal < 0.35 else (110, 128) if arousal < 0.65 else (124, 999)
    fits = [r for r in crate if r.bpm and lo <= r.bpm < hi]
    return rng.choice(fits or crate)


def find(crate: list[Record], query: str) -> Optional[Record]:
    """A record whose artist and title contain every word of the query."""
    words = re.findall(r"\w+", (query or "").lower())
    if not words:
        return None
    hits = [r for r in crate if all(w in f"{r.artist} {r.title}".lower() for w in words)]
    return hits[0] if hits else None
