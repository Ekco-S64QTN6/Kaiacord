"""
Strudel-backed music engine.

Kaia's own numpy synthesiser could hold a 20 ms deadline comfortably but could
not sound good: it was a sawtooth through a ladder filter, and no amount of
tuning made that musical. Strudel is a mature live-coding environment whose
sound design is the work of a lot of people over several years, so this drives
Strudel instead of competing with it.

    local HTTP server (assets/strudel/)
        -> Chromium via Playwright, audio routed to a PipeWire null sink
            -> ffmpeg captures the sink monitor as s16le
                -> StrudelAudioSource hands 20 ms frames to discord.py

Strudel is AGPL-3.0 (https://codeberg.org/uzu/strudel). It is fetched as its own
unmodified bundle by tools/maintenance/fetch_music_assets.py and only driven
from here — no Strudel source is copied into this project, so its copyleft does
not reach Kaiacord.

Two behaviours here look like bugs and are not:

* The browser runs *headed*. Headless Chromium opens an audio stream and emits
  pure silence — routing looks perfect, the sink-input is present, uncorked and
  at full volume, and the capture is 0.0 RMS. Only headed mode makes sound. The
  window is parked off-screen unless music.show_window is set.
* Patterns are applied by clicking a real button. `evaluate()` called through
  Playwright is not a user gesture: it returns true, logs "[cyclist] start",
  reports a running AudioContext, and produces nothing.
"""

from __future__ import annotations

import functools
import http.server
from concurrent.futures import ThreadPoolExecutor
import os
import socket
import socketserver
import subprocess
import threading
import time
from pathlib import Path

from utils.infrastructure.logging.kaia_logger import (log_action, log_debug,
                                                      log_error, log_info,
                                                      log_warning)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = PROJECT_ROOT / "assets" / "strudel"
SINK_NAME = "kaia_music"
FRAME_BYTES = 960 * 2 * 2          # 20 ms, 48 kHz, stereo, s16le


def assets_present() -> bool:
    return (ASSET_DIR / "strudel-repl.js").is_file() and (ASSET_DIR / "player.html").is_file()


# ── PipeWire / PulseAudio sink ───────────────────────────────────────

def _pactl(*args: str) -> str:
    return subprocess.run(["pactl", *args], capture_output=True, text=True,
                          timeout=10).stdout


def ensure_sink() -> bool:
    """Create the null sink Chromium plays into, if it is not already there.

    A dedicated sink keeps the capture clean: reading the default monitor would
    pull in everything else on the machine, so a YouTube tab would go out over
    Discord alongside the music.
    """
    try:
        if SINK_NAME in _pactl("list", "short", "sinks"):
            return True
        _pactl("load-module", "module-null-sink", f"sink_name={SINK_NAME}",
               "sink_properties=device.description=KaiaMusic")
        ok = SINK_NAME in _pactl("list", "short", "sinks")
        log_info(f"[music] created null sink '{SINK_NAME}'" if ok
                 else f"[music] could not create sink '{SINK_NAME}'")
        return ok
    except Exception as exc:
        log_error(f"[music] sink setup failed: {exc}")
        return False


def monitor_to_speakers(enable: bool = True) -> None:
    """Loop the sink back to the default output so a human can hear it.

    The null sink has no speakers attached, so by default the operator sees
    audio meters moving and hears nothing — which reads as a fault and is not.
    """
    try:
        if enable:
            _pactl("load-module", "module-loopback",
                   f"source={SINK_NAME}.monitor", "latency_msec=60")
        else:
            for line in _pactl("list", "short", "modules").splitlines():
                if "module-loopback" in line and SINK_NAME in line:
                    _pactl("unload-module", line.split("\t")[0])
    except Exception as exc:
        log_debug(f"[music] loopback toggle failed: {exc}")


# ── the engine ───────────────────────────────────────────────────────

class StrudelEngine:
    """Owns the local server, the browser and the ffmpeg capture."""

    def __init__(self, show_window: bool = False):
        self.show_window = show_window
        self._srv = None
        self._srv_thread = None
        self._pw = None
        self._browser = None
        self._page = None
        self._ffmpeg: subprocess.Popen | None = None
        self.port = 0
        self.current_code: str | None = None
        # Set when the page goes away under us. With show_window on the operator
        # can simply close the window, so this is an ordinary end to the set —
        # not a pattern failure to log and retry against a dead page.
        self.page_closed = False
        # Playwright's sync API is pinned to the thread that created it, and
        # raises "Cannot switch to a different thread" anywhere else. The
        # session starts the engine on an executor thread and then drives it
        # from the event loop thread, so every Playwright call is marshalled
        # onto this single worker instead.
        self._pool = ThreadPoolExecutor(max_workers=1,
                                        thread_name_prefix="kaia-strudel-pw")

    def _call(self, fn, *args):
        """Run `fn` on the one thread that owns the Playwright objects."""
        return self._pool.submit(fn, *args).result()

    # ── lifecycle ────────────────────────────────────────────────────

    def _serve(self) -> None:
        handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                    directory=str(ASSET_DIR))
        # Quiet: SimpleHTTPRequestHandler logs every asset fetch to stderr.
        handler_cls = type("QuietHandler", (handler.func,),
                           {"log_message": lambda *a, **k: None})
        socketserver.TCPServer.allow_reuse_address = True
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self._srv = socketserver.TCPServer(
            ("127.0.0.1", self.port),
            functools.partial(handler_cls, directory=str(ASSET_DIR)))
        self._srv_thread = threading.Thread(target=self._srv.serve_forever,
                                            daemon=True, name="kaia-strudel-http")
        self._srv_thread.start()

    def start(self) -> None:
        self._call(self._start_impl)

    def _start_impl(self) -> None:
        if not assets_present():
            raise RuntimeError(
                "Strudel assets missing — run tools/maintenance/fetch_music_assets.py")
        if not ensure_sink():
            raise RuntimeError(f"could not create the '{SINK_NAME}' audio sink")

        self._serve()
        os.environ["PULSE_SINK"] = SINK_NAME
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        args = ["--autoplay-policy=no-user-gesture-required", "--no-sandbox",
                "--window-size=760,520"]
        if not self.show_window:
            args.append("--window-position=-32000,-32000")
        self._browser = self._pw.chromium.launch(
            headless=False,                 # headless emits silence; see module docstring
            executable_path=self._pw.chromium.executable_path, args=args)
        # no_viewport: Playwright otherwise pins the page to a fixed 1280x720
        # that ignores the real window. The window opens at 760x520 and the
        # operator resizes it, but the page kept rendering at 1280x720 — so the
        # code was cut off at 1280 however wide the window got, and everything
        # past the viewport was black void. With no_viewport the page uses the
        # window's own size and reflows when it is resized.
        self._page = self._browser.new_page(no_viewport=True)
        self._page.goto(f"http://127.0.0.1:{self.port}/player.html",
                        wait_until="load", timeout=45000)
        self._page.wait_for_function("() => window.__kaia && window.__kaia.ready",
                                     timeout=30000)
        log_info(f"[music] Strudel engine up on port {self.port} "
                 f"(window {'visible' if self.show_window else 'off-screen'})")

    def play(self, code: str) -> bool:
        """Evaluate a pattern. Returns False if Strudel reported an error."""
        return self._call(self._play_impl, code)

    def _play_impl(self, code: str) -> bool:
        if self._page is None or self.page_closed:
            return False
        try:
            self._page.evaluate(
                "c => { window.__kaia.pending = c; window.__kaia.staged = true; }", code)
            self._page.click("#apply", timeout=15000)
            err = self._page.evaluate("() => window.__kaia.error")
            if err:
                log_warning(f"[music] Strudel rejected the pattern: {err}")
                return False
            self.current_code = code
            return True
        except Exception as exc:
            if self._note_if_gone(exc):
                return False
            log_error(f"[music] failed to apply pattern: {exc}")
            return False

    # ── has the page gone away? ──────────────────────────────────────

    @staticmethod
    def _is_gone(exc: Exception) -> bool:
        """True for the family of Playwright errors that mean 'no page left'."""
        m = str(exc).lower()
        return ("has been closed" in m or "target closed" in m
                or "browser has been closed" in m or "target crashed" in m)

    def _note_if_gone(self, exc: Exception) -> bool:
        """Record a vanished page once, quietly. Returns True if it is gone."""
        if not self._is_gone(exc):
            return False
        if not self.page_closed:
            self.page_closed = True
            log_warning("[music] the Strudel player window was closed; "
                        "ending the session.")
        return True

    def alive(self) -> bool:
        """False once the page is gone, so a session can stop cleanly."""
        if self._page is None or self.page_closed:
            return False
        try:
            if self._call(lambda: self._page.is_closed()):
                self.page_closed = True
                log_warning("[music] the Strudel player window was closed; "
                            "ending the session.")
                return False
            return True
        except Exception as exc:
            self._note_if_gone(exc)
            return False

    def last_error(self) -> str | None:
        """Whatever Strudel last reported, via the owning thread.

        Reaching for `engine._page` from outside raises greenlet's "Cannot
        switch to a different thread"; every caller needs this instead.
        """
        if self._page is None:
            return None
        try:
            return self._call(lambda: self._page.evaluate("() => window.__kaia.error"))
        except Exception:
            return None

    def current_pattern(self) -> str | None:
        if self._page is None:
            return None
        try:
            return self._call(lambda: self._page.evaluate("() => window.__kaia.current"))
        except Exception:
            return None

    def set_label(self, genre: str, section: str) -> None:
        """Show what is playing in the editor's header."""
        if self._page is None:
            return
        try:
            self._call(lambda: self._page.evaluate(
                "a => window.__kaiaSetLabel && window.__kaiaSetLabel(a[0], a[1])",
                [genre, section]))
        except Exception as exc:
            log_debug(f"[music] label update failed: {exc}")

    def human_edited(self) -> bool:
        """True if somebody has typed in the editor since Kaia last applied.

        Kaia holds her next edit while this is set, so a human who is part-way
        through changing something does not have it yanked out from under them.
        """
        if self._page is None:
            return False
        try:
            return bool(self._call(
                lambda: self._page.evaluate("() => !!window.__kaia.dirty")))
        except Exception:
            return False

    def stop(self) -> None:
        self._call(self._stop_impl)

    def _stop_impl(self) -> None:
        if self._page is None or self.page_closed:
            return
        try:
            self._page.evaluate(
                "() => { window.__kaia.pending = null; window.__kaia.staged = true; }")
            self._page.click("#apply", timeout=10000)
            self.current_code = None
        except Exception as exc:
            if not self._is_gone(exc):
                log_debug(f"[music] stop: {exc}")

    # ── capture ──────────────────────────────────────────────────────

    def open_capture(self) -> subprocess.Popen:
        """ffmpeg reading the sink monitor, writing raw s16le to stdout."""
        self.close_capture()
        # Loudness control lives here rather than in the patterns. Measured
        # across the genre set, raw output ran 0.05 to 0.29 RMS with three
        # genres peaking at full scale — so switching genre was a level jump
        # and the loudest ones clipped. A compressor plus a true-peak limiter
        # normalises all of them without needing a hand-tuned gain per pattern
        # that would drift the moment a pattern is edited.
        self._ffmpeg = subprocess.Popen(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-f", "pulse", "-i", f"{SINK_NAME}.monitor",
             "-af", "acompressor=threshold=0.12:ratio=3:attack=25:release=450,"
                    "alimiter=limit=0.85:attack=5:release=60",
             "-f", "s16le", "-ar", "48000", "-ac", "2", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=FRAME_BYTES * 8)
        return self._ffmpeg

    def close_capture(self) -> None:
        if self._ffmpeg is None:
            return
        try:
            self._ffmpeg.terminate()
            self._ffmpeg.wait(timeout=3)
        except Exception:
            try:
                self._ffmpeg.kill()
            except Exception:
                pass
        self._ffmpeg = None

    def close(self) -> None:
        try:
            self._call(self._close_impl)
        finally:
            self._pool.shutdown(wait=False)

    def _close_impl(self) -> None:
        self.close_capture()
        for shut, what in ((lambda: self._browser and self._browser.close(), "browser"),
                           (lambda: self._pw and self._pw.stop(), "playwright"),
                           (lambda: self._srv and self._srv.shutdown(), "http server")):
            try:
                shut()
            except Exception as exc:
                log_debug(f"[music] closing {what}: {exc}")
        self._browser = self._pw = self._srv = self._page = None
