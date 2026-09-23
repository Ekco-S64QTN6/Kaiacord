"""A lane: one `$:` line of a Strudel program, and the edits made to it.

Each part of a track (`tracks.py`) is played as a lane. The track engine owns
the arrangement; a lane carries the part's sound plus whatever has been chained
onto it since — which is how Kaia's requests (`dj.py`) change a playing part:
`set_param` rewrites one call's argument in place, `add_fx` appends an effect.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


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
