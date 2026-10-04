"""What the scanner sees, for the receiver dashboard: band panoramas and waterfalls.

The watcher (in its child process) measures one 2.4 MHz slice at a time — a
whole pass of the voice bands every two or three seconds — and, while it holds
a channel, that slice every 0.2 s. Each spectrum arrives here and is laid into
the panorama of the band it falls in, at that band's own resolution, so a band
is one row across however many slices tile it. A row is pushed to the band's
waterfall each pass (and five times a second while holding, so the held
channel scrolls the way a receiver's does). Levels are shown relative to the
slice's median: slices differ by several dB at the tuner and would otherwise
stripe the picture.

A night's waterfall is kept at a coarser time step and saved as a picture per
band when the watch ends (`save_night`), so the day has something to look at.
"""
from __future__ import annotations

import base64
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

import numpy as np

from utils.radio import waterfall as wf

COLS = 2048                       # panorama width, whatever the band's span: ~5 kHz a column on 10 MHz
ROWS = 360                        # live waterfall history, per band
NIGHT_EVERY = 6                   # passes folded into one row of a night's picture
NIGHT_ROWS = 2400
LOW_DB, SPAN_DB = -6.0, 40.0      # relative dB shown, bottom of the colour scale and its span
HOLD_ROW_S = 0.2

NAMES = {
    (144_000_000, 148_000_000): "2 m",
    (150_800_000, 162_560_000): "VHF · MURS · marine · NOAA",
    (440_000_000, 450_000_000): "70 cm repeaters",
    (460_000_000, 470_000_000): "UHF · FRS / GMRS",
    (222_000_000, 225_000_000): "1.25 m",
    (420_000_000, 440_000_000): "70 cm low",
    (450_000_000, 460_000_000): "UHF business",
    (926_200_000, 928_200_000): "33 cm",
}


#: A gap this many columns wide or less is drawn across: a slice's DC guard,
#: which the tuner's centre spike keeps from ever being measured — 40 kHz,
#: 21 columns on the 4 MHz 2 m band.
FILL_COLS = 32


def _fill_gaps(row: np.ndarray) -> np.ndarray:
    bad = np.isnan(row)
    if not bad.any() or bad.all():
        return row
    out = row.copy()
    idx = np.flatnonzero(~bad)
    runs = np.split(np.flatnonzero(bad), np.flatnonzero(np.diff(np.flatnonzero(bad)) > 1) + 1)
    for r in runs:
        if len(r) <= FILL_COLS and r[0] > idx[0] and r[-1] < idx[-1]:
            out[r] = np.interp(r, idx, row[idx])
    return out


def quantize(rel: np.ndarray) -> np.ndarray:
    v = np.nan_to_num((_fill_gaps(rel) - LOW_DB) / SPAN_DB, nan=0.0)
    return (np.clip(v, 0.0, 1.0) * 255).astype(np.uint8)


class _Band:
    def __init__(self, lo: int, hi: int, name: str):
        self.lo, self.hi, self.name = lo, hi, name
        self.row = np.full(COLS, np.nan, dtype=np.float32)
        self.rows: deque = deque(maxlen=ROWS)
        self.night: list = []
        self._acc: Optional[np.ndarray] = None
        self._acc_n = 0
        self.touched = False
        self.seq = 0

    def col(self, f):
        return (np.asarray(f, dtype=np.float64) - self.lo) / (self.hi - self.lo) * COLS


class Scope:
    def __init__(self, bands=None):
        spans = bands or (wf.FAST_BANDS + wf.SLOW_BANDS)
        self.bands = [_Band(lo, hi, NAMES.get((lo, hi), f"{lo / 1e6:g}–{hi / 1e6:g} MHz")) for lo, hi in spans]
        self.lock = threading.Lock()
        self.live: Optional[dict] = None
        self.lockouts: list = []
        self.passes = 0
        self.updated = 0.0
        self.cols = COLS
        self._last_hold_row = 0.0

    # ── feeding ──────────────────────────────────────────────────────

    def feed(self, msg: dict) -> None:
        with self.lock:
            self.updated = time.time()
            if msg.get("kind") == "pass":
                self.passes = int(msg.get("pass", self.passes))
                self.lockouts = list(msg.get("lockouts") or [])
                self._push(all_touched=True)
                return
            spec = np.asarray(msg["spec"], dtype=np.float32)
            center = int(msg["center"])
            step = wf.FS / wf.NFFT * (wf.NFFT // len(spec))
            freqs = center + (np.arange(len(spec)) - len(spec) / 2) * step
            off = freqs - center
            valid = (np.abs(off) <= wf.FS * wf.USABLE / 2) & (np.abs(off) >= wf.DC_GUARD_HZ)
            if not valid.any():
                return
            rel = spec - np.median(spec[valid])
            for b in self.bands:
                m = valid & (freqs >= b.lo) & (freqs < b.hi)
                if m.sum() < 2:
                    continue
                pos = b.col(freqs[m])
                for side in (pos < b.col(center), pos > b.col(center)):     # either side of the DC guard
                    if side.sum() < 2:
                        continue
                    c0, c1 = int(np.ceil(pos[side].min())), int(np.floor(pos[side].max())) + 1
                    c0, c1 = max(0, c0), min(COLS, c1)
                    if c1 > c0:
                        b.row[c0:c1] = np.interp(np.arange(c0, c1), pos[side], rel[m][side])
                b.touched = True
            self.live = {"t": time.time(), "center": center, "state": msg.get("state", "hop"),
                         "freq": int(msg.get("freq") or 0), "level": float(msg.get("level") or 0.0),
                         "open": bool(msg.get("open")), "lo": float(freqs[0]), "hi": float(freqs[-1]),
                         "spec": quantize(rel)}
            if msg.get("state") in ("hold", "follow", "pinned") and time.time() - self._last_hold_row >= HOLD_ROW_S:
                self._last_hold_row = time.time()
                self._push(all_touched=False, center=center)

    def _push(self, all_touched: bool, center: Optional[int] = None) -> None:
        for b in self.bands:
            if not b.touched or (center is not None and not (b.lo - wf.FS / 2 <= center <= b.hi + wf.FS / 2)):
                continue
            q = quantize(b.row)
            b.rows.append(q)
            b.seq += 1
            if all_touched:
                b._acc = q if b._acc is None else np.maximum(b._acc, q)
                b._acc_n += 1
                if b._acc_n >= NIGHT_EVERY:
                    b.night.append(b._acc)
                    del b.night[:-NIGHT_ROWS]
                    b._acc, b._acc_n = None, 0

    # ── reading ──────────────────────────────────────────────────────

    def bands_info(self) -> list:
        with self.lock:
            return [{"i": i, "name": b.name, "lo": b.lo, "hi": b.hi, "seq": b.seq} for i, b in enumerate(self.bands)]

    def rows_since(self, i: int, seq: int, limit: int = ROWS) -> tuple[int, str, int]:
        """(rows, base64 of them oldest first, the band's seq now)."""
        with self.lock:
            b = self.bands[i]
            n = min(limit, b.seq - seq, len(b.rows))
            if n <= 0:
                return 0, "", b.seq
            data = b"".join(r.tobytes() for r in list(b.rows)[-n:])
            return n, base64.b64encode(data).decode("ascii"), b.seq

    def live_info(self) -> Optional[dict]:
        with self.lock:
            if not self.live or time.time() - self.live["t"] > 5:
                return None
            d = dict(self.live)
            d["spec"] = base64.b64encode(d["spec"].tobytes()).decode("ascii")
            return d

    # ── a night's picture ────────────────────────────────────────────

    def save_night(self, folder: Path, keep_nights: int = 14) -> list[Path]:
        """Each band's night as a PNG (time down, frequency across), then the
        night store is cleared. Returns what was written."""
        from PIL import Image, ImageDraw
        from utils.radio.spectrogram import _palette
        folder.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d")
        out = []
        with self.lock:
            nights = [(b, np.array(b.night)) for b in self.bands if len(b.night) >= 10]
            for b in self.bands:
                b.night, b._acc, b._acc_n = [], None, 0
        for b, rows in nights:
            img = Image.fromarray(_palette()[rows], "RGB").resize((COLS, max(200, min(1200, len(rows)))))
            canvas = Image.new("RGB", (COLS, img.height + 22), (4, 6, 12))
            canvas.paste(img, (0, 22))
            ImageDraw.Draw(canvas).text((6, 4), f"{b.name} · {b.lo / 1e6:g}–{b.hi / 1e6:g} MHz · night of {stamp}",
                                        fill=(0, 240, 255))
            name = folder / f"{stamp}_{b.lo // 1_000_000}MHz.png"
            tmp = name.with_name(f".{name.name}.tmp")
            canvas.save(tmp, format="PNG", optimize=True)
            tmp.replace(name)
            out.append(name)
        for old in sorted(folder.glob("*.png"))[:-keep_nights * len(self.bands)]:
            old.unlink(missing_ok=True)
        return out


scope = Scope()
