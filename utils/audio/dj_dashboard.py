"""The DJ booth: a pop-out window showing two CDJs and a mixer for `!music records`.

Everything on it is the mixer's own state, read from the running
`records.CrossfadeSource` — the decks it holds, where each is, its beat grid,
the transition it planned, the band gains it is applying this frame and the
levels it is producing. Nothing is animated for show: a knob turns because
the mix moved it.

A small HTTP server on 127.0.0.1 serves `assets/dj/index.html`, a state
stream (`/events`, server-sent events, 20 a second), each record's three-band
waveform (`/wave/<id>`, computed by ffmpeg off the voice thread and cached),
and one control, `POST /skip`, the same skip `!music skip` makes. When a set
starts the page is opened as an app window in Playwright's Chromium, the way
the Strudel window is, and closed when the set ends.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

import numpy as np

from utils.infrastructure.logging.kaia_logger import log_debug, log_info, log_warning

PAGE = Path(__file__).resolve().parents[2] / "assets" / "dj" / "index.html"
WAVE_RATE = 8000
#: Waveform columns per second of the record, each a low / mid / high level.
WAVE_COLS_PER_S = 100
STREAM_HZ = 20

_server: Optional[ThreadingHTTPServer] = None
_port = 0
_window: Optional[subprocess.Popen] = None
_profile_dir: Optional[str] = None
_waves: dict[str, Optional[dict]] = {}          # id -> waveform, None while computing
_paths: dict[str, str] = {}                     # id -> file
_lock = threading.Lock()
_mood_cache = {"at": 0.0, "value": {}}


def _cfg(key: str, default):
    from utils.infrastructure.system.yaml_config import config
    return config.get(f"music.{key}", default)


def track_id(path: str) -> str:
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]


# ── Waveforms ────────────────────────────────────────────────────────

def waveform(path: str) -> Optional[dict]:
    """Low / mid / high levels of a record, WAVE_COLS_PER_S columns a second
    of its own time, each scaled 0–255 against its own loudest. ffmpeg does the
    decoding and the band split; numpy only averages, in slices, so the voice
    thread is never kept waiting on the GIL."""
    graph = ("[0:a]aresample=8000,pan=mono|c0=0.5*c0+0.5*c1,asplit=3[a][b][c];"
             "[a]lowpass=f=180,lowpass=f=180[l];[b]highpass=f=180,lowpass=f=2500[m];"
             "[c]highpass=f=2500[h];[l][m][h]amerge=inputs=3[out]")
    try:
        raw = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", path, "-filter_complex", graph,
                              "-map", "[out]", "-f", "s16le", "-ar", str(WAVE_RATE), "-ac", "3", "pipe:1"],
                             capture_output=True, timeout=120).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    x = np.frombuffer(raw, dtype=np.int16)
    step = WAVE_RATE // WAVE_COLS_PER_S
    cols = len(x) // (3 * step)
    if cols < 10:
        return None
    x = x[: cols * step * 3].reshape(cols, step, 3)
    out = np.zeros((cols, 3), dtype=np.float32)
    for i in range(0, cols, 2000):
        chunk = x[i:i + 2000].astype(np.float32)
        out[i:i + 2000] = np.sqrt(np.mean(chunk * chunk, axis=1))
        time.sleep(0)
    scale = np.percentile(out, 99.5, axis=0)
    scale[scale == 0] = 1.0
    levels = np.clip(out / scale * 255.0, 0, 255).astype(np.uint8)
    return {"cols_per_s": WAVE_COLS_PER_S, "seconds": round(cols / WAVE_COLS_PER_S, 2),
            "data": base64.b64encode(levels.tobytes()).decode("ascii")}


def _want_wave(path: str) -> str:
    """Start computing a record's waveform if nobody has; returns its id."""
    tid = track_id(path)
    with _lock:
        if tid in _waves:
            return tid
        _waves[tid] = None
        _paths[tid] = path
        while len(_waves) > 24:                  # a set's worth; the oldest go
            old = next(iter(_waves))
            _waves.pop(old, None)
            _paths.pop(old, None)

    def run():
        w = waveform(path)
        with _lock:
            if tid in _paths:
                _waves[tid] = w or {"error": "could not read"}
    threading.Thread(target=run, daemon=True, name="kaia-dj-wave").start()
    return tid


# ── State ────────────────────────────────────────────────────────────

def _mood() -> dict:
    if time.time() - _mood_cache["at"] > 10:
        try:
            from utils.core.kaia_art_intent import mood
            _mood_cache["value"] = {k: round(float(v), 2) for k, v in (mood() or {}).items()
                                    if isinstance(v, (int, float))}
        except Exception:
            _mood_cache["value"] = {}
        _mood_cache["at"] = time.time()
    return _mood_cache["value"]


def _grid(g) -> Optional[dict]:
    if g is None:
        return None
    return {"bpm": round(g.bpm, 3), "downbeat": round(g.downbeat, 4), "contrast": round(g.contrast, 2),
            "bar_known": bool(g.bar_known)}


def _record(rec) -> dict:
    return {"id": _want_wave(rec.path), "title": rec.title, "artist": rec.artist, "name": rec.name,
            "bpm": rec.bpm, "key": rec.key, "genre": rec.genre}


def _deck(d, state: str) -> dict:
    g = d.grid
    return {**_record(d.record), "slot": d.slot, "state": state, "ratio": round(d.ratio, 5),
            "pitch": round((d.ratio - 1.0) * 100, 2), "gain_db": d.gain,
            "pos": round(d.at() * d.ratio, 4),            # seconds of the record's own time
            "length": round(d.end * d.ratio, 3),
            "tempo": round(g.bpm * d.ratio, 2) if g else (round(d.record.bpm * d.ratio, 2) if d.record.bpm else None),
            "grid": _grid(g), "buffering": not d.ready(5)}


def snapshot(session) -> dict:
    """The booth as it stands: both decks, the mixer, the set."""
    if session is None or session.source is None:
        return {"live": False, "t": time.time()}
    src = session.source
    cur, inc, plan, queued = src.current, src.incoming, src.plan, src._queued
    decks = {}
    if cur is not None:
        decks[str(cur.slot)] = _deck(cur, "playing")
    if inc is not None:
        started = src._start_frame is not None and cur is not None and cur.played >= src._start_frame
        decks[str(inc.slot)] = _deck(inc, "playing" if started else "cued")
    elif queued is not None and cur is not None:
        decks[str(3 - cur.slot)] = {**_record(queued.record), "slot": 3 - cur.slot,
                                    "state": "planning" if src._planning else "loaded",
                                    "ratio": 1.0, "pitch": 0.0, "gain_db": queued.gain, "pos": 0.0,
                                    "length": round(queued.seconds, 3), "tempo": queued.record.bpm,
                                    "grid": _grid(queued.grid), "buffering": False}
    a_low, a_high, b_low, b_high = src.applied
    out_slot = str(cur.slot) if cur else "1"
    in_slot = str(3 - cur.slot) if cur else "2"
    channels = {
        out_slot: {"low": a_low, "high": a_high, "level": src.levels["a"]},
        in_slot: {"low": b_low, "high": b_high, "level": src.levels["b"]},
    }
    mix = None
    if plan is not None and cur is not None:
        now = cur.at()
        mix = {"kind": plan.kind, "mode": plan.mode, "why": plan.why, "out_slot": out_slot, "in_slot": in_slot,
               "start": round(plan.start, 3), "drop": round(plan.drop, 3), "length": round(plan.length, 3),
               "beat": round(plan.beat, 4), "done": round(plan.done, 3), "now": round(now, 3),
               "ratio": round(plan.ratio, 5), "out_ratio": round(cur.ratio, 5)}
    late = src.late
    return {
        "live": True, "t": time.time(), "channel": session.channel_name, "by": session.requested_by,
        "started": session.started_at, "played": len(session.names), "listeners": session._humans(),
        "decks": decks, "channels": channels, "master": src.levels["master"], "mix": mix,
        "planning": src.planning_mode, "late": {"count": len(late), "worst_ms": round(max(late) * 1000) if late else 0},
        "history": src.history[-12:], "names": session.names[-30:], "mood": _mood(),
        "mix_beats": src._mix_beats, "blend_choices": list(src.BLEND_CHOICES), "controls": src.controls.state(), "paused": sorted(src.paused),
        "requests": [_name_of(session, p) for p in session.requests],
    }


def _name_of(session, path: str) -> str:
    rec = next((r for r in session.crate if r.path == path), None)
    return rec.name if rec else os.path.basename(path)


def crate(session) -> dict:
    """The library by genre, for the booth's crate browser."""
    if session is None:
        return {"live": False, "genres": {}}
    played = set(session.played)
    asked = set(session.requests)
    genres: dict[str, list] = {}
    for r in sorted(session.crate, key=lambda r: ((r.genre or "~").lower(), (r.artist or "").lower(), r.title.lower())):
        genres.setdefault(r.genre or "Unsorted", []).append({
            "id": track_id(r.path), "title": r.title, "artist": r.artist, "bpm": r.bpm, "key": r.key,
            "played": r.path in played, "requested": r.path in asked})
    return {"live": True, "count": len(session.crate), "genres": genres}


def _session():
    from utils.audio import records
    for s in list(records._sessions.values()):
        return s
    return None


# ── HTTP ─────────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    server_version = "KaiaBooth/1"

    def log_message(self, *a, **k):          # every request would land in the bot's stderr
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path in ("/", "/index.html"):
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/state":
                self._send(200, json.dumps(snapshot(_session())).encode(), "application/json")
            elif path == "/crate":
                self._send(200, json.dumps(crate(_session())).encode(), "application/json")
            elif path.startswith("/wave/"):
                tid = path.rsplit("/", 1)[-1]
                with _lock:
                    w = _waves.get(tid, "missing")
                if w == "missing":
                    self._send(404, b"{}", "application/json")
                elif w is None:
                    self._send(202, b'{"pending": true}', "application/json")
                else:
                    self._send(200, json.dumps(w).encode(), "application/json")
            elif path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                while _server is not None:
                    self.wfile.write(b"data: " + json.dumps(snapshot(_session())).encode() + b"\n\n")
                    self.wfile.flush()
                    time.sleep(1.0 / STREAM_HZ)
            else:
                self._send(404, b"not here", "text/plain")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            log_debug(f"[dj] {path}: {e}")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n or n > 4096:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def do_POST(self):
        s = _session()
        if s is None or s.source is None:
            return self._send(409, b"", "text/plain")
        body, src = self._body(), s.source
        if self.path == "/skip":
            log_info("[records] skip from the DJ booth")
            s.skip()
            ok = True
        elif self.path == "/control":
            slot = body.get("slot")
            ok = src.controls.set(int(slot) if slot not in (None, "") else None, str(body.get("name", "")),
                                  body.get("value"))
        elif self.path == "/blend":
            ok = src.set_mix_beats(int(body.get("beats") or 0))
            if ok:
                log_info(f"[records] blends from the booth: {src._mix_beats} beats")
        elif self.path == "/reset":
            src.controls.reset()
            src.paused.clear()
            log_info("[records] the booth handed the mix back to Kaia")
            ok = True
        elif self.path == "/pause":
            slot = int(body.get("slot") or 0)
            if slot in src.paused:
                src.paused.discard(slot)
            elif slot in (1, 2):
                src.paused.add(slot)
            ok = slot in (1, 2)
        elif self.path == "/queue":
            rec = next((r for r in s.crate if track_id(r.path) == body.get("id")), None)
            if rec:
                s.request(rec)
            ok = rec is not None
        else:
            return self._send(404, b"", "text/plain")
        self._send(204 if ok else 400, b"", "text/plain")


def url() -> str:
    return f"http://127.0.0.1:{_port}/" if _server else ""


def serve() -> str:
    """Start the booth's server if it isn't running; returns its address."""
    global _server, _port
    if _server is not None:
        return url()
    want = int(_cfg("dj_dashboard_port", 47431) or 0)
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
    threading.Thread(target=_server.serve_forever, daemon=True, name="kaia-dj-http").start()
    log_info(f"[records] DJ booth at {url()}")
    return url()


_chromium: Optional[str] = None


def _browser() -> Optional[str]:
    """The browser the booth opens in: `music.dj_browser` if set, else an
    installed Chrome, Chromium, Brave or Edge, else Playwright's Chromium.
    Playwright's build is Chrome for Testing, which pins a "for testing"
    banner across the top of the window; a normal browser in app mode shows
    none."""
    global _chromium
    if _chromium is None:
        chosen = str(_cfg("dj_browser", "") or "").strip()
        if not chosen:
            for name in ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser",
                         "brave-browser", "brave", "microsoft-edge-stable"):
                chosen = shutil.which(name) or ""
                if chosen:
                    break
        if not chosen:
            root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or Path.home() / ".cache" / "ms-playwright")
            found = sorted(root.glob("chromium-*/chrome-linux*/chrome"), reverse=True)
            chosen = str(found[0]) if found else ""
        _chromium = chosen
    return _chromium or None


def open_window() -> None:
    """Pop the booth out as an app window (blocking: run it off the loop)."""
    global _window, _profile_dir
    if not _cfg("dj_dashboard", True) or not serve():
        return
    if _window is not None and _window.poll() is None:
        return
    exe = _browser()
    if not exe:
        log_warning(f"[records] no browser for the DJ booth; it's at {url()}")
        return
    _profile_dir = _profile_dir or tempfile.mkdtemp(prefix="kaia-dj-")
    try:
        from utils.radio.kiwi import _die_with_parent
        _window = subprocess.Popen(
            [exe, f"--app={url()}", f"--user-data-dir={_profile_dir}", "--window-size=1600,1000",
             "--no-first-run", "--no-default-browser-check", "--disable-features=Translate",
             "--class=KaiaBooth"] + (["--test-type"] if "ms-playwright" in exe else []),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=_die_with_parent, env={**os.environ})
    except OSError as e:
        log_warning(f"[records] the DJ booth window would not open: {e}; it's at {url()}")


def close_window() -> None:
    global _window
    w, _window = _window, None
    if w is not None and w.poll() is None:
        try:
            w.terminate()
            w.wait(timeout=5)
        except Exception:
            try:
                w.kill()
            except Exception:
                pass
