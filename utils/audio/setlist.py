"""Which records lock with which, measured ahead of time, and the sets that follow.

Simulated on the real crate with the planner as it was, 34 of 40 planned blends
had no common beat at all — pop, hip-hop and synthwave pairs whose drums do not
share a pulse, laid over each other for 64 beats because their tracked ticks ran
straight — and four of the six that did were 30–55 ms apart. No grid can fix a
pair that does not lock; choosing partners that do can.

`build` plans every tempo-compatible pair the way the mixer would (end of the
outgoing, the default blend length) and measures it (`mixcheck`): an edge is
kept only if the bars agree, as planned or after one measured shift. The result
— `memory/records/graph.json` — is extended, never rebuilt: a record added to
the library costs its own pairs, and a record removed drops out. `make_sets`
walks the graph into sets, each a run of records where every transition was
measured to lock; Kaia plays them in rotation (`RecordsSession._choose`), and
the live planner still measures every blend before it starts.
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from utils.infrastructure.logging.kaia_logger import log_action, log_debug, log_info, log_warning

VERSION = 2
SET_LENGTH = 24
MAX_SETS = 16

_lock = threading.Lock()
_building = threading.Event()


def graph_path() -> Path:
    from utils.infrastructure.monitoring.telemetry_paths import telemetry_path
    return Path(telemetry_path("memory/records/graph.json"))


def load() -> dict:
    try:
        g = json.loads(graph_path().read_text(encoding="utf-8"))
        if g.get("version") == VERSION:
            return g
    except (OSError, ValueError):
        pass
    return {"version": VERSION, "records": {}, "edges": {}, "checked": {}, "sets": [], "built": 0}


def save(g: dict) -> None:
    from utils.core.atomic_write import write_atomic
    write_atomic(graph_path(), json.dumps(g, ensure_ascii=False))


class _Side:
    """What planning needs of one record, read once per build."""

    def __init__(self, rec):
        from utils.audio import beatgrid, records as R, mixcheck
        self.rec = rec
        self.seconds = R.probe_seconds(rec.path)
        beatgrid.ensure_ticks(rec.path, rec.bpm)
        self.grid = beatgrid.grid_for(rec.path, rec.bpm)
        self.lead = beatgrid.first_sound(rec.path)
        self.bass_in = beatgrid.bass_entry(rec.path, rec.bpm)
        self.music_end = self.seconds
        if self.seconds:
            last = beatgrid.last_strong_beat(rec.path, rec.bpm, round(self.seconds, 1))
            if last:
                self.music_end = min(self.seconds, last + 240.0 / max(1.0, rec.bpm))
        self.out_grid = (R._default_grid_at(rec, max(0.0, self.music_end - 68.0), 45.0)
                         if self.seconds else None)
        self.env_ok = mixcheck.envelope(rec.path) is not None

    @property
    def ok(self) -> bool:
        from utils.audio import records as R
        return bool(self.seconds and self.seconds >= R.MIN_RECORD_S and self.grid and self.env_ok)


def measure(a: _Side, b: _Side, mix_beats: Optional[int] = None) -> Optional[dict]:
    """The blend a → b as the mixer would plan it at a's end, measured. An edge
    ({"ms": shift applied, "agree", "bars", "ratio"}) if it locks, else None."""
    from utils.audio import records as R, mixcheck
    nxt = R.Next(b.rec, b.seconds, 0.0, b.grid, b.lead, b.bass_in)
    beats = mix_beats or R.MIX_BEATS
    now = max(0.0, a.music_end - 140.0)
    plan = R.plan_transition(now, 1.0, a.out_grid, a.music_end, nxt, "end", beats, lead=2.0)
    while plan.kind != "blend" and plan.fallback == "room" and beats > R.MIN_BLEND_BEATS:
        beats //= 2
        plan = R.plan_transition(now, 1.0, a.out_grid, a.music_end, nxt, "end", beats, lead=2.0)
    if plan.kind != "blend":
        return None
    v, shift = verify(a.rec.path, 1.0, b.rec.path, plan)
    if not v.locked:
        return None
    return {"ms": round(shift * 1000, 1), "agree": v.agree, "bars": v.bars, "ratio": round(plan.ratio, 5)}


def verify(out_path: str, out_ratio: float, in_path: str, plan):
    """(verdict, shift seconds): `plan` measured; where every bar agrees the
    incoming is off by one amount, measured again shifted by it. The shift is
    what to add to `plan.start` (negative: earlier)."""
    from utils.audio import mixcheck
    args = (out_path, out_ratio, in_path, plan.ratio)
    v = mixcheck.check(*args, plan.start, plan.offset, plan.drop, plan.length, plan.beat)
    if v.locked or v.correction_ms is None:
        return v, 0.0
    shift = -v.correction_ms / 1000.0
    v2 = mixcheck.check(*args, plan.start + shift, plan.offset, plan.drop, plan.length, plan.beat)
    return (v2, shift) if v2.locked else (v, 0.0)


def build(crate: list, budget_s: Optional[float] = None, progress: Optional[Callable[[str], None]] = None) -> dict:
    """Measure every unmeasured tempo-compatible pair in `crate`, extending the
    saved graph; drop records no longer in it. Resumable: saved as it goes."""
    from utils.audio import library
    if _building.is_set():
        return load()
    _building.set()
    try:
        started = time.time()
        with _lock:
            g = load()
        live = {r.path: r for r in crate if r.bpm}
        for gone in [p for p in g["records"] if p not in live]:
            g["records"].pop(gone, None)
            g["edges"].pop(gone, None)
            g["checked"].pop(gone, None)
            for e in g["edges"].values():
                e.pop(gone, None)
            for c in g["checked"].values():
                if gone in c:
                    c.remove(gone)
        for p in live:
            try:
                m = os.path.getmtime(p)
            except OSError:
                continue
            if g["records"].get(p, {}).get("mtime") != m:   # new or changed: measure it again
                g["records"][p] = {"mtime": m}
                g["edges"].pop(p, None)
                g["checked"].pop(p, None)
                for e in g["edges"].values():
                    e.pop(p, None)
                for c in g["checked"].values():
                    if p in c:
                        c.remove(p)
        sides: dict = {}

        def side(rec) -> Optional[_Side]:
            if rec.path not in sides:
                try:
                    sides[rec.path] = _Side(rec)
                except Exception as e:
                    log_debug(f"[sets] {rec.name} not readable: {e}")
                    sides[rec.path] = None
            s = sides[rec.path]
            return s if s is not None and s.ok else None

        todo = 0
        measured = locked = 0
        for a_path, a_rec in live.items():
            checked = set(g["checked"].get(a_path, []))
            cands = [b for b in live.values() if b.path != a_path and b.path not in checked
                     and library.tempo_ratio(a_rec.bpm, b.bpm)]
            if not cands:
                continue
            todo += len(cands)
            a = side(a_rec)
            if a is None:
                g["checked"][a_path] = sorted(checked | {b.path for b in cands})
                continue
            for b_rec in cands:
                if budget_s and time.time() - started > budget_s:
                    break
                b = side(b_rec)
                edge = measure(a, b) if b is not None else None
                measured += 1
                if edge:
                    g["edges"].setdefault(a_path, {})[b_rec.path] = edge
                    locked += 1
                g["checked"].setdefault(a_path, []).append(b_rec.path)
            with _lock:
                save(g)
            if progress:
                progress(f"{a_rec.name}: {len(g['edges'].get(a_path, {}))} partners")
            if budget_s and time.time() - started > budget_s:
                break
        g["sets"] = make_sets(g, live)
        g["built"] = time.time()
        with _lock:
            save(g)
        n_edges = sum(len(e) for e in g["edges"].values())
        log_info(f"[sets] measured {measured} pairs ({locked} lock); {n_edges} locking transitions in the "
                 f"library, {len(g['sets'])} sets")
        return g
    finally:
        _building.clear()


def make_sets(g: dict, live: dict, rng: Optional[random.Random] = None) -> list:
    """Sets walked through the graph: each next record is a measured lock from
    the one before, never repeated in the set, preferring a key it sits with and
    records the other sets have not used. Longest first."""
    from utils.audio import library
    rng = rng or random.Random(1)
    edges = {a: {b: e for b, e in nb.items() if b in live} for a, nb in g.get("edges", {}).items() if a in live}
    used: dict = {}
    sets = []
    starts = sorted(edges, key=lambda a: -len(edges[a]))
    for start in starts:
        if len(sets) >= MAX_SETS:
            break
        if used.get(start, 0) >= 1 and len(sets) >= 4:
            continue
        path, seen = [start], {start}
        while len(path) < SET_LENGTH:
            cur = path[-1]
            options = [b for b in edges.get(cur, {}) if b not in seen]
            if not options:
                break

            def score(b):
                step = library.key_step(live[cur].key, live[b].key)
                ahead = len([x for x in edges.get(b, {}) if x not in seen])
                return ((0 if step in (0, 1) else 1 if step == 2 else 2), used.get(b, 0), -min(ahead, 6),
                        rng.random())
            nxt = min(options, key=score)
            path.append(nxt)
            seen.add(nxt)
        if len(path) >= 4:
            sets.append(path)
            for p in path:
                used[p] = used.get(p, 0) + 1
    sets.sort(key=len, reverse=True)
    return sets


def partners(g: dict, path: str) -> dict:
    return g.get("edges", {}).get(path, {})


def live_sets(g: dict, crate: list) -> list:
    """The graph's sets with only records still in the crate, those of 4 or more."""
    live = {r.path for r in crate}
    sets = [[p for p in s if p in live] for s in g.get("sets", [])]
    return [s for s in sets if len(s) >= 4]


def _rotation_path() -> Path:
    from utils.infrastructure.monitoring.telemetry_paths import telemetry_path
    return Path(telemetry_path("memory/records/set_rotation.json"))


def peek_rotation(n_sets: int) -> Optional[int]:
    """The index the next `!music records` will start, without advancing it."""
    if not n_sets:
        return None
    try:
        return int(json.loads(_rotation_path().read_text(encoding="utf-8")).get("next", 0)) % n_sets
    except (OSError, ValueError):
        return 0


def next_set(g: dict, crate: list) -> Optional[list]:
    """The next set in rotation (paths still in the crate), advancing the
    rotation kept beside the graph so each session starts the next one."""
    sets = live_sets(g, crate)
    if not sets:
        return None
    from utils.core.atomic_write import write_atomic
    path = _rotation_path()
    try:
        k = int(json.loads(path.read_text(encoding="utf-8")).get("next", 0))
    except (OSError, ValueError):
        k = 0
    try:
        write_atomic(path, json.dumps({"next": k + 1}))
    except OSError:
        pass
    return sets[k % len(sets)]


def build_in_background(crate: list, budget_s: Optional[float] = None,
                        on_done: Optional[Callable[[dict], None]] = None) -> bool:
    """Start `build` on a thread if one is not running. True if started."""
    if _building.is_set():
        return False

    def run():
        try:
            g = build(crate, budget_s)
            if on_done:
                on_done(g)
        except Exception as e:
            log_warning(f"[sets] graph build failed: {e}")
    threading.Thread(target=run, daemon=True, name="kaia-records-sets").start()
    log_action("[sets] measuring which records lock with which (background)")
    return True
