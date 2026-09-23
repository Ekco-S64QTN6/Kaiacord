"""Tracks: a genre as an arranged piece, played by Strudel at bar precision.

The previous model was a script of single edits a Python timer applied every
ten-odd seconds: a bare kick, then a bass twenty seconds later, then a hat. It
took minutes to become music, and every change landed wherever the timer
happened to fire rather than on a downbeat.

A track here is the other way round. Every part is present from the first
program, and carries its own arrangement over a form — intro, groove, build,
drop, breakdown, build, drop, outro — as per-bar Strudel sequences:

    $: <sound>.gain("<0.8!8 1!24 ...>").mask("<1!16 0!8 1!...>")

Strudel indexes a `<a b c>` sequence by its own cycle counter (one cycle is one
bar here), so the arrangement plays with sample accuracy: a drop lands on the
one, a snare roll accelerates bar by bar, a riser opens bar by bar. Python only
re-renders between passes (a new key, new figures) and when Kaia takes a
request, and because every sequence is rotated to an anchor on Strudel's clock
(`scheduler.now()`), a re-render mid-song keeps its place in the form.

Automation values:
    number              the same every bar of the section
    (start, end)        a ramp across the section, one step per bar
    "a b c"             listed per bar, padded with the last value
A part's `play` is a set of section names, "all", or per-section bar masks
("1110" plays three bars and rests the fourth, then stays at the last value).
"""
from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from typing import Optional, Union

from utils.audio.performance import Lane

Auto = Union[float, int, str, tuple]


@dataclass
class Part:
    name: str
    sound: Union[str, list]                  # one Strudel expression, or alternatives per pass
    play: Union[str, dict] = "all"
    auto: dict = field(default_factory=dict)  # param -> {section: Auto, "default": value}
    say: str = ""                             # what she calls it


@dataclass
class Track:
    name: str
    bpm: float
    blurb: str
    form: list                                # [(section, bars)]
    parts: list
    keys: tuple = ("a",)
    header: str = ""
    labels: dict = field(default_factory=dict)  # section -> what she says when it starts
    energy: dict = field(default_factory=dict)  # section -> whole-mix level, applied as velocity

    @property
    def bars(self) -> int:
        return sum(b for _, b in self.form)

    def seconds(self) -> float:
        return self.bars * 4 * 60.0 / self.bpm

    def section_at(self, bar: int) -> tuple[str, int, int]:
        """(section, first bar, bars) for a bar of the form."""
        at = 0
        for name, bars in self.form:
            if bar < at + bars:
                return name, at, bars
            at += bars
        name, bars = self.form[-1]
        return name, at - bars, bars


# ── per-bar arrangement ──────────────────────────────────────────────────

def _per_bar(track: Track, spec: dict, default) -> list:
    out = []
    for section, bars in track.form:
        value = spec.get(section, spec.get("default", default))
        if isinstance(value, tuple) and len(value) == 2:
            a, b = value
            steps = [a + (b - a) * (i / max(1, bars - 1)) for i in range(bars)]
        elif isinstance(value, str) and " " in value.strip():
            items = value.split()
            steps = [items[min(i, len(items) - 1)] for i in range(bars)]
        else:
            steps = [value] * bars
        out.extend(steps)
    return out


def _mask_bars(track: Track, play) -> list[int]:
    if play == "all":
        return [1] * track.bars
    if isinstance(play, str):
        on = set(play.split())
        return [1 if s in on else 0 for s, bars in track.form for _ in range(bars)]
    out = []
    for section, bars in track.form:
        v = play.get(section, 0)
        if v is True or v == 1:
            out.extend([1] * bars)
        elif isinstance(v, str) and v:
            out.extend(int(v[min(i, len(v) - 1)]) for i in range(bars))
        else:
            out.extend([0] * bars)
    return out


def _fmt(v) -> str:
    if isinstance(v, float):
        s = f"{v:.3f}".rstrip("0").rstrip(".")
        return s or "0"
    return str(v)


def sequence(values: list, anchor: int) -> str:
    """A per-bar list as a Strudel `<...>` sequence, rotated so bar 0 falls on `anchor`."""
    n = len(values)
    rotated = [values[(i - anchor) % n] for i in range(n)]
    runs, prev, count = [], None, 0
    for v in map(_fmt, rotated):
        if v == prev:
            count += 1
            continue
        if prev is not None:
            runs.append(prev if count == 1 else f"{prev}!{count}")
        prev, count = v, 1
    runs.append(prev if count == 1 else f"{prev}!{count}")
    return "<" + " ".join(runs) + ">"


def arrangement(track: Track, part: Part, anchor: int, energy: bool = True) -> tuple[str, bool]:
    """The chain a part's arrangement adds, and whether it ever plays.

    The track's energy curve rides on every part as `velocity`, which Strudel
    multiplies into gain: the kick and bass carry the loudness of every
    section, so parts entering alone barely lift a drop over the groove.
    """
    bars = _mask_bars(track, part.play)
    if not any(bars):
        return "", False
    chain = ""
    auto = dict(part.auto)
    if energy and track.energy and "velocity" not in auto:
        auto["velocity"] = {"default": 1, **track.energy}
    for param, spec in auto.items():
        values = _per_bar(track, spec, spec.get("default", 1))
        if len(set(map(_fmt, values))) == 1:
            chain += f".{param}({_fmt(values[0])})"
        else:
            chain += f'.{param}("{sequence(values, anchor)}")'
    if not all(bars):
        chain += f'.mask("{sequence(bars, anchor)}")'
    return chain, True


# ── performance ──────────────────────────────────────────────────────────

_KEY_ORDER = ("c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b")

# ── the mix ──────────────────────────────────────────────────────────────
#
# Target loudness per role, in dB relative to a kick at 0.30 RMS. Written
# gains cannot be trusted across sample banks and synths: a 909 kick at gain
# 1.0 measured 28 dB above 909 hats at 0.32, which buries everything but the
# kick. `audition_tracks.py --calibrate` solos each part in Strudel, measures
# it, and writes the correction to levels.json; the engine applies it as
# postgain, so a DJ request that changes `gain` does not undo the balance.

REFERENCE_RMS = 0.30
ROLE_DB = {
    "kick": 0, "kit": -1, "break": -5, "bass": -7, "sub": -6, "reese": -8, "rumble": -8,
    "acid": -9, "lead": -10, "gate": -9, "stab": -12, "hoover": -10, "piano": -10, "keys": -11,
    "pad": -14, "strings": -13, "choir": -14, "halo": -14, "drone": -9, "seq": -8, "seq2": -12,
    "pulse": -10, "hats": -17, "ohat": -16, "shaker": -19, "rim": -16, "perc": -16, "clap": -11,
    "snare": -9, "ride": -20, "roll": -12, "riser": -14, "crash": -14, "arp": -14, "zaps": -13,
    "pluck": -14, "bells": -15, "top": -15, "fx": -16, "crackle": -26, "wind": -22, "glass": -15,
    "chimes": -17, "melody": -12, "melodica": -12, "skank": -12, "siren": -16, "space": -15,
}
LEVELS_PATH = __import__("pathlib").Path(__file__).with_name("levels.json")


def load_levels() -> dict:
    try:
        import json
        return json.loads(LEVELS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class TrackPerformance:
    """A track playing: its lanes, its place in the form, and its passes.

    Offers what the session and the DJ use: `lanes` (name -> Lane with `live`
    and `set_param`), `cpm`, `soloed`, `code()`, `describe()`.
    """

    def __init__(self, track: Track, rng: Optional[random.Random] = None, anchor: int = 0):
        self.track = track
        self.name = track.name
        self.rng = rng or random.Random()
        self.cpm = f"{_fmt(float(track.bpm))}/4"
        self.anchor = anchor
        self.passes = 0
        self.soloed: Optional[str] = None
        self.key = ""
        self.lanes: dict[str, Lane] = {}
        self._arr: dict[str, str] = {}
        self._cycle = float(anchor)
        self.last_say = ""
        self._levels = load_levels().get(track.name, {})
        self.energy = True                       # False while calibrating: levels are set flat
        self._repatch()

    # ── content ──────────────────────────────────────────────────────

    def _repatch(self) -> None:
        """Choose this pass's key and figures, and reset the lanes."""
        keys = self.track.keys or ("a",)
        choices = [k for k in keys if k != self.key] or list(keys)
        self.key = self.rng.choice(choices)
        self.lanes, self._arr, self._masks = {}, {}, {}
        for part in self.track.parts:
            sound = part.sound if isinstance(part.sound, str) else self.rng.choice(part.sound)
            sound = sound.replace("@KEY@", self.key)
            chain, plays = arrangement(self.track, part, self.anchor, self.energy)
            if not plays:
                continue
            self.lanes[part.name] = Lane(name=part.name, base=sound, live=True)
            level = self._levels.get(part.name)
            if level and abs(level - 1.0) > 0.01:
                chain = f".postgain({_fmt(round(level, 3))})" + chain
            self._arr[part.name] = chain
            self._masks[part.name] = _mask_bars(self.track, part.play)
        self.soloed = None

    def reanchor(self, anchor: int) -> None:
        """Move bar 0 of the form to Strudel cycle `anchor`, changing nothing else."""
        self.anchor = anchor
        for part in self.track.parts:
            if part.name in self._arr:
                chain = arrangement(self.track, part, anchor, self.energy)[0]
                level = self._levels.get(part.name)
                if level and abs(level - 1.0) > 0.01:
                    chain = f".postgain({_fmt(round(level, 3))})" + chain
                self._arr[part.name] = chain

    def code(self) -> str:
        out = []
        if self.track.header:
            out.append(self.track.header)
        out.append(f"setcpm({self.cpm})")
        for name, lane in self.lanes.items():
            if not lane.live:
                continue
            muted = self.soloed is not None and name != self.soloed
            body = lane.base + self._arr.get(name, "") + "".join(lane.chain)
            out.append(("_$: " if muted else "$: ") + body)
        return "\n".join(out)

    # ── clock ────────────────────────────────────────────────────────

    def position(self, cycle: float) -> tuple[int, int, float]:
        """(pass, bar in form, fraction of the bar) for a Strudel cycle."""
        rel = max(0.0, cycle - self.anchor)
        whole = int(math.floor(rel))
        return whole // self.track.bars, whole % self.track.bars, rel - whole

    def update(self, cycle: float) -> dict:
        """Where the set is. `new_pass` is True once, when a pass boundary is crossed."""
        self._cycle = cycle
        p, bar, _ = self.position(cycle)
        section, first, bars = self.track.section_at(bar)
        new_pass = p > self.passes
        if new_pass:
            self.passes = p
        return {"pass": p, "bar": bar, "section": section, "new_pass": new_pass,
                "section_bar": bar - first, "section_bars": bars}

    def cycles_to_next_pass(self, cycle: float) -> float:
        rel = max(0.0, cycle - self.anchor)
        return self.track.bars - (rel % self.track.bars)

    def next_pass(self) -> None:
        """Re-patch for the coming pass. Push the code during its last bar."""
        self._repatch()

    def label(self, section: str) -> str:
        return self.track.labels.get(section, section.replace("_", " "))

    def describe(self) -> dict:
        p, bar, frac = self.position(self._cycle)
        section, first, bars = self.track.section_at(bar)
        names = [s for s, _ in self.track.form]
        bar_s = 4 * 60.0 / self.track.bpm
        return {
            "section": self.label(section),
            "section_index": names.index(section) + 1,
            "sections_total": len(names),
            "lanes": [n for n, l in self.lanes.items()
                      if l.live and self._masks.get(n, [1] * self.track.bars)[bar]],
            "soloed": self.soloed,
            "remaining_s": round(max(0.0, (first + bars - bar - frac) * bar_s), 1),
            "passes": self.passes,
            "key": self.key,
        }


def transpose_ok(key: str) -> bool:
    return key in _KEY_ORDER


def parts_named(track: Track) -> list[str]:
    return [p.name for p in track.parts]


def check(track: Track) -> list[str]:
    """Problems a track definition has before it is ever played."""
    problems = []
    names = {s for s, _ in track.form}
    for part in track.parts:
        spec_sections = set()
        if isinstance(part.play, dict):
            spec_sections |= set(part.play)
        elif part.play != "all":
            spec_sections |= set(part.play.split())
        for param, spec in part.auto.items():
            spec_sections |= {k for k in spec if k != "default"}
        for s in spec_sections - names:
            problems.append(f"{track.name}.{part.name}: unknown section '{s}'")
        for sound in ([part.sound] if isinstance(part.sound, str) else part.sound):
            if sound.count("(") != sound.count(")"):
                problems.append(f"{track.name}.{part.name}: unbalanced brackets")
            if re.search(r"setcpm|setcps", sound):
                problems.append(f"{track.name}.{part.name}: sets its own tempo")
            # An event longer than a bar is locked to Strudel's absolute bar
            # count, not to the form: when it starts in a bar the arrangement
            # masks, it never sounds at all. That silenced every slowed pad.
            if re.search(r">/\d", sound) or re.search(r"(?<![a-z)])\)\.slow\(\d", sound) and not re.search(
                    r"(?:perlin|sine|cosine|tri|saw|square|rand)(?:\.range\([^()]*\))?\.slow\(", sound):
                problems.append(f"{track.name}.{part.name}: an event longer than a bar")
    for k in track.keys:
        if not transpose_ok(k):
            problems.append(f"{track.name}: key '{k}' is not a note name")
    return problems
