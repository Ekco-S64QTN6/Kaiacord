"""What a data catch says: APRS packets and pager messages, via multimon-ng.

The scanner files a burst as data when it has a digital mode's shape or Bell
202 tones (APRS). multimon-ng, if installed (`pacman -S multimon-ng`), reads
the catch's own demodulated audio — resampled from 12 kHz to the 22,050 Hz it
expects — for AX.25 at 1200 baud (in TNC2 form: `SRC>DST,PATH:payload`) and
POCSAG at 512/1200/2400. Without it nothing changes: a data catch is a data
catch. On the scanner's real 144.390 audio it read every packet the watch
held (W5EAK-9 via two digipeaters, an iGate's message).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Optional

import numpy as np

MODES = ("AFSK1200", "POCSAG512", "POCSAG1200", "POCSAG2400")
_APRS = re.compile(r"^APRS: ([A-Z0-9]{1,6}(?:-\d{1,2})?)>([^:]+):(.*)$")
_POCSAG = re.compile(r"^(POCSAG\d+): Address:\s*(\d+)\s+Function:\s*(\d)\s*(?:(Alpha|Numeric):\s*(.*))?$")


def binary() -> Optional[str]:
    return shutil.which("multimon-ng")


def available() -> bool:
    return binary() is not None


def parse(text: str) -> list[dict]:
    """multimon-ng's output (run with -A) as records: {"mode", "text", ...}."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if (m := _APRS.match(line)):
            src, path, payload = m.groups()
            out.append({"mode": "APRS", "src": src, "path": path, "payload": payload.strip(),
                        "text": f"[APRS] {src}>{path}: {payload.strip()}"})
        elif (m := _POCSAG.match(line)):
            mode, addr, fn, kind, msg = m.groups()
            msg = (msg or "").strip()
            if msg:
                out.append({"mode": mode, "address": int(addr), "function": int(fn), "payload": msg,
                            "text": f"[{mode}] {addr}: {msg}"})
    return out


def decode(audio: np.ndarray, rate: int = 12_000, timeout: float = 20.0) -> list[dict]:
    """Decode a catch's audio (int16 at `rate`); [] when nothing is readable
    or multimon-ng isn't installed."""
    exe = binary()
    if exe is None or len(audio) < rate // 2:
        return []
    from fractions import Fraction
    from scipy.signal import resample_poly
    r = Fraction(22_050, rate).limit_denominator(1000)
    x = np.clip(resample_poly(np.asarray(audio, dtype=float), r.numerator, r.denominator), -32767, 32767)
    args = [exe, "-t", "raw", "-q", "-A", "-e", "-u"]
    for m in MODES:
        args += ["-a", m]
    try:
        p = subprocess.run(args + ["-"], input=x.astype(np.int16).tobytes(), capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return []
    return parse(p.stdout.decode("utf-8", errors="replace"))


def summary(records: list[dict], limit: int = 600) -> str:
    """The records as one transcript line for the ledger."""
    seen, parts = set(), []
    for r in records:
        if r["text"] not in seen:
            seen.add(r["text"])
            parts.append(r["text"])
    return " · ".join(parts)[:limit]
