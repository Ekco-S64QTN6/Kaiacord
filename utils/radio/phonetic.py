"""Turn a transcript of an EAM broadcast into callsign, preamble and message.

An EAM is read in the NATO phonetic alphabet, with structure that makes a
noisy transcript recoverable:

    "<preamble> standby" ×2–3 · "message follows" · <message> ·
    "I say again" · <message> · "this is <callsign>, out"

- Every character is one of 36 spoken words, so a word maps to a character
  by (fuzzy) lookup rather than by trusting the recogniser's spelling.
- The alphabet is base32 (A–Z, 2–7): a 0, 1, 8 or 9 is a recognition error.
- The preamble is read several times and the message twice; readings are
  merged, and a position the readings disagree on becomes `?` rather than a
  guess. A `?` is honest; a wrong letter shown with confidence is not.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Optional

LETTERS = {
    "alpha": "A", "alfa": "A", "bravo": "B", "charlie": "C", "delta": "D", "echo": "E",
    "foxtrot": "F", "golf": "G", "hotel": "H", "india": "I", "juliet": "J", "juliett": "J",
    "kilo": "K", "lima": "L", "mike": "M", "november": "N", "oscar": "O", "papa": "P",
    "quebec": "Q", "romeo": "R", "sierra": "S", "tango": "T", "uniform": "U", "victor": "V",
    "whiskey": "W", "whisky": "W", "xray": "X", "yankee": "Y", "zulu": "Z",
}
DIGITS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
          "six": "6", "seven": "7", "eight": "8", "nine": "9", "niner": "9", "fife": "5", "tree": "3"}
WORDS = {**LETTERS, **DIGITS}
EAM_ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
FUZZY_CUTOFF = 0.72

#: Words that are structure, not content.
_MARKERS = {"standby", "stand", "by", "message", "follows", "follow", "break", "i", "say",
            "again", "this", "is", "out", "all", "stations", "skyking", "do", "not", "answer"}


def _normalise(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower().replace("x-ray", "xray"))


def symbol(word: str) -> Optional[str]:
    """The character a spoken word stands for, or None."""
    w = _normalise(word)
    if not w:
        return None
    if w in WORDS:
        return WORDS[w]
    if w.isdigit():                      # "25" written for "two five"
        return w
    # Fuzzy matching needs four letters: "aha" scores 0.75 against "alpha".
    if w in _MARKERS or len(w) < 4:
        return None
    hit = difflib.get_close_matches(w, WORDS.keys(), n=1, cutoff=FUZZY_CUTOFF)
    return WORDS[hit[0]] if hit else None


def tokens(transcript: str) -> list[str]:
    return [t for t in re.split(r"[\s,.;:!?]+", transcript.replace("x-ray", "xray").replace("X-ray", "xray")) if t]


#: How many unrecognised words a run of characters may bridge.
MAX_BRIDGE = 2


def _runs(toks: list[str]) -> list[tuple[int, str]]:
    """(index, symbols) for each run of consecutive symbol words. Up to
    MAX_BRIDGE unknown words between two symbols are kept as '?' each: they
    were probably characters the recogniser misheard."""
    runs, cur, start = [], [], None
    syms = [symbol(t) for t in toks]
    markers = [_normalise(t) in _MARKERS for t in toks]
    i = 0
    while i < len(toks):
        if syms[i] is not None:
            if start is None:
                start = i
            cur.append(syms[i])
            i += 1
            continue
        if cur:
            gap = 0
            # Only real words: "a.m." or "uh" is noise between readings, not a character.
            while (i + gap < len(toks) and gap < MAX_BRIDGE and syms[i + gap] is None
                   and not markers[i + gap] and len(_normalise(toks[i + gap])) >= 3):
                gap += 1
            if gap and i + gap < len(toks) and syms[i + gap] is not None:
                cur.extend("?" * gap)
                i += gap
                continue
            runs.append((start, "".join(cur)))
            cur, start = [], None
        i += 1
    if cur:
        runs.append((start, "".join(cur)))
    return runs


def merge(a: str, b: str) -> str:
    """Merge two readings of the same text. Agreement is kept; disagreement is '?';
    a character only one reading has is kept (the other dropped it)."""
    if not a:
        return b
    if not b:
        return a
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(a[i1:i2])
        elif op == "replace":
            sa, sb = a[i1:i2], b[j1:j2]
            if len(sa) == len(sb):
                out.append("".join(x if x == y or y == "?" else (y if x == "?" else "?") for x, y in zip(sa, sb)))
            elif set(sa) == {"?"} or set(sb) == {"?"}:
                out.append(sb if set(sa) == {"?"} else sa)      # a heard span beats a blank one
            else:
                out.append(max(sa, sb, key=len))
        elif op == "delete":
            out.append(a[i1:i2])
        elif op == "insert":
            out.append(b[j1:j2])
    return "".join(out)


def _vote(readings: Iterable[str], length: int) -> str:
    rs = [r for r in readings if len(r) == length]
    if not rs:
        return ""
    return "".join(Counter(col).most_common(1)[0][0] for col in zip(*rs))


def _split_repeats(run: str, preambles: list[str]) -> list[str]:
    """A run that holds both readings back to back (nothing separated them in
    the transcript) is split where the message starts again."""
    if len(run) < 40:
        return [run]
    heads = {p[:4] for p in preambles if len(p) >= 4} or {run[:4]}
    for head in heads:
        best = None
        for k in range(20, len(run) - 3):
            if difflib.SequenceMatcher(None, run[k:k + 4], head).ratio() >= 0.75:
                best = k
                break
        if best:
            return [run[:best].rstrip("?"), run[best:]]
    return [run]


def _repair_head(preamble: str, message: str) -> str:
    """The message opens with the preamble, which was read several more times:
    let the preamble's reading replace however the message's first characters
    came out, including a character the message reading dropped."""
    window = message[:len(preamble) + 2]
    matcher = difflib.SequenceMatcher(None, preamble, window, autojunk=False)
    blocks = [b for b in matcher.get_matching_blocks() if b.size]
    if not blocks or sum(b.size for b in blocks) < len(preamble) - 2:
        return message            # the message does not open with this preamble
    last = blocks[-1]
    end_in_message = last.b + last.size + (len(preamble) - (last.a + last.size))
    return preamble + message[end_in_message:]


def _clean(text: str) -> str:
    return "".join(c if c in EAM_ALPHABET else "?" for c in text)


@dataclass
class ParsedEAM:
    callsign: str = ""
    preamble: str = ""
    message: str = ""
    readings: list = field(default_factory=list)

    @property
    def uncertain(self) -> int:
        return self.message.count("?")

    @property
    def usable(self) -> bool:
        return len(self.message) >= 20 and self.uncertain <= len(self.message) // 4


def _callsign(toks: list[str], known: Iterable[str]) -> str:
    known = [k.upper() for k in known]
    candidates = []
    for i in range(len(toks) - 2):
        if _normalise(toks[i]) == "this" and _normalise(toks[i + 1]) == "is":
            words = [t for t in toks[i + 2:i + 4] if _normalise(t) not in _MARKERS and symbol(t) is None]
            if words:
                joined = " ".join(words).upper()
                # Stations say their name twice: "this is Implicate, Implicate".
                if len(words) == 2 and _normalise(words[0]) == _normalise(words[1]):
                    joined = words[0].upper()
                candidates.append(joined)
                candidates.append(words[0].upper())
    for c in candidates:
        squashed = c.replace(" ", "")
        for k in known:
            if difflib.SequenceMatcher(None, squashed, k.replace(" ", "")).ratio() >= 0.75:
                return k
    return candidates[0] if candidates else ""


def parse(transcript: str, known_callsigns: Iterable[str] = ()) -> ParsedEAM:
    toks = tokens(transcript)
    norm = [_normalise(t) for t in toks]
    runs = _runs(toks)

    def after(i: int) -> list[str]:
        return [r for start, r in runs if start >= i]

    # Preambles: runs of about six right before "stand by" / "standby".
    preambles = []
    for start, r in runs:
        end = start + len(r)
        following = norm[end:end + 2]
        if following[:1] == ["standby"] or following == ["stand", "by"]:
            preambles.append(r[-6:])
    # Message readings: the first run after "message follows" and after "say again".
    # Every long run after "message follows" is a reading: the marker before
    # the second one ("I say again") is often the part the recogniser loses.
    readings = []
    for i in range(len(norm) - 1):
        if (norm[i], norm[i + 1]) in (("message", "follows"), ("message", "follow")):
            readings = [r for r in after(i + 2) if len(r) >= 20]
            break
    if not readings:
        longest = max((r for _, r in runs), key=len, default="")
        readings = [longest] if len(longest) >= 12 else []

    readings = [part for r in readings for part in _split_repeats(r, preambles)]
    message = ""
    for r in readings:
        message = merge(message, r)
    preamble = _vote(preambles, 6) or (message[:6] if len(message) >= 6 else "")
    if preamble and message and not message.startswith(preamble):
        message = _repair_head(preamble, message)
    return ParsedEAM(callsign=_callsign(toks, known_callsigns), preamble=_clean(preamble),
                     message=_clean(message), readings=readings)


def accuracy(ours: str, truth: str) -> float:
    """Share of the logged message's characters we got right, in place."""
    if not truth:
        return 0.0
    matcher = difflib.SequenceMatcher(None, ours, truth, autojunk=False)
    return sum(b.size for b in matcher.get_matching_blocks()) / len(truth)
