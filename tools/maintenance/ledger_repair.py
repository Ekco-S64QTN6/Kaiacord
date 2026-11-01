#!/usr/bin/env python3
"""Bring the scanner's ledger up to how catches are judged now.

Three repairs, each a dry run unless --apply:

  --clips   Every carrier catch that kept a clip is transcribed the way
            `scanner.classify` now would. Words: the catch becomes voice; a
            short reply or a Morse ID keeps its clip. Nothing heard: the clip
            and its spectrogram are removed — it was kept only because
            Whisper had not been asked (the nightly allowance ran out at
            ~01:30 and dispatch went in as carriers; the 900 MHz hoppers
            passed as "sounded like speech").
  --merge   Rows one transmitter was split across, a grid step apart (5 kHz
            on the ham bands, 6.25 elsewhere), are folded into the busier
            one (`ledger.merge`): pairs where both rows hold voice, and with
            --carriers a voiceless row beside one SHADOW_RATIO times busier.
            `--pair SRC=DST` (MHz) adds a pair measured some other way.
  --streets Dispatch transcripts' misheard street names put right against
            memory/radio/streets.json (`fetch_street_names.py`).

    python tools/maintenance/ledger_repair.py --clips --merge            # what it would do
    python tools/maintenance/ledger_repair.py --clips --merge --apply

Transcription is CPU Whisper, 2–10 s a clip. --apply is refused during the
scanner's hours: the watch is writing then.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _audio(path: Path):
    import numpy as np
    from utils.radio import rtl
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "s16le", "-ac", "1",
                          "-ar", str(rtl.SAMPLE_RATE), "-"], capture_output=True, check=True, timeout=60).stdout
    return np.frombuffer(raw, np.int16)


def _words(audio, freq_hz: int) -> str:
    """What classify() would hear (`scanner.hear`), as it would take it:
    speech, or a short reply, or ""."""
    from utils.radio import scanner
    from utils.radio.waterfall import voice_like
    text = scanner.hear(audio, freq_hz, voice_like(audio))
    return text if scanner.looks_like_speech(text) or scanner.short_reply(text, freq_hz) else ""


def repair_clips(apply: bool) -> dict:
    from utils.radio import ledger, scanner
    folder = scanner._clips_dir()
    rows = [e for e in ledger.events_since(0, ("carrier",)) if e.get("clip")]
    out = {"voice": 0, "short": 0, "morse": 0, "dropped": 0, "missing": 0}
    for e in rows:
        path = folder / e["clip"]
        if not path.is_file():
            out["missing"] += 1
            if apply:
                ledger.forget_clips([e["clip"]])
            continue
        audio = _audio(path)
        text = _words(audio, e["freq_hz"])
        mhz = f"{e['freq_hz'] / 1e6:.5f}"
        if text and not scanner.looks_like_speech(text):
            out["short"] += 1
            print(f"short   {mhz}  {e['clip']}  {text!r} kept")
        elif text:
            out["voice"] += 1
            print(f"voice   {mhz}  {e['clip']}  {text[:100]!r}")
            if apply:
                ledger.relabel_voice(e["id"], text)
        elif scanner.morse_id(audio):
            out["morse"] += 1
            print(f"morse   {mhz}  {e['clip']}  kept")
        else:
            out["dropped"] += 1
            print(f"drop    {mhz}  {e['clip']}  no words")
            if apply:
                path.unlink(missing_ok=True)
                path.with_suffix(".png").unlink(missing_ok=True)
                ledger.forget_clips([e["clip"]])
    return out


#: A voiceless row is a split of its neighbour when the neighbour has this many
#: times its hits. Measured 31 Oct over six minutes of both UHF spans at 293 Hz:
#: 858 key-ups on 9 such pairs, every one within 470 Hz of the busier row's
#: channel, none on the other.
SHADOW_RATIO = 3
SHADOW_MIN_HITS = 10             # under this the busier row's count says nothing


def split_pairs(extra: list[tuple[int, int]], carriers: bool = False) -> list[tuple[int, int]]:
    """(src, dst) pairs one grid step apart: both rows heard a voice, or with
    `carriers` a found row with no voice beside one SHADOW_RATIO times busier.
    The busier (or listed) row keeps the name. A row with busy neighbours on
    both sides is left alone: it may be a channel between two."""
    from utils.radio import ledger, scanner
    rows = {c["freq_hz"]: c for c in ledger.channels() if c["hits"] or c["source"] == "listed"}
    pairs = []
    for f, c in sorted(rows.items()):
        o = rows.get(f + scanner._step(f))
        if not o or "listed" == c["source"] == o["source"]:
            continue
        keep_c = c["source"] == "listed" or (o["source"] != "listed" and c["hits"] >= o["hits"])
        src, dst = (o, c) if keep_c else (c, o)
        if c["voice"] and o["voice"]:
            pairs.append((src["freq_hz"], dst["freq_hz"]))
            continue
        if not carriers or src["voice"] or src["source"] == "listed":
            continue
        other = rows.get(2 * src["freq_hz"] - dst["freq_hz"])          # its neighbour on the far side
        if dst["hits"] >= max(SHADOW_MIN_HITS, SHADOW_RATIO * src["hits"]) and not (other and other["hits"] > src["hits"]):
            pairs.append((src["freq_hz"], dst["freq_hz"]))
    taken, out = set(), []
    for s, d in pairs:                                                    # a row merged away can't receive
        if s not in taken and d not in taken:
            out.append((s, d))
            taken.add(s)
    out += [(s, d) for s, d in extra if s in rows and s not in taken and s != d]
    return out


def repair_splits(extra: list[tuple[int, int]], apply: bool, carriers: bool = False) -> int:
    from utils.radio import ledger
    rows = {c["freq_hz"]: c for c in ledger.channels()}
    pairs = split_pairs(extra, carriers)
    for src, dst in pairs:
        s, d = rows[src], rows.get(dst) or {"hits": 0, "voice": 0}
        print(f"merge   {src / 1e6:.5f} ({s['hits']} hits, {s['voice']} voice) → "
              f"{dst / 1e6:.5f} ({d['hits']} hits, {d['voice']} voice)")
        if apply:
            ledger.merge(src, dst)
    return len(pairs)


def repair_streets(apply: bool) -> int:
    """Voice transcripts on dispatch channels, street names put right as
    classify now would (`scanner.fix_streets`)."""
    from utils.radio import ledger, scanner
    n = 0
    for e in ledger.events_since(0, ("voice",)):
        fixed = scanner.fix_streets(e.get("transcript") or "", e["freq_hz"])
        if fixed != (e.get("transcript") or ""):
            n += 1
            print(f"streets {e['freq_hz'] / 1e6:.5f}  {fixed[:110]!r}")
            if apply:
                ledger.set_transcript(e["id"], fixed)
    return n


def _pair(text: str) -> tuple[int, int]:
    a, b = text.split("=")
    return round(float(a) * 1e6), round(float(b) * 1e6)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--clips", action="store_true", help="transcribe kept carrier clips; relabel or drop")
    ap.add_argument("--merge", action="store_true", help="fold split rows into one")
    ap.add_argument("--streets", action="store_true",
                    help="put misheard street names right in dispatch transcripts (needs streets.json)")
    ap.add_argument("--carriers", action="store_true",
                    help="with --merge: also voiceless rows beside one SHADOW_RATIO times busier")
    ap.add_argument("--pair", action="append", default=[], type=_pair, metavar="SRC=DST",
                    help="also merge this pair (MHz), e.g. 464.34375=464.3375")
    ap.add_argument("--apply", action="store_true", help="write; without it, only report")
    a = ap.parse_args(argv)
    if not (a.clips or a.merge or a.streets):
        ap.error("nothing to do: give --clips, --merge and/or --streets")
    if a.apply:
        from utils.radio import scanner
        if scanner.within_hours():
            print("refused: inside the scanner's hours (radio.local.hours); the watch is writing", file=sys.stderr)
            return 2
    if a.clips:
        print(("applied" if a.apply else "would apply") + f": {repair_clips(a.apply)}")
    if a.merge:
        n = repair_splits(a.pair, a.apply, a.carriers)
        print(("merged" if a.apply else "would merge") + f" {n} pair(s)")
    if a.streets:
        n = repair_streets(a.apply)
        print(("corrected" if a.apply else "would correct") + f" street names in {n} transcript(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
