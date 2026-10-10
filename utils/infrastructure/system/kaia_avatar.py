"""The shared Kaia codec avatar's files, for the dashboards that show her.

KAIA//RX and the DJ booth both serve `assets/kaia-avatar/` under `/kaia/`:
the engine (`js/<name>.js`) and the portraits (`portraits/<face>/<file>`).
The same engine runs Kaia's security dashboard and Kaiagotchi's; the copies
are kept identical, so a page brings its own states with
`KaiaAnimator.registerMood` instead of editing the engine.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[3] / "assets" / "kaia-avatar"
TYPES = {".js": "text/javascript; charset=utf-8", ".json": "application/json", ".webp": "image/webp"}
_SEGMENT = re.compile(r"^[\w.\-]+$")


def resolve(rel: str) -> Optional[tuple[Path, str]]:
    """The file and content type for a path under `/kaia/`, or None. Every
    segment is checked by name, the type must be one the avatar uses, and the
    resolved path must stay inside ROOT."""
    parts = rel.split("/")
    if not (1 < len(parts) <= 3 and all(_SEGMENT.match(p) and p not in (".", "..") for p in parts)):
        return None
    path = (ROOT / Path(*parts)).resolve()
    ctype = TYPES.get(path.suffix)
    if ctype is None or ROOT.resolve() not in path.parents or not path.is_file():
        return None
    return path, ctype
