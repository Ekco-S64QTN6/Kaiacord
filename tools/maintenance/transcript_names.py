#!/usr/bin/env python3
"""Correct the names YouTube's speech recognition mishears in a transcript.

Auto-generated captions are good at ordinary English and bad at proper nouns:
a Dune lore video comes back with "house ATT treaties" for House Atreides and
"oracus" for Arrakis. Those are exactly the words retrieval keys on, so a
question about the Atreides never finds the transcript that is about them.

The local chat model reads the transcript in chunks, with the video's title,
and returns a glossary — `heard -> correct` pairs. It never rewrites the text.
Python applies the glossary, and only the pairs that are safe to apply to a
whole document:

* the misheard form must occur in the chunk the model was shown
* it is a phrase ("ATT treaties", "free men"), or a single word that is not
  English ("oracus"). A single real word ("neat" for the narrator Ned) is
  never replaced: it is certainly used as itself somewhere else in the text.
* both sides are short, and the correction is not just the same words recased
* the correction is shaped like a name — capitalised — and *sounds like* what
  was heard. Speech recognition errs by sound, so a real fix shares its
  consonant skeleton with the mishearing: "atres" and "Atreides" do, and
  "simx" and "thinking machines" do not. Without this the model supplies
  confident, plausible, wrong answers — "sorceresses of rosac" became "Bene
  Gesserit", a different order entirely.

Precision over recall: a name left misspelled costs a little retrieval, and a
real word rewritten across a six-hour transcript costs the transcript.

    python tools/maintenance/transcript_names.py <file.md>            # dry run
    python tools/maintenance/transcript_names.py <file.md> --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Awaitable, Callable

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CHUNK_WORDS = 2500
MAX_PHRASE_WORDS = 4
_SAFE_CORRECTION = re.compile(r"^[\w][\w' .\-]*$", re.UNICODE)

PROMPT = """This is part of an auto-generated YouTube transcript.
Video title: {title}
Channel: {channel}

Speech recognition mangles names and specialised terms. List every proper noun
or subject-specific term in the excerpt below that was clearly misheard, with
its correct spelling given what this video is about.

Rules:
- "heard" must be copied exactly as it appears in the excerpt.
- Only include terms you are confident about. Leave out ordinary words that
  are used correctly, and do not rephrase anything.
- If nothing was misheard, return an empty list.

Reply with JSON only: {{"corrections": [{{"heard": "...", "correct": "..."}}]}}

Excerpt:
{excerpt}"""


def _english_words() -> set[str]:
    try:
        from nltk.corpus import words
        return {w.lower() for w in words.words()}
    except Exception:
        return set()


_ENGLISH: set[str] | None = None


def is_english_word(token: str) -> bool:
    global _ENGLISH
    if _ENGLISH is None:
        _ENGLISH = _english_words()
    t = token.lower().strip("'.-")
    if not _ENGLISH:
        return True          # no word list: treat as English, i.e. do not replace
    # The list has lemmas, not inflections: "treaties" is only there as "treaty".
    candidates = {t, t[:-1] if t.endswith("s") else t,
                  t[:-2] if t.endswith("es") else t,
                  t[:-3] + "y" if t.endswith("ies") else t}
    return any(c in _ENGLISH for c in candidates)


def _split_frontmatter(markdown: str) -> tuple[str, str]:
    if markdown.startswith("---\n"):
        end = markdown.find("\n---\n", 4)
        if end != -1:
            return markdown[:end + 5], markdown[end + 5:]
    return "", markdown


def _is_prose(line: str) -> bool:
    s = line.strip()
    return bool(s) and not s.startswith(("#", "**Source:**", "---", "[", "!"))


def prose_chunks(markdown: str, size: int = CHUNK_WORDS) -> list[str]:
    """The transcript's spoken text, in chunks of about `size` words."""
    _fm, body = _split_frontmatter(markdown)
    words: list[str] = []
    for line in body.splitlines():
        if _is_prose(line):
            words.extend(line.split())
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


# Consonant classes that speech recognition confuses with each other.
_SOUND = str.maketrans({"c": "k", "q": "k", "g": "k", "z": "s", "v": "f",
                        "d": "t", "b": "p", "j": "k"})
_NAME_FILLERS = {"of", "the", "de", "von", "van", "al", "el", "and"}
MIN_SOUND_SIMILARITY = 0.7


def sound_key(text: str) -> str:
    """A crude phonetic skeleton: consonant classes, vowels dropped after the
    first letter, repeats collapsed. 'ATT treaties' and 'Atreides' both give
    'atrts'."""
    letters = re.sub(r"[^a-z]", "", text.lower().replace("ph", "f").replace("x", "ks"))
    if not letters:
        return ""
    body = letters[0] + re.sub(r"[aeiouyhw]", "", letters[1:])
    body = body.translate(_SOUND)
    return re.sub(r"(.)\1+", r"\1", body)


def sounds_alike(heard: str, correct: str) -> bool:
    from difflib import SequenceMatcher
    a, b = sound_key(heard), sound_key(correct)
    return bool(a and b) and SequenceMatcher(None, a, b).ratio() >= MIN_SOUND_SIMILARITY


def looks_like_a_name(text: str) -> bool:
    words = [w for w in text.split() if w.lower() not in _NAME_FILLERS]
    return bool(words) and all(w[0].isupper() for w in words)


def _norm(s: str) -> str:
    return " ".join(s.split()).strip(" .,;:!?\"'")


def valid_pair(heard: str, correct: str, excerpt: str) -> bool:
    heard, correct = _norm(heard), _norm(correct)
    if not heard or not correct:
        return False
    if re.sub(r"[^a-z]", "", heard.lower()) == re.sub(r"[^a-z]", "", correct.lower()):
        return False                                  # a recasing is not a mishearing
    if len(re.sub(r"[^a-z]", "", heard.lower())) < 3:
        return False                                  # "gz" could be anything
    if not looks_like_a_name(correct) or not sounds_alike(heard, correct):
        return False
    if len(heard.split()) > MAX_PHRASE_WORDS or len(correct.split()) > MAX_PHRASE_WORDS:
        return False
    if not _SAFE_CORRECTION.match(correct):
        return False
    if not _pattern(heard).search(excerpt):
        return False                                  # the model must quote, not invent
    if len(heard.split()) == 1 and is_english_word(heard):
        return False                                  # a real word is used as itself elsewhere
    return True


def _pattern(heard: str) -> re.Pattern:
    body = r"\s+".join(re.escape(w) for w in heard.split())
    return re.compile(rf"(?<![\w']){body}(?![\w'])", re.IGNORECASE)


def _parse(reply: str) -> list[tuple[str, str]]:
    try:
        data = json.loads(reply)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", reply or "", re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    items = data.get("corrections", []) if isinstance(data, dict) else data
    out = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and isinstance(item.get("heard"), str) \
                and isinstance(item.get("correct"), str):
            out.append((item["heard"], item["correct"]))
    return out


async def find_corrections(markdown: str, title: str, channel: str,
                           chat: Callable[[str], Awaitable[str]]) -> dict[str, str]:
    """Ask `chat` for a glossary chunk by chunk; return the pairs safe to apply."""
    votes: dict[str, Counter] = defaultdict(Counter)
    for excerpt in prose_chunks(markdown):
        try:
            reply = await chat(PROMPT.format(title=title, channel=channel or "unknown",
                                             excerpt=excerpt))
        except Exception:
            continue
        for heard, correct in _parse(reply):
            if valid_pair(heard, correct, excerpt):
                votes[_norm(heard).lower()][_norm(correct)] += 1

    glossary: dict[str, str] = {}
    for heard, counts in votes.items():
        ranked = counts.most_common(2)
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            continue                                   # the model disagrees with itself
        glossary[heard] = ranked[0][0]
    return glossary


def apply_corrections(markdown: str, glossary: dict[str, str]) -> tuple[str, dict[str, int]]:
    """Apply the glossary to the spoken text and the summary. Returns (text, counts)."""
    counts: dict[str, int] = {}
    ordered = sorted(glossary.items(), key=lambda kv: -len(kv[0]))
    patterns = [(_pattern(h), h, c) for h, c in ordered]

    def fix(line: str) -> str:
        for pat, heard, correct in patterns:
            line, n = pat.subn(correct, line)
            if n:
                counts[heard] = counts.get(heard, 0) + n
        return line

    frontmatter, body = _split_frontmatter(markdown)
    fm_lines, in_summary = [], False
    for line in frontmatter.splitlines(keepends=True):
        if line.startswith("summary:"):
            in_summary = True
            line = fix(line)
        elif in_summary and line.startswith("  "):
            line = fix(line)
        else:
            in_summary = False
        fm_lines.append(line)
    body_lines = [fix(line) if _is_prose(line) else line
                  for line in body.splitlines(keepends=True)]
    return "".join(fm_lines) + "".join(body_lines), counts


def describe(counts: dict[str, int], glossary: dict[str, str], limit: int = 6) -> str:
    """'ATT treaties → Atreides (41), …' for the command's reply and the log."""
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    shown = [f"{h} → {glossary[h]} ({n})" for h, n in ranked[:limit]]
    more = len(ranked) - limit
    return ", ".join(shown) + (f", and {more} more" if more > 0 else "")


def _title_and_channel(markdown: str) -> tuple[str, str]:
    title = re.search(r"^title:\s*(.+)$", markdown, re.MULTILINE)
    channel = re.search(r"^author:\s*(.+)$", markdown, re.MULTILINE) or \
        re.search(r"\*\*Channel:\*\*\s*([^\n*]+)", markdown)
    heading = re.search(r"^# (.+)$", markdown, re.MULTILINE)
    t = (title.group(1) if title else heading.group(1) if heading else "").strip().strip("'\"")
    return t, (channel.group(1).strip().strip("'\"") if channel else "")


async def _cli_chat(prompt: str) -> str:
    import ollama
    from utils.infrastructure.gpu.gpu_manager import chat_options
    from utils.infrastructure.system.yaml_config import config
    client = ollama.AsyncClient(timeout=300)
    resp = await client.chat(model=config.chat_model,
                             messages=[{"role": "user", "content": prompt}],
                             options=chat_options(temperature=0.1, num_predict=600),
                             format="json", keep_alive=-1)
    return resp["message"]["content"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--apply", action="store_true", help="write the corrections")
    args = ap.parse_args()

    from utils.core.atomic_write import write_atomic
    for path in args.files:
        text = path.read_text(encoding="utf-8")
        title, channel = _title_and_channel(text)
        chunks = len(prose_chunks(text))
        print(f"{path.name}: {chunks} chunk(s), asking the model…", flush=True)
        glossary = asyncio.run(find_corrections(text, title, channel, _cli_chat))
        fixed, counts = apply_corrections(text, glossary)
        if not counts:
            print("  nothing to correct")
            continue
        for heard, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {n:4}  {heard!r} -> {glossary[heard]!r}")
        if args.apply:
            write_atomic(path, fixed)
            print(f"  written ({sum(counts.values())} replacements)")
        else:
            print("  dry run — re-run with --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
