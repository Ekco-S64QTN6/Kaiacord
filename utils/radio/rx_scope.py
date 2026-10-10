"""What the scanner sees, for the receiver dashboard: band panoramas and waterfalls.

The watcher (in its child process) measures one 2.4 MHz slice at a time — a
whole pass of the voice bands every two or three seconds — and, while it holds
a channel, that slice every 0.2 s. Each spectrum arrives here and is laid into
the panorama of the band it falls in, at that band's own resolution, so a band
is one row across however many slices tile it, at the resolution the watcher
sends (`COL_HZ`, ~2.3 kHz a column, so zooming in separates channels on the
widest band too). A row is pushed to every band's waterfall once per pass and
only then: a hold scrolls the TUNED span instead, a row per spectrum, so the
band waterfalls keep one steady pace. Each pass also lays every band side by
side into one overview row (`OV_COLS` wide, max-pooled so a narrow carrier
survives) — the whole dial at a glance, which never jumps. Levels are shown
relative to the slice's median: slices differ by several dB at the tuner and
would otherwise stripe the picture.

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

COLS = 2048                       # the TUNED span's width (every bin) and a night picture's
COL_HZ = wf.FS / wf.NFFT * wf.Watcher.SCOPE_STEP   # a band column: the resolution the watcher sends while hopping
MAX_COLS = 8192                   # a band's panorama width is its span / COL_HZ, up to this
ROWS = 360                        # live waterfall history, per band
OV_COLS = 2400                    # the overview: every band side by side
OV_ROWS = 600
OV_MIN_SHARE = 0.06               # a narrow band still gets this much of the overview's width
NIGHT_EVERY = 6                   # passes folded into one row of a night's picture
NIGHT_ROWS = 2400
LOW_DB, SPAN_DB = -6.0, 40.0      # relative dB shown, bottom of the colour scale and its span

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


def band_cols(lo: int, hi: int) -> int:
    return int(min(MAX_COLS, max(256, np.ceil((hi - lo) / COL_HZ))))


class _Band:
    def __init__(self, lo: int, hi: int, name: str, cols: int = 0):
        self.lo, self.hi, self.name = lo, hi, name
        self.cols = cols or band_cols(lo, hi)
        self.row = np.full(self.cols, np.nan, dtype=np.float32)
        self.rows: deque = deque(maxlen=ROWS)
        self.night: list = []
        self._acc: Optional[np.ndarray] = None
        self._acc_n = 0
        self.touched = False
        self.seq = 0

    def col(self, f):
        return (np.asarray(f, dtype=np.float64) - self.lo) / (self.hi - self.lo) * self.cols


class Scope:
    def __init__(self, bands=None):
        spans = bands or (wf.FAST_BANDS + wf.SLOW_BANDS)
        self.bands = [_Band(lo, hi, NAMES.get((lo, hi), f"{lo / 1e6:g}–{hi / 1e6:g} MHz")) for lo, hi in spans]
        # The slice the watch is sitting on (a hold, a tune, a net), every bin of
        # it, a row per spectrum: the receiver's own span. Kept last in `bands`
        # so the page draws it like any band; its range moves with the dongle.
        self.span = _Band(0, wf.FS, "TUNED", cols=COLS)
        self.span.is_span = True
        self.bands.append(self.span)
        self.lock = threading.Lock()
        self.live: Optional[dict] = None
        self.lockouts: list = []
        self.passes = 0
        self.updated = 0.0
        self.cols = COLS
        self._layout_overview()

    def _layout_overview(self) -> None:
        """Each band's share of the overview: by span, with a floor so the 2 MHz
        33 cm band is still a visible strip beside the 20 MHz 70 cm one."""
        bands = self.bands[:-1]
        order = sorted(range(len(bands)), key=lambda k: bands[k].lo)      # low to high, like a dial
        spans = np.array([bands[k].hi - bands[k].lo for k in order], dtype=np.float64)
        share = np.maximum(spans / spans.sum(), OV_MIN_SHARE) if len(bands) else spans
        share = share / share.sum() if len(bands) else share
        edges = np.round(np.concatenate([[0], np.cumsum(share)]) * OV_COLS).astype(int)
        self.ov_segments = [(0, 0)] * len(bands)                           # indexed by band, placed by frequency
        for slot, k in enumerate(order):
            self.ov_segments[k] = (int(edges[slot]), int(edges[slot + 1]))
        self.ov_rows: deque = deque(maxlen=OV_ROWS)
        self.ov_seq = 0

    @staticmethod
    def _pool(row: np.ndarray, width: int) -> np.ndarray:
        """A quantized row max-pooled to `width` columns (a narrow carrier survives)."""
        if width <= 0:
            return np.zeros(0, np.uint8)
        idx = np.linspace(0, len(row), width + 1).astype(int)[:-1]
        return np.maximum.reduceat(row, np.minimum(idx, len(row) - 1)).astype(np.uint8)

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
            if msg.get("state", "hop") != "hop":
                self._feed_span(center, spec)
            for b in self.bands[:-1]:
                m = valid & (freqs >= b.lo) & (freqs < b.hi)
                if m.sum() < 2:
                    continue
                pos = b.col(freqs[m])
                for side in (pos < b.col(center), pos > b.col(center)):     # either side of the DC guard
                    if side.sum() < 2:
                        continue
                    c0, c1 = int(np.ceil(pos[side].min())), int(np.floor(pos[side].max())) + 1
                    c0, c1 = max(0, c0), min(b.cols, c1)
                    if c1 > c0:
                        b.row[c0:c1] = np.interp(np.arange(c0, c1), pos[side], rel[m][side])
                b.touched = True
            self.live = {"t": time.time(), "center": center, "state": msg.get("state", "hop"),
                         "freq": int(msg.get("freq") or 0), "level": float(msg.get("level") or 0.0),
                         "open": bool(msg.get("open")), "lo": float(freqs[0]), "hi": float(freqs[-1]),
                         "spec": quantize(rel)}

    def _feed_span(self, center: int, spec: np.ndarray) -> None:
        """The watch's own slice, full width: every bin as measured (the tuner's
        centre spike included, as a receiver shows it), one row per spectrum."""
        sp = self.span
        lo = center - wf.FS // 2
        if sp.lo != lo:                                  # retuned: a new span
            sp.lo, sp.hi = lo, center + wf.FS // 2
            sp.rows.clear()
            sp.name = f"TUNED · {center / 1e6:.3f}"
        n = len(spec)
        row = np.interp(np.linspace(0, n - 1, self.cols), np.arange(n), spec) if n != self.cols else spec
        sp.row = (row - np.median(row)).astype(np.float32)
        sp.touched = True
        # A row per spectrum: the watcher already holds them to its frame rate,
        # and a hold's 0.2 s read arrives as several frames at once.
        sp.rows.append(quantize(sp.row))
        sp.seq += 1

    def _push(self, all_touched: bool) -> None:
        ov = np.zeros(OV_COLS, np.uint8)
        for b, (x0, x1) in zip(self.bands[:-1], self.ov_segments):
            if not b.touched:
                continue
            q = quantize(b.row)
            ov[x0:x1] = self._pool(q, x1 - x0)
            b.rows.append(q)
            b.seq += 1
            if all_touched:
                b._acc = q if b._acc is None else np.maximum(b._acc, q)
                b._acc_n += 1
                if b._acc_n >= NIGHT_EVERY:
                    b.night.append(b._acc)
                    del b.night[:-NIGHT_ROWS]
                    b._acc, b._acc_n = None, 0
        self.ov_rows.append(ov)
        self.ov_seq += 1

    # ── reading ──────────────────────────────────────────────────────

    def bands_info(self) -> list:
        with self.lock:
            return [{"i": i, "name": b.name, "lo": b.lo, "hi": b.hi, "seq": b.seq, "cols": b.cols,
                     "span": getattr(b, "is_span", False)}
                    for i, b in enumerate(self.bands)]

    def overview_info(self) -> dict:
        """The overview's layout: its width and where each band sits in it."""
        with self.lock:
            return {"cols": OV_COLS, "seq": self.ov_seq,
                    "segments": [{"i": i, "x0": x0, "x1": x1} for i, (x0, x1) in enumerate(self.ov_segments)]}

    def overview_since(self, seq: int, limit: int = OV_ROWS) -> tuple[int, str, int]:
        """(rows, base64 of them oldest first, the overview's seq now)."""
        with self.lock:
            n = min(limit, self.ov_seq - seq, len(self.ov_rows))
            if n <= 0:
                return 0, "", self.ov_seq
            data = b"".join(r.tobytes() for r in list(self.ov_rows)[-n:])
            return n, base64.b64encode(data).decode("ascii"), self.ov_seq

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
