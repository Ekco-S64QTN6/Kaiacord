"""
Live-coding performance model: the track is edited, not swapped.

The first version replaced the whole program at every section boundary, which
is not how any of this is actually made. Watching Switch Angel narrate a build
("lower the depth of the duck to 0.8", "destroy the bass with diode
distortion", "drop the bass to F1", "add 30 semitones", "isolate the lead",
"bring in the angels"), almost every move is a *small edit to a line that is
already playing*. Parts arriving and leaving is the minority of it.

So a performance here holds structured state — a set of lanes, each with a base
pattern and a chain of effects — and applies operations to it:

    ADD    bring a lane in
    DROP   take it out
    FX     append an effect to a lane that is already playing
    SET    change one parameter's value in place
    SOLO   mute everything except one lane
    CLEAR  release a solo

Rendering that state produces the program text, so consecutive sections differ
by a line or two rather than entirely, which is what the editor shows and what
Strudel hot-swaps.

`trancegate` and `rlpf` appear in Switch Angel's patches but are her own
helpers and do not exist in Strudel; the equivalents used here are
`tremolo`/`tremolosync`/`tremolodepth` and `lpf(...).lpq(...)`.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

ADD, DROP, FX, SET, SOLO, CLEAR = "add", "drop", "fx", "set", "solo", "clear"


@dataclass
class Lane:
    """One `$:` line: a base pattern plus whatever has been chained onto it."""
    name: str
    base: str
    chain: list[str] = field(default_factory=list)
    live: bool = False

    def render(self, muted: bool = False) -> str:
        prefix = "_$: " if muted else "$: "
        body = self.base + "".join(self.chain)
        return prefix + body

    def add_fx(self, fx: str) -> bool:
        """Append an effect, unless an equivalent call is already there."""
        name = _call_name(fx)
        if name and any(_call_name(c) == name for c in self.chain):
            return False
        self.chain.append(fx)
        return True

    def set_param(self, call: str, value: str) -> bool:
        """Rewrite one call's argument in place, wherever it lives.

        This is the operation the whole model exists for: it turns a section
        change into "that number is different now" rather than a new program.
        """
        pattern = re.compile(rf"\.{re.escape(call)}\(([^()]*)\)")
        for i, part in enumerate(self.chain):
            if pattern.search(part):
                self.chain[i] = pattern.sub(f".{call}({value})", part, count=1)
                return True
        if pattern.search(self.base):
            self.base = pattern.sub(f".{call}({value})", self.base, count=1)
            return True
        self.chain.append(f".{call}({value})")
        return True


def _call_name(fragment: str) -> str | None:
    m = re.match(r"\.([A-Za-z_][A-Za-z0-9_]*)\(", fragment.strip())
    return m.group(1) if m else None


@dataclass
class Move:
    """One narrated edit, with how long to sit on it before the next."""
    op: str
    lane: str = ""
    arg: str = ""
    value: str = ""
    seconds: float = 20.0
    say: str = ""          # shown in the UI and written to the log


class Performance:
    """Applies a genre's script of moves to live lane state."""

    def __init__(self, cpm: str, lanes: dict[str, str], script: list[Move],
                 name: str = "", header: str = ""):
        self.cpm = cpm
        self.name = name
        self.header = header
        self._defs = dict(lanes)
        self.lanes: dict[str, Lane] = {
            n: Lane(name=n, base=b) for n, b in lanes.items()}
        self.script = script
        self._i = 0
        self._elapsed = 0.0
        self.passes = 0
        self.soloed: str | None = None
        self.last_say = ""
        self._apply(self.script[0]) if self.script else None

    # ── state ────────────────────────────────────────────────────────

    def _apply(self, mv: Move) -> None:
        lane = self.lanes.get(mv.lane)
        if mv.op == ADD and lane:
            lane.live = True
        elif mv.op == DROP and lane:
            lane.live = False
        elif mv.op == FX and lane:
            lane.add_fx(mv.arg)
        elif mv.op == SET and lane:
            lane.set_param(mv.arg, mv.value)
        elif mv.op == SOLO:
            self.soloed = mv.lane or None
        elif mv.op == CLEAR:
            self.soloed = None
        self.last_say = mv.say

    def code(self) -> str:
        """The full program text for the current state."""
        out = [f"setcpm({self.cpm})"]
        if self.header:
            out.append(self.header)
        for name, lane in self.lanes.items():
            if not lane.live:
                continue
            muted = self.soloed is not None and name != self.soloed
            out.append(lane.render(muted=muted))
        return "\n".join(out)

    def advance(self, dt: float) -> bool:
        """Tick. True when a move was applied and code() is new."""
        if not self.script:
            return False
        self._elapsed += dt
        if self._elapsed < self.script[self._i].seconds:
            return False
        self._elapsed = 0.0
        self._i += 1
        if self._i >= len(self.script):
            # Start again from a clean slate rather than piling effects up
            # forever: after one pass every lane is carrying every mutation.
            self._i = 0
            self.passes += 1
            self.lanes = {n: Lane(name=n, base=b) for n, b in self._defs.items()}
            self.soloed = None
        self._apply(self.script[self._i])
        return True

    # ── introspection ────────────────────────────────────────────────

    def describe(self) -> dict:
        mv = self.script[self._i] if self.script else Move(op=CLEAR)
        live = [n for n, l in self.lanes.items() if l.live]
        return {
            "section": mv.say or mv.op,
            "section_index": self._i + 1,
            "sections_total": len(self.script),
            "lanes": live,
            "soloed": self.soloed,
            "remaining_s": round(max(0.0, mv.seconds - self._elapsed), 1),
            "passes": self.passes,
        }


def build(genre: dict, rng: random.Random | None = None) -> Performance:
    """Instantiate a genre's script, with the timings lightly varied."""
    rng = rng or random.Random()
    script = [
        Move(op=m["op"], lane=m.get("lane", ""), arg=m.get("arg", ""),
             value=str(m.get("value", "")), say=m.get("say", ""),
             seconds=max(6.0, m.get("seconds", 20.0) * rng.uniform(0.85, 1.2)))
        for m in genre["script"]
    ]
    return Performance(cpm=genre["cpm"], lanes=genre["lanes"], script=script,
                       name=genre.get("name", ""), header=genre.get("header", ""))
