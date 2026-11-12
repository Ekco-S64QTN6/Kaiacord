"""Which of her beliefs a message actually touches.

A belief used to be recalled when the message shared any one word with its
topic. On 354 real turns that put "you have a formed opinion on…" into 28% of
prompts, almost always wrongly: "open direction" recalled her view on AI and
open source, "whatever way makes sense, human or not" her view on human
adaptation to technology, and a "/" in a topic matched a "/" in a message.
Each false recall also counted as a use, so the beliefs with the most ordinary
words in their topics ("system", "human", "ai") reached hundreds of uses and
could never be evicted. And 410 of her 497 aliases are phrases, which a
word-set intersection can never match, so the alias expansion was mostly dead.

Here a belief is recalled when the message carries one of its phrases whole
(its topic, a part of its topic, or an alias of two words or more), or shares
several distinctive words with it, one of them from its topic. A word is
distinctive when few of her beliefs use it: "system" appears in nineteen and
proves nothing. One shared word is never enough, however rare: "observation",
"timeline" and "understanding" each name one belief and turn up in ordinary
talk about anything. Recall is deliberately narrow. Her reflections reach a
reply through retrieval as well; this note is for when the subject is on the
table.

Read the speaker's own words, never the enriched message. Pure Python.
"""
from __future__ import annotations

import math
import re
from typing import Dict, Iterable, List, Tuple

_WORD = re.compile(r"[a-z][a-z0-9'’-]*")
_SPLIT_TOPIC = re.compile(r"\s*(?:&|/|,|;|\band\b|\bvs\.?\b)\s*")

STOP = frozenset("""
a an the and or but not no nor so if then than that this these those there here it its it's
i i'm i've i'd i'll me my mine we us our you your you're they them their he she his her him
is are was were be been being am do does did doing have has had having can could would should
will shall may might must to of in on at by for with from into onto over under about as up out
off what which who whom whose when where why how all any some more most much many such only
just like really very also too even still ever never always maybe well yes yeah nope okay ok
think thought know knew say said says see seen get got make made go going want need thing
things way lot bit kind sort one two kaia
""".split())

#: Shared distinctive words must add up to this much (in units of a word that
#: names exactly one belief) when no whole phrase matched.
MIN_SCORE = 2.2


def _norm(word: str) -> str:
    word = word.lower().replace("’", "'").strip("'-")
    for suffix, keep in (("ies", "y"), ("sses", "ss"), ("s", "")):
        if word.endswith(suffix) and len(word) > len(suffix) + 2 and not word.endswith("ss"):
            return word[: -len(suffix)] + keep
    return word


def content_words(text: str) -> List[str]:
    """Lower-cased content words in order, plurals folded."""
    return [w for w in (_norm(m) for m in _WORD.findall((text or "").lower())) if w and w not in STOP]


def _tuples(items: Iterable[str]) -> List[Tuple[str, ...]]:
    seen, out = set(), []
    for item in items:
        words = tuple(content_words(item))
        if words and words not in seen:
            seen.add(words)
            out.append(words)
    return out


def _subjects(belief: dict) -> List[Tuple[str, ...]]:
    """The belief's topic and the parts of it: what the belief is about."""
    topic = str(belief.get("topic") or "")
    return _tuples([topic] + [part for part in _SPLIT_TOPIC.split(topic.lower()) if part])


def _phrases(belief: dict) -> List[Tuple[str, ...]]:
    """Its subjects and its aliases, as word tuples."""
    return _tuples([" ".join(s) for s in _subjects(belief)]
                   + [str(alias) for alias in (belief.get("aliases") or [])])


def _contains(haystack: List[str], needle: Tuple[str, ...]) -> bool:
    n = len(needle)
    return any(tuple(haystack[i:i + n]) == needle for i in range(len(haystack) - n + 1))


def relevant(own_words: str, beliefs: Iterable[dict], limit: int = 3) -> List[Tuple[dict, float, str]]:
    """The beliefs this message touches, strongest first: (belief, score, why)."""
    beliefs = [b for b in beliefs if isinstance(b, dict) and b.get("topic") and b.get("position")]
    message = content_words(own_words)
    if not message or not beliefs:
        return []
    said = set(message)
    phrases = [_phrases(b) for b in beliefs]
    subjects = [_subjects(b) for b in beliefs]
    vocab = [{w for phrase in ps for w in phrase} for ps in phrases]
    used_by: Dict[str, int] = {}
    for words in vocab:
        for w in words:
            used_by[w] = used_by.get(w, 0) + 1
    total = len(beliefs)

    def weight(word: str) -> float:
        # 1.0 for a word one belief uses, falling to 0 for one half of them use.
        return max(0.0, math.log((total / 2) / used_by[word]) / math.log(total / 2)) if total > 2 else 1.0

    hits = []
    for belief, ps, subs, words in zip(beliefs, phrases, subjects, vocab):
        shared = said & words
        if not shared:
            continue
        subject_words = {w for sub in subs for w in sub}
        whole = [p for p in ps if len(p) >= 2 and _contains(message, p)]
        score = sum(weight(w) for w in shared)
        if whole:
            best = max(whole, key=len)
            matched = {w for phrase in whole for w in phrase}
            hits.append((belief, score + len(matched), "phrase: " + " ".join(best)))
            continue
        if len(shared) >= 2 and score >= MIN_SCORE and shared & subject_words:
            hits.append((belief, score, "shares: " + ", ".join(sorted(shared))))
    hits.sort(key=lambda h: (-h[1], -float(h[0].get("confidence", 0.5) or 0.5)))
    return hits[:limit]
