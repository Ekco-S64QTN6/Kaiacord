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

# Operation cues, tested against the cleaned sentence. Order matters: the more
# specific phrases first.
_OPS = [
    ("*", r"\b(?:times|multipl\w*|product|doubles?\s+by|tripl\w*\s+by|scaled\s+by)\b"),
    ("/", r"\b(?:divid\w*|split\w*\s+(?:into|among|between)|shared?\s+(?:among|between)|per\s+each|ratio)\b"),
    ("-", r"\b(?:minus|subtract\w*|less|loses?|lost|slows?|slowed|decreas\w*|reduc\w*|drops?|dropped|"
          r"falls?|fell|sheds?|gives?\s+away|eats?|spends?|fewer|lower\w*\s+by|takes?\s+away|remov\w*)\b"),
    ("+", r"\b(?:plus|add\w*|gains?|gained|increas\w*|speeds?\s+up|faster|accelerat\w*|more|grows?|grew|"
          r"rais\w*|joins?|joined|finds?|found|gets?|another|extra|total|sum|combined|together)\b"),
]


def _collapse(word: str) -> str:
    return re.sub(r"(.)\1+", r"\1", word)


# The cues are matched on doubled-letter-collapsed text ("increaasses"), so
# they are collapsed the same way: "less" is "les", "add" is "ad".
_OPS_COLLAPSED = [(op, re.compile(_collapse(pat))) for op, pat in _OPS]

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


def clean(challenge: str) -> str:
    """The challenge as plain lowercase words: noise symbols removed (joining
    the pieces of a word they split), case flattened."""
    text = re.sub(r"[^A-Za-z0-9.\s]", "", challenge or "")
    return re.sub(r"\s+", " ", text).strip().lower()


def _number_tokens(words: list[str]) -> list[tuple[int, int, float]]:
    """(start, end, value) for each number in the word list: digits, or runs of
    number words, joining fragments a word was split into."""
    out = []
    i = 0
    while i < len(words):
        w = words[i]
        if re.fullmatch(r"\d+(?:\.\d+)?", w):
            out.append((i, i + 1, float(w)))
            i += 1
            continue
        # The longest join of up to three fragments that is a number word.
        val, used = None, 0
        for n in (3, 2, 1):
            if i + n <= len(words):
                joined = _collapse("".join(words[i:i + n]))
                if joined in _WORDS:
                    val, used = _WORDS[joined], n
                    break
        if val is None:
            i += 1
            continue
        start, total, current = i, 0, val
        i += used
        # Continue a compound: "twenty five", "two hundred".
        while i < len(words):
            nxt, nused = None, 0
            for n in (3, 2, 1):
                if i + n <= len(words):
                    joined = _collapse("".join(words[i:i + n]))
                    if joined in _WORDS:
                        nxt, nused = _WORDS[joined], n
                        break
            if nxt is None:
                if words[i] == "and":            # "two hundred and five"
                    i += 1
                    continue
                break
            if nxt in (100, 1000):
                current = max(1, current) * nxt
                if nxt == 1000:
                    total, current = total + current, 0
            elif current >= 20 and current % 10 == 0 and nxt < 10 and current < 100:
                current += nxt
            elif current >= 100 and nxt < 100:
                current += nxt
            else:
                break
            i += nused
        out.append((start, i, float(total + current)))
    return out


def solve(challenge: str) -> Optional[str]:
    """The answer as Moltbook wants it ("15.00"), or None if not certain."""
    text = clean(challenge)
    words = text.split()
    nums = _number_tokens(words)
    if len(nums) != 2:
        return None
    a, b = nums[0][2], nums[1][2]
    op = explicit_operator(challenge)
    if op is None:
        squashed = " ".join(_collapse(w) for w in words)
        found = [o for o, pat in _OPS_COLLAPSED if pat.search(squashed)]
        if not found:
            return None
        op = found[0]
    # "doubles" / "triples" with only one stated number would be a third
    # operand; with two numbers stated, trust the explicit cue.
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
