"""KAIA//RX: the scanner's spectra laid into band panoramas, served to the page."""
import json
import threading
import time
import urllib.request
from types import SimpleNamespace as NS

import numpy as np
import pytest

from utils.radio import rx_scope
from utils.radio import waterfall as w


def _spec(center, signal_hz=None, db=30.0):
    """A slice's smoothed spectrum as the watcher sends it: flat noise, one signal."""
    spec = np.full(w.NFFT, -60.0, dtype=np.float32) + np.random.default_rng(0).normal(0, 0.5, w.NFFT)
    if signal_hz:
        k = int(round((signal_hz - center) / (w.FS / w.NFFT) + w.NFFT / 2))
        spec[k - 4:k + 5] += db
    return spec[::w.Watcher.SCOPE_STEP].astype(np.float16)


def test_a_signal_lands_in_its_bands_panorama_at_its_frequency():
    s = rx_scope.Scope(bands=[(144_000_000, 148_000_000)])
    s.feed({"kind": "spec", "center": 146_000_000, "state": "hop", "spec": _spec(146_000_000, 146_520_000)})
    s.feed({"kind": "pass", "pass": 1, "lockouts": [(146_940_000, 1200)]})
    n, data, seq = s.rows_since(0, 0)
    import base64
    row = np.frombuffer(base64.b64decode(data), np.uint8)
    cols = s.bands[0].cols
    col = int(np.argmax(row))
    hz = 144_000_000 + (col + 0.5) / cols * 4_000_000
    assert n == 1 and len(row) == cols and abs(hz - 146_520_000) < 5_000
    assert row[int((146_000_000 - 144_000_000) / 4e6 * cols)] > 0                   # the DC guard drawn across
    assert s.lockouts == [(146_940_000, 1200)] and s.passes == 1


def test_a_hold_scrolls_the_tuned_span_not_the_band_and_a_night_is_saved(tmp_path, monkeypatch):
    """Band waterfalls keep one pace — a row a pass; a hold scrolls the TUNED span."""
    s = rx_scope.Scope(bands=[(144_000_000, 148_000_000)])
    monkeypatch.setattr(rx_scope, "NIGHT_EVERY", 1)
    for i in range(12):
        s.feed({"kind": "spec", "center": 146_000_000, "state": "hop", "spec": _spec(146_000_000, 146_520_000)})
        s.feed({"kind": "pass", "pass": i})
    before, ov_before = s.bands[0].seq, s.ov_seq
    s.feed({"kind": "spec", "center": 146_000_000, "state": "hold", "freq": 146_520_000, "level": 22.0,
            "spec": _spec(146_000_000, 146_520_000)})
    assert s.bands[0].seq == before and s.ov_seq == ov_before         # the band and the overview don't jump
    assert s.span.seq == 1 and s.live_info()["state"] == "hold"
    saved = s.save_night(tmp_path)
    assert len(saved) == 1 and saved[0].is_file() and not s.bands[0].night


def test_the_watcher_feeds_the_scope_every_visit_and_pass(monkeypatch):
    import utils.radio.dongle as dongle
    from tools.tests.unit.test_local_scanner import _SimDongle
    from utils.radio import scanner
    d = _SimDongle([(146_520_000, 40, 8)], 55)
    d.stop = threading.Event()
    monkeypatch.setattr(w, "time", NS(time=lambda: d.t))
    monkeypatch.setattr(dongle, "Dongle", lambda **k: d)
    got = []
    watcher = w.Watcher(lambda c: None, stop=d.stop, scope=got.append,
                        hops=w.hop_plan([c["freq_hz"] for c in scanner.seed_channels()]))
    watcher.run()
    kinds = {m["kind"] for m in got}
    states = {m.get("state") for m in got if m["kind"] == "spec"}
    assert kinds == {"spec", "pass"} and "hop" in states and states & {"hold", "follow"}
    # Hopping: every SCOPE_STEP-th bin. On one channel: every bin, for the full-width span.
    assert all(len(m["spec"]) == w.NFFT // w.Watcher.SCOPE_STEP for m in got if m["kind"] == "spec" and m["state"] == "hop")
    assert all(len(m["spec"]) == w.NFFT for m in got if m["kind"] == "spec" and m["state"] != "hop")


def test_the_dashboard_serves_state_and_refuses_a_path(monkeypatch):
    import asyncio
    from utils.radio import rx_dashboard
    monkeypatch.setattr(rx_dashboard, "_cfg", lambda k, d: 0 if k == "dashboard_port" else d)

    async def _serve():
        return rx_dashboard.serve()
    base = asyncio.run(_serve())
    try:
        with urllib.request.urlopen(base + "state", timeout=5) as r:
            st = json.loads(r.read())
        assert {"mode", "bands", "kaia", "lockouts"} <= set(st)
        with urllib.request.urlopen(base, timeout=5) as r:
            assert b"KAIA" in r.read()
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + "clip/..%2F..%2F.env", timeout=5)
        with urllib.request.urlopen(base + "kaia/js/kaia-codec.js", timeout=5) as r:     # the avatar engine
            assert b"KaiaCodec" in r.read()
        for bad in ("kaia/js/..%2F..%2F..%2F.env", "kaia/../rx/index.html", "kaia/js/x.py", "kaia/js"):
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(base + bad, timeout=5)
        with urllib.request.urlopen(base + "overview", timeout=5) as r:
            assert {"rows", "data", "seq"} <= set(json.loads(r.read()))
    finally:
        srv, rx_dashboard._server = rx_dashboard._server, None
        srv.shutdown()


def test_a_held_slice_becomes_the_tuned_span_full_width():
    s = rx_scope.Scope(bands=[(144_000_000, 148_000_000)])
    full = np.full(w.NFFT, -60.0, dtype=np.float32)
    k = int(round((146_520_000 - 146_000_000) / (w.FS / w.NFFT) + w.NFFT / 2))
    full[k - 2:k + 3] += 30
    s.feed({"kind": "spec", "center": 146_000_000, "state": "pinned", "freq": 146_520_000, "spec": full.astype(np.float16)})
    span = s.bands[-1]
    assert getattr(span, "is_span", False) and span.lo == 146_000_000 - w.FS // 2 and span.seq == 1
    n, data, _ = s.rows_since(len(s.bands) - 1, 0)
    import base64
    row = np.frombuffer(base64.b64decode(data), np.uint8)
    hz = span.lo + (int(np.argmax(row)) + 0.5) / len(row) * w.FS
    assert n == 1 and abs(hz - 146_520_000) < 3_000             # ~1.2 kHz a column: channels apart
    s.feed({"kind": "spec", "center": 147_000_000, "state": "pinned", "spec": full.astype(np.float16)})
    assert span.lo == 147_000_000 - w.FS // 2                    # retuned: a new span
    assert {b["span"] for b in s.bands_info()} == {False, True}


def test_squelch_open_plays_a_tuned_channel_all_the_time(monkeypatch):
    """SQL OPEN: a tuned channel is heard hiss and all, not only when it keys up."""
    import utils.radio.dongle as dongle
    from tools.tests.unit.test_local_scanner import _SimDongle
    d = _SimDongle([], 8)                                  # nothing transmits
    d.stop = threading.Event()
    monkeypatch.setattr(w, "time", NS(time=lambda: d.t))
    monkeypatch.setattr(dongle, "Dongle", lambda **k: d)
    heard = {"auto": [], "open": []}
    for mode in ("auto", "open"):
        d.t, d.stop = 0.0, threading.Event()
        watcher = w.Watcher(lambda c: None, stop=d.stop, sink=heard[mode].append,
                            squelch_open=(lambda: mode == "open"))
        watcher.run_pinned(146_520_000, until=4.0)
    assert not heard["auto"]                               # squelched: nothing keyed up, nothing heard
    assert len(heard["open"]) > 20 and all(len(a) for a in heard["open"])


def test_the_squelch_setting_reaches_the_running_watch():
    from utils.radio import scanner
    import multiprocessing as mp
    v = mp.get_context("fork").Value("b", 0)
    scanner._squelch_value = v
    try:
        assert scanner.set_squelch_open(True) and v.value == 1 and scanner.squelch_open()
        assert not scanner.set_squelch_open(False) and v.value == 0
    finally:
        scanner._squelch_value = None


def test_a_wide_band_keeps_the_watchers_resolution():
    """20 MHz at the watcher's ~2.3 kHz a column, not squeezed into 2048: two
    channels 12.5 kHz apart stay two peaks."""
    s = rx_scope.Scope(bands=[(420_000_000, 440_000_000)])
    b = s.bands[0]
    assert b.cols >= 4 * 2048 * 0.9 or b.cols == rx_scope.MAX_COLS
    spec = _spec(430_000_000)
    spec = spec.astype(np.float32)
    step = w.FS / w.NFFT * w.Watcher.SCOPE_STEP
    for f in (430_300_000, 430_312_500):
        k = int(round((f - 430_000_000) / step + len(spec) / 2))
        spec[k - 1:k + 2] += 30                              # a narrowband signal: a few bins wide
    s.feed({"kind": "spec", "center": 430_000_000, "state": "hop", "spec": spec.astype(np.float16)})
    row = rx_scope.quantize(b.row)
    c1, c2 = (int(round(b.col(f))) for f in (430_300_000, 430_312_500))
    mid = row[(c1 + c2) // 2]
    assert row[c1] > 200 and row[c2] > 200 and mid < min(row[c1], row[c2])     # two peaks, a dip between


def test_the_overview_lays_every_band_low_to_high_a_row_a_pass():
    s = rx_scope.Scope(bands=[(440_000_000, 450_000_000), (144_000_000, 148_000_000)])
    info = s.overview_info()
    seg = {g["i"]: (g["x0"], g["x1"]) for g in info["segments"]}
    assert seg[1][0] == 0 and seg[1][1] == seg[0][0] and seg[0][1] == rx_scope.OV_COLS     # 2 m first: by frequency
    s.feed({"kind": "spec", "center": 146_000_000, "state": "hop", "spec": _spec(146_000_000, 146_520_000)})
    assert s.ov_seq == 0                                     # nothing until the pass ends
    s.feed({"kind": "pass", "pass": 1})
    n, data, seq = s.overview_since(0)
    import base64
    row = np.frombuffer(base64.b64decode(data), np.uint8)
    x0, x1 = seg[1]
    peak = x0 + int(np.argmax(row[x0:x1]))
    hz = 144_000_000 + (peak + 0.5 - x0) / (x1 - x0) * 4_000_000
    assert n == 1 and seq == 1 and len(row) == rx_scope.OV_COLS and abs(hz - 146_520_000) < 30_000
    assert row[seg[0][0]:seg[0][1]].max() == 0               # a band not yet visited stays dark
