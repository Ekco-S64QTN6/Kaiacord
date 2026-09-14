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

import math
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
        for i, part in enumerate(self.chain):
            if (rewritten := _sub_call(part, call, value)) is not None:
                self.chain[i] = rewritten
                return True
        if (rewritten := _sub_call(self.base, call, value)) is not None:
            self.base = rewritten
            return True
        self.chain.append(f".{call}({value})")
        return True


def _sub_call(text: str, call: str, value: str) -> str | None:
    """Replace `call(...)`'s argument, counting brackets. None if not found.

    An `[^()]*` argument pattern only ever matched flat values, so any
    parameter already carrying an expression — `.degradeBy(perlin.range(.5,.9)
    .slow(13))`, which is most of a generative patch — was invisible to SET and
    a second conflicting call got appended instead of the value changing.

    The *head* call is matched too. A lane's first call carries no leading dot
    — `n("<0 4 0 9 7>*16").scale(...)`, `chord("<Cm7 Fm7>").voicing()` — so a
    dotted search never found it, `SET n` appended a second `.n(...)` at the
    end of the chain, and `set_param` still returned True. Nothing reported it.
    That is why every dance genre's riff was frozen for the whole set: the
    scripts could edit filters, ducking and FM, but the one thing they could
    not change was the notes.
    """
    start = text.find(f".{call}(")
    if start < 0:
        # Head call: `call(` at position 0, with no dot in front of it.
        if text.startswith(f"{call}("):
            open_at = len(call)
            depth = 0
            for i in range(open_at, len(text)):
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                    if depth == 0:
                        return f"{text[:open_at]}({value}){text[i + 1:]}"
            return None
        return None
    open_at = start + len(call) + 1
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return f"{text[:open_at]}({value}){text[i + 1:]}"
    return None


def _call_name(fragment: str) -> str | None:
    m = re.match(r"\.([A-Za-z_][A-Za-z0-9_]*)\(", fragment.strip())
    return m.group(1) if m else None


def _lambda_spans(body: str) -> list[tuple[int, int]]:
    """Character ranges belonging to inline `x=>x...` branches.

    A branch carries its own instrument on purpose: bells routes a coin flip to
    a bright voice or a distant one. A blind string replace hit both the lane
    and the branch, so after one re-patch both sides of the bernoulli gate were
    the same instrument and the gate stopped doing anything audible.
    """
    spans = []
    for m in re.finditer(r"[a-z]\s*=>\s*", body):
        depth, i = 0, m.start()
        while i < len(body):
            if body[i] == "(":
                depth += 1
            elif body[i] == ")":
                if depth == 0:
                    break
                depth -= 1
            i += 1
        spans.append((m.start(), i))
    return spans


def _replace_outside(body: str, old: str, new: str) -> str:
    """Replace `old` with `new`, but never inside an inline branch."""
    spans = _lambda_spans(body)
    out, at = [], 0
    for hit in re.finditer(re.escape(old), body):
        if any(a <= hit.start() < b for a, b in spans):
            continue
        out.append(body[at:hit.start()])
        out.append(new)
        at = hit.end()
    out.append(body[at:])
    return "".join(out)


def _lane_level(body: str, levels: dict) -> float | None:
    """The lane's measured output level, honouring layered sounds.

    `s("a,b:0:0.4")` is two sources with the second at 40%, so its level is
    level(a) + 0.4*level(b). Treating the layers as equal is what made the
    compensation wrong for the choir lane.
    """
    spans = _lambda_spans(body)
    hit = next((m for m in re.finditer(r'\.s\("([^"]+)"', body)
                if not any(a <= m.start() < b for a, b in spans)), None)
    if not hit:
        return None
    total = 0.0
    for part in hit.group(1).split(","):
        bits = part.split(":")
        lvl = levels.get(bits[0].strip())
        if lvl is None:
            continue
        weight = 1.0
        if len(bits) > 2:
            try:
                weight = float(bits[2])
            except ValueError:
                weight = 1.0
        total += lvl * weight
    return total or None


def _apply_variants(defs: dict, variants: dict, rng: random.Random) -> dict:
    """Rewrite the lane definitions for a new pass through the script.

    Without this a pass ends by restoring the original lanes verbatim, so an
    hour of listening is the same set played over and over — the notes inside
    each lane vary, but the system never rewrites itself. Here the patch is
    re-patched between passes: a new key, a new mode for the melodic voices,
    different struck instruments, a different logic-gate mask, and fresh primes
    on the modulation. The generative machinery is unchanged; what changes is
    what it is generating *from*.
    """
    if not variants:
        return dict(defs)

    out = dict(defs)
    key = rng.choice(variants.get("key", [])) if variants.get("key") else None
    mode = rng.choice(variants.get("mode", [])) if variants.get("mode") else None

    def rewrite(body: str) -> str:
        if key:
            # scale("<root><octave>:<mode>") — move the root, keep the octave.
            body = re.sub(r'scale\("([a-g]#?)(\d):', lambda m: f'scale("{key}{m.group(2)}:', body)
            # note("c2") / choose("c2","g1",...) roots move with it.
            body = re.sub(r'(note|choose)\(("(?:[a-g]#?\d)"(?:\s*,\s*"[a-g]#?\d")*)\)',
                          lambda m: f'{m.group(1)}(' + _move_roots(m.group(2), key) + ')', body)
        if mode:
            body = re.sub(r'(scale\("[a-g]#?\d):[a-z:]+"', lambda m: f'{m.group(1)}:{mode}"', body)
        levels = {inst: lvl
                  for fam in (variants.get("swap") or {}).values()
                  if isinstance(fam, dict)
                  for inst, lvl in fam.items()}
        before_level = _lane_level(body, levels)

        for _, choices in (variants.get("swap") or {}).items():
            # Match whichever member of the family is currently in the lane, not
            # just the one named as the key: after the first swap the key token
            # is gone, so keying on it froze every lane on its second instrument
            # for the rest of the session.
            spans = _lambda_spans(body)
            present = next(
                (c for c in choices
                 if any(not any(a <= h.start() < b for a, b in spans)
                        for h in re.finditer(re.escape(c), body))),
                None)
            if not present:
                continue
            picked = rng.choice(list(choices))
            body = _replace_outside(body, present, picked)
            # A bernoulli branch that ends up on the same instrument as the lane
            # is a coin flip nobody can hear. Keep the two sides distinct.
            alts = [c for c in choices if c != picked]
            if alts:
                for a, b_ in _lambda_spans(body):
                    inner = body[a:b_]
                    if picked in inner:
                        body = (body[:a] + inner.replace(picked, rng.choice(alts))
                                + body[b_:])

        if variants.get("primes"):
            # ONLY the modulation periods. A blanket `.slow(N)` substitution
            # also rewrote the *trigger* rates — turing1 went from .slow(3) to
            # .slow(31) and the sub from .slow(2) to .slow(17), so one re-patch
            # made the rack ten times sparser and quietly undid the fix for
            # "it takes forever to get going". A slow() that belongs to a signal
            # is modulation; a slow() applied to the pattern is tempo.
            body = _MOD_SLOW.sub(
                lambda m: f"{m.group(1)}.slow({rng.choice(_PRIMES)})", body)
        if variants.get("euclids"):
            body = re.sub(r'struct\("x\(\d+,\d+\)"\)',
                          lambda m: f'struct("x{rng.choice(variants["euclids"])}")', body)

        # Compensate once, from the lane's ACTUAL level before and after — not
        # from a blend of per-family ratios. Soundfonts are nowhere near level
        # (gm_vibraphone is 5x gm_kalimba; gm_glockenspiel is 8x quieter than
        # gm_celesta), and a lane that layers two of them at different weights
        # cannot be corrected by averaging their ratios: measured that way the
        # swell still wandered 2.3x over sixty passes while single-source lanes
        # held at 1.00x. The level of the whole lane is the thing to hold.
        after_level = _lane_level(body, levels)
        if before_level and after_level and before_level != after_level:
            hits = list(re.finditer(r"\.gain\(([\d.]+)\)", body))
            if hits:
                last = hits[-1]
                scaled = min(2.0, max(0.02, round(
                    float(last.group(1)) * (before_level / after_level), 4)))
                body = body[:last.start()] + f".gain({scaled})" + body[last.end():]

        return body

    return {name: rewrite(body) for name, body in out.items()}


_PRIMES = (7, 11, 13, 17, 19, 23, 29, 31, 37, 41)

# A `.slow()` hanging off a signal (perlin, rand, a choose list) sets how fast a
# modulation drifts. A `.slow()` applied to the pattern sets how often notes
# happen. Only the first kind may be re-rolled.
_MOD_SLOW = re.compile(
    r"((?:perlin|sine|cosine|tri|saw|square|rand)(?:\.range\([^()]*\))?"
    r"|choose\([^()]*\)"
    r"|irand\(\d+\))\.slow\(\d+\)"
)

_NOTE_ORDER = ("c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b")


def _move_roots(note_list: str, key: str) -> str:
    """Transpose a list of quoted note names so the set keeps its shape."""
    notes = re.findall(r'"([a-g]#?)(\d)"', note_list)
    if not notes:
        return note_list
    try:
        base = _NOTE_ORDER.index(notes[0][0])
        shift = (_NOTE_ORDER.index(key) - base) % 12
    except ValueError:
        return note_list
    moved = []
    for name, octv in notes:
        idx = _NOTE_ORDER.index(name) + shift
        moved.append(f'"{_NOTE_ORDER[idx % 12]}{int(octv) + idx // 12}"')
    return ",".join(moved)


@dataclass
class Move:
    """One narrated edit, with how long to sit on it before the next."""
    op: str
    lane: str = ""
    arg: str = ""
    value: str = ""
    seconds: float = 20.0
    say: str = ""          # shown in the UI and written to the log


def _inject_events(base: list, pool: list, rng: random.Random) -> list:
    """Drop a few one-off events into a copy of the script.

    Re-patching between passes changes what the voices *are*; this changes what
    happens to them. Without it every pass walks the same nineteen moves in the
    same order, which after an hour is the thing you notice — the surprises are
    always in the same places. The pool is re-rolled on every wrap, so no two
    passes get the same events at the same points.
    """
    if not pool:
        return list(base)
    out = list(base)
    for _ in range(rng.randint(2, 4)):
        ev = rng.choice(pool)
        mv = Move(op=ev["op"], lane=ev.get("lane", ""), arg=ev.get("arg", ""),
                  value=str(ev.get("value", "")), say=ev.get("say", ""),
                  seconds=float(ev.get("seconds", 18)))
        # Never before the rack is up: an event that fires into silence is
        # just a move nobody hears.
        out.insert(rng.randint(3, max(4, len(out) - 1)), mv)
    return out


class Performance:
    """Applies a genre's script of moves to live lane state."""

    def __init__(self, cpm: str, lanes: dict[str, str], script: list[Move],
                 name: str = "", header: str = "",
                 variants: dict | None = None,
                 rng: random.Random | None = None,
                 events: list | None = None):
        self.cpm = cpm
        self.name = name
        self.header = header
        self._defs = dict(lanes)
        self.variants = variants or {}
        self.rng = rng or random.Random()
        self.events = events or []
        self._base_script = list(script)
        self.lanes: dict[str, Lane] = {
            n: Lane(name=n, base=b) for n, b in lanes.items()}
        self.script = script
        self._i = 0
        self._elapsed = 0.0
        self.passes = 0
        self.soloed: str | None = None
        self.last_say = ""
        if self.events:
            self.script = _inject_events(self._base_script, self.events, self.rng)
        self._apply(self.script[0]) if self.script else None

    # ── state ────────────────────────────────────────────────────────

    def _apply(self, mv: Move) -> None:
        # ADD and DROP take a comma-separated list, because no dance record
        # opens on a bare kick for twenty seconds. A narrated build is right
        # for a video where someone is talking over it; as something to listen
        # to it is a click track until the second move lands. The opening move
        # of a genre brings a whole groove up at once.
        if mv.op in (ADD, DROP):
            for name in (n.strip() for n in mv.lane.split(",")):
                if (target := self.lanes.get(name)):
                    target.live = (mv.op == ADD)
            self.last_say = mv.say
            return

        lane = self.lanes.get(mv.lane)
        if mv.op == FX and lane:
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
            # Re-patch rather than restore: a new key, mode, instruments, mask
            # and modulation primes, so the next hour is not this one again.
            self._defs = _apply_variants(self._defs, self.variants, self.rng)
            self.script = _inject_events(self._base_script, self.events, self.rng)
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
                       name=genre.get("name", ""), header=genre.get("header", ""),
                       variants=genre.get("variants"), rng=rng,
                       events=genre.get("events"))
