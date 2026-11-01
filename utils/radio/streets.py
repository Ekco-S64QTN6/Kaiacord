"""Street names in dispatch transcripts, put right against a local street list.

Whisper hears dispatch English well and local names badly: "South Cockroach
Hill Road" for Cockrell Hill, "Medfetter Drive", "Ocean Union". A street the
list does not hold, followed by its type (Road, Drive…), is replaced by the
one street of that type it sounds like — the same consonant-skeleton test
`!youtube`'s name corrector uses. Precision over recall: a name the list
already holds, under any type, is never touched; nor is a lowercase or
comma-broken span, nor a near-tie between two candidates.

The list is a deployment fact and lives in git-ignored memory/radio/
streets.json, built by tools/maintenance/fetch_street_names.py from
OpenStreetMap. Without it nothing is corrected.
"""
from __future__ import annotations

import json
import re
import threading
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

#: A street's type as spoken → as listed. Only types a dispatcher says after a name.
TYPES = {"street": "street", "avenue": "avenue", "road": "road", "drive": "drive", "lane": "lane",
         "boulevard": "boulevard", "way": "way", "trail": "trail", "court": "court", "place": "place",
         "circle": "circle", "parkway": "parkway", "freeway": "freeway", "expressway": "expressway",
         "highway": "highway", "terrace": "terrace", "plaza": "plaza", "crossing": "crossing",
         "loop": "loop", "row": "row", "cove": "cove", "path": "path", "run": "run", "pass": "pass",
         "walk": "walk", "square": "square", "turnpike": "turnpike", "ave": "avenue", "st": "street",
         "rd": "road", "dr": "drive", "ln": "lane", "blvd": "boulevard"}
DIRECTIONS = {"north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest",
              "n", "s", "e", "w", "ne", "nw", "se", "sw"}
MAX_NAME_WORDS = 3
MIN_SOUND = 0.8                  # consonant skeletons at least this close
MIN_SPELLED = 0.7                # and the spellings
MIN_SCORE = 0.79                 # their mean; with the same syllable count it kept "Cockroach Hill" →
                                 # Cockrell Hill and turned away "Condo" → Coronado, "Levar" → Lear
MIN_LETTERS = 5                  # shorter names match too much by chance
SPELLED_ANY_START = 0.85         # spelled this close, the first sound may differ ("Rockmorton")
MIN_MARGIN = 0.08                # the best candidate must beat the next by this much

_lock = threading.Lock()
_cache: dict = {}


def path() -> Path:
    return Path(telemetry_path("memory/radio/streets.json"))


def split_name(name: str) -> Optional[tuple[str, str]]:
    """'South Cockrell Hill Road' → ('cockrell hill', 'road'); None if it has no type."""
    words = re.sub(r"[^\w' -]", " ", name).lower().split()
    while words and words[0] in DIRECTIONS:
        words = words[1:]
    if len(words) < 2 or words[-1] not in TYPES:
        return None
    return " ".join(words[:-1]), TYPES[words[-1]]


def build(names: list[str]) -> dict:
    """The stored shape: every street's name and the types it is listed with."""
    by_name: dict = {}
    for n in names:
        s = split_name(n)
        if s:
            by_name.setdefault(s[0], set()).add(s[1])
    return {"names": {k: sorted(v) for k, v in sorted(by_name.items())}}


def _index() -> Optional[dict]:
    p = path()
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    with _lock:
        if _cache.get("mtime") != mtime:
            names = json.loads(p.read_text(encoding="utf-8")).get("names", {})
            by_type: dict = {}
            for n, types in names.items():
                for t in types:
                    by_type.setdefault(t, []).append((n, sound_key(n)))
            _cache.update(mtime=mtime, names=names, by_type=by_type)
        return _cache


_SOUND = str.maketrans({"c": "k", "q": "k", "g": "k", "z": "s", "v": "f", "d": "t", "b": "p", "j": "k"})


def sound_key(text: str) -> str:
    """Consonant skeleton: classes speech recognition confuses merged, vowels
    after the first letter dropped, repeats collapsed."""
    letters = re.sub(r"[^a-z]", "", text.lower().replace("ph", "f").replace("x", "ks").replace("ck", "k"))
    if not letters:
        return ""
    body = letters[0] + re.sub(r"[aeiouyhw]", "", letters[1:])
    return re.sub(r"(.)\1+", r"\1", body.translate(_SOUND))


_ENGLISH: Optional[set] = None


def is_english_word(word: str) -> bool:
    """True when `word` is ordinary English — never replaced: "Avenue" became
    "Avon", "First" "Vista", "Upholstery" "Foster". Without a word list
    (nltk's) every word counts as English, so only phrases are corrected."""
    global _ENGLISH
    if _ENGLISH is None:
        try:
            from nltk.corpus import words
            _ENGLISH = {w.lower() for w in words.words()}
        except Exception:
            _ENGLISH = set()
    w = word.lower().strip("'.-")
    return not _ENGLISH or any(c in _ENGLISH for c in {w, w[:-1] if w.endswith("s") else w})


def _ordinary(heard: str) -> bool:
    words = heard.split()
    return (any(w in TYPES or w in DIRECTIONS for w in words)
            or (len(words) == 1 and is_english_word(words[0])))


def syllables(text: str) -> int:
    """Vowel groups — near enough: a mishearing keeps the beat of the word."""
    return len(re.findall(r"[aeiouy]+", text.lower()))


def _best(heard: str, kind: str, idx: dict) -> Optional[str]:
    key = sound_key(heard)
    joined = heard.replace(" ", "")
    if len(joined) < MIN_LETTERS:
        return None
    scored = []
    for name, nkey in idx["by_type"].get(kind, ()):
        flat = name.replace(" ", "")
        # Spacing alone ("beltline") needs no fix.
        if not nkey or abs(len(nkey) - len(key)) > 3 or flat == joined:
            continue
        if len(name.split()) != len(heard.split()) and \
                SequenceMatcher(None, joined, name.replace(" ", "")).ratio() < 0.9:
            continue
        sound = SequenceMatcher(None, key, nkey).ratio()
        spelled = SequenceMatcher(None, heard, name).ratio()
        if sound < MIN_SOUND or spelled < MIN_SPELLED:
            continue
        if key[0] != nkey[0] and spelled < SPELLED_ANY_START:
            continue
        if (sound + spelled) / 2 < MIN_SCORE or syllables(name) != syllables(heard):
            continue
        scored.append(((sound + spelled) / 2, name))
    if not scored:
        return None
    scored.sort(reverse=True)
    if len(scored) > 1 and scored[0][0] - scored[1][0] < MIN_MARGIN:
        return None
    return scored[0][1]


_WORD = re.compile(r"[A-Za-z][\w'.-]*|\d[\w-]*|[^\w\s]")


def correct(text: str) -> tuple[str, list[tuple[str, str]]]:
    """(text with misheard street names put right, [(heard, street)])."""
    idx = _index()
    if not idx or not text:
        return text, []
    tokens = [(m.start(), m.end(), m.group()) for m in _WORD.finditer(text)]
    edits, changes = [], []
    for i, (_, _, w) in enumerate(tokens):
        kind = TYPES.get(w.lower().rstrip("."))
        if not kind or not w[0].isupper():
            continue
        run = []                                   # capitalised words right before the type
        j = i - 1
        while j >= 0 and len(run) < MAX_NAME_WORDS + 1 and tokens[j][2][0].isupper() and tokens[j][2].isalpha():
            run.insert(0, j)
            j -= 1
        while run and tokens[run[0]][2].lower() in DIRECTIONS:
            run = run[1:]
        if not run or len(run) > MAX_NAME_WORDS:
            continue
        heard = " ".join(tokens[k][2] for k in run).lower()
        if heard in idx["names"] or _ordinary(heard):
            continue
        fix = _best(heard, kind, idx)
        # A known tail ("Hill" in "Cockroach Hill") means the run may have picked
        # up a word that isn't the name — unless the whole run matches a street
        # of as many words.
        tail_known = any(" ".join(tokens[k][2] for k in run[s:]).lower() in idx["names"] for s in range(1, len(run)))
        if fix and tail_known and len(fix.split()) != len(run):
            fix = None
        if fix:
            edits.append((tokens[run[0]][0], tokens[run[-1]][1], fix.title()))
            changes.append((heard, fix))
    for start, end, new in reversed(edits):
        text = text[:start] + new + text[end:]
    return text, changes
