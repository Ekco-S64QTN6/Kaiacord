"""Compaction for log payloads.

Measured on a 30,498-line production log: **6,080 lines (19.9%) carried no
timestamp** — they were continuation lines of multi-line payloads dumped into
the log by a single call. Kaia's constitution appeared 771 times in full, the
persona 390 times, and `Pre-chunking large document (N chars)` 1,056 times.

The compaction lives here, applied once in `UnifiedLogger.log()`, rather than
at each call site: there were six sites producing the bulk of it and nothing
stopping a seventh being added.

Two things are deliberately never touched:
  * exception tracebacks — their line structure *is* the information;
  * anything short and single-line — the overwhelming majority of entries.
"""
from __future__ import annotations

import re

# A payload longer than this is summarised rather than printed.
MAX_LINE_CHARS = 400
# Multi-line payloads keep this many characters of their first line.
FIRST_LINE_CHARS = 160
# URLs longer than this have their query string collapsed.
MAX_URL_CHARS = 120

_TRACEBACK_MARKERS = (
    "Traceback (most recent call last)",
    '\n  File "',
)

# Discord CDN links carry ?ex=&is=&hm= signing tokens that are longer than the
# path and never useful in a log.
_URL = re.compile(r'(https?://[^\s<>"\']+)')

_WHITESPACE_RUN = re.compile(r'[ \t]{3,}')


def is_traceback(message: str) -> bool:
    """True if the message is (or contains) a Python traceback."""
    return any(marker in message for marker in _TRACEBACK_MARKERS)


def shorten_urls(message: str, max_url: int = MAX_URL_CHARS) -> str:
    """Collapse the query string of over-long URLs.

    Discord attachment URLs are ~90 characters of path followed by ~150 of
    signing token; the token is noise in a log and changes every request, so it
    also defeats duplicate detection.
    """
    def _repl(match):
        url = match.group(1)
        if len(url) <= max_url:
            return url
        head, sep, query = url.partition("?")
        if sep and len(head) <= max_url:
            return f"{head}?…({len(query)} chars)"
        return f"{url[:max_url]}…({len(url)} chars)"

    return _URL.sub(_repl, message)


def compact(message: str,
            max_chars: int = MAX_LINE_CHARS,
            first_line_chars: int = FIRST_LINE_CHARS) -> str:
    """Reduce a log payload to a single informative line.

    Returns the message unchanged when it is already short and single-line,
    which is the common case and must stay allocation-cheap.
    """
    if not message:
        return message

    # Tracebacks pass through untouched: collapsing one destroys the only
    # thing that makes it useful.
    if is_traceback(message):
        return message

    has_newline = "\n" in message
    if not has_newline and len(message) <= max_chars:
        # Still worth shortening a lone giant URL on an otherwise short line.
        return shorten_urls(message)

    message = shorten_urls(message)

    if has_newline:
        lines = message.splitlines()
        head = lines[0].strip()
        # A leading blank or decorative line ("---", "# title") is not a useful
        # summary on its own; take the first line with substance.
        for candidate in lines:
            stripped = candidate.strip()
            if stripped and not set(stripped) <= set("-=_*# "):
                head = stripped
                break
        remaining = len(lines) - 1
        body_chars = len(message)
        head = _WHITESPACE_RUN.sub("  ", head)
        if len(head) > first_line_chars:
            head = head[:first_line_chars].rstrip() + "…"
        return f"{head} … [+{remaining} lines, {body_chars} chars]"

    return message[:max_chars].rstrip() + f"… [{len(message)} chars]"


def summarize_payload(label: str, payload: str) -> str:
    """Build the canonical one-line form for an intentional payload injection.

    Use at call sites that would otherwise interpolate a whole document:
    `log_debug(summarize_payload("constitution", text))` →
    `constitution: 4,012 chars, 96 lines`.
    """
    text = payload or ""
    return f"{label}: {len(text):,} chars, {text.count(chr(10)) + 1} lines"


class RepeatAggregator:
    """Collapse runs of the same message into one line plus a count.

    `Pre-chunking large document (5231 chars)...` appeared 1,056 times in one
    log. The existing duplicate check hashes the exact string, so a varying
    number defeats it; this normalises digits before comparing.

    Not a rate limiter: the first occurrence always passes through immediately,
    and the tally is emitted when the run ends, so nothing is silently lost.
    """

    _DIGITS = re.compile(r"\d+")

    def __init__(self, min_run: int = 3):
        self.min_run = min_run
        self._key = None
        self._count = 0

    @classmethod
    def _normalize(cls, message: str) -> str:
        return cls._DIGITS.sub("#", message.strip())[:200]

    def feed(self, message: str):
        """Return (emit, suffix_line).

        `emit` is False while a run is being swallowed. `suffix_line` is a
        summary to log first when a run has just ended, else None.
        """
        key = self._normalize(message)
        if key == self._key:
            self._count += 1
            return (self._count < self.min_run), None

        finished = None
        if self._key is not None and self._count >= self.min_run:
            # Report what was SUPPRESSED, not the total: the first
            # (min_run - 1) occurrences were already printed, so a total would
            # double-count them.
            finished = (f"… {self._count - (self.min_run - 1)} more like the "
                        f"previous message (suppressed)")
        self._key, self._count = key, 1
        return True, finished

    def flush(self):
        """Emit any pending tally (call before shutdown)."""
        if self._key is not None and self._count >= self.min_run:
            out = (f"… {self._count - (self.min_run - 1)} more like the "
                   f"previous message (suppressed)")
            self._key, self._count = None, 0
            return out
        return None
