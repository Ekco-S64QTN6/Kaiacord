"""Whether the turn being generated is private (a DM or an invitation-only thread).

A private turn's text must not land in the diagnostic logs under memory/ that
other tooling reads and replays (the dogtag replay file, the hallucination log).
The turn's task sets this before generation; a worker thread started with
asyncio.to_thread inherits it, so the loggers deep in the safety pipeline can
ask without every call site passing a flag.
"""
from __future__ import annotations

from contextvars import ContextVar, Token

_private: ContextVar[bool] = ContextVar("kaia_private_turn", default=False)

WITHHELD = "[private turn: text withheld]"


def enter(is_private: bool) -> Token:
    return _private.set(bool(is_private))


def leave(token: Token) -> None:
    _private.reset(token)


def active() -> bool:
    return _private.get()


def text(value: str) -> str:
    """`value`, or a marker in its place while a private turn is being handled."""
    return WITHHELD if (value and _private.get()) else value
