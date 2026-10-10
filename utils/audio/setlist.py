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
#: How pairs are measured. A graph measured by an earlier method is measured
#: again whole: the judge has only ever become stricter, so an old edge is not
#: evidence.
METHOD = 4
MAX_SETS = 16
#: A set runs about an hour: it is walked until it reaches SET_TARGET_S of
#: played time, and one that cannot reach SET_MIN_S is not a set.
SET_TARGET_S = 3600.0
SET_MIN_S = 3000.0
#: Records longer than this are whole mixes and live sets, not records to mix.
MAX_SET_RECORD_S = 900.0
#: A record appears in at most this many sets, so the sets cover the library.
MAX_USES = 2
#: Records the walk may visit looking for an hour, per set.
WALK_BUDGET = 4000
#: Genre families a set is held to where it can be, first match wins.
FAMILIES = (
    ("Drum & Bass", ("drum & bass", "drum and bass", "dnb", "jungle", "breakbeat", "breaks")),
    ("Techno & Trance", ("techno", "trance", "industrial", "ebm", "hardstyle", "acid")),
    ("House & Disco", ("house", "disco", "garage", "french touch", "funk")),
    ("Synthwave & New Wave", ("synthwave", "synthpop", "synth-pop", "new wave", "darkwave", "retrowave",
                              "outrun", "italo")),
    ("Hip-hop & Phonk", ("hip-hop", "hip hop", "rap", "phonk", "trap", "grime")),
    ("Downtempo", ("downtempo", "chill", "ambient", "trip-hop", "trip hop", "lo-fi", "lofi")),
    ("Pop & Rock", ("pop", "rock", "indie", "punk")),
)

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
    ({"ms": shift applied, "agree", "bars", "ratio", "beats", "back", "cue"}) if
    any of the places it could be mixed locks (`find_blend`), else None."""
    from utils.audio import records as R
    nxt = R.Next(b.rec, b.seconds, 0.0, b.grid, b.lead, b.bass_in)
    found = find_blend(max(0.0, a.music_end - 180.0), a.rec.path, 1.0, a.out_grid, a.music_end, nxt, "end",
                       mix_beats or R.MIX_BEATS, lead=2.0)
    if found is None:
        return None
    plan, v, shift, how = found
    return {"ms": round(shift * 1000, 1), "agree": v.agree, "bars": v.bars, "ratio": round(plan.ratio, 5), **how}


#: Where else a blend is tried when the first place does not lock: the outgoing
#: mixed out up to this many 8-bar phrases earlier (past a beatless outro, into
#: the last part with a groove), or a skip waiting this many 4-bar phrases…
BACK_PHRASES = 5
SKIP_WAITS = 3
#: …the incoming cued at its own choice or at one of these bars past bar one…
CUES = (None, 0, 8, 16, 32)
#: …and the blend shortened, halving down to this (a short blend that locks
#: beats any transition that does not).
SHORTEST_BEATS = 16


def find_blend(now: float, out_path: str, out_ratio: float, out_grid, music_end: float, nxt, mode: str,
               mix_beats: int, lead: float = 2.0, verify_fn: Optional[Callable] = None,
               budget_s: Optional[float] = None, lengths: Optional[list] = None):
    """The first place a blend into `nxt` locks, searched the way a DJ looks for
    one: the planned spot first, then the incoming cued at another phrase, the
    outgoing mixed out a phrase or more earlier (a skip: a phrase or more later),
    then a shorter blend. (plan, verdict, shift, how) or None; `plan.start`
    already carries the shift."""
    from utils.audio import records as R
    verify_fn = verify_fn or verify
    started = time.time()
    if lengths is None:
        lengths, b = [], mix_beats
        while b >= SHORTEST_BEATS:
            lengths.append(b)
            b //= 2
    beat = 60.0 / (out_grid.bpm * out_ratio) if out_grid else 0.5
    seen = set()
    for beats in lengths:
        for step in range(BACK_PHRASES + 1 if mode == "end" else SKIP_WAITS + 1):
            if mode == "end":
                at, end = now, music_end - step * 32 * beat
            else:
                at, end = now + step * 16 * beat, music_end
            for cue in CUES:
                if budget_s and time.time() - started > budget_s:
                    return None
                plan = R.plan_transition(at, out_ratio, out_grid, end, nxt, mode, beats, lead=lead, in_bars=cue)
                if plan.kind != "blend":
                    if plan.fallback == "tempo":
                        return None
                    if cue is None and plan.fallback in ("beat", "room"):
                        break                    # no blend fits from here: try the next place
                    continue
                key = (round(plan.drop, 2), round(plan.offset, 2), beats)
                if key in seen:
                    continue
                seen.add(key)
                v, shift = verify_fn(out_path, out_ratio, nxt.record.path, plan)
                if v.locked:
                    plan.start += shift
                    plan.check = v.summary() + (f"; moved {shift * 1000:+.0f} ms" if shift else "")
                    return plan, v, shift, {"beats": beats, "back": step, "cue": cue}
    return None


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


def _lock_path() -> Path:
    from utils.infrastructure.monitoring.telemetry_paths import telemetry_path
    return Path(telemetry_path("memory/records/graph.lock"))


def _take_lock():
    """An exclusive lock on the build, across processes (the bot's background
    build and one run by hand); None if another build holds it."""
    import fcntl
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def building() -> bool:
    """A build is running, here or in another process."""
    if _building.is_set():
        return True
    fh = _take_lock()
    if fh is None:
        return True
    fh.close()
    return False


def _changed(entry: Optional[dict], path: str) -> bool:
    """The file's audio is not what the graph measured: new, or a different
    signature (`library.audio_signature`). A file only retagged is unchanged."""
    from utils.audio import library
    if not entry:
        return True
    try:
        if entry.get("mtime") == os.path.getmtime(path):
            return False
    except OSError:
        return False
    sig = entry.get("sig")
    return sig is None or sig != library.audio_signature(path)


def needs_build(g: dict, crate: list) -> bool:
    """Something to measure: a record new or changed since the graph saw it,
    or pairs left from an older way of measuring."""
    if g.get("method", 2) < METHOD:
        return True
    recs = g.get("records", {})
    return any(_changed(recs.get(r.path), r.path) for r in crate if r.bpm and os.path.exists(r.path))


def pending(g: dict, crate: list) -> dict:
    """What a build would measure: records new or changed, and pairs not yet checked."""
    from utils.audio import library
    live = {r.path: r for r in crate if r.bpm}
    changed = {p for p in live if os.path.exists(p) and _changed(g["records"].get(p), p)}
    stale = g.get("method", 2) < METHOD
    pairs = 0
    for a, ra in live.items():
        done = set() if a in changed or stale else set(g["checked"].get(a, []))
        done -= changed
        pairs += sum(1 for b, rb in live.items()
                     if b != a and b not in done and library.tempo_ratio(ra.bpm, rb.bpm))
    return {"records": len(changed), "pairs": pairs}


_W_LIVE: dict = {}
_W_SIDES: dict = {}


def _side(path: str) -> Optional[_Side]:
    """A worker's _Side for `path`, read once."""
    if path not in _W_SIDES:
        try:
            _W_SIDES[path] = _Side(_W_LIVE[path])
        except Exception as e:
            log_debug(f"[sets] {path} not readable: {e}")
            _W_SIDES[path] = None
        if len(_W_SIDES) > 400:
            _W_SIDES.pop(next(iter(_W_SIDES)))
    s = _W_SIDES[path]
    return s if s is not None and s.ok else None


def _worker_init() -> None:
    """A measuring worker dies with the process that started it."""
    import ctypes
    import signal
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)    # PR_SET_PDEATHSIG
    except Exception:
        pass


def _measure_row(row: tuple) -> tuple:
    """(a, {b: edge}, [every b measured]) for one outgoing record."""
    a_path, cands = row
    a = _side(a_path)
    edges = {}
    if a is not None:
        for b_path in cands:
            b = _side(b_path)
            edge = measure(a, b) if b is not None else None
            if edge:
                edges[b_path] = edge
    return a_path, edges, list(cands)


def build(crate: list, budget_s: Optional[float] = None,
          progress: Optional[Callable[[str], None]] = None, jobs: int = 1) -> Optional[dict]:
    """Measure every unmeasured tempo-compatible pair in `crate`, extending the
    saved graph; drop records no longer in it. Resumable: saved as it goes.
    None if another build is running."""
    from utils.audio import library
    lock = _take_lock()
    if lock is None:
        return None
    _building.set()
    try:
        started = time.time()
        with _lock:
            g = load()
        live = {r.path: r for r in crate if r.bpm}
        if g.get("method", 2) < METHOD:
            g["checked"], g["edges"], g["method"] = {}, {}, METHOD
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
            entry = g["records"].get(p)
            if entry and entry.get("mtime") != m and not _changed(entry, p):
                entry["mtime"] = m                          # retagged, same audio: kept
            elif not entry or entry.get("mtime") != m:      # new or changed: measure it again
                g["records"][p] = {"mtime": m, "sig": library.audio_signature(p)}
                g["edges"].pop(p, None)
                g["checked"].pop(p, None)
                for e in g["edges"].values():
                    e.pop(p, None)
                for c in g["checked"].values():
                    if p in c:
                        c.remove(p)
            if not g["records"][p].get("sig"):
                g["records"][p]["sig"] = library.audio_signature(p)
            if not g["records"][p].get("seconds"):
                from utils.audio import records as R
                g["records"][p]["seconds"] = R.probe_seconds(p)
        rows = []
        for a_path, a_rec in live.items():
            checked = set(g["checked"].get(a_path, []))
            cands = [b.path for b in live.values() if b.path != a_path and b.path not in checked
                     and library.tempo_ratio(a_rec.bpm, b.bpm)]
            if cands:
                rows.append((a_path, cands))
        measured = locked = 0
        jobs = max(1, min(jobs, len(rows)))
        global _W_LIVE
        _W_LIVE = live
        if jobs > 1:
            import multiprocessing
            pool = multiprocessing.get_context("fork").Pool(jobs, initializer=_worker_init)
            results = pool.imap_unordered(_measure_row, rows)
        else:
            pool, results = None, map(_measure_row, rows)
        try:
            for n, (a_path, edges, done) in enumerate(results, 1):
                g["edges"].setdefault(a_path, {}).update(edges)
                if not g["edges"][a_path]:
                    g["edges"].pop(a_path)
                g["checked"][a_path] = sorted(set(g["checked"].get(a_path, [])) | set(done))
                measured += len(done)
                locked += len(edges)
                if n % max(1, jobs) == 0 or n == len(rows):
                    with _lock:
                        save(g)
                if progress:
                    progress(f"[{n}/{len(rows)}] {live[a_path].name}: {len(edges)} of {len(done)} lock")
                if budget_s and time.time() - started > budget_s:
                    break
        finally:
            if pool is not None:
                pool.terminate()
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
        lock.close()


def family(rec) -> str:
    g = (getattr(rec, "genre", "") or "").lower()
    for name, words in FAMILIES:
        if any(w in g for w in words):
            return name
    return "Electronic"


def _seconds(g: dict, path: str) -> float:
    return float((g.get("records", {}).get(path) or {}).get("seconds") or 0.0)


def played_seconds(g: dict, path: list, live: dict) -> float:
    """About how long a set plays: every record's length, less what each
    transition overlaps or skips (the blend, an earlier mix-out, a later cue)."""
    total = sum(_seconds(g, p) for p in path)
    for a, b in zip(path, path[1:]):
        e = g.get("edges", {}).get(a, {}).get(b, {})
        beat = 60.0 / (live[a].bpm or 120.0)
        total -= (e.get("beats", 64) + 32 * e.get("back", 0) + 4 * (e.get("cue") or 0)) * beat
    return total


def make_sets(g: dict, live: dict, rng: Optional[random.Random] = None) -> list:
    """Sets walked through the graph, about an hour each: every next record a
    measured lock from the one before, no song twice in a set (another file or
    mix of it included), held to one genre family where the graph allows,
    preferring a key it sits with and records the other sets have not used.
    Each start is searched (depth first, backing out of dead ends) until the
    walk reaches SET_TARGET_S; one that cannot reach SET_MIN_S is dropped."""
    from utils.audio import library
    rng = rng or random.Random(1)
    secs_known = any(_seconds(g, p) for p in live)

    def eligible(p):
        if p not in live:
            return False
        sec = _seconds(g, p)
        return not secs_known or (sec >= 30.0 and sec <= MAX_SET_RECORD_S)
    edges = {a: {b: e for b, e in nb.items() if eligible(b)}
             for a, nb in g.get("edges", {}).items() if eligible(a)}
    fam = {p: family(live[p]) for p in live}
    used: dict = {}
    sets: list = []
    target = SET_TARGET_S if secs_known else float("inf")
    floor = SET_MIN_S if secs_known else 0.0

    def length(path):
        return played_seconds(g, path, live) if secs_known else float(len(path))

    def walk(start):
        best, best_len = [start], length([start])
        budget = [WALK_BUDGET]
        path = [start]

        def options(cur):
            out = [b for b in edges.get(cur, {}) if used.get(b, 0) < MAX_USES
                   and not any(library.same_song(live[b], live[x]) for x in path)]

            def score(b):
                step = library.key_step(live[cur].key, live[b].key)
                ahead = sum(1 for x in edges.get(b, {}) if x not in path)
                return ((0 if step in (0, 1) else 1 if step == 2 else 2) + (0 if fam[b] == fam[start] else 2),
                        used.get(b, 0), -min(ahead, 6), rng.random())
            return sorted(out, key=score)[:5]

        def dfs():
            nonlocal best, best_len
            n = length(path)
            if n > best_len:
                best, best_len = list(path), n
            if n >= target or budget[0] <= 0:
                return n >= target
            for b in options(path[-1]):
                budget[0] -= 1
                path.append(b)
                if dfs():
                    return True
                path.pop()
            return False
        dfs()
        return best, best_len

    # Starts spread over the families and tempo bands, the best-connected first.
    groups: dict = {}
    for a in sorted(edges, key=lambda a: -len(edges[a])):
        if len(edges[a]) >= 2:
            groups.setdefault((fam[a], int((live[a].bpm or 0) // 8)), []).append(a)
    order = sorted(groups.values(), key=len, reverse=True)
    starts = []
    while any(order):
        for grp in order:
            if grp:
                starts.append(grp.pop(0))
    for start in starts:
        if len(sets) >= MAX_SETS:
            break
        if used.get(start, 0) >= 1:
            continue
        path, n = walk(start)
        if n < floor or len(path) < 4:
            continue
        sets.append(path)
        for p in path:
            used[p] = used.get(p, 0) + 1
    sets.sort(key=lambda st: (family_of(st, live), min(live[p].bpm or 0 for p in st)))
    return sets


def family_of(st: list, live: dict) -> str:
    """A set's genre family: the one most of its records are in."""
    from collections import Counter
    c = Counter(family(live[p]) for p in st if p in live)
    return c.most_common(1)[0][0] if c else "Electronic"


def describe(g: dict, st: list, live: dict) -> dict:
    """What the booth and the set listing say about a set."""
    bpms = [live[p].bpm for p in st if p in live and live[p].bpm]
    return {"family": family_of(st, live), "minutes": round(played_seconds(g, st, live) / 60),
            "bpm": [min(bpms), max(bpms)] if bpms else None}


def partners(g: dict, path: str) -> dict:
    return g.get("edges", {}).get(path, {})


def live_sets(g: dict, crate: list) -> list:
    """The graph's sets, each cut short at the first record no longer in the
    crate (what follows it was measured from it), those of 4 or more."""
    live = {r.path for r in crate}
    out = []
    for st in g.get("sets", []):
        run = []
        for p in st:
            if p not in live:
                break
            run.append(p)
        if len(run) >= 4:
            out.append(run)
    return out


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
    """Measure what is new in `crate` in a separate, niced process
    (`tools/maintenance/records_graph.py`): the measuring is numpy-heavy, and in
    the bot's own process it holds the GIL against the voice thread. `on_done`
    gets the graph when it finishes. True if started."""
    import subprocess
    import sys
    import tempfile
    if building():
        return False
    from dataclasses import asdict
    from utils.infrastructure.monitoring.telemetry_paths import is_test_run
    root = Path(__file__).resolve().parents[2]
    fd, rows = tempfile.mkstemp(prefix="kaia-crate-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump([asdict(r) for r in crate], fh)
    cmd = [sys.executable, str(root / "tools" / "maintenance" / "records_graph.py"), "--apply", "--quiet", "--jobs", "3",
           "--crate", rows]
    if budget_s:
        cmd += ["--budget-min", f"{budget_s / 60:.2f}"]
    env = dict(os.environ)
    if is_test_run() and "KAIACORD_TELEMETRY_SUFFIX" not in env:
        env["KAIACORD_TELEMETRY_SUFFIX"] = ".test"
    _building.set()

    def run():
        try:
            log_file = open(os.devnull, "w")
            proc = subprocess.Popen(cmd, cwd=str(root), env=env, stdout=subprocess.PIPE, stderr=log_file, text=True)
            out, _ = proc.communicate()
            log_file.close()
            if proc.returncode == 0:
                log_info(f"[sets] background build: {(out or '').strip().splitlines()[-1:] or ['done']}")
            else:
                log_warning(f"[sets] background build exited {proc.returncode}")
            if on_done:
                on_done(load())
        except Exception as e:
            log_warning(f"[sets] graph build failed: {e}")
        finally:
            _building.clear()
            try:
                os.remove(rows)
            except OSError:
                pass
    threading.Thread(target=run, daemon=True, name="kaia-records-sets").start()
    log_action("[sets] measuring which records lock with which (background process)")
    return True
