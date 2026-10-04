"""KAIA//RX — the receiver dashboard: what the local scanner sees and hears.

A pop-out window in the DJ booth's style, laid out like a desktop SDR
receiver: the band's panorama spectrum over its waterfall (`rx_scope`), a big
frequency readout and signal meter for what the watch is on, the ledger's
channels as bookmarks, the catches it kept (each with its spectrogram and a
play button), the carriers it has locked out, and a monitor that plays the
scanner's audio in the window. A click on the waterfall tunes the dongle to
that channel for a while (`scanner.tune`); ▶ SCAN runs the scan outside the
nightly hours while the page is open (`scanner.start_scan`).

Served from 127.0.0.1 only: `assets/rx/index.html`, `/events` (state, ten a
second), `/waterfall/<band>`, `/ledger`, `/catches`, `/clip/<name>`,
`/spec/<name>`, `/night/<name>`, `/log` (every catch but noise), `/audio`
(the monitor: raw 12 kHz s16le, silent while hopping), and POST `/tune`,
`/scan` (leave a tuned channel), `/start`, `/stop`. `!scanner dash` opens the window; nothing opens it
at night unasked.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

import numpy as np

from utils.infrastructure.logging.kaia_logger import log_debug, log_info, log_warning

PAGE = Path(__file__).resolve().parents[2] / "assets" / "rx" / "index.html"
STREAM_HZ = 10
MHZ = 1_000_000
_SAFE = re.compile(r"^[\w.\-]+$")

_server: Optional[ThreadingHTTPServer] = None
_port = 0
_loop: Optional[asyncio.AbstractEventLoop] = None
_window: Optional[subprocess.Popen] = None
_profile: Optional[str] = None
_monitors: list[queue.Queue] = []
_mon_lock = threading.Lock()
_last_audio = {"t": 0.0, "level": -90.0}


def _cfg(key: str, default):
    from utils.infrastructure.system.yaml_config import config
    return config.get(f"radio.local.{key}", default)


# ── the monitor ──────────────────────────────────────────────────────

def audio(chunk) -> None:
    """A chunk of the scanner's 12 kHz audio, from scanner._sink: kept for the
    signal meter and handed to every page that is monitoring."""
    try:
        a = np.asarray(chunk, dtype=np.int16)
    except Exception:
        return
    if len(a):
        rms = float(np.sqrt(np.mean(a.astype(np.float32) ** 2)))
        _last_audio.update(t=time.time(), level=round(20 * np.log10(max(rms, 1.0) / 32768), 1))
    with _mon_lock:
        for q in list(_monitors):
            try:
                q.put_nowait(a.tobytes())
            except queue.Full:
                pass


# ── state ────────────────────────────────────────────────────────────

def status() -> dict:
    from utils.radio import rtl, scanner, live
    from utils.radio.rx_scope import scope
    lv = scope.live_info()
    tuned = scanner.tuned()
    pinned = getattr(scanner, "_pinned", None)
    local = [s for s in live.active() if getattr(s, "local", False)]
    if local:
        mode, freq = "live", int(getattr(local[0], "freq_hz", 0) or 0)
    elif scanner.running() and lv:
        mode = {"hop": "scanning", "hold": "holding", "follow": "following", "pinned": "tuned" if tuned else "net"}.get(lv["state"], lv["state"])
        freq = lv["freq"] or lv["center"]
    elif scanner.running():
        mode, freq = "starting", 0
    elif scanner.asked():
        mode, freq = "starting", 0
    else:
        mode, freq = ("idle" if rtl.available() else "no dongle"), 0
    return {"mode": mode, "freq": freq, "live": lv, "passes": scope.passes, "lockouts": scope.lockouts,
            "tuned": tuned, "net": pinned if pinned and not tuned else None,
            "hours": str(_cfg("hours", "00:00-06:00")), "gain": _cfg("gain", rtl.DEFAULT_GAIN),
            "audio_level": _last_audio["level"] if time.time() - _last_audio["t"] < 1.5 else -90.0,
            "along": scanner.listening_along(), "kaia": _kaia_line(mode, freq, lv, tuned),
            "asked": scanner.asked(), "nightly": scanner.within_hours(), "cols": scope.cols,
            "bands": scope.bands_info(), "t": time.time()}


def _kaia_line(mode: str, freq: int, lv, tuned) -> str:
    from utils.radio import ledger
    if mode in ("holding", "following", "tuned", "net") and freq:
        ch = ledger.channel(freq) or {}
        what = ch.get("label") or ch.get("service") or "something"
        if mode == "following":
            return f"{freq / MHZ:.4f} — {what}. that sounded like a voice; i'm staying for the reply."
        if mode == "tuned":
            left = max(0, int((tuned["until"] - time.time()) / 60))
            return f"sitting on {freq / MHZ:.4f} for you ({what}), {left} min left. anything that keys up, i keep."
        if mode == "holding" and not (lv or {}).get("open"):
            return (f"something rose over the noise on {freq / MHZ:.4f} — {what}. no carrier that holds yet; "
                    "if it's only pulses i'll leave it and keep sweeping.")
        return f"something keyed up on {freq / MHZ:.4f} — {what}. listening."
    if mode == "scanning":
        return "sweeping the voice bands, a pass every few seconds. quiet until something holds a carrier."
    if mode == "starting":
        return "opening the dongle — the first sweep is a few seconds away."
    if mode == "live":
        return f"playing {freq / MHZ:.4f} live in voice."
    tonight = ledger.catches_since(time.time() - 18 * 3600)
    voice = sum(1 for e in tonight if e["kind"] == "voice")
    return (f"the scanner sleeps until {_cfg('hours', '00:00-06:00').split('-')[0]}. "
            f"last night: {len(tonight)} catches, {voice} with a voice. ▶ SCAN to sweep now, "
            "or click the waterfall to sit on one channel.")


def ledger_rows() -> list:
    from utils.radio import ledger
    out = []
    for c in ledger.channels():
        if not (c["hits"] or c.get("source") == "listed"):
            continue
        out.append({"freq": c["freq_hz"], "label": c.get("label") or "", "service": c.get("service") or "",
                    "hits": c["hits"], "voice": c["voice"], "data": c.get("data", 0),
                    "last": c.get("last_seen"), "hours": ledger.active_hours(c),
                    "transcript": c.get("last_transcript") or ""})
    out.sort(key=lambda r: (-r["voice"], -r["hits"]))
    return out[:200]


def catch_rows(limit: int = 40) -> list:
    from utils.radio import ledger, scanner
    folder = scanner._clips_dir()
    rows = []
    for e in ledger.recent(200, kinds=("voice", "data", "carrier")):
        clip = e.get("clip")
        if not clip or not (folder / clip).is_file():
            continue
        rows.append({"id": e["id"], "ts": e["ts"], "freq": e["freq_hz"], "kind": e["kind"],
                     "seconds": e.get("seconds"), "clip": clip, "transcript": e.get("transcript") or "",
                     "label": e.get("label") or e.get("service") or ""})
        if len(rows) >= limit:
            break
    return rows


def log_rows(limit: int = 150) -> list:
    """Every catch but noise, newest first: the carriers `!scanner history`
    folds into one line are listed here."""
    from utils.radio import ledger
    return [{"ts": e["ts"], "freq": e["freq_hz"], "kind": e["kind"], "seconds": e.get("seconds"),
             "label": e.get("label") or e.get("service") or "", "transcript": e.get("transcript") or ""}
            for e in ledger.recent(limit)]


def nights() -> list:
    from utils.radio import scanner
    d = scanner.nights_dir()
    return sorted((p.name for p in d.glob("*.png")), reverse=True) if d.is_dir() else []


# ── HTTP ─────────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    server_version = "KaiaRX/1"

    def log_message(self, *a, **k):
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj) -> None:
        self._send(200, json.dumps(obj).encode(), "application/json")

    def _file(self, path: Path, ctype: str) -> None:
        if not path.is_file():
            return self._send(404, b"", "text/plain")
        size = path.stat().st_size
        start, end = 0, size - 1
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes="):
            a, _, b = rng[6:].split(",")[0].partition("-")
            if a.strip():
                start, end = int(a), (int(b) if b.strip() else end)
            elif b.strip():
                start = max(0, size - int(b))
            end = min(end, size - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(path, "rb") as fh:
            fh.seek(start)
            self.wfile.write(fh.read(end - start + 1))

    def do_GET(self):
        from utils.radio import scanner, spectrogram
        from utils.radio.rx_scope import scope
        path = self.path.split("?", 1)[0]
        try:
            if path in ("/", "/index.html"):
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/state":
                self._json(status())
            elif path == "/ledger":
                self._json(ledger_rows())
            elif path == "/catches":
                self._json(catch_rows())
            elif path == "/nights":
                self._json(nights())
            elif path == "/log":
                self._json(log_rows())
            elif path.startswith("/waterfall/"):
                i = int(path.rsplit("/", 1)[-1])
                n, data, seq = scope.rows_since(i, 0)
                self._json({"rows": n, "data": data, "seq": seq})
            elif path.startswith(("/clip/", "/spec/", "/night/")):
                name = path.rsplit("/", 1)[-1]
                if not _SAFE.match(name):
                    return self._send(404, b"", "text/plain")
                if path.startswith("/night/"):
                    return self._file(scanner.nights_dir() / name, "image/png")
                clip = scanner._clips_dir() / name
                if path.startswith("/clip/"):
                    return self._file(clip, "audio/ogg")
                pic = spectrogram.render(clip, f"{name}")
                return self._file(pic, "image/png") if pic else self._send(404, b"", "text/plain")
            elif path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                seen = {}
                while _server is not None:
                    scanner.seen_by_dashboard()
                    st = status()
                    rows = {}
                    for b in st["bands"]:
                        n, data, seq = scope.rows_since(b["i"], seen.get(b["i"], b["seq"]), limit=40)
                        seen[b["i"]] = seq
                        if n:
                            rows[b["i"]] = {"n": n, "data": data}
                    st["rows"] = rows
                    self.wfile.write(b"data: " + json.dumps(st).encode() + b"\n\n")
                    self.wfile.flush()
                    time.sleep(1.0 / STREAM_HZ)
            elif path == "/audio":
                q: queue.Queue = queue.Queue(maxsize=50)
                with _mon_lock:
                    _monitors.append(q)
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    while _server is not None:
                        try:
                            data = q.get(timeout=1.0)
                        except queue.Empty:
                            data = b"\x00\x00" * 1200             # 0.1 s of silence keeps the stream alive
                        self.wfile.write(data)
                        self.wfile.flush()
                finally:
                    with _mon_lock:
                        if q in _monitors:
                            _monitors.remove(q)
            else:
                self._send(404, b"not here", "text/plain")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            log_debug(f"[rx] {path}: {e}")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n or n > 2048:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def do_POST(self):
        from utils.radio import scanner
        body = self._body()
        if _loop is None:
            return self._json({"ok": False, "say": "the bot's loop isn't available"})
        try:
            if self.path == "/tune":
                freq = int(float(body.get("freq") or 0))
                if not 24 * MHZ <= freq <= 1_700 * MHZ:
                    return self._json({"ok": False, "say": "that's outside what the dongle can tune"})
                minutes = min(60.0, max(1.0, float(body.get("minutes") or 15)))
                fut = asyncio.run_coroutine_threadsafe(scanner.tune(freq, minutes), _loop)
            elif self.path == "/scan":
                fut = asyncio.run_coroutine_threadsafe(scanner.untune(), _loop)
            elif self.path == "/start":
                minutes = min(240.0, max(1.0, float(body.get("minutes") or 30)))
                fut = asyncio.run_coroutine_threadsafe(scanner.start_scan(minutes), _loop)
            elif self.path == "/stop":
                fut = asyncio.run_coroutine_threadsafe(scanner.stop_scan(), _loop)
            else:
                return self._send(404, b"", "text/plain")
            # The answer if it comes quickly; otherwise say it is under way.
            # Waiting the restart out held the page's request for up to a
            # minute, and the page gave up (broken pipe) and clicked again.
            try:
                say = fut.result(timeout=2.5)
            except TimeoutError:
                say = {"/tune": "tuning…", "/scan": "back to the scan…", "/start": "starting the scan…",
                       "/stop": "stopping…"}.get(self.path, "on it…")
            self._json({"ok": True, "say": say})
        except Exception as e:
            log_warning(f"[rx] {self.path} failed: {e}")
            self._json({"ok": False, "say": str(e)})


def url() -> str:
    return f"http://127.0.0.1:{_port}/" if _server else ""


def serve() -> str:
    """Start the dashboard's server if it isn't running; returns its address.
    Call from the bot's loop (it is kept for the tune requests)."""
    global _server, _port, _loop
    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        pass
    if _server is not None:
        return url()
    want = int(_cfg("dashboard_port", 47432) or 0)
    for port in (want, 0):
        try:
            _server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
            break
        except OSError:
            continue
    if _server is None:
        return ""
    _server.daemon_threads = True
    _port = _server.server_address[1]
    threading.Thread(target=_server.serve_forever, daemon=True, name="kaia-rx-http").start()
    log_info(f"[scanner] receiver dashboard at {url()}")
    return url()


def open_window() -> str:
    """Pop the dashboard out as an app window (blocking: run it off the loop).
    Returns its address."""
    global _window, _profile
    if not url():
        return ""
    if _window is not None and _window.poll() is None:
        return url()
    from utils.audio.dj_dashboard import _browser
    exe = _browser()
    if not exe:
        return url()
    _profile = _profile or tempfile.mkdtemp(prefix="kaia-rx-")
    try:
        from utils.radio.kiwi import _die_with_parent
        _window = subprocess.Popen(
            [exe, f"--app={url()}", f"--user-data-dir={_profile}", "--window-size=1600,1000",
             "--no-first-run", "--no-default-browser-check", "--class=KaiaRX",
             "--autoplay-policy=no-user-gesture-required"] + (["--test-type"] if "ms-playwright" in exe else []),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=_die_with_parent, env={**os.environ})
    except OSError as e:
        log_warning(f"[scanner] the receiver dashboard window would not open: {e}; it's at {url()}")
    return url()
