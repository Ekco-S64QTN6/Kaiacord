#!/usr/bin/env python3
"""Build the scanner's street list from OpenStreetMap.

The scanner puts misheard street names in dispatch transcripts right against
this list (`utils/radio/streets.py`). Which streets is a deployment fact, so the
area is an argument and the list lands in git-ignored memory/radio/streets.json.
One Overpass query: every named highway way in the administrative area.

    python tools/maintenance/fetch_street_names.py "Dallas County"            # counts only
    python tools/maintenance/fetch_street_names.py "Dallas County" --write
    python tools/maintenance/fetch_street_names.py "Dallas" --admin-level 8 --write

Read-only on OpenStreetMap; re-run when the area changes.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "Kaiacord-scanner/1.0 (street list for dispatch transcripts)"


def query(area: str, admin_level: int) -> str:
    name = area.replace('"', '\\"')
    return (f'[out:csv("name";false)][timeout:150];'
            f'area["name"="{name}"]["boundary"="administrative"]["admin_level"="{admin_level}"]->.a;'
            f'way(area.a)["highway"]["name"];out tags;')


def fetch(area: str, admin_level: int) -> list[str]:
    body = urllib.parse.urlencode({"data": query(area, admin_level)}).encode()
    req = urllib.request.Request(OVERPASS, data=body, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=200) as r:
        text = r.read().decode("utf-8", "replace")
    return sorted({line.strip() for line in text.splitlines() if line.strip()})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("area", help='administrative area name in OpenStreetMap, e.g. "Dallas County"')
    ap.add_argument("--admin-level", type=int, default=6, help="6 is a US county, 8 a city")
    ap.add_argument("--write", action="store_true", help="write memory/radio/streets.json")
    a = ap.parse_args(argv)
    from utils.core.atomic_write import write_atomic
    from utils.radio import streets
    names = fetch(a.area, a.admin_level)
    data = streets.build(names)
    print(f"{len(names)} named ways, {len(data['names'])} street names with a type")
    if not data["names"]:
        print("nothing found: check the area name and admin level", file=sys.stderr)
        return 1
    if a.write:
        p = streets.path()
        p.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(p, json.dumps(data, ensure_ascii=False))
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
