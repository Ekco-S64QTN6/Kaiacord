"""Her own commands, when someone asks about them.

Asked about `!help` she called it "an internal diagnostic tool… a vulnerability":
nothing in her prompt says what her commands are, so she made something up. A turn
that names a `!` command or asks what her commands are carries the registry's own
lines for them, and nothing else does; the registry is what `!help` renders from.
"""
from __future__ import annotations

import re

_ASKS = re.compile(r"\b(?:what|which|list|show|tell\s+me)\b[^.!?\n]{0,30}\bcommands?\b"
                   r"|\byour\s+commands?\b|\bwhat\s+can\s+you\s+do\b", re.IGNORECASE)
_NAMED = re.compile(r"(?<![\w!])!([a-z][a-z0-9_]*)\b", re.IGNORECASE)


def _line(cmd) -> str:
    return f"{cmd.usage}: {cmd.summary}" + (" (owner only)" if cmd.owner_only else "")


def note_for(own_words: str) -> str:
    text = own_words or ""
    if text.lstrip().startswith("!"):
        return ""                                # a command being run, not one being talked about
    asked = bool(_ASKS.search(text))
    named = {n.lower() for n in _NAMED.findall(text)}
    if not asked and not named:
        return ""
    from utils.commands.registry import COMMANDS
    wanted = [c for c in COMMANDS if named & {i.lower() for i in c.invocations}]
    # `!help` is the list of everything, so asking about it is asking for the list.
    if asked or any(c.name == "help" for c in wanted):
        wanted += [c for c in COMMANDS if not c.owner_only and c not in wanted]
    if not wanted:
        return ""
    lines = "\n".join(f"- {_line(c)}" for c in wanted)
    return ("YOUR COMMANDS — real `!` commands people type in this server, each answered in its own box. "
            "They are ordinary features, not internal tools. Say only what is listed here:\n" + lines)
