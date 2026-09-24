#!/usr/bin/env python3
"""Write memory/x_cookies.json for twikit from a logged-in browser session.

    venv/bin/python3 tools/social/export_x_cookies.py
    venv/bin/python3 tools/social/export_x_cookies.py --cookie-file ~/.../cookies.sqlite
    venv/bin/python3 tools/social/export_x_cookies.py --manual <auth_token> <ct0>

With no arguments it tries Chrome, Firefox, Edge and Chromium in turn.
`--cookie-file` reads one Firefox-family profile directly (Firedragon,
LibreWolf, a non-default profile). `--manual` takes the two cookies that
matter, copied from the browser's dev tools.

The file holds a live session: anyone with it is logged in as the account.
See docs/04-security/x-twikit-credentials.md.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "memory" / "x_cookies.json"
DOMAINS = (".x.com", ".twitter.com")


def _save(cookies: dict) -> None:
    # twikit 2.x loads a flat {name: value} map.
    from utils.core.atomic_write import write_atomic
    OUT.parent.mkdir(exist_ok=True)
    write_atomic(OUT, json.dumps(cookies, indent=2))
    print(f"Wrote {len(cookies)} cookies to {OUT}. Restart the bot to use them.")


def _collect(loader, **kw) -> dict:
    cookies = {}
    for domain in DOMAINS:
        try:
            for c in loader(domain_name=domain, **kw):
                cookies[c.name] = c.value
        except Exception as e:
            print(f"    {domain}: {e}")
    return cookies


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--cookie-file", help="a Firefox-family cookies.sqlite to read")
    ap.add_argument("--manual", nargs=2, metavar=("AUTH_TOKEN", "CT0"),
                    help="write these two cookies without reading a browser")
    args = ap.parse_args()

    if args.manual:
        _save({"auth_token": args.manual[0], "ct0": args.manual[1]})
        return 0

    try:
        import browser_cookie3
    except ImportError:
        print("browser_cookie3 is not installed: venv/bin/pip install browser_cookie3")
        return 1

    if args.cookie_file:
        sources = [("Firefox profile", browser_cookie3.firefox, {"cookie_file": args.cookie_file})]
    else:
        sources = [(name, getattr(browser_cookie3, name.lower()), {})
                   for name in ("Chrome", "Firefox", "Edge", "Chromium")]

    for name, loader, kw in sources:
        print(f"  Trying {name}...")
        cookies = _collect(loader, **kw)
        if "auth_token" in cookies:
            _save(cookies)
            return 0
        if cookies:
            print(f"    {len(cookies)} cookies but no auth_token: not logged in there")

    print("No logged-in X session found. Log into x.com in the browser, or use --manual.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
