#!/usr/bin/env python3
"""Carry the records caches over to the complete-payload audio identity.

`library.audio_signature` was a SHA-1 of the first and last 256 KB of a
record's audio; it is now a versioned BLAKE2 of the whole payload
(`utils/audio/audio_identity.py`). Every cache keyed by the old value reads as
"audio changed" under the new one, so without this the measured pair graph
is thrown away and every beat-tick file is refused. The ticks cannot simply
be made again: `beat_ticks.py` needs Essentia under the system Python.

What is carried over, and only where the old evidence still holds:

  graph.json   a record whose old signature, recomputed now, is the one the
               graph stored gets the new identity; its edges are kept.
  ticks/*.json a tick file with no identity gets the record's identity, the
               catalog BPM it is read against, and no alternate phase: exactly
               how these ticks were used before. Only where it is evidently
               this record's: written after the record last changed, or its
               tempo within TEMPO_AGREES of the catalog's (a retag moves the
               record's mtime and leaves the audio alone).

Maps and onset envelopes are not touched: their curves changed (`songmap`
VERSION 3, `mixcheck` .v2.npz) and are remade from the audio on first use.

    venv/bin/python3 tools/maintenance/migrate_record_identity.py          # what would change
    venv/bin/python3 tools/maintenance/migrate_record_identity.py --apply

Refuses while a graph build holds `graph.lock`. Safe to run again: anything
already on the new identity is left alone.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PREFIX = "v2:"
#: A tick file's tempo this close to the catalog's is this record's beat.
TEMPO_AGREES = 0.04


def legacy_signature(path: str) -> Optional[str]:
    """The old `library.audio_signature`: ID3 tags skipped, the first and last
    256 KB of what is left hashed with its length."""
    try:
        with open(path, "rb") as f:
            head = f.read(10)
            start = 0
            if len(head) == 10 and head[:3] == b"ID3":
                size = ((head[6] & 0x7F) << 21) | ((head[7] & 0x7F) << 14) | ((head[8] & 0x7F) << 7) | (head[9] & 0x7F)
                start = 10 + size + (10 if head[5] & 0x10 else 0)
            f.seek(0, 2)
            end = f.tell()
            if end - 128 >= start:
                f.seek(end - 128)
                if f.read(3) == b"TAG":
                    end -= 128
            if end <= start:
                return None
            span = 262144
            f.seek(start)
            a = f.read(min(span, end - start))
            f.seek(max(start, end - span))
            b = f.read(end - max(start, end - span))
    except OSError:
        return None
    return hashlib.sha1(a + b + str(end - start).encode()).hexdigest()[:20]


def migrate_graph(g: dict) -> dict:
    """Upgrade the graph's record identities in place; count what happened."""
    from utils.audio.library import audio_signature
    counts = {"kept": 0, "upgraded": 0, "changed": 0, "missing": 0}
    for path, entry in g.get("records", {}).items():
        sig = entry.get("sig") or ""
        if sig.startswith(PREFIX):
            counts["kept"] += 1
            continue
        if not os.path.isfile(path):
            counts["missing"] += 1
            continue
        if not sig or legacy_signature(path) != sig:
            counts["changed"] += 1          # left as is: the build measures it again
            continue
        identity = audio_signature(path)
        if identity is None:
            counts["missing"] += 1
            continue
        entry["sig"] = identity
        counts["upgraded"] += 1
    return counts


def migrate_ticks(records: dict, apply: bool) -> dict:
    """`records`: path -> catalog BPM (None when unknown)."""
    from utils.audio import beatgrid
    from utils.audio.library import audio_signature
    from utils.core.atomic_write import write_atomic
    counts = {"kept": 0, "upgraded": 0, "unverified": 0, "unreadable": 0}
    for path, bpm in sorted(records.items()):
        cache = beatgrid._ticks_path(path)
        if not cache.exists() or not os.path.isfile(path):
            continue
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            counts["unreadable"] += 1
            continue
        if not isinstance(data, dict) or beatgrid._valid_tick_array(data.get("ticks")) is None:
            counts["unreadable"] += 1
            continue
        if data.get("audio_signature"):
            counts["kept"] += 1
            continue
        written_after = os.path.getmtime(path) <= cache.stat().st_mtime + 1.0
        try:
            agrees = bool(bpm) and abs(float(data.get("bpm")) / float(bpm) - 1.0) <= TEMPO_AGREES
        except (TypeError, ValueError, ZeroDivisionError):
            agrees = False
        if not (written_after or agrees):
            counts["unverified"] += 1       # left for beat_ticks.py to find again
            continue
        identity = audio_signature(path)
        if identity is None:
            counts["unreadable"] += 1
            continue
        data["audio_signature"] = identity
        data["target_bpm"] = round(float(bpm), 3) if bpm else None
        data["alternate_ticks"] = None
        if apply:
            write_atomic(cache, json.dumps(data))
        counts["upgraded"] += 1
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the changes (default: report only)")
    ap.add_argument("--catalog", help="dj_catalog.json (default: music.library_catalog)")
    args = ap.parse_args(argv)

    from utils.audio import library, setlist
    catalog = args.catalog
    if not catalog:
        from utils.infrastructure.system.yaml_config import config
        catalog = config.get("music.library_catalog", "") or ""
    crate = library.load(catalog) if catalog else []

    lock = setlist._take_lock()
    if lock is None:
        print("REFUSED: a records graph build is running (graph.lock); try again when it ends.",
              file=sys.stderr)
        return 2
    try:
        g = setlist.load()
        graph = migrate_graph(g)
        if args.apply and graph["upgraded"]:
            setlist.save(g)
    finally:
        lock.close()

    bpms = {path: None for path in g.get("records", {})}
    bpms.update({r.path: r.bpm for r in crate})
    ticks = migrate_ticks(bpms, args.apply)

    verb = "upgraded" if args.apply else "would upgrade"
    print(f"graph.json: {verb} {graph['upgraded']}, already current {graph['kept']}, "
          f"audio changed {graph['changed']}, missing {graph['missing']}")
    print(f"ticks:      {verb} {ticks['upgraded']}, already current {ticks['kept']}, "
          f"not shown to be this record's {ticks['unverified']}, unreadable {ticks['unreadable']}")
    if not args.apply and (graph["upgraded"] or ticks["upgraded"]):
        print("(nothing written: --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
