#!/usr/bin/env python3
"""
Play every genre pattern and confirm it actually makes sound.

A Strudel pattern that fails to parse does not raise: evaluate() returns true,
the scheduler logs "[cyclist] start", the AudioContext reports "running", and
the result is silence. The only reliable test is to play it and measure the
audio, which is what this does.

    python tools/maintenance/verify_strudel_patterns.py
    python tools/maintenance/verify_strudel_patterns.py --genre techno --seconds 8
"""
import argparse
import os
import subprocess
import sys
import time
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np                                            # noqa: E402
from utils.audio.strudel_patterns import GENRES, genre_names  # noqa: E402
from utils.audio.performance import build                     # noqa: E402
from utils.audio.strudel_engine import StrudelEngine, SINK_NAME  # noqa: E402


def measure(seconds: float, tmp: Path) -> tuple[float, float]:
    # Same filter chain the live capture uses, so what is measured here is
    # what Discord would actually receive.
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "pulse",
         "-i", f"{SINK_NAME}.monitor", "-t", str(seconds),
         "-af", "acompressor=threshold=0.12:ratio=3:attack=25:release=450,"
                "alimiter=limit=0.85:attack=5:release=60",
         "-ar", "48000", "-ac", "2", "-y", str(tmp)],
        check=True, timeout=seconds + 30)
    with wave.open(str(tmp)) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    a = a.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(a * a))), float(np.abs(a).max())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--genre", help="verify only this one")
    ap.add_argument("--seconds", type=float, default=4.0)
    ap.add_argument("--quick", action="store_true",
                    help="only the fullest state of each genre")
    ap.add_argument("--settle", type=float, default=3.5)
    args = ap.parse_args()

    names = [args.genre] if args.genre else genre_names()
    tmp = Path("/tmp/strudel_verify.wav")
    failures, checked = [], 0

    engine = StrudelEngine(show_window=False)
    try:
        engine.start()
        time.sleep(12)                      # REPL bundle + sample prebake
        for name in names:
            perf = build(GENRES[name])
            print(f"{name}:")
            steps = range(len(perf.script))
            for i in steps:
                code = perf.code()
                live = perf.describe()["lanes"]
                # A step with nothing playing is a legitimate state (the script
                # can strip back to silence); do not call that a failure.
                if live and not (args.quick and i < len(perf.script) - 1):
                    engine.play(code)
                    time.sleep(args.settle)
                    rms, peak = measure(args.seconds, tmp)
                    ok = rms > 0.002
                    checked += 1
                    if not ok:
                        failures.append(f"{name}[{i}] {perf.describe()['section']}")
                    print(f"  {'OK  ' if ok else 'DEAD'} {i:2d} {perf.describe()['section'][:34]:34s} "
                          f"rms={rms:.4f}")
                    if not ok:
                        err = engine.last_error()
                        if err:
                            print(f"       strudel said: {str(err)[:110]}")
                perf.advance(10_000)
            engine.stop()
            time.sleep(0.4)
    finally:
        engine.close()

    print(f"\n{checked - len(failures)}/{checked} states produce audio")
    if failures:
        print("SILENT:", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
