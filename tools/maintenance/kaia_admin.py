#!/usr/bin/env python3
"""KAIA // OPS: the admin dashboard, in a window of its own.

A separate process on 127.0.0.1 that reads what the bot writes — the log,
memory/, knowledge_base/, Ollama, the machine — and never touches the bot's
event loop. Read-only: the only thing it runs is the read-only diagnostics on
its CHECKS tab, when clicked.

    venv/bin/python3 tools/maintenance/kaia_admin.py              # serve and open the window
    venv/bin/python3 tools/maintenance/kaia_admin.py --no-window  # serve only; open the URL yourself
    venv/bin/python3 tools/maintenance/kaia_admin.py --detach     # serve in the background and return

If one is already serving on the port, this opens a window onto it and exits.
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
# Anything an imported module logs goes to its own file, never into the bot's.
os.environ.setdefault("KAIACORD_LOG_FILE", str(ROOT / "logs" / "kaia_admin.log"))


def already_serving(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1.5) as r:
            return b"kaia-ops" in r.read()
    except Exception:
        return False


def open_window(url: str) -> None:
    from utils.infrastructure.system import app_window
    if app_window.launch(url, "KAIA // OPS", "KaiaOps", size="1720x1040", icon="utilities-system-monitor") is None:
        import webbrowser
        webbrowser.open(url)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--port", type=int, default=0, help="default 47433")
    ap.add_argument("--no-window", action="store_true")
    ap.add_argument("--detach", action="store_true", help="serve in the background and return")
    args = ap.parse_args()
    from utils.admin.server import DEFAULT_PORT, serve
    port = args.port or DEFAULT_PORT
    if already_serving(port):
        url = f"http://127.0.0.1:{port}/"
        print(f"KAIA // OPS is already serving at {url}")
        if not args.no_window:
            open_window(url)
        return 0
    if args.detach:
        if os.fork():
            import time
            for _ in range(80):
                if already_serving(port):
                    url = f"http://127.0.0.1:{port}/"
                    print(f"KAIA // OPS serving at {url} (in the background)")
                    if not args.no_window:
                        open_window(url)
                    return 0
                time.sleep(0.25)
            print("KAIA // OPS did not come up; see logs/kaia_admin.log", file=sys.stderr)
            return 1
        os.setsid()
        log = open(ROOT / "logs" / "kaia_admin.log", "a")
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        devnull = os.open(os.devnull, os.O_RDONLY)
        os.dup2(devnull, 0)
    srv = serve(port)
    if args.detach and srv.server_address[1] != port:
        return 1                                # the parent waits on this port only
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"KAIA // OPS at {url}  (Ctrl-C to stop)", flush=True)
    if not args.no_window and not args.detach:
        open_window(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
