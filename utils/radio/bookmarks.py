"""The receiver's bookmarks: channels someone chose to name, tag and mark.

Separate from the ledger (what the scanner has heard): a bookmark is a
person's note. Each has a frequency, a name, a tag (with the tag's colour),
and two marks the scanner obeys — `priority` (the trigger takes a weaker
signal there, and a habitual-data channel bookmarked priority is always held)
and `ignore` (never a trigger: the person decided it is noise). Nothing else
ignores a channel on anyone's behalf.

Stored at memory/radio/bookmarks.json (a test file under pytest), written
atomically. Gqrx's bookmarks.csv can be read in and the bookmarks written out
in the same format, so the two receivers share one list.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Optional

from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

_lock = threading.Lock()
GQRX_PATH = Path.home() / ".config" / "gqrx" / "bookmarks.csv"
DEFAULT_TAG = "Untagged"
DEFAULT_COLOR = "#94a3b8"
MODES = ("Narrow FM", "WFM (mono)", "AM", "USB", "LSB", "CW-U", "Raw I/Q")


def path() -> Path:
    return Path(telemetry_path("memory/radio/bookmarks.json"))


def load() -> dict:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("tags", {})
    data.setdefault("items", [])
    return data


def _save(data: dict) -> None:
    from utils.core.atomic_write import write_atomic
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data["items"].sort(key=lambda b: b["freq"])
    write_atomic(p, json.dumps(data, indent=1, ensure_ascii=False))


def _clean(item: dict, old: Optional[dict] = None) -> dict:
    b = dict(old or {})
    b["freq"] = int(round(float(item.get("freq", b.get("freq", 0)))))
    b["name"] = str(item.get("name", b.get("name", "")) or "").strip()[:80]
    b["tag"] = str(item.get("tag", b.get("tag", DEFAULT_TAG)) or DEFAULT_TAG).strip()[:40]
    b["mode"] = str(item.get("mode", b.get("mode", "Narrow FM")) or "Narrow FM")
    b["bw"] = int(item.get("bw", b.get("bw", 12500)) or 12500)
    b["priority"] = bool(item.get("priority", b.get("priority", False)))
    b["ignore"] = bool(item.get("ignore", b.get("ignore", False)))
    if b["priority"] and b["ignore"]:
        b["ignore"] = not item.get("priority")          # the mark just set wins
        b["priority"] = not b["ignore"]
    b["notes"] = str(item.get("notes", b.get("notes", "")) or "")[:400]
    b.setdefault("added", time.time())
    return b


def upsert(item: dict, tolerance_hz: int = 1000) -> dict:
    """Add a bookmark, or update the one within `tolerance_hz` of it."""
    with _lock:
        data = load()
        f = int(round(float(item["freq"])))
        old = next((b for b in data["items"] if abs(b["freq"] - f) <= tolerance_hz), None)
        new = _clean(item, old)
        if old:
            data["items"][data["items"].index(old)] = new
        else:
            data["items"].append(new)
        if new["tag"] not in data["tags"]:
            data["tags"][new["tag"]] = str(item.get("color") or DEFAULT_COLOR)
        _save(data)
        return new


def remove(freq: int, tolerance_hz: int = 1000) -> bool:
    with _lock:
        data = load()
        keep = [b for b in data["items"] if abs(b["freq"] - int(freq)) > tolerance_hz]
        if len(keep) == len(data["items"]):
            return False
        data["items"] = keep
        _save(data)
        return True


def set_tag_color(tag: str, color: str) -> None:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color or ""):
        raise ValueError("a colour is #rrggbb")
    with _lock:
        data = load()
        data["tags"][tag] = color
        _save(data)


def marks() -> tuple[list[int], list[int]]:
    """(priority frequencies, ignored frequencies)."""
    items = load()["items"]
    return [b["freq"] for b in items if b.get("priority")], [b["freq"] for b in items if b.get("ignore")]


# ── Gqrx ─────────────────────────────────────────────────────────────

def parse_gqrx(text: str) -> tuple[dict, list[dict]]:
    """(tags {name: colour}, bookmarks) from Gqrx's bookmarks.csv: a tag table
    ("# Tag name ; color"), a blank line, then "# Frequency ; Name ;
    Modulation ; Bandwidth ; Tags" rows. A row may carry several tags
    (comma-separated); the first is kept as this bookmark's tag."""
    tags, items, section = {}, [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            low = line.lower()
            section = "tags" if "tag name" in low else "items" if "frequency" in low else section
            continue
        cols = [c.strip() for c in line.split(";")]
        if section == "tags" and len(cols) >= 2:
            tags[cols[0]] = cols[1] if re.fullmatch(r"#[0-9a-fA-F]{6}", cols[1]) else DEFAULT_COLOR
        elif section == "items" and len(cols) >= 2:
            try:
                f = int(cols[0])
            except ValueError:
                continue
            tag = (cols[4].split(",")[0].strip() if len(cols) > 4 and cols[4] else DEFAULT_TAG) or DEFAULT_TAG
            try:
                bw = int(cols[3]) if len(cols) > 3 and cols[3] else 12500
            except ValueError:
                bw = 12500
            items.append({"freq": f, "name": cols[1], "mode": cols[2] if len(cols) > 2 and cols[2] else "Narrow FM",
                          "bw": bw, "tag": tag})
    return tags, items


def import_gqrx(text: Optional[str] = None) -> dict:
    """Merge Gqrx bookmarks in: new frequencies are added, and an existing
    bookmark keeps its own name and marks (what was set here wins). Returns
    {added, kept, tags}."""
    if text is None:
        text = GQRX_PATH.read_text(encoding="utf-8", errors="replace")
    tags, items = parse_gqrx(text)
    added = kept = 0
    with _lock:
        data = load()
        for t, c in tags.items():
            data["tags"].setdefault(t, c)
        have = data["items"]
        for it in items:
            if any(abs(b["freq"] - it["freq"]) <= 1000 for b in have):
                kept += 1
                continue
            have.append(_clean(it))
            data["tags"].setdefault(it["tag"], DEFAULT_COLOR)
            added += 1
        _save(data)
    return {"added": added, "kept": kept, "tags": len(tags)}


def export_gqrx() -> str:
    """The bookmarks as Gqrx's bookmarks.csv."""
    data = load()
    tags = dict(data["tags"])
    for b in data["items"]:
        tags.setdefault(b["tag"], DEFAULT_COLOR)
    out = ["# Tag name          ;  color"]
    out += [f"{t:<20}; {c}" for t, c in sorted(tags.items())]
    out += ["", "# Frequency ; Name                                 ; Modulation          ;  Bandwidth; Tags"]
    for b in data["items"]:
        name = b["name"].replace(";", ",") or f"{b['freq'] / 1e6:.4f} MHz"
        out.append(f"{b['freq']:>12}; {name:<37}; {b['mode']:<20}; {b['bw']:>10}; {b['tag']}")
    return "\n".join(out) + "\n"


def gqrx_available() -> bool:
    return GQRX_PATH.is_file()
