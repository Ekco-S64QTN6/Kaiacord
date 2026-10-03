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
    col = int(np.argmax(row))
    hz = 144_000_000 + (col + 0.5) / rx_scope.COLS * 4_000_000
    assert n == 1 and abs(hz - 146_520_000) < 8_000
    assert row[int((146_000_000 - 144_000_000) / 4e6 * rx_scope.COLS)] > 0          # the DC guard drawn across
    assert s.lockouts == [(146_940_000, 1200)] and s.passes == 1


def test_a_held_channel_scrolls_and_a_night_is_saved(tmp_path, monkeypatch):
    s = rx_scope.Scope(bands=[(144_000_000, 148_000_000)])
    monkeypatch.setattr(rx_scope, "NIGHT_EVERY", 1)
    for i in range(12):
        s.feed({"kind": "spec", "center": 146_000_000, "state": "hop", "spec": _spec(146_000_000, 146_520_000)})
        s.feed({"kind": "pass", "pass": i})
    before = s.bands[0].seq
    s._last_hold_row = 0
    s.feed({"kind": "spec", "center": 146_000_000, "state": "hold", "freq": 146_520_000, "level": 22.0,
            "spec": _spec(146_000_000, 146_520_000)})
    assert s.bands[0].seq == before + 1 and s.live_info()["state"] == "hold"
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
    assert all(len(m["spec"]) == w.NFFT // w.Watcher.SCOPE_STEP for m in got if m["kind"] == "spec")


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
    finally:
        srv, rx_dashboard._server = rx_dashboard._server, None
        srv.shutdown()
