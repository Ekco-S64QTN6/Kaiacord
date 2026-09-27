#!/usr/bin/env python3
"""A notebook of everything the local scanner has heard, built from its ledger.

Writes `docs/reports/reference/local_band_notebook.md` (git-ignored: which
frequencies are live around the station is a deployment fact). One entry per
frequency: what it seems to be, when it is on the air, how long and how often
it keys up, what was said on it, and the clips kept. Everything under the
"## My notes" heading is kept as written across refreshes.

    python tools/maintenance/band_notebook.py            # print it
    python tools/maintenance/band_notebook.py --write    # write the file

Read-only on the ledger. Identification is measured, not guessed where it can
be: a data clip is checked for Bell 202 AFSK (1200/2200 Hz, APRS and packet);
anything else is described by its shape and left for a person to name.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

LEDGER = ROOT / "memory" / "radio" / "local_ledger.sqlite3"
CLIPS = ROOT / "memory" / "radio" / "local_clips"
OUT = ROOT / "docs" / "reports" / "reference" / "local_band_notebook.md"
NOTES_HEADING = "## My notes"

KNOWN = {
    144_390_000: "APRS — position and telemetry packets, 1200 baud AFSK",
    146_520_000: "2m national simplex calling",
    162_400_000: "NOAA weather", 162_425_000: "NOAA weather", 162_450_000: "NOAA weather",
    162_475_000: "NOAA weather", 162_500_000: "NOAA weather", 162_525_000: "NOAA weather",
    162_550_000: "NOAA weather",
}


def _rows() -> tuple[list[dict], list[dict]]:
    con = sqlite3.connect(f"file:{LEDGER}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    channels = [dict(r) for r in con.execute("SELECT * FROM channels")]
    events = [dict(r) for r in con.execute("SELECT * FROM events ORDER BY ts")]
    return channels, events


def clip_profile(clip: Path) -> dict | None:
    """What a clip holds, measured in 50 ms frames: how long a carrier was
    present (the demodulated noise above 3 kHz goes quiet under a signal), how
    much of that time the energy sat on the Bell 202 AFSK tones, and the
    frequency under which 95% of the signal's audio energy lies.

    Whole-clip measures could not tell anything apart, since every clip ends in
    squelch-tail noise: APRS scored 25% on the tones against 22% for plain noise.
    Per frame, the APRS sample had 12% of frames over 0.6 on the tones; no other
    clip had one."""
    try:
        raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(clip),
                              "-f", "s16le", "-ac", "1", "-ar", "12000", "-"],
                             capture_output=True, timeout=60, check=True).stdout
    except Exception:
        return None
    import numpy as np
    a = np.frombuffer(raw, dtype=np.int16).astype(float)
    n = 600
    if len(a) < n * 10:
        return None
    f = np.fft.rfftfreq(n, 1 / 12000)
    band = (f > 300) & (f < 3000)
    tones = ((abs(f - 1200) < 150) | (abs(f - 2200) < 150)) & band
    high = f > 3000
    sig_frames, afsk, spectra = 0, 0, []
    for k in range(0, len(a) - n, n):
        sp = np.abs(np.fft.rfft(a[k:k + n] * np.hanning(n))) ** 2
        total = sp[f > 100].sum() or 1e-9
        if sp[high].sum() / total < 0.15:                  # quieted: a carrier is present
            sig_frames += 1
            spectra.append(sp)
            if sp[tones].sum() / max(sp[band].sum(), 1e-9) > 0.6:
                afsk += 1
    edge = 0
    if spectra:
        mean = np.mean(spectra, axis=0)
        cum = np.cumsum(mean[f > 100]) / mean[f > 100].sum()
        edge = int(f[f > 100][np.searchsorted(cum, 0.95)])
    return {"signal_s": round(sig_frames * n / 12000, 1),
            "afsk_share": round(afsk / sig_frames, 2) if sig_frames else 0.0, "edge_hz": edge}


def _hours(events: list[dict]) -> str:
    counts = defaultdict(int)
    for e in events:
        counts[datetime.fromtimestamp(e["ts"]).hour] += 1
    return ", ".join(f"{h:02d}h×{n}" for h, n in sorted(counts.items()))


def _cadence(events: list[dict]) -> str:
    """The usual gap between key-ups on a busy night, if there is one."""
    ts = [e["ts"] for e in events]
    gaps = [b - a for a, b in zip(ts, ts[1:]) if b - a < 1800]
    if len(gaps) < 4:
        return ""
    med = statistics.median(gaps)
    spread = statistics.pstdev(gaps) / med if med else 9
    regular = spread < 0.35
    return (f"every ~{med:.0f} s" + (" (regular — a beacon or telemetry)" if regular else " (irregular)"))


def real_voice(e: dict) -> bool:
    """A voice event whose transcript still passes today's speech test: the
    ledger keeps what was decided at the time, and "We'll be right back." off
    a bare carrier was once taken for speech."""
    if e["kind"] != "voice":
        return False
    from utils.radio.scanner import looks_like_speech
    return looks_like_speech(e.get("transcript") or "")


def noise_rise_events(events: list[dict]) -> set[int]:
    """Full-minute holds that came in a run across several frequencies: a rise
    in the noise (a household source switching on), not transmitters. The
    watch held hiss this way until 44c5979; the ledger still has those rows."""
    long = [e for e in events if e["seconds"] >= 45 and e["kind"] != "voice"]
    out = set()
    for e in long:
        near = {x["freq_hz"] for x in long if abs(x["ts"] - e["ts"]) <= 900}
        if len(near) >= 4:
            out.add(e["id"])
    return out


def _what(freq: int, ch: dict, evs: list[dict], prof: dict | None) -> str:
    afsk = prof["afsk_share"] if prof else None
    if freq in KNOWN:
        return KNOWN[freq] + (f" (clip: AFSK tones in {afsk:.0%} of the signal)" if afsk else "")
    kinds = {k: sum(1 for e in evs if e["kind"] == k) for k in ("voice", "data", "carrier")}
    kinds["voice"] = sum(1 for e in evs if real_voice(e))
    secs = [e["seconds"] for e in evs]
    if afsk is not None and afsk >= 0.05:
        return f"packet data (Bell 202 AFSK tones in {afsk:.0%} of the signal) — APRS or similar"
    if prof and prof["signal_s"] >= 10 and statistics.median(secs) >= 15 and not kinds["voice"]:
        return (f"long transmissions with no voice ({prof['signal_s']:.0f} s of carrier in the sample, "
                f"energy to {prof['edge_hz'] / 1000:.1f} kHz) — a continuous data link, an open mic or a dead carrier")
    if prof and prof["signal_s"] >= 0.5 and statistics.median(secs) < 15 and not kinds["voice"]:
        return (f"a digital data burst ({prof['signal_s']:.1f} s of carrier, energy filling 0–{prof['edge_hz'] / 1000:.1f} kHz; "
                "not AFSK packet, not voice) — a data modem: telemetry, an alarm link, fleet location or a pager")
    if kinds["voice"]:
        return "voice traffic" + (f" — {ch['label']}" if ch.get("label") else "")
    if kinds["data"]:
        return "digital (broadband: DMR, P25, NXDN or similar)"
    if secs and max(secs) >= 55 and len(evs) <= 3:
        return "a near-constant carrier (held the full minute) — a birdie, a spur or a dead carrier"
    if secs and statistics.median(secs) < 8 and len(evs) >= 5:
        return "short repeating bursts with no voice — telemetry, a data link or a pager"
    return "unidentified"


def build() -> str:
    channels, events = _rows()
    by_freq = defaultdict(list)
    for e in events:
        by_freq[e["freq_hz"]].append(e)
    chan = {c["freq_hz"]: c for c in channels}
    clips = {p.name for p in CLIPS.glob("*.ogg")} if CLIPS.exists() else set()

    rise = noise_rise_events(events)
    ghosts = sorted({e["freq_hz"] for e in events if e["id"] in rise
                     and all(x["id"] in rise for x in by_freq[e["freq_hz"]])})
    entries = []
    for freq, evs in by_freq.items():
        if freq in ghosts:
            continue
        ch = chan.get(freq, {})
        kept = [e["clip"] for e in evs if e.get("clip") and e["clip"] in clips]
        prof = None
        if kept and not any(real_voice(e) for e in evs):
            prof = clip_profile(CLIPS / kept[-1])
        secs = [e["seconds"] for e in evs]
        entries.append({
            "freq": freq, "ch": ch, "evs": evs, "what": _what(freq, ch, evs, prof),
            "voice": sum(1 for e in evs if real_voice(e)),
            "clips": kept[-3:], "secs": secs,
        })
    entries.sort(key=lambda x: (-x["voice"], -len(x["evs"]), x["freq"]))

    first = datetime.fromtimestamp(events[0]["ts"]).strftime("%d %b %Y") if events else "—"
    last = datetime.fromtimestamp(events[-1]["ts"]).strftime("%d %b %Y %H:%M") if events else "—"
    out = [
        "# Local band notebook",
        "",
        f"Everything the RTL-SDR scanner has heard around the station, from its ledger "
        f"({len(events)} catches on {len(entries)} frequencies, {first} to {last}). "
        f"Regenerate with `python tools/maintenance/band_notebook.py --write`; the notes at the "
        f"bottom are kept.",
        "",
        "Frequencies are what the scanner snapped the catch to (5 kHz amateur, 6.25 kHz land-mobile "
        "grid), so a transmitter can appear on a neighbouring step. \"Carrier\" means the scanner "
        "heard no voice and no broadband digital shape — often data or telemetry, sometimes a spur.",
        "",
        "## At a glance",
        "",
        "| MHz | What | Catches | Voice | When (local hours) | Length |",
        "|--:|:--|--:|--:|:--|:--|",
    ]
    for x in entries:
        s = x["secs"]
        length = f"{statistics.median(s):.0f} s" + (f" (to {max(s):.0f})" if max(s) > statistics.median(s) * 1.5 else "")
        out.append(f"| {x['freq'] / 1e6:.4f} | {x['what'][:70]} | {len(x['evs'])} | {x['voice'] or ''} "
                   f"| {_hours(x['evs'])[:60]} | {length} |")

    out += ["", "## Frequencies", ""]
    for x in entries:
        ch, evs = x["ch"], x["evs"]
        out.append(f"### {x['freq'] / 1e6:.4f} MHz — {x['what']}")
        out.append("")
        facts = [f"band: {ch.get('band') or '?'}, service: {ch.get('service') or '?'}"]
        if ch.get("label"):
            facts.append(f"listed as: {ch['label']}")
        facts.append(f"first heard {datetime.fromtimestamp(evs[0]['ts']):%d %b %H:%M}, "
                     f"last {datetime.fromtimestamp(evs[-1]['ts']):%d %b %H:%M}")
        facts.append(f"active hours: {_hours(evs)}")
        cad = _cadence(evs)
        if cad:
            facts.append(f"keys up {cad}")
        out += [f"- {f}" for f in facts]
        said = [e for e in evs if e["kind"] == "voice" and e.get("transcript")]
        for e in said[-4:]:
            note = "" if real_voice(e) else " — not speech: a Whisper phrase off a carrier"
            out.append(f"- {datetime.fromtimestamp(e['ts']):%d %b %H:%M} ({e['seconds']:.0f} s): "
                       f"“{e['transcript'][:200]}”{note}")
        if x["clips"]:
            out.append(f"- clips: {', '.join(f'`{c}`' for c in x['clips'])} (in `memory/radio/local_clips/`)")
        out.append("")

    if ghosts:
        out += ["## Not transmitters", "",
                "Full-minute holds that came in a run across several frequencies within 15 minutes: "
                "a rise in the local noise (something switching on nearby), which the scanner held as "
                "if it were a signal until 27 Sept. Kept here so they aren't mistaken for stations:", "",
                ", ".join(f"{f / 1e6:.4f}" for f in ghosts), ""]
    listed = [c for c in channels if c.get("source") == "listed" and c["freq_hz"] not in by_freq
              and c.get("label") and not c["label"].startswith(("FRS/GMRS ch", "MURS ch", "NOAA WX"))]
    if listed:
        out += ["## Listed and not heard yet", "",
                "Channels from config and the national list the scanner watches but has no catch on:", ""]
        out += [f"- {c['freq_hz'] / 1e6:.4f} — {c['label']}" for c in sorted(listed, key=lambda c: c["freq_hz"])]
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="write docs/reports/reference/local_band_notebook.md")
    args = ap.parse_args()
    text = build()
    notes = f"{NOTES_HEADING}\n\n_Anything here is kept when the notebook is regenerated._\n"
    if OUT.exists():
        old = OUT.read_text(encoding="utf-8")
        if NOTES_HEADING in old:
            notes = old[old.index(NOTES_HEADING):]
    full = text.rstrip() + "\n\n" + notes.rstrip() + "\n"
    if not args.write:
        print(full)
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    from utils.core.atomic_write import write_atomic
    write_atomic(OUT, full)
    print(f"wrote {OUT} ({full.count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
