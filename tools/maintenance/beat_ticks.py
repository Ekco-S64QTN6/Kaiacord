#!/usr/bin/env python3
"""Beat positions for records, from Essentia's beat tracker, cached for the mixer.

The mixer's own grids came from the rise in energy under 160 Hz, which on real
records follows the bassline as much as the kick: their phase wandered by up to
half a beat from one stretch of a record to the next, and blends played two
kicks 30–180 ms apart. Essentia's RhythmExtractor2013 (multifeature) holds its
ticks within ~4–8 ms whether a record is read raw or stretched.

Run by the system Python, which has Essentia (the bot's venv does not):

    /usr/bin/python3 tools/maintenance/beat_ticks.py PATH [PATH…]        # these records
    /usr/bin/python3 tools/maintenance/beat_ticks.py --catalog FILE       # a whole dj_catalog.json

Each record's ticks go to <cache>/<sha1 of path>.json with BPM, confidence,
ticks, the complete audio signature and requested folding BPM. An entry is
retained only while both identities match. A tracker that lands on half or
double the catalog's tempo is folded
back to it (half-time ticks get the beats between them). Existing entries are
kept unless --force. Prints one line per record; exits non-zero if any failed.

The ticks are used as the tracker gives them. Moving them onto "the kick" by
the rise in 50–150 Hz energy was tried and is wrong: an off-beat bassline
rises in the same band, and on one record that rise peaked 182 ms before the
beat over the whole record and 43 ms after it in one minute of it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.audio.audio_identity import audio_signature

CACHE = ROOT / "memory" / "records" / "ticks"


def cache_path(path: str, cache: Path = CACHE) -> Path:
    return cache / (hashlib.sha1(path.encode("utf-8")).hexdigest()[:16] + ".json")


#: The tracker's onset buffer overflows on an hour-long mix; beyond this a
#: plan has no ticks to count on and uses its grid's own line.
MAX_SECONDS = 900


def _decode(path: str):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-t", str(MAX_SECONDS), "-i", path, "-ac", "1", "-ar", "44100",
                          "-f", "f32le", "pipe:1"], capture_output=True, timeout=180).stdout
    return np.frombuffer(raw, dtype=np.float32)


def fold(bpm: float, ticks, want):
    """Fold octave tempo errors without discarding the alternate double-tempo phase."""
    import numpy as np
    ticks = np.asarray(ticks, dtype=float)
    if not want or len(ticks) < 4:
        return bpm, ticks, None
    r = bpm / want
    if 0.45 < r < 0.55:
        mids = (ticks[:-1] + ticks[1:]) / 2
        return bpm * 2, np.sort(np.concatenate([ticks, mids])), None
    if 1.8 < r < 2.2:
        # Both phases are plausible at half the tracker rate. The runtime grid
        # chooses one only when its local onset evidence clearly prefers it.
        return bpm / 2, ticks[::2], ticks[1::2]
    return bpm, ticks, None


def analyse(path: str, want_bpm=None, identity: Optional[str] = None) -> dict:
    import essentia
    essentia.log.infoActive = False
    import essentia.standard as es
    identity = identity or audio_signature(path)
    if identity is None:
        raise ValueError("could not identify record audio")
    x = _decode(path)
    if len(x) < 44100 * 10:
        raise ValueError("under ten seconds of audio")
    bpm, ticks, conf, _, _ = es.RhythmExtractor2013(method="multifeature")(x)
    bpm, ticks, alternate_ticks = fold(float(bpm), ticks, want_bpm)
    if audio_signature(path, refresh=True) != identity:
        raise RuntimeError("record audio changed while beat ticks were being analysed")
    return {
        "bpm": round(float(bpm), 3),
        "confidence": round(float(conf), 3),
        "audio_signature": identity,
        "target_bpm": round(float(want_bpm), 3) if want_bpm else None,
        "ticks": [round(float(t), 4) for t in ticks],
        "alternate_ticks": ([round(float(t), 4) for t in alternate_ticks]
                            if alternate_ticks is not None else None),
    }


def _write(dest: Path, data: dict) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, dest)                   # atomic: a half-written cache entry is never read


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--catalog", help="a dj_catalog.json: every record in it")
    ap.add_argument("--bpm", type=float, help="the catalog tempo of the one PATH given")
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--force", action="store_true", help="redo records already cached")
    a = ap.parse_args()
    cache = Path(a.cache)
    jobs = [(p, a.bpm) for p in a.paths]
    if a.catalog:
        rows = json.loads(Path(os.path.expanduser(a.catalog)).read_text(encoding="utf-8"))
        jobs += [(r["filepath"], float(r["bpm"]) if r.get("bpm") else None) for r in rows if r.get("filepath")]
    if not jobs:
        ap.error("give record paths or --catalog")
    failed = 0
    for path, bpm in jobs:
        dest = cache_path(path, cache)
        try:
            identity = audio_signature(path)
            if identity is None:
                raise ValueError("could not identify record audio")
            if dest.exists() and not a.force:
                try:
                    cached = json.loads(dest.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    cached = {}
                target_bpm = round(float(bpm), 3) if bpm else None
                alternate = cached.get("alternate_ticks")
                phase_cache_complete = (
                    alternate is None
                    or (isinstance(alternate, list) and len(alternate) >= 16)
                )
                if (cached.get("audio_signature") == identity
                        and "target_bpm" in cached
                        and "alternate_ticks" in cached
                        and phase_cache_complete
                        and cached.get("target_bpm") == target_bpm):
                    continue
            data = analyse(path, bpm, identity=identity)
            # A missing field is a legacy schema and must be regenerated once;
            # test doubles and future alternate analyzers still write explicit null.
            data.setdefault("alternate_ticks", None)
            _write(dest, data)
            print(f"ok   {data['bpm']:7.2f} bpm  conf {data['confidence']:.2f}  {len(data['ticks'])} beats  {os.path.basename(path)}")
        except Exception as e:
            failed += 1
            print(f"FAIL {os.path.basename(path)}: {e}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
