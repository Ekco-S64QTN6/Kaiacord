"""KAIA//RX as a receiver: tuned in place, heard without delay, logged with
what it learned — habits, periods, bookmarks — and what is worth a look."""
import json
import queue
import sqlite3
import struct
import threading
import time
import urllib.request
from types import SimpleNamespace as NS

import numpy as np
import pytest

from utils.radio import waterfall as w


# ── the demodulator and squelch ──────────────────────────────────────────────

def _fm(n, offset=150_000, seed=3):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / w.FS
    return (np.exp(1j * (2 * np.pi * offset * t + 2.5 * np.sin(2 * np.pi * 1000 * t))) * 0.5
            + 0.02 * (rng.standard_normal(n) + 1j * rng.standard_normal(n))).astype(np.complex64)


def test_chunked_demodulation_is_one_continuous_signal():
    """Per-chunk resample_poly padded every chunk's edges — a click at each
    boundary — and slipped on reads that aren't multiples of 50 samples."""
    iq = _fm(w.FS)
    whole = w.NbfmDemod(150_000)(iq)
    d, parts, i = w.NbfmDemod(150_000), [], 0
    for n in np.random.default_rng(1).integers(20_000, 90_000, 100):
        parts.append(d(iq[i:i + n]))
        i += n
        if i >= len(iq):
            break
    chunked = np.concatenate(parts)
    m = min(len(whole), len(chunked))
    assert abs(len(whole) - len(chunked)) <= 1 and np.array_equal(whole[:m], chunked[:m])


def test_the_live_squelch_opens_at_once_and_still_tells_a_pulse_from_a_carrier():
    hiss = (np.diff(np.random.default_rng(1).normal(size=12_000 + 1)) * 5000).astype(np.int16)
    tone = (np.sin(np.linspace(0, 800 * np.pi, 12_000)) * 3000).astype(np.int16)
    sq = w.LiveSquelch()
    assert not sq.push(hiss[:2400])[0].any() and not sq.is_open
    out = sq.push(tone[:2400])[0]
    first = np.flatnonzero(out.reshape(-1, w.FRAME).any(axis=1))[0]
    assert first <= 2 and sq.is_open                       # the second frame: no look-ahead
    sq.push(tone)
    assert sq.opened                                       # a run of OPEN_S: a transmission
    pulse = w.LiveSquelch()
    for _ in range(6):
        pulse.push(tone[:2400])                            # 0.2 s bursts
        pulse.push(hiss[:12_000])
    assert not pulse.opened


def test_a_span_row_is_full_resolution_with_the_centre_spike_removed():
    iq = (np.random.default_rng(0).standard_normal(w.PIN_CHUNK) * 0.05 + 0.3).astype(np.complex64)   # a DC offset
    row = w.span_row(iq)
    assert row.dtype == np.uint8 and len(row) == w.SPAN_NFFT
    centre = int(row[w.SPAN_NFFT // 2 - 2:w.SPAN_NFFT // 2 + 3].max())
    assert centre <= np.percentile(row, 99.9)              # no spike standing over the noise
    x = iq - iq.mean()
    raw = 10 * np.log10(np.abs(np.fft.fftshift(np.fft.fft(iq[:w.SPAN_NFFT]))) ** 2 + 1e-12)
    assert raw[w.SPAN_NFFT // 2] - np.median(raw) > 40      # which it would, without the removal


# ── one watcher, switched in place ───────────────────────────────────────────

class Sky:
    """A simulated dongle on a simulated clock (the scanner tests' model),
    counting opens and retunes."""

    def __init__(self, txs, until):
        from tools.tests.unit.test_local_scanner import _SimDongle
        self.d = _SimDongle(txs, until)
        self.d.stop = threading.Event()
        self.opens = 0
        self.tunes = []
        real_tune = self.d.tune

        def tune(c):
            self.tunes.append(c)
            return real_tune(c)
        self.d.tune = tune

    def install(self, monkeypatch):
        import utils.radio.dongle as dongle

        def factory(**k):
            self.opens += 1
            return self.d
        monkeypatch.setattr(dongle, "Dongle", factory)
        monkeypatch.setattr(w, "time", NS(time=lambda: self.d.t))


def _control(script, sky):
    """Commands released when the simulated clock passes their time."""
    pending = sorted(script, key=lambda x: x[0])

    def control():
        out = []
        while pending and sky.d.t >= pending[0][0]:
            out.append(pending.pop(0)[1])
        return out
    return control


def test_a_tune_switches_the_running_watch_in_place(monkeypatch):
    sky = Sky([], 30)
    sky.install(monkeypatch)
    got = []
    ctl = _control([(10.0, {"op": "tune", "freq": 146_520_000, "until": 100}),
                    (14.0, {"op": "tune", "freq": 146_700_000, "until": 100}),      # inside the same span
                    (18.0, {"op": "scan"})], sky)
    wt = w.Watcher(lambda c: None, stop=sky.d.stop, scope=got.append, control=ctl)
    wt.run()
    spans = [m for m in got if m["kind"] == "span"]
    on = [m for m in spans if m["freq"] == 146_520_000]
    # Picked up between hops, then one retune and one read: a fifth of a second.
    assert on and on[0]["t"] - 10.0 < 0.25
    moved = [m for m in spans if m["freq"] == 146_700_000]
    assert moved and moved[0]["t"] - 14.0 < 0.1 and moved[0]["center"] == on[0]["center"]    # no retune: one read
    assert sky.opens == 1                                   # never reopened
    after_tune = [c for c in sky.tunes if True]
    assert after_tune.count(146_520_000 - w.PIN_OFFSET_HZ) == 1 and 146_700_000 - w.PIN_OFFSET_HZ not in sky.tunes
    hops_after = [m for m in got if m["kind"] == "spec" and m["t"] > 18.0]
    assert hops_after and hops_after[0]["t"] - 18.0 < 0.2   # back to the sweep at once


def test_a_tune_ends_a_hold_at_once(monkeypatch):
    sky = Sky([(146_860_000, 20, 60, "voice")], 45)          # a minute-long over, held
    sky.install(monkeypatch)
    caught = []
    ctl = _control([(30.0, {"op": "tune", "freq": 446_000_000, "until": 100})], sky)
    wt = w.Watcher(caught.append, stop=sky.d.stop, control=ctl,
                   hops=w.hop_plan([146_860_000, 446_000_000]))
    wt.run()
    time.sleep(0.2)
    held = [c for c in caught if abs(c.freq_hz - 146_860_000) < 5000]
    assert held and held[0].started + held[0].seconds - 30.0 <= w.HOLD_CHUNK_S + 0.05


def test_a_habitual_channel_is_seen_not_held_unless_it_runs_long(monkeypatch):
    f = 463_512_500
    txs = [(f, 40 + 43 * k, 3.0, "tone") for k in range(4)] + [(f, 230, 25.0, "voice")]
    sky = Sky(txs, 270)
    sky.install(monkeypatch)
    caught = []
    wt = w.Watcher(caught.append, stop=sky.d.stop, hops=w.hop_plan([f]), habits={f: 6.0})
    wt.run()
    time.sleep(0.2)
    seen = [c for c in caught if isinstance(c, w.Sighting)]
    held = [c for c in caught if isinstance(c, w.Catch) and abs(c.freq_hz - f) < 5000]
    assert len(seen) >= 3
    assert held and all(c.started >= 230 for c in held)     # only the burst that ran long


def test_every_tenth_burst_of_a_habit_is_held_as_a_sample():
    wt = w.Watcher(lambda c: None, habits={463_512_500: 6.0})
    held = [wt._habit_holds(463_512_500, 20.0, 100.0 + 60 * k) for k in range(20)]
    assert [k + 1 for k, h in enumerate(held) if h] == [10, 20]


def test_what_else_keys_up_in_the_held_slice_is_recorded_too(monkeypatch):
    """A followed conversation keeps the watch on one channel; a second
    channel in the same slice talking meanwhile used to be lost."""
    a, b = 462_562_500, 462_712_500
    txs = [(a, 40, 6, "voice"), (a, 50, 5, "voice"), (b, 44, 8, "voice")]
    sky = Sky(txs, 80)
    sky.install(monkeypatch)
    caught = []
    wt = w.Watcher(caught.append, stop=sky.d.stop, hops=w.hop_plan([a, b]))
    wt.run()
    time.sleep(0.2)
    freqs = {round(c.freq_hz / 5000) * 5000 for c in caught}
    assert any(abs(x - a) <= 5000 for x in freqs) and any(abs(x - b) <= 5000 for x in freqs)
    side = next(c for c in caught if abs(c.freq_hz - b) <= 5000)
    assert side.started < 48 and w.carrier_seconds(side.audio) > 4


def test_ignore_is_never_a_trigger_and_priority_takes_a_weaker_signal(monkeypatch):
    from tools.tests.unit.test_local_scanner import _simulate
    from utils.radio import scanner
    f = 443_850_000
    monkeypatch.setattr(scanner, "seed_channels", lambda: [{"freq_hz": f}])
    orig = w.Watcher.__init__

    def with_marks(marks):
        def init(self, *a, **k):
            orig(self, *a, **k)
            self.priority, self.ignore = marks
        return init
    monkeypatch.setattr(w.Watcher, "__init__", with_marks(([], [f])))
    freqs, _ = _simulate(monkeypatch, [(f, 40, 10)], 70, snr_db=25)
    assert not any(abs(x - f) <= 5000 for x in freqs)
    # Priority: the threshold itself, near the bookmark and nowhere else.
    wt = w.Watcher(lambda c: None)
    wt.priority, wt.ignore = [146_520_000], [146_940_000]
    g, fq = wt._gates(146_700_000), w._bin_freqs(146_700_000)
    near = lambda x: np.abs(fq - x) <= 2000
    assert (g[near(146_520_000)] == w.PRIORITY_GATE_DB).all() and np.isinf(g[near(146_940_000)]).all()
    assert (g[near(146_300_000)] == w.GATE_DB).all()


# ── the ledger ───────────────────────────────────────────────────────────────

@pytest.fixture
def led(tmp_path, monkeypatch):
    from utils.radio import ledger
    monkeypatch.setattr(ledger, "telemetry_path", lambda p: str(tmp_path / "ledger.sqlite3"))
    return ledger


def test_an_old_ledger_gains_the_new_columns_in_place(tmp_path, monkeypatch):
    from utils.radio import ledger
    p = tmp_path / "old.sqlite3"
    con = sqlite3.connect(p)
    con.executescript("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, freq_hz INTEGER, ts REAL, "
                      "seconds REAL, kind TEXT, rms REAL, hf_ratio REAL, clip TEXT, transcript TEXT);"
                      "INSERT INTO events (freq_hz, ts, seconds, kind) VALUES (146520000, 1, 5, 'carrier');")
    con.commit()
    con.close()
    monkeypatch.setattr(ledger, "telemetry_path", lambda _: str(p))
    ledger.record(146_520_000, "voice", 6, 1, 0.1, transcript="hello there everyone", peak_db=21.5, carrier_s=4.2)
    rows = sqlite3.connect(p).execute("SELECT kind, peak_db, carrier_s FROM events ORDER BY id").fetchall()
    assert rows == [("carrier", None, None), ("voice", 21.5, 4.2)]


def test_a_sighting_counts_as_activity_but_not_as_a_catch(led):
    led.record(463_512_500, "seen", 0, 0, 0, when=1000.0, peak_db=18)
    ch = led.channel(463_512_500)
    assert ch["hits"] == 1 and not ch["voice"] and not ch["data"]
    assert led.catches_since(0) == [] and led.heard_at(463_512_500, 0) == [1000.0]


def test_habits_are_brief_voiceless_channels_heard_often(led):
    now = time.time()
    for k in range(40):
        led.record(463_512_500, "carrier", 5.0 + (k % 3), 1, 0.01, when=now - 3600 + 43 * k)
        led.record(460_575_000, "carrier", 5.0, 1, 0.01, when=now - 3000 + 50 * k)
    led.record(460_575_000, "voice", 30, 1, 0.1, transcript="engine five respond", when=now - 60)
    for k in range(5):
        led.record(446_000_000, "carrier", 4, 1, 0.01, when=now - 100 * k)
    h = led.habitual(now)
    assert set(h) == {463_512_500} and 6.0 <= h[463_512_500] <= 8.0


def test_a_timer_is_found_through_missed_bursts_and_jitter():
    rng = np.random.default_rng(5)
    P = 43.1
    ts = [k * P + rng.uniform(-2.0, 2.0) for k in range(600) if rng.random() < 0.3]     # 70% missed
    period, conf = __import__("utils.radio.ledger", fromlist=["x"]).period_of(ts)
    assert abs(period - P) < 0.5 and conf >= 0.5
    noise = np.cumsum(rng.exponential(60, 200))
    assert __import__("utils.radio.ledger", fromlist=["x"]).period_of(noise)[1] < 0.3


# ── bookmarks ────────────────────────────────────────────────────────────────

GQRX = """# Tag name          ;  color
Amateur             ; #22c55e
Business            ; #eab308

# Frequency ; Name                                 ; Modulation          ;  Bandwidth; Tags
  146520000; 2m National Simplex Calling            ; Narrow FM           ;      10000; Amateur
  460575000; County dispatch                        ; Narrow FM           ;      12500; Business,Fire-EMS
  bogus; not a row
"""


@pytest.fixture
def bm(tmp_path, monkeypatch):
    from utils.radio import bookmarks
    monkeypatch.setattr(bookmarks, "telemetry_path", lambda p: str(tmp_path / "bookmarks.json"))
    return bookmarks


def test_gqrx_bookmarks_come_in_and_go_back_out(bm):
    tags, items = bm.parse_gqrx(GQRX)
    assert tags == {"Amateur": "#22c55e", "Business": "#eab308"}
    assert [(i["freq"], i["tag"]) for i in items] == [(146_520_000, "Amateur"), (460_575_000, "Business")]
    bm.upsert({"freq": 460_575_000, "name": "my name for it", "priority": True})
    r = bm.import_gqrx(GQRX)
    assert r == {"added": 1, "kept": 1, "tags": 2}
    d = bm.load()
    mine = next(b for b in d["items"] if b["freq"] == 460_575_000)
    assert mine["name"] == "my name for it" and mine["priority"]          # what was set here wins
    tags2, items2 = bm.parse_gqrx(bm.export_gqrx())
    assert {i["freq"] for i in items2} == {146_520_000, 460_575_000} and tags2["Amateur"] == "#22c55e"


def test_marks_are_exclusive_and_reach_the_watch(bm):
    bm.upsert({"freq": 463_725_000, "ignore": True})
    b = bm.upsert({"freq": 463_725_000, "priority": True})
    assert b["priority"] and not b["ignore"]
    assert bm.marks() == ([463_725_000], [])
    assert bm.remove(463_725_000) and bm.marks() == ([], [])


# ── what is worth a look ─────────────────────────────────────────────────────

def test_highlights_rank_words_new_channels_and_urgency(led):
    from utils.radio import interest
    now = time.time()
    for k in range(30):
        led.record(463_512_500, "carrier", 5, 1, 0.01, when=now - 7200 + k * 60)
    led.record(146_860_000, "voice", 8, 1, 0.1, clip="a.ogg", transcript="net control this is kilo five checking in", when=now - 600)
    led.record(460_575_000, "voice", 40, 1, 0.1, clip="b.ogg",
               transcript="medical emergency, engine five respond to the structure fire on main street", when=now - 300)
    top = interest.highlights()
    assert [t["freq"] for t in top[:2]] == [460_575_000, 146_860_000]
    assert any("urgent" in w for w in top[0]["why"]) and "first time heard" in top[0]["why"]
    assert all(t["freq"] != 463_512_500 for t in top)


def test_channels_are_sorted_into_what_they_do():
    from utils.radio import interest
    assert interest.classify_channel({"freq_hz": 1, "voice": 3, "hits": 9}, {})[0] == "talk"
    assert interest.classify_channel({"freq_hz": 1, "voice": 0, "hits": 90, "data": 0}, {}, (43.1, 0.6))[0] == "timer"
    assert interest.classify_channel({"freq_hz": 1, "voice": 0, "hits": 90, "data": 0}, {1: 6.0})[0] == "data"
    assert interest.classify_channel({"freq_hz": 1, "voice": 0, "hits": 0}, {})[0] == "quiet"


# ── the scanner takes a tune in place ────────────────────────────────────────

def test_a_running_watch_takes_a_tune_and_back_to_scan_as_commands(monkeypatch):
    from utils.radio import live, scanner
    q = queue.Queue()
    monkeypatch.setattr(scanner, "_control", q)
    monkeypatch.setattr(scanner, "_proc", NS(is_alive=lambda: True))
    monkeypatch.setattr(scanner, "snap_channel", lambda f: f)
    monkeypatch.setattr(live, "active", lambda: [])
    monkeypatch.setattr(scanner, "due_net", lambda now=None: None)
    monkeypatch.setattr(scanner, "_tuned", None)
    monkeypatch.setattr(scanner, "_pinned", None)
    assert "146.5200" in scanner.tune_now(146_520_000, 5)
    cmd = q.get_nowait()
    assert cmd["op"] == "tune" and cmd["freq"] == 146_520_000 and scanner.tuned()["freq_hz"] == 146_520_000
    monkeypatch.setattr(scanner, "_scan_wanted", lambda: True)
    assert scanner.untune_now() == "back to the scan" and q.get_nowait() == {"op": "scan"} and not scanner.tuned()
    stopped = []
    monkeypatch.setattr(scanner, "_scan_wanted", lambda: False)
    monkeypatch.setattr(scanner, "_stop_all", lambda: stopped.append(1))
    assert scanner.untune_now().startswith("off") and stopped
    monkeypatch.setattr(scanner, "_proc", None)
    assert scanner.tune_now(146_520_000) is None            # nothing running: tune() starts a watch


# ── the dashboard ────────────────────────────────────────────────────────────

@pytest.fixture
def dash(monkeypatch, bm, led):
    import asyncio
    from utils.radio import rx_dashboard
    monkeypatch.setattr(rx_dashboard, "_cfg", lambda k, d: 0 if k == "dashboard_port" else d)

    async def _serve():
        return rx_dashboard.serve()
    base = asyncio.run(_serve())
    yield base
    srv, rx_dashboard._server = rx_dashboard._server, None
    srv.shutdown()


def _post(url, body, origin=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"Origin": origin} if origin else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


def test_the_span_streams_each_row_as_it_is_made(dash):
    from utils.radio.rx_scope import scope
    got = []

    def read():
        with urllib.request.urlopen(dash + "span", timeout=5) as r:
            buf = b""
            while len(got) < 3:
                buf += r.read1(65536)
                while len(buf) >= 4:
                    hl = struct.unpack("<I", buf[:4])[0]
                    if hl == 0:
                        buf = buf[4:]
                        continue
                    if len(buf) < 8 + hl:
                        break
                    rl = struct.unpack("<I", buf[4 + hl:8 + hl])[0]
                    if len(buf) < 8 + hl + rl:
                        break
                    got.append((json.loads(buf[4:4 + hl]), buf[8 + hl:8 + hl + rl]))
                    buf = buf[8 + hl + rl:]
    t = threading.Thread(target=read, daemon=True)
    t.start()
    time.sleep(0.3)
    for k in range(3):
        scope.feed({"kind": "span", "center": 146_120_000, "state": "pinned", "freq": 146_520_000, "level": 3.0,
                    "open": False, "row": np.full(w.SPAN_NFFT, 40 + k, np.uint8)})
        time.sleep(0.05)
    t.join(5)
    assert len(got) >= 3
    head, row = got[-1]
    assert head["freq"] == 146_520_000 and head["lo"] == 146_120_000 - w.FS // 2 and len(row) == w.SPAN_NFFT


def test_bookmarks_and_tunes_are_same_origin_only(dash, monkeypatch):
    from utils.radio import scanner
    monkeypatch.setattr(scanner, "push_marks", lambda: None)
    code, j = _post(dash + "bookmarks", {"freq": 146_520_000, "name": "calling", "tag": "Amateur"})
    assert code == 200 and j["ok"]
    with urllib.request.urlopen(dash + "bookmarks", timeout=5) as r:
        assert [b["name"] for b in json.loads(r.read())["items"]] == ["calling"]
    with urllib.request.urlopen(dash + "bookmarks.csv", timeout=5) as r:
        assert b"146520000; calling" in r.read()
    assert _post(dash + "bookmarks", {"freq": 1}, origin="http://evil.example")[0] == 403
    calls = []
    monkeypatch.setattr(scanner, "tune_now", lambda f, m: calls.append(f) or "on it")
    code, j = _post(dash + "tune", {"freq": 446_000_000})
    assert j == {"ok": True, "say": "on it", "now": True} and calls == [446_000_000]


def test_streaming_keeps_every_sample_while_the_last_chunk_is_processed():
    """rtlsdr_read_sync buffers nothing between calls: read inline, processing
    time was samples lost (a tuned channel kept 78% of its audio)."""
    class Paced:
        streams = True

        def __init__(self):
            self.n = 0

        def read(self, n):
            time.sleep(n / w.FS)                    # samples arrive in real time
            self.n += n
            return np.zeros(n, np.complex64)
    d = Paced()
    src = w._source(d, w.PIN_CHUNK)
    t0 = time.time()
    got = 0
    while time.time() - t0 < 1.0:
        got += len(src.read())
        time.sleep(0.012)                           # a third of each chunk spent processing
    src.close()
    assert isinstance(src, w.Stream) and got >= 0.9 * w.FS * (time.time() - t0) - 2 * w.PIN_CHUNK
    assert isinstance(w._source(object(), 10), w._Inline)          # a simulated dongle is read inline
