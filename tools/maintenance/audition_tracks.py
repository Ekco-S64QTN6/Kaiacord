#!/usr/bin/env python3
"""Play the arranged tracks in Strudel and measure what comes out.

A Strudel pattern that cannot be parsed, or names a sample that does not exist,
does not raise: it plays silence. Reading the code proves nothing, so this
plays it.

    audition_tracks.py                      every genre: parts, then sections
    audition_tracks.py --genre psytrance
    audition_tracks.py --parts-only | --sections-only
    audition_tracks.py --demo DIR           also record build → drop as an mp3

For each part it solos the part in a section where it plays and checks it
makes sound. For each section it records a few bars and reports loudness and
the low / mid / high balance, so the energy curve — groove, build, drop,
breakdown — can be checked as numbers: a drop should be the loudest section and
carry the most low end; a breakdown should drop the low end away.

Needs the music assets (fetch_music_assets.py), ffmpeg and a display: Strudel
only makes sound in a headed browser. Do not run it while Kaia is playing a
set; it shares her audio sink.
"""
import argparse
import math
import subprocess
import sys
import time
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np                                            # noqa: E402
from utils.audio.strudel_engine import SINK_NAME, StrudelEngine  # noqa: E402
from utils.audio.strudel_patterns import GENRES, genre_names   # noqa: E402
from utils.audio.tracks import (LEVELS_PATH, REFERENCE_RMS, ROLE_DB,  # noqa: E402
                                TrackPerformance, _mask_bars, load_levels)

TMP = Path("/tmp/kaia_audition.wav")


def record(seconds: float, out: Path) -> np.ndarray:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "pulse",
                    "-i", f"{SINK_NAME}.monitor", "-t", f"{seconds:.2f}",
                    "-ar", "48000", "-ac", "2", "-y", str(out)],
                   check=True, timeout=seconds + 30)
    with wave.open(str(out)) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    return a.reshape(-1, 2).mean(axis=1)


def gated_rms(mono: np.ndarray, window: int = 2400) -> float:
    """Loudness while the part is sounding: 50 ms windows within 30 dB of the loudest.

    A part that plays one bar in two, or a melody with rests, averaged over the
    rests reads far quieter than it sounds, and calibration then boosted it.
    """
    n = mono.size // window
    if n == 0:
        return 0.0
    w = np.sqrt((mono[: n * window].reshape(n, window) ** 2).mean(axis=1))
    keep = w[w > w.max() * 0.0316]
    return float(np.sqrt((keep ** 2).mean())) if keep.size else 0.0


def bands(mono: np.ndarray) -> dict:
    """Loudness and the share of energy below 150 Hz, 150 Hz–5 kHz and above."""
    if mono.size == 0:
        return {"rms": 0.0, "low": 0.0, "mid": 0.0, "high": 0.0}
    spec = np.abs(np.fft.rfft(mono * np.hanning(mono.size))) ** 2
    freqs = np.fft.rfftfreq(mono.size, 1 / 48000)
    total = spec.sum() + 1e-12
    return {"rms": float(np.sqrt(np.mean(mono ** 2))), "gated": gated_rms(mono),
            "low": float(spec[freqs < 150].sum() / total),
            "mid": float(spec[(freqs >= 150) & (freqs < 5000)].sum() / total),
            "high": float(spec[freqs >= 5000].sum() / total)}


def render_at(perf, bar_to_start: int, engine) -> float:
    """Play the form from `bar_to_start`, beginning at the next cycle."""
    cycle = engine.cycle() or 0.0
    perf.reanchor(int(math.ceil(cycle)) + 1 - bar_to_start)
    engine.play(perf.code())
    bar_s = 240.0 / perf.track.bpm
    # wait for the next cycle boundary, then one more bar for samples to load
    wait = (math.ceil(cycle) + 1 - (engine.cycle() or cycle)) * bar_s
    time.sleep(max(0.0, wait) + 0.05)
    return bar_s


def audition(engine, name: str, do_parts: bool, do_sections: bool, demo: Path | None,
             calibrate: dict | None = None) -> list[str]:
    track = GENRES[name]["track"]
    perf = TrackPerformance(track, anchor=0)
    problems = []
    bar_s = 240.0 / track.bpm
    print(f"\n{name}  ({track.bpm:g} bpm, key {perf.key}, {track.bars} bars, {track.seconds() / 60:.1f} min)")

    measured = {}
    if do_parts:
        perf.energy = False                  # levels are balanced flat; the curve rides on top
        for part in track.parts:
            if part.name not in perf.lanes:
                continue
            first = loudest_bar(track, part)
            perf.soloed = part.name
            # Start a bar early so the measured bar is not the first a sample
            # is fetched for.
            render_at(perf, max(0, first - 1), engine)
            time.sleep(bar_s * (1.0 if first > 0 else 0.3))
            b = bands(record(min(8.0, 2 * bar_s), TMP))
            measured[part.name] = b["gated"]
            err = engine.last_error()
            target = REFERENCE_RMS * 10 ** (ROLE_DB.get(part.name, -14) / 20)
            # Silent means far below what the part is meant to be, not below a
            # fixed floor: vinyl crackle is supposed to sit at -26 dB.
            ok = b["gated"] > max(0.0005, target * 0.05) and not err
            if not ok:
                problems.append(f"{name}.{part.name}")
            section = track.section_at(first)[0]
            off = 20 * math.log10(max(b["gated"], 1e-6) / target)
            print(f"  {'ok  ' if ok else 'SILENT'} part {part.name:9} ({section:7}) level={b['gated']:.4f} "
                  f"({off:+.1f} dB from target)"
                  + (f"  strudel: {str(err)[:80]}" if err else ""))
        perf.soloed = None
        perf.energy = True

    if do_sections:
        at = 0
        for section, bars in track.form:
            render_at(perf, at, engine)
            b = bands(record(min(bars * bar_s, max(3.0, 2 * bar_s)), TMP))
            print(f"  section {section:8} rms={b['rms']:.3f}  low={b['low']:.2f} mid={b['mid']:.2f} "
                  f"high={b['high']:.2f}  " + "#" * int(b["rms"] * 200))
            at += bars

    if demo is not None:
        names = [s for s, _ in track.form]
        start_section = "build" if "build" in names else names[1]
        start = sum(b for s, b in track.form[:names.index(start_section)])
        render_at(perf, max(0, start - 4), engine)
        seconds = min(90.0, 28 * bar_s)
        demo.mkdir(parents=True, exist_ok=True)
        wav = demo / f"{name}.wav"
        record(seconds, wav)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(wav),
                        "-b:a", "192k", "-y", str(demo / f"{name}.mp3")], check=True)
        wav.unlink()
        print(f"  demo: {demo / (name + '.mp3')} ({seconds:.0f}s)")
    if calibrate is not None and measured:
        levels = calibrate.setdefault(name, {})
        for part_name, rms in measured.items():
            target = REFERENCE_RMS * 10 ** (ROLE_DB.get(part_name, -14) / 20)
            current = levels.get(part_name, 1.0)
            if rms > 0.0005:
                # rms was measured with the current level already applied.
                levels[part_name] = round(max(0.05, min(8.0, current * target / rms)), 3)
            print(f"    level {part_name:9} {levels.get(part_name, 1.0):6.3f}  "
                  f"({20 * math.log10(max(rms, 1e-6) / REFERENCE_RMS):+.1f} dB → {ROLE_DB.get(part_name, -14):+d} dB)")
    return problems


def loudest_bar(track, part) -> int:
    """The bar to measure a part at: where it plays, at its highest gain."""
    from utils.audio.tracks import _per_bar
    bars = _mask_bars(track, part.play)
    if "gain" in part.auto:
        gains = _per_bar(track, part.auto["gain"], part.auto["gain"].get("default", 1))
        candidates = [i for i, on in enumerate(bars) if on]
        return max(candidates, key=lambda i: float(gains[i]))
    return bars.index(1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--genre", action="append", help="only these (repeatable)")
    ap.add_argument("--parts-only", action="store_true")
    ap.add_argument("--sections-only", action="store_true")
    ap.add_argument("--demo", type=Path, help="record a build→drop clip per genre into this directory")
    ap.add_argument("--calibrate", action="store_true",
                    help="measure each part and write the level corrections to utils/audio/levels.json")
    args = ap.parse_args()
    levels = load_levels() if args.calibrate else None

    names = args.genre or genre_names()
    engine = StrudelEngine(show_window=False)
    problems = []
    try:
        engine.start()
        time.sleep(8)
        from utils.audio.strudel_patterns import warmup_program
        engine.warm_up(warmup_program())
        for name in names:
            problems += audition(engine, name, not args.sections_only or args.calibrate,
                                 not args.parts_only and not args.calibrate, args.demo, levels)
            if levels is not None:
                import json
                LEVELS_PATH.write_text(json.dumps(levels, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            engine.stop()
            time.sleep(0.5)
    finally:
        engine.close()
    print("\nsilent parts:", ", ".join(problems) if problems else "none")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
