#!/usr/bin/env python3
"""Read memory/diagnostics/mem_probe.jsonl: how RSS moved, what the heap trim
gave back, and (with diagnostics.memory_trace on) which lines Python's growth
came from. Read-only.

    venv/bin/python3 tools/maintenance/mem_report.py [--since-hours 24]
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since-hours", type=float, default=48.0)
    ap.add_argument("--file", default=str(ROOT / "memory" / "diagnostics" / "mem_probe.jsonl"))
    a = ap.parse_args()
    path = Path(a.file)
    if not path.is_file():
        print(f"no samples yet at {path}", file=sys.stderr)
        return 1
    cut = time.time() - a.since_hours * 3600
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("ts", 0) >= cut]
    if not rows:
        print("no samples in that window", file=sys.stderr)
        return 1
    print(f"{len(rows)} samples, {datetime.fromtimestamp(rows[0]['ts']):%a %H:%M} → {datetime.fromtimestamp(rows[-1]['ts']):%a %H:%M}\n")
    print("   when        RSS   trimmed  after  traced")
    for r in rows:
        print(f"  {datetime.fromtimestamp(r['ts']):%a %H:%M}  {r['rss_mb']:7.0f}  {r.get('trimmed_mb', 0):7.0f}  {r.get('rss_after_trim_mb', r['rss_mb']):5.0f}"
              f"  {r.get('traced_mb', '—'):>6}")
    hours = max(0.25, (rows[-1]["ts"] - rows[0]["ts"]) / 3600)
    after = [r.get("rss_after_trim_mb", r["rss_mb"]) for r in rows]
    print(f"\nRSS after trim: {after[0]:.0f} → {after[-1]:.0f} MB ({(after[-1] - after[0]) / hours:+.0f} MB/h); "
          f"trim gave back {sum(r.get('trimmed_mb', 0) for r in rows):.0f} MB in all")
    traced = [r["traced_mb"] for r in rows if "traced_mb" in r]
    if len(traced) >= 2:
        print(f"Python traced: {traced[0]:.0f} → {traced[-1]:.0f} MB ({(traced[-1] - traced[0]) / hours:+.0f} MB/h)")
        last = next((r["sites"] for r in reversed(rows) if isinstance(r.get("sites"), list)), [])
        if last:
            print("\nGrew most since the first sample:")
            for s in last:
                print(f"  +{s['mb']:7.1f} MB  {s['blocks']:+8d} blocks  {s['site']}")
    else:
        print("tracemalloc was off: set diagnostics.memory_trace: true in kaia.yaml to name the sites")
    return 0


if __name__ == "__main__":
    sys.exit(main())
