#!/usr/bin/env python3
"""
Fetch everything the !music engine needs. Run once after cloning.

Nothing this downloads is committed: Strudel is AGPL-3.0, and fetching it here
rather than vendoring it keeps that copyleft off Kaiacord while still using the
real thing. Same shape as `npm install`.

    python tools/maintenance/fetch_music_assets.py
"""
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets" / "strudel"
# The full REPL component, not @strudel/web. The slim bundle has no _scope,
# _pianoroll, slider, trancegate or rlpf, and every one of them fails silently
# there — the page loads, patterns evaluate, and the visuals simply never
# appear. 1.3.0 or newer is also required for supersaw / trans / duck / orbit
# and `$:` lanes, all of which are missing from 1.0.x.
BUNDLE_URL = "https://unpkg.com/@strudel/repl@1.3.0"


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    dest = ASSETS / "strudel-repl.js"
    print(f"→ {BUNDLE_URL}")
    with urllib.request.urlopen(BUNDLE_URL, timeout=180) as r:
        dest.write_bytes(r.read())
    print(f"  saved {dest.relative_to(ROOT)} ({dest.stat().st_size // 1024} KiB)")

    if not (ASSETS / "player.html").is_file():
        print("!! player.html is missing from assets/strudel/ — it is part of "
              "the repo and should not have been deleted.")
        return 1

    print("→ Chromium for Playwright")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                   check=False)

    missing = [t for t in ("ffmpeg", "pactl") if not shutil.which(t)]
    if missing:
        print(f"!! not on PATH: {', '.join(missing)} — the capture needs both.")
        return 1

    print("\nready. `!music on --house` in a Discord voice channel.")
    print("To hear it on this machine as well, set music.monitor_on_speakers: true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
