"""A dashboard as a desktop window, not a browser tab.

The DJ booth and KAIA//RX are pages served on 127.0.0.1. Opened in Chrome's app
mode they still behaved like a website: a "press Esc to show your cursor"
notice on every knob turn, page zoom on a touchpad pinch that cut the mixer in
half, a right-click menu, a browser in the taskbar. This opens them in a GTK
window holding a WebKitGTK view — its own title, window class and icon, none
of the browser around it.

Run by the *system* Python (`/usr/bin/python3`), which has GObject
introspection and WebKitGTK; the bot's venv has neither, and this file imports
nothing from the project so either interpreter can load it. `launch()` is what
the bot calls; it returns None when GTK/WebKit is not available, and the
caller falls back to a browser.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Optional

SYSTEM_PYTHON = "/usr/bin/python3"
_available: Optional[bool] = None


def available() -> bool:
    """Whether the system Python can open a WebKitGTK window."""
    global _available
    if _available is None:
        py = SYSTEM_PYTHON if os.path.exists(SYSTEM_PYTHON) else shutil.which("python3")
        try:
            # And GStreamer able to play sound: WebKitGTK's audio — media
            # elements and Web Audio alike — goes out through an audio sink from
            # gst-plugins-good. Without one the window opens and plays nothing
            # (the receiver's monitor, the booth's headphones), so a browser,
            # which plays, is better.
            out = subprocess.run([py, "-c", "import gi; gi.require_version('Gtk', '3.0'); "
                                  "gi.require_version('WebKit2', '4.1'); gi.require_version('Gst', '1.0'); "
                                  "from gi.repository import Gtk, WebKit2, Gst; Gst.init(None); "
                                  "import sys; sys.exit(0 if Gst.ElementFactory.find('autoaudiosink') else 3)"],
                                 capture_output=True, timeout=20)
            _available = out.returncode == 0
        except (OSError, subprocess.SubprocessError):
            _available = False
    return _available


def launch(url: str, title: str, wm_class: str, size: str = "1600x1000", icon: str = "",
           preexec_fn=None) -> Optional[subprocess.Popen]:
    """Open `url` in its own window; None if this machine can't."""
    if not available():
        return None
    py = SYSTEM_PYTHON if os.path.exists(SYSTEM_PYTHON) else shutil.which("python3")
    try:
        return subprocess.Popen([py, os.path.abspath(__file__), "--url", url, "--title", title,
                                 "--class", wm_class, "--size", size, "--icon", icon],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                preexec_fn=preexec_fn, env={**os.environ})
    except OSError:
        return None


def _main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Open a local dashboard in its own window.")
    ap.add_argument("--url", required=True)
    ap.add_argument("--title", default="Kaia")
    ap.add_argument("--class", dest="wm_class", default="Kaia")
    ap.add_argument("--size", default="1600x1000")
    ap.add_argument("--icon", default="")
    a = ap.parse_args()

    # WebKitGTK's DMA-BUF renderer fails on this machine's NVIDIA driver under
    # Wayland ("Error 71 (Protocol error) dispatching to Wayland display") and
    # the window closes at once; without it the page is still composited.
    os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import GLib, Gtk, WebKit2

    GLib.set_prgname(a.wm_class)                 # the window class the desktop groups it by
    GLib.set_application_name(a.title)
    w, h = (int(x) for x in a.size.lower().split("x"))
    win = Gtk.Window(title=a.title)
    win.set_default_size(w, h)
    if a.icon:
        win.set_icon_name(a.icon)

    view = WebKit2.WebView()
    s = view.get_settings()
    s.set_enable_webaudio(True)
    s.set_media_playback_requires_user_gesture(False)     # the headphones and the monitor play when asked
    s.set_enable_developer_extras(False)
    s.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.ALWAYS)
    s.set_enable_smooth_scrolling(True)
    view.connect("context-menu", lambda *args: True)      # no browser menu on right-click
    view.load_uri(a.url)

    win.add(view)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(_main())
