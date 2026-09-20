#!/usr/bin/env python3
"""Separate Kaia's actual dreams from everything else that landed in the folder.

`knowledge_base/kaia_dreams/` is its own RAG index, and `context_optimizer`
labels anything retrieved from it **INTERNAL REFLECTION (DREAM)** — as something
Kaia thought. Three classes of file get in that are not reflections:

  transcript  raw `User:` / `Kaia:` logs written there by an older pipeline.
              These duplicate `user_logs/`, which is indexed separately.
  empty       the model reporting there was nothing to summarise.
  scraped     web prose with no reflection in it.

The damage compounds: the dream engine treats `kaia_dreams` as a valid source
(`dream_source_type = 'prior_dream'`), so a transcript-shaped file teaches the
next night's dream to emit `User:`-prefixed fragments inside a reflection.

This tool only sorts. It writes nothing into the corpus and calls no model.

    python tools/maintenance/triage_dreams.py                # report only
    python tools/maintenance/triage_dreams.py --apply        # quarantine
    python tools/maintenance/triage_dreams.py --show transcript --limit 5

Quarantined files move to `knowledge_base/_quarantine/dreams/<class>/`, which is
excluded from indexing, so nothing is destroyed and the move is reversible.
Dry run by default (CLAUDE.md §10).
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DREAMS = Path("knowledge_base/kaia_dreams")
# `_quarantine`, with the underscore. `RAGIndexerMixin._is_excluded_path`
# matches "/_quarantine" and nothing else, so the old spelling put every
# quarantined transcript straight back into the index — and this tool runs
# with --apply from the weekly curation task, so it would have done that
# unattended, defeating its own purpose.
QUARANTINE = Path("knowledge_base/_quarantine/dreams")

# The heading the current dream engine writes. Its presence is what makes a file
# a reflection; everything else in the folder is residue from an older pipeline.
REFLECTION_MARKER = "## Kaia's Reflection"

# A transcript line. Anchored, because "user:" appears mid-prose often enough
# that an unanchored search misclassifies real reflections.
# Markdown emphasis included: the ebook ingest path emitted `**User:** ` and an
# anchored `^(?:User|Kaia):` filed 295 of those under "no reflection in the file"
# rather than naming them for what they are.
TRANSCRIPT_LINE = re.compile(r"^\**(?:User|Kaia)\**:", re.MULTILINE)

# The model announcing it had nothing to work with. These are not failures worth
# keeping as evidence — they are the absence of a dream.
EMPTY_PHRASES = (
    "there is no meaningful interaction",
    "the cleaned log is empty",
    "no meaningful content",
    "appears to be a result of a malfunction",
)

# Below this a reflection has not said anything, whatever its shape.
MIN_REFLECTION_CHARS = 200

# An empty-phrase means "nothing was dreamt" only when the file *opens* with it,
# which is what the model does when it has nothing: "There is no meaningful
# interaction to extract from the provided chat log." is the first thing on the
# page. She also writes about her own empty logs inside real reflections, and
# condemning those on a substring match anywhere in the body would delete
# genuine material. Position separates the two; length does not.
EMPTY_PHRASE_WINDOW = 200


def body_of(text: str) -> str:
    """The file without its YAML frontmatter.

    Written defensively because a chunk of this corpus is malformed: the closing
    fence is fused to the first line of content (`---User: speeding ticket...`),
    so an anchored `^User:` never matches and 272 plainly-transcript files were
    being filed as "no reflection in the file" instead.
    """
    t = text.lstrip()
    if not t.startswith("---"):
        return text
    end = t.find("\n---", 3)
    if end == -1:
        return text
    rest = t[end + 4:]
    # The fence may be fused to the content rather than followed by a newline.
    return rest.lstrip("-").lstrip("\n")


def classify(text: str) -> str:
    """What this file is. The reflection marker is checked first on purpose.

    Testing the empty-phrases first would condemn a genuine reflection that
    happened to use one of those phrases in passing — she writes about her own
    logs often enough for that to be a real risk. The phrases only mean
    "nothing was dreamt" when they are the whole file.
    """
    if REFLECTION_MARKER in text:
        body = text.split(REFLECTION_MARKER, 1)[1].strip()
        low_body = body.lower()
        if len(body) < MIN_REFLECTION_CHARS:
            return "empty"
        if any(p in low_body[:EMPTY_PHRASE_WINDOW] for p in EMPTY_PHRASES):
            return "empty"
        return "reflection"
    body = body_of(text)
    if any(p in body.lower()[:EMPTY_PHRASE_WINDOW] for p in EMPTY_PHRASES):
        return "empty"
    if TRANSCRIPT_LINE.search(body) or TRANSCRIPT_LINE.match(body.lstrip()):
        return "transcript"
    return "residue"


def source_of(text: str) -> str:
    m = re.search(r"^Source: (.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def is_recursive(text: str) -> bool:
    """A reflection whose source was itself a dream file."""
    s = source_of(text)
    return bool(s) and ("dream_" in s or "kaia_dreams" in s)


# `consolidated/` is this folder's *output*, not its input: one document per
# book, person and topic, written by consolidate_dreams.py. Those files carry
# `document_type: Consolidated Dream Reflection` and no `## Kaia's Reflection`
# heading, so `classify()` reads all 46 of them as residue.
#
# The weekly curation task runs `triage_dreams --apply` *before* consolidation,
# so this would have quarantined the previous week's entire output every week —
# destroying exactly what the pass exists to produce, unattended, while logging
# a successful triage.
CONSOLIDATED = "consolidated"


def scan() -> list:
    out = []
    for f in sorted(DREAMS.rglob("*.md")):
        if QUARANTINE in f.parents:
            continue
        if CONSOLIDATED in f.relative_to(DREAMS).parts:
            continue
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.append((f, classify(t), is_recursive(t)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="move non-reflections to quarantine (default: report only)")
    ap.add_argument("--show", choices=("transcript", "empty", "residue", "reflection"),
                    help="print samples of one class and exit")
    ap.add_argument("--limit", type=int, default=8)
    args = ap.parse_args()

    if not DREAMS.exists():
        print(f"{DREAMS} does not exist.")
        return 1

    files = scan()
    counts = Counter(c for _, c, _ in files)
    recursive = sum(1 for _, c, r in files if c == "reflection" and r)

    if args.show:
        for f, c, _ in files:
            if c != args.show:
                continue
            t = f.read_text(encoding="utf-8", errors="replace")
            body = t.split("---", 2)[-1].strip()
            print(f"\n--- {f.relative_to(DREAMS)}")
            print("   ", body[:400].replace("\n", " | "))
            args.limit -= 1
            if args.limit <= 0:
                break
        return 0

    total = len(files)
    print(f"{total} files in {DREAMS}\n")
    for name, label in (("reflection", "real reflections (keep)"),
                        ("transcript", "raw User:/Kaia: transcripts"),
                        ("empty",      "nothing was dreamt"),
                        ("residue",    "no reflection in the file")):
        n = counts.get(name, 0)
        print(f"  {n:5d}  {100*n//max(total,1):3d}%  {label}")
    print(f"\n  {recursive:5d}  of the reflections are reflections on an earlier dream")
    print("         (harmless once the transcripts are out; while they are in the "
          "folder\n          this is how the transcript shape propagates)")

    doomed = [f for f, c, _ in files if c != "reflection"]
    if not doomed:
        print("\nNothing to quarantine.")
        return 0

    if not args.apply:
        print(f"\n{len(doomed)} file(s) would move to {QUARANTINE}/<class>/.")
        print("Re-run with --apply to move them. Nothing is deleted.")
        return 0

    moved = 0
    for f, c, _ in files:
        if c == "reflection":
            continue
        dest = QUARANTINE / c / f.relative_to(DREAMS).parent
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(dest / f.name))
        moved += 1
    print(f"\n{moved} file(s) moved to {QUARANTINE}/.")
    print("Re-index so the dreams index drops them: "
          "venv/bin/python3 tools/maintenance/reindex_rag.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
