#!/usr/bin/env python3
"""KAIA//RX without a dongle or the bot: the real scanner, a simulated sky.

Runs the real `waterfall.Watcher` against a simulated RTL-SDR paced in real
time — FM voice and tone transmissions keying up on the seeded channels across
the voice bands — and serves the real receiver dashboard on it. The sweep,
holds, follows, lockouts, waterfalls and monitor audio are all the scanner's
own; only the radio is pretend. Nothing is written to the ledger: catches are
dropped, and tune/scan buttons answer that the bot's loop isn't here.

    venv/bin/python3 tools/maintenance/rx_preview.py            # then open the printed address
    venv/bin/python3 tools/maintenance/rx_preview.py --busy 3   # three times the traffic

For looking at the page while working on it. Never start this while the bot's
own scanner holds the dongle — it doesn't touch the dongle, but the dashboard
port is shared (it takes a free one if the configured port is taken).
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.radio import waterfall as w                       # noqa: E402


class PacedSky:
    """A dongle whose samples arrive in real time: FM transmissions in noise.
    Same signal model as the scanner's simulated-dongle tests."""

    def __init__(self, txs: list, snr_db: float = 22.0):
        self.txs, self.t0, self.center = txs, time.time(), 0
        rng = np.random.default_rng(7)
        self.rng = rng
        self.noise = ((rng.standard_normal(2_000_000) + 1j * rng.standard_normal(2_000_000)) * 0.7).astype(np.complex64)
        self.amp = 10 ** (snr_db / 20) / np.sqrt(w.FS / 12.5e3) * 4

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def tune(self, c):
        self.center = c
        time.sleep(0.03)                                    # a retune's settle, roughly as the R820T
        return True

    def read(self, n):
        start = time.time()
        t = (start - self.t0) + np.arange(n) / w.FS
        o = int(self.rng.integers(0, len(self.noise) - n))
        x = self.noise[o:o + n].copy()
        for f, t_on, dur, kind in list(self.txs):
            off = f - self.center
            if abs(off) < w.FS / 2 and t_on < t[-1] and t_on + dur > t[0]:
                on = (t >= t_on) & (t < t_on + dur)
                dev = 3.75 * (0.1 + np.abs(np.sin(2 * np.pi * 2.5 * t))) if kind == "voice" else 3.75
                x += (self.amp * on * np.exp(1j * (2 * np.pi * off * t + dev * np.sin(2 * np.pi * 800 * t)))).astype(np.complex64)
        lag = n / w.FS - (time.time() - start)
        if lag > 0:
            time.sleep(lag)                                 # samples arrive no faster than a real dongle's
        return x


def traffic(channels: list[int], busy: float, stop: threading.Event, txs: list, t0: float) -> None:
    """Keep keying up: a voice over (and often a reply), a tone, now and then a long carrier."""
    rng = random.Random(3)
    while not stop.is_set():
        now = time.time() - t0
        del txs[:-60]
        f = rng.choice(channels)
        kind = rng.choice(["voice", "voice", "voice", "tone"])
        dur = rng.uniform(3, 9)
        txs.append((f, now + rng.uniform(0.5, 2), dur, kind))
        if kind == "voice" and rng.random() < 0.6:          # a reply after the over
            txs.append((f, now + dur + rng.uniform(1.5, 3), rng.uniform(2, 6), "voice"))
        stop.wait(rng.uniform(6, 14) / busy)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--busy", type=float, default=1.0, help="traffic multiplier (default 1)")
    ap.add_argument("--port", type=int, default=0, help="dashboard port (default: the configured one, else free)")
    a = ap.parse_args()

    import utils.radio.dongle as dongle
    from utils.radio import rtl, rx_dashboard, scanner
    from utils.radio.rx_scope import scope

    txs: list = []
    sky = PacedSky(txs)
    stop = threading.Event()
    dongle.Dongle = lambda **k: sky                         # the Watcher opens "the dongle": this
    scanner.running = lambda: True                          # the dashboard shows what a running watch would
    rtl.available = lambda: True
    if a.port:
        rx_dashboard._cfg = (lambda real: (lambda k, d: a.port if k == "dashboard_port" else real(k, d)))(rx_dashboard._cfg)

    channels = [c["freq_hz"] for c in scanner.seed_channels()]
    watcher = w.Watcher(lambda catch: None, stop=stop, scope=scope.feed, sink=rx_dashboard.audio,
                        hops=w.hop_plan(channels), squelch_open=scanner.squelch_open)
    threading.Thread(target=traffic, args=(channels, a.busy, stop, txs, sky.t0), daemon=True).start()
    threading.Thread(target=watcher.run, name="rx-preview-watch", daemon=True).start()

    async def _serve():
        return rx_dashboard.serve()
    url = asyncio.run(_serve())
    print(f"KAIA//RX preview (simulated sky, {len(channels)} seeded channels) at {url}  — Ctrl-C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
