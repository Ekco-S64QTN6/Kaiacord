"""Keep code she writes out of the prose filters.

The post-generation pipeline is built for prose: it strips ``` fences (gemma
sometimes wraps a whole reply in one), lowercases, collapses whitespace and
drops sentences by pattern. Run over code, that flattens indentation and
deletes lines. `stash` swaps each fenced block whose body looks like code for
a one-word placeholder paragraph before the filters run, and `restore` puts
the block back afterwards, byte for byte. A fence around prose is left in
place for the filters to strip, as before.
"""
import re
from typing import List, Tuple

_FENCE = re.compile(r"```([\w+#.-]*)[ \t]*\n(.*?)\n?```", re.S)
_PLACEHOLDER = "kaiacodeblock{}"
_FOUND = re.compile(r"kaiacodeblock(\d+)")

# A line reads as code if it is indented, carries code punctuation, calls
# something, or opens with a keyword prose doesn't start a line with.
_CODE_LINE = re.compile(
    r"^(?:[ \t]{2,}\S"
    r"|.*[;{}=<>\[\]]"
    r"|.*\w\(.*\)"
    r"|\s*(?:def|class|import|from|return|function|const|let|var|#include|SELECT|sudo|pip|apt|git|cd|ls)\b"
    r"|\s*[$#>] )")


def looks_like_code(body: str) -> bool:
    """At least half of the block's non-blank lines read as code."""
    lines = [l for l in body.splitlines() if l.strip()]
    return bool(lines) and sum(bool(_CODE_LINE.match(l)) for l in lines) * 2 >= len(lines)


def stash(text: str) -> Tuple[str, List[str]]:
    """(text with code blocks replaced by placeholders, the blocks)."""
    blocks: List[str] = []

    def _swap(m):
        if not looks_like_code(m.group(2)):
            return m.group(0)
        blocks.append(m.group(0))
        return f"\n\n{_PLACEHOLDER.format(len(blocks) - 1)}\n\n"

    return (_FENCE.sub(_swap, text) if "```" in text else text), blocks


def restore(text: str, blocks: List[str]) -> str:
    """Put the blocks back. One whose placeholder a filter removed goes at the end."""
    if not blocks:
        return text
    placed = set()

    def _back(m):
        i = int(m.group(1))
        if i >= len(blocks):
            return m.group(0)
        placed.add(i)
        return blocks[i]

    text = _FOUND.sub(_back, text)
    missing = [b for i, b in enumerate(blocks) if i not in placed]
    return "\n\n".join([text.strip(), *missing]).strip() if missing else text.strip()
