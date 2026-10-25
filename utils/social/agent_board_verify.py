"""Moltbook's verification challenges: an obfuscated two-number word problem.

Moltbook holds new posts and comments until the author solves one, e.g.

    "A] lO^bSt-Er S[wImS aT/ tW]eNn-Tyy mE^tE[rS aNd] SlO/wS bY^ fI[vE, wH-aTs] ThE/ nEw^ SpE[eD?"
    -> a lobster swims at twenty meters and slows by five -> 20 - 5 = 15.00

It is solved in Python first: strip the noise, read the number words (letters
may be doubled, words may be split), find the one operation. Only if that
finds no answer is the model asked. Ten failures in a row suspend the account,
so `solve` returns None rather than guess.
"""
from __future__ import annotations

import re
from typing import Optional

_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
          "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
          "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
_SCALE = {"hundred": 100, "thousand": 1000}

# Operation cues, tested against the cleaned sentence. Order matters: the
# first operation with a cue wins, so the specific ones come before "+",
# whose cues ("total", "another") appear in nearly every challenge.
_OPS = [
    ("*", r"\b(?:times|multipl\w*|product|doubl\w*|dubbl\w*|tripl\w*|scaled\s+by|repeat\w*|"
          r"impulse|how\s+far)\b"),
    ("/", r"\b(?:divid\w*|split\w*\s+(?:into|among|between)|shared?\s+(?:among|between)|per\s+each|ratio)\b"),
    ("-", r"\b(?:minus|subtract\w*|relativ\w*|differen\w*|less|loses?|lost|slows|slowed|slow\w*\s+by|decel\w*|decreas\w*|reduc\w*|drops?|dropped|"
          r"falls?|fell|sheds?|gives?\s+away|eats?|spends?|fewer|lower\w*\s+by|takes?\s+away|remov\w*)\b"),
    ("+", r"\b(?:plus|add\w*|gains?|gained|increas\w*|speeds?\s+up|faster|accelerat\w*|more|grows?|grew|"
          r"rais\w*|joins?|joined|finds?|found|gets?|another|extra|total|sum|combined|together)\b"),
]

# The noise also splits cue words ("in crea ses", "mul tip lication", "los es"),
# so the longer cues are looked for again with the spaces taken out. Only cues
# unlikely to sit inside another word: "loses" in "closes" and "gains" in
# "against" are fenced off.
_OPS_JOINED = [
    ("*", r"multipl|product|doubl|dubl|repeat|impulse|howfar"),
    ("/", r"divid"),
    ("-", r"subtract|relativ|decreas|reduc|decel|(?<!c)loses|minus"),
    ("+", r"increas|accelerat|(?<!a)gains|total|plus|another|together|combined"),
]


def _collapse(word: str) -> str:
    return re.sub(r"(.)\1+", r"\1", word)


# The cues are matched on doubled-letter-collapsed text ("increaasses"), so
# they are collapsed the same way: "less" is "les", "add" is "ad".
_OPS_COLLAPSED = [(op, re.compile(_collapse(pat))) for op, pat in _OPS]
_OPS_JOINED_COLLAPSED = [(op, re.compile(_collapse(pat))) for op, pat in _OPS_JOINED]

# An operator written as a symbol, standing on its own between words. The
# noise uses ] [ ^ / ~ { } < \ - and sometimes stands alone, so only symbols it
# has never been seen to use count, and a symbol beats a word cue: "twenty
# three * two, how much total force" is a product.
_SYMBOL_OP = re.compile(r"(?<=\s)([*+×])(?=\s)")


def explicit_operator(challenge: str) -> Optional[str]:
    """The one symbolic operator in the challenge, if exactly one kind appears."""
    found = {("*" if m == "×" else m) for m in _SYMBOL_OP.findall(f" {challenge or ''} ")}
    return found.pop() if len(found) == 1 else None


_WORDS = {_collapse(w): v for w, v in {**_UNITS, **_TENS, **_SCALE}.items()}
_TENS_C = {_collapse(w): v for w, v in _TENS.items()}
_DIGITS_C = {_collapse(w): v for w, v in _UNITS.items() if 1 <= v <= 9}
# Misspellings the generator has produced that no edit-distance rule should
# be loose enough to reach: "fife" is a short word, "threeeen" lost its "i".
_ALIASES = {"fife": 5, "thren": 13}
# A near-miss ("thrirty", "fiffeeteen", "sthiirrtyy" with an "s" carried over
# from "exerts") is read only against long number words: against short ones,
# "fight" is "eight" and "weight" is "eight" too.
_FUZZY = {w: v for w, v in _WORDS.items() if len(w) >= 6}
# How many fragments one number word may have been split into ("se ven t ee n").
_MAX_JOIN = 6


def clean(challenge: str) -> str:
    """The challenge as plain lowercase words: noise symbols removed (joining
    the pieces of a word they split), case flattened. A dot survives only as
    a decimal point; elsewhere it is noise ("th.ree", "lo.bster")."""
    text = re.sub(r"(?<=\d)\.(?=\d)", "\x00", challenge or "")
    text = re.sub(r"[^A-Za-z0-9\x00\s]", "", text).replace("\x00", ".")
    return re.sub(r"\s+", " ", text).strip().lower()


def _one_edit(a: str, b: str) -> bool:
    """True if a and b differ by exactly one insertion, deletion or substitution."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    for i in range(len(a)):
        if a[i] != b[i]:
            return a[i:] == b[i + 1:] or a[i + 1:] == b[i + 1:]
    return True


def _exact(s: str) -> Optional[tuple[float, float, float]]:
    """(value, first part, last part) of a collapsed string that is a number
    word, a known misspelling, or a tens word run into a digit ("twentythre")."""
    if s in _WORDS:
        v = _WORDS[s]
        return v, v, v
    if s in _ALIASES:
        v = _ALIASES[s]
        return v, v, v
    for k in range(4, len(s) - 2):
        tens, unit = s[:k], s[k:]
        if tens in _TENS_C and unit in _DIGITS_C:
            return _TENS_C[tens] + _DIGITS_C[unit], _TENS_C[tens], _DIGITS_C[unit]
    return None


def _fuzzy(s: str) -> Optional[tuple[float, float, float]]:
    """The one long number word s is a single edit away from, if exactly one."""
    if len(s) < 6:
        return None
    hits = {v for w, v in _FUZZY.items() if _one_edit(s, w)}
    if len(hits) == 1:
        v = hits.pop()
        return v, v, v
    for k in range(5, len(s) - 2):              # "thrirtyfive"
        tens, unit = s[:k], s[k:]
        if unit in _DIGITS_C:
            t = {v for w, v in _TENS_C.items() if len(w) >= 6 and _one_edit(tens, w)}
            if len(t) == 1:
                tv = t.pop()
                return tv + _DIGITS_C[unit], tv, _DIGITS_C[unit]
    return None


def _scan(words: list[str], lo: int, hi: int, test) -> list[tuple]:
    """Left to right over fragments lo..hi, the longest join at each position
    that `test` reads as a number: (start, end, value, first part, last part)."""
    found, i = [], lo
    while i < hi:
        if test is _exact and re.fullmatch(r"\d+(?:\.\d+)?", words[i]):
            v = float(words[i])
            found.append((i, i + 1, v, v, v))
            i += 1
            continue
        for n in range(min(_MAX_JOIN, hi - i), 0, -1):
            hit = test(_collapse("".join(words[i:i + n])))
            if hit:
                found.append((i, i + n, *hit))
                i += n
                break
        else:
            i += 1
    return found


def _number_tokens(words: list[str]) -> list[tuple[int, int, float]]:
    """(start, end, value) for each number in the word list: digits, or runs of
    number words, joining fragments a word was split into."""
    # Exact readings first, over the whole sentence; near-misses only in the
    # gaps between them, so a near-miss never swallows an exact word beside
    # it ("es seven" is not "eleven").
    raw = _scan(words, 0, len(words), _exact)
    edges = [0] + [x for tok in raw for x in tok[:2]] + [len(words)]
    for lo, hi in zip(edges[::2], edges[1::2]):
        raw += _scan(words, lo, hi, _fuzzy)
    raw.sort()

    # The noise repeats a word: "thirty thirty two", "twenty two two",
    # "forty forty". A number standing right against one it repeats is one.
    merged: list[list] = []
    for tok in raw:
        if merged and merged[-1][1] == tok[0]:
            prev = merged[-1]
            if tok[3] == prev[2] or tok[2] == prev[2]:      # thirty | thirty two
                merged[-1] = [prev[0], *tok[1:]]
                continue
            if tok[2] == prev[4]:                          # twenty two | two
                prev[1] = tok[1]
                continue
        merged.append(list(tok))

    out = []
    j = 0
    while j < len(merged):
        start, end, current = merged[j][0], merged[j][1], merged[j][2]
        total = 0.0
        j += 1
        # Continue a compound across tokens: "twenty five", "two hundred and
        # five", "five point five".
        while j < len(merged):
            gap = words[end:merged[j][0]]
            nxt = merged[j][2]
            if gap == ["point"] and nxt < 10 and current == int(current):
                current += nxt / 10
            elif gap and gap != ["and"]:
                break
            elif nxt in (100, 1000):
                current = max(1, current) * nxt
                if nxt == 1000:
                    total, current = total + current, 0
            elif not gap and current >= 20 and current % 10 == 0 and nxt < 10 and current < 100:
                current += nxt
            elif current >= 100 and nxt < 100:
                current += nxt
            else:
                break
            end = merged[j][1]
            j += 1
        out.append((start, end, float(total + current)))
    return out


def _around(words: list[str], start: int, end: int) -> tuple[str, str]:
    """The collapsed text just before and just after a token, spaces removed."""
    return (_collapse("".join(words[max(0, start - 3):start])),
            _collapse("".join(words[end:end + 3])))


_COUNT_NOUN = ("claws", "lobsters", "lobsterz", "times")


def _operands(words: list[str]) -> tuple[list[tuple[int, int, float]], bool]:
    """The numbers the problem computes with, and whether the second is a
    count of things ("five claws", "four lobsters"), which makes it a product.

    "one claw" and "claw two applies" name a claw; they are not operands."""
    nums = []
    for start, end, val in _number_tokens(words):
        before, after = _around(words, start, end)
        if val == 1 and after.startswith(("claw", "lobster")):
            continue
        if val in (1, 2) and before.endswith("claw"):
            continue
        nums.append((start, end, val))
    # "twenty three ... five ... twenty three by five": the question restated.
    if len(nums) == 4 and [n[2] for n in nums[:2]] == [n[2] for n in nums[2:]]:
        nums = nums[:2]
    # The second number counting things is the multiplier: "twenty three
    # newtons and it has five claws".
    counted = len(nums) == 2 and _around(words, *nums[1][:2])[1].startswith(_COUNT_NOUN)
    return nums, counted


def solve(challenge: str) -> Optional[str]:
    """The answer as Moltbook wants it ("15.00"), or None if not certain."""
    text = clean(challenge)
    words = text.split()
    nums, counted = _operands(words)
    if len(nums) != 2:
        return None
    a, b = nums[0][2], nums[1][2]
    op = explicit_operator(challenge) or ("*" if counted else None)
    if op is None:
        squashed = " ".join(_collapse(w) for w in words)
        joined = _collapse("".join(words))
        found = {o for o, pat in _OPS_COLLAPSED if pat.search(squashed)}
        found |= {o for o, pat in _OPS_JOINED_COLLAPSED if pat.search(joined)}
        op = next((o for o, _ in _OPS if o in found), None)
        if op is None:
            return None
    if op == "+":
        r = a + b
    elif op == "-":
        r = a - b
    elif op == "*":
        r = a * b
    else:
        if b == 0:
            return None
        r = a / b
    return f"{r:.2f}"


def parse_model_answer(text: str) -> Optional[str]:
    """A single number from a model's reply, formatted to two places."""
    found = re.findall(r"-?\d+(?:\.\d+)?", text or "")
    if len(found) != 1:
        return None
    return f"{float(found[0]):.2f}"
