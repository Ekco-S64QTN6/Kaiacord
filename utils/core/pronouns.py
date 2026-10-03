"""How Kaia refers to the people she talks about.

The model guesses a pronoun from a name when it is told nothing, and guessed
wrong: the inner monologue called Starkind "he" in five thoughts over ten days.
`people.pronouns` (kaia.yaml) lists the ones people have said, by the name
they go by here; anyone not listed is "they", by name where she can. One line,
built here, goes into every prompt that has her speak about someone.
"""
from __future__ import annotations

from typing import Iterable, Optional


def known() -> dict:
    """{lowercase name: pronouns} from `people.pronouns`."""
    try:
        from utils.infrastructure.system.yaml_config import config
        raw = config.get("people.pronouns", {}) or {}
    except Exception:
        raw = {}
    return {str(k).strip().lower(): str(v).strip() for k, v in dict(raw).items() if str(v).strip()}


def of(name: str) -> Optional[str]:
    if not name:
        return None
    table = known()
    key = name.strip().lower()
    return table.get(key) or table.get(key.split()[0] if key.split() else key)


def line(names: Optional[Iterable[str]] = None) -> str:
    """The instruction: the listed people's pronouns (those named, or all of
    them), and "they" for everyone else."""
    table = known()
    wanted = {n.strip().lower() for n in names or [] if n and n.strip()}
    rows = [(k, v) for k, v in table.items() if not wanted or k in wanted or k.split()[0] in {w.split()[0] for w in wanted}]
    listed = "; ".join(f"{k} — {v}" for k, v in rows)
    return ((f"People's pronouns: {listed}. " if listed else "")
            + "Anyone else: they/them, never a guess from their name — or just use their name.")
