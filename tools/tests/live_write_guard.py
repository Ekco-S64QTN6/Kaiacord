"""Fails the run if a test writes to the bot's live data.

The bot may be running while the suite does. Every write under memory/,
knowledge_base/ or logs/ has to go to a path with ".test" in it
(`telemetry_paths`); bot_state.json, the RAG manifest and the TTRPG world state
each went unredirected for months, found one at a time by the damage. An audit
hook sees all of it, whichever module does the writing. Creating a directory is
not counted: `mkdir(exist_ok=True)` changes nothing that exists.

A path is judged by where it leads, not how it is spelled: symlinks are
resolved, so a write through an alias of the checkout is still a write to it.
A hard link has no path to resolve, so making one to live data is itself the
offence.
"""
from __future__ import annotations

import os
import sys
import threading

LIVE = ("memory" + os.sep, "knowledge_base" + os.sep, "logs" + os.sep)
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND

current_test = "<collection>"
offences: dict = {}
_lock = threading.Lock()
_root = os.getcwd() + os.sep


def live_path(path) -> str:
    """`path` relative to the repo if it is live data, else ""."""
    try:
        name = os.fsdecode(path)
    except TypeError:
        return ""
    root = os.path.realpath(_root) + os.sep
    full = os.path.realpath(name)
    if not full.startswith(root):
        return ""
    rel = full[len(root):]
    if not rel.startswith(LIVE) or any(".test" in part for part in rel.split(os.sep)):
        return ""
    return rel


def is_write(mode, flags) -> bool:
    if isinstance(mode, str) and any(c in mode for c in "wax+"):
        return True
    return isinstance(flags, int) and bool(flags & _WRITE_FLAGS)


def _note(path) -> None:
    rel = live_path(path)
    if rel:
        with _lock:
            offences.setdefault(rel, current_test)


def _hook(event, args) -> None:
    try:
        if event == "open":
            path, mode, flags = args
            if path is not None and not isinstance(path, int) and is_write(mode, flags):
                _note(path)
        elif event in ("os.remove", "shutil.rmtree"):
            _note(args[0])
        elif event in ("os.rename", "os.link"):
            _note(args[0])
            _note(args[1])
        elif event == "os.symlink":
            _note(args[1])
    except Exception:
        pass


def install() -> None:
    sys.addaudithook(_hook)
