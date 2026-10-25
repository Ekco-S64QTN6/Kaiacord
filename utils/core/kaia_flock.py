"""Kaia's own flock: the sheep she breeds and mutates, and the votes that steer them.

Electric Sheep is a genetic algorithm with people as its fitness function: the
screensaver shows sheep, viewers vote, and the server breeds the liked ones and
lets the disliked ones die. This is that loop, on Discord:

    breed     two sheep crossed by flam3-genome (alternate, interpolate or union)
    mutate    one sheep's coefficients, variations or colours changed by flam3-genome
    adopt     every child that passes the strict preview is kept, named kaia.<n>,
              with its parents, its depth and the Electric Sheep it descends from
    vote      👍 / 👎 on a posted piece counts for the sheep in it, once per person;
              a sheep at CULL_AT or below is never picked or bred again

Her children live in memory/art/kaia_flock/ (git-ignored); the flock they come
from is kaia_sheep's. A bred or mutated sheep is a derivative of CC BY-NC sheep,
so its credit names the Electric Sheep it descends from (`credit`).
"""
from __future__ import annotations

import json
import os
import random
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from utils.core import kaia_sheep as ks
from utils.infrastructure.logging.kaia_logger import log_debug, log_info
from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

FLOCK = Path(telemetry_path(os.path.join("memory", "art", "kaia_flock")))
INDEX = FLOCK / "index.json"
VOTES = Path(telemetry_path(os.path.join("memory", "art", "votes.json")))
UP, DOWN = "👍", "👎"
CULL_AT = -2               # net votes at which a sheep leaves the gene pool
MAX_POSTS = 2000           # posts remembered for voting; the oldest are forgotten
_lock = threading.Lock()


def _read(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _write(path: Path, data) -> None:
    from utils.core.atomic_write import write_atomic
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps(data, indent=1, ensure_ascii=False))


# ── her sheep ───────────────────────────────────────────────────────

def _index() -> dict:
    data = _read(INDEX, {})
    data.setdefault("next", 1)
    data.setdefault("sheep", {})
    return data


def hers() -> dict:
    """name -> entry, for her sheep actually on disk."""
    return {n: e for n, e in _index()["sheep"].items() if (FLOCK / f"{n}.flam3").exists()}


def genome_of(name: str) -> Optional[str]:
    for path in (FLOCK / f"{name}.flam3", ks.FLOCK_DIR / f"{name}.flam3"):
        try:
            return path.read_text()
        except OSError:
            continue
    return None


def depth(name: str) -> int:
    """Generations from the Electric Sheep flock: its sheep are 0."""
    return int(hers().get(name, {}).get("depth", 0))


def ancestors(name: str) -> list[str]:
    """The Electric Sheep a sheep descends from (itself, for one of theirs)."""
    entry = hers().get(name)
    return list(entry.get("ancestors", [])) if entry else [name]


def adopt(genome: str, parents: list[str], method: str) -> str:
    """Keep a child in her flock and return its name."""
    with _lock:
        data = _index()
        name = f"kaia.{data['next']}"
        data["next"] += 1
        genome = re.sub(r'(<flame\b[^>]*?\bname=")[^"]*(")', rf"\g<1>{name}\g<2>", genome, count=1)
        if f'name="{name}"' not in genome:
            genome = genome.replace("<flame", f'<flame name="{name}"', 1)
        roots: list[str] = []
        for p in parents:
            for a in ancestors(p):
                if a not in roots:
                    roots.append(a)
        data["sheep"][name] = {
            "parents": list(parents), "method": method, "born": time.time(),
            "depth": 1 + max((depth(p) for p in parents), default=0),
            "ancestors": roots, **ks.describe(genome)}
        FLOCK.mkdir(parents=True, exist_ok=True)
        from utils.core.atomic_write import write_atomic
        write_atomic(FLOCK / f"{name}.flam3", genome)
        _write(INDEX, data)
    log_info(f"[art] {name} joined her flock ({method} from {' × '.join(parents)})")
    return name


def resolve(token: str, channel_id: Optional[int] = None) -> Optional[str]:
    """A sheep named the way people will type it: `kaia.3` / `k3`, an Electric
    Sheep's number (`541`, `00541`) or full name, or `last` (the last sheep
    posted in this channel)."""
    t = (token or "").strip().lower()
    if not t:
        return None
    if t == "last":
        return _read(VOTES, {}).get("last", {}).get(str(channel_id))
    if m := re.fullmatch(r"k(?:aia\.)?(\d+)", t):
        name = f"kaia.{int(m.group(1))}"
        return name if name in hers() else None
    flock = ks.flock()
    if t in flock:
        return t
    if t.isdigit():
        hits = [n for n in flock if n.rsplit(".", 1)[-1].lstrip("0") == t.lstrip("0")]
        return sorted(hits)[0] if hits else None
    return None


# ── votes ───────────────────────────────────────────────────────────

def score(name: str, votes: Optional[dict] = None) -> int:
    v = (votes if votes is not None else _read(VOTES, {})).get("votes", {}).get(name, {})
    return len(v.get("up", [])) - len(v.get("down", []))


def scores() -> dict:
    votes = _read(VOTES, {})
    return {n: score(n, votes) for n in votes.get("votes", {})}


def culled(name: str, table: Optional[dict] = None) -> bool:
    return (table if table is not None else scores()).get(name, 0) <= CULL_AT


def weight(name: str, table: dict) -> float:
    """How likely a sheep is to be picked or bred: liked ones more, culled ones never."""
    s = table.get(name, 0)
    if s <= CULL_AT:
        return 0.0
    return 1.0 + 0.5 * s if s > 0 else 1.0 / (1 - s)


def record_post(message_id: int, channel_id: int, names: list[str]) -> None:
    """Remember which sheep a posted piece showed, so reactions on it count."""
    with _lock:
        votes = _read(VOTES, {})
        posts = votes.setdefault("posts", {})
        posts[str(message_id)] = list(names)
        for old in list(posts)[:-MAX_POSTS]:
            del posts[old]
        if names:
            votes.setdefault("last", {})[str(channel_id)] = names[-1]
        _write(VOTES, votes)


def vote(message_id: int, user_id: int, emoji: str, add: bool) -> list[tuple[str, int]]:
    """Count (or take back) one person's vote on a posted piece. Returns
    [(sheep, new score)], empty when the message was not a sheep or the emoji
    is not a vote. A new vote replaces that person's opposite one."""
    if emoji not in (UP, DOWN):
        return []
    with _lock:
        votes = _read(VOTES, {})
        names = votes.get("posts", {}).get(str(message_id))
        if not names:
            return []
        side, other = ("up", "down") if emoji == UP else ("down", "up")
        uid = str(user_id)
        for name in names:
            v = votes.setdefault("votes", {}).setdefault(name, {"up": [], "down": []})
            if add:
                if uid in v[other]:
                    v[other].remove(uid)
                if uid not in v[side]:
                    v[side].append(uid)
            elif uid in v[side]:
                v[side].remove(uid)
        _write(VOTES, votes)
        return [(n, score(n, votes)) for n in names]


# ── choosing, breeding, mutating ────────────────────────────────────

def gene_pool(intent=None) -> list[str]:
    """Every sheep that may be picked or bred: the Electric Sheep flock (steered
    by what she chose) and her own, minus the culled."""
    table = scores()
    pool = ks.candidates(ks.flock(), intent) + sorted(hers())
    return [n for n in dict.fromkeys(pool) if not culled(n, table)]


def pick(rng: random.Random, intent=None, exclude=()) -> str:
    table = scores()
    pool = [n for n in gene_pool(intent) if n not in exclude] or [n for n in ks.flock() if n not in exclude]
    if not pool:
        raise RuntimeError("the flock is empty — run tools/maintenance/fetch_art_flock.py")
    return rng.choices(pool, weights=[weight(n, table) or 0.01 for n in pool])[0]


def breed(rng: random.Random, a: Optional[str] = None, b: Optional[str] = None,
          intent=None, tries: int = 4) -> Optional[ks.Piece]:
    """A child of two sheep that survives the strict preview, or None. Named
    parents are kept; an unnamed one is drawn again on each try."""
    for attempt in range(tries):
        pa = a or pick(rng, intent, exclude=(b,) if b else ())
        pb = b or pick(rng, intent, exclude=(pa,))
        ga, gb = genome_of(pa), genome_of(pb)
        if not ga or not gb:
            return None
        child = ks._cross(ga, gb, rng)
        if child and ks._preview_ok(child, strict=True):
            return ks.Piece(child, [pa, pb], bred=True, method="bred")
        log_debug(f"[art] cross {attempt + 1} of {pa} × {pb} came out degenerate")
    return None


def mutate(rng: random.Random, a: Optional[str] = None, intent=None, tries: int = 4) -> Optional[ks.Piece]:
    """A mutation of one sheep that survives the strict preview, or None."""
    for attempt in range(tries):
        pa = a or pick(rng, intent)
        ga = genome_of(pa)
        if not ga:
            return None
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.flam3"
            path.write_text(ga)
            r = ks._run("flam3-genome", {"mutate": path, "seed": rng.randrange(1 << 30),
                                         "isaac_seed": rng.randrange(1 << 30)}, timeout=30)
        child = next(iter(ks.split_flames(r.stdout).values()), None)
        if child and ks._preview_ok(child, strict=True):
            return ks.Piece(child, [pa], bred=True, method="mutated")
        log_debug(f"[art] mutation {attempt + 1} of {pa} came out degenerate")
    return None


def credit(names: list[str]) -> str:
    """The licence credit for the sheep shown: theirs by number, hers with the
    Electric Sheep she descends from."""
    mine = hers()
    parts = []
    for n in names:
        entry = mine.get(n)
        if entry:
            roots = entry.get("ancestors", [])
            parts.append(f"{n}, {entry.get('method', 'bred')} from {' × '.join(entry.get('parents', []))}"
                         f" (of {', '.join(roots[:4])}{' …' if len(roots) > 4 else ''})")
        else:
            parts.append(n)
    return " → ".join(parts) + f" · {ks.CREDIT}"
