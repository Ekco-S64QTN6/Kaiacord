#!/usr/bin/env python3
"""Which records lock with which, measured, and the hour-long sets walked through them.

The graph (`memory/records/graph.json`) is extended, never rebuilt: a record
new to the catalog, or whose file changed, costs its own pairs. Run by the bot
in a niced background process when a records set starts and the crate holds
records the graph has not measured; run it by hand after adding music:

    venv/bin/python3 tools/maintenance/records_graph.py                 # what would be measured
    venv/bin/python3 tools/maintenance/records_graph.py --apply         # measure, rebuild the sets
    venv/bin/python3 tools/maintenance/records_graph.py --sets-only --apply
    venv/bin/python3 tools/maintenance/records_graph.py --md ~/Downloads/kaia_dj_sets.md

New records need their beats tracked first (`beat_ticks.py`, system Python);
the build tracks any it finds without them. Only one build runs at a time,
across processes; a second exits at once.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _crate(args):
    from utils.audio import library
    if args.crate:
        rows = json.loads(Path(args.crate).read_text(encoding="utf-8"))
        return [library.Record(**r) for r in rows]
    catalog = args.catalog
    if not catalog:
        from utils.infrastructure.system.yaml_config import config
        catalog = config.get("music.library_catalog", "")
    return library.load(catalog)


def write_listing(g: dict, crate: list, path: Path) -> int:
    """The sets as a Markdown track listing."""
    from utils.audio import setlist
    live = {r.path: r for r in crate}
    sets = setlist.live_sets(g, crate)
    lines = ["# Kaia's DJ sets", "",
             f"{len(sets)} sets, every transition measured to lock. Written {time.strftime('%Y-%m-%d %H:%M')}.", ""]
    for i, st in enumerate(sets, 1):
        d = setlist.describe(g, st, live)
        bpm = f"{d['bpm'][0]:.0f}–{d['bpm'][1]:.0f} bpm" if d["bpm"] else ""
        lines += [f"## Set {i} · {d['family']} · {bpm} · about {d['minutes']} min", ""]
        for j, p in enumerate(st, 1):
            r = live[p]
            lines.append(f"{j}. {r.name} — {r.bpm or '?':g} bpm, {r.key or '?'}" if r.bpm else f"{j}. {r.name}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return len(sets)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--catalog", help="dj_catalog.json (default: music.library_catalog)")
    ap.add_argument("--crate", help=argparse.SUPPRESS)       # the bot's crate, as JSON rows
    ap.add_argument("--apply", action="store_true", help="measure and write the graph")
    ap.add_argument("--sets-only", action="store_true", help="rebuild the sets from the graph as it is")
    ap.add_argument("--budget-min", type=float, default=None, help="stop measuring after this many minutes")
    ap.add_argument("--jobs", type=int, default=max(1, min(6, (os.cpu_count() or 2) // 2)),
                    help="processes measuring at once (default: half the cores, at most 6)")
    ap.add_argument("--md", type=Path, help="also write the sets as a Markdown listing here")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    try:
        os.nice(10)
    except OSError:
        pass
    import signal
    # Stopped (by the bot, or by hand): unwind, so the workers are stopped and
    # what was measured is already saved.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    from utils.audio import library, setlist
    crate = _crate(args)
    if not crate:
        print("no records: the catalog is missing or empty", file=sys.stderr)
        return 2
    g = setlist.load()
    if args.sets_only:
        live = {r.path: r for r in crate if r.bpm}
        g["sets"] = setlist.make_sets(g, live)
        if args.apply:
            setlist.save(g)
        print(f"{len(g['sets'])} sets" + ("" if args.apply else " (not written: --apply)"))
    elif not args.apply:
        todo = setlist.pending(g, crate)
        print(f"{len(crate)} records; {todo['records']} new or changed, {todo['pairs']} pairs to measure "
              f"(--apply to measure them)")
    else:
        progress = None if args.quiet else (lambda line: print(line, flush=True))
        g = setlist.build(crate, budget_s=args.budget_min * 60 if args.budget_min else None, progress=progress, jobs=args.jobs)
        if g is None:
            print("another build is running; nothing done", file=sys.stderr)
            return 3
        print(f"{sum(len(e) for e in g['edges'].values())} locking transitions, {len(g['sets'])} sets")
    if args.md:
        n = write_listing(g, crate, args.md.expanduser())
        print(f"wrote {n} sets to {args.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
