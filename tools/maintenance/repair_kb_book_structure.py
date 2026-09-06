#!/usr/bin/env python3
"""
repair_kb_book_structure.py — repair structure in already-converted knowledge_base books.

For books whose original EPUB/PDF is no longer available, so re-running
ebook_to_kb_md.py is not an option. Three conservative repairs:

  1. Strip OCR/print page numbers. Only numbers belonging to an ascending run are
     removed, so a standalone publication year ("1968", "1912") is preserved — those sit
     alone and are not part of a sequence.
  2. Promote genuine chapter markers that are present as plain text
     ("Chapter One", "CHAPTER 12", screenplay "INT./EXT." scene headings) to '## '.
  3. Demote stray '# ' headings inside the body, so the document has exactly one root.

Deliberately NOT done: inventing chapter breaks. Several books in the library
(Neuromancer, Snow Crash, Hagakure, Johnny Mnemonic) simply have no chapter markers in
their text. Inserting boundaries at guessed positions would put headings in the wrong
place, which retrieves worse than no headings at all.

Usage:
    python3 tools/maintenance/repair_kb_book_structure.py [FILE ...] [--apply] [--quiet]

Runs as a dry run by default and prints what it would change.
"""

from __future__ import annotations

import argparse
import glob
import io
import re
import sys
from pathlib import Path

RE_BARE_NUM = re.compile(r"^[ \t]*(\d{1,4})[ \t]*$")
RE_BODY_H1 = re.compile(r"^# (?!.*\Z)", re.M)

CHAPTER_PATTERNS = [
    # "Chapter One", "Chapter Twenty-Three"
    re.compile(r"^[ \t]*(Chapter\s+(?:One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|"
               r"Eleven|Twelve|Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen|"
               r"Nineteen|Twenty|Twenty[- ]\w+|Thirty|Thirty[- ]\w+)"
               r"(?:\s*[:.—-]\s*[^\n]{0,70})?)[ \t]*$", re.M | re.I),
    # "CHAPTER 12", "Chapter 3."
    re.compile(r"^[ \t]*(Chapter\s+\d{1,3}(?:\s*[:.—-]\s*[^\n]{0,70})?)[ \t]*$",
               re.M | re.I),
    # "PART ONE", "BOOK II"
    re.compile(r"^[ \t]*((?:PART|BOOK)\s+[A-Z0-9]{1,10}(?:\s*[:.—-]\s*[^\n]{0,70})?)[ \t]*$",
               re.M),
]

# Screenplay scene headings — a real structural boundary in a script.
RE_SLUGLINE = re.compile(r"^[ \t]*((?:INT\.|EXT\.|INT/EXT\.)[^\n]{2,90})$", re.M)


def find_page_number_runs(lines: list[str], min_run: int = 5) -> set[int]:
    """Line indices holding page numbers, identified by ascending runs.

    A page number is one member of a mostly-monotonic sequence. A publication year
    appears once, out of sequence, so it never joins a run and is preserved.
    """
    hits = [(i, int(m.group(1))) for i, l in enumerate(lines)
            if (m := RE_BARE_NUM.match(l))]
    drop: set[int] = set()
    run: list[tuple[int, int]] = []

    def flush():
        if len(run) >= min_run:
            drop.update(i for i, _ in run)

    for entry in hits:
        if run and 0 < entry[1] - run[-1][1] <= 3:
            run.append(entry)
        else:
            flush()
            run = [entry]
    flush()
    return drop


def strip_page_numbers(text: str) -> tuple[str, int]:
    lines = text.split("\n")
    drop = find_page_number_runs(lines)
    if not drop:
        return text, 0
    kept = [l for i, l in enumerate(lines) if i not in drop]
    return "\n".join(kept), len(drop)


def promote_chapters(text: str) -> tuple[str, int]:
    n = 0

    def _sub(m):
        nonlocal n
        n += 1
        return f"## {m.group(1).strip()}"

    for pat in CHAPTER_PATTERNS:
        text = pat.sub(_sub, text)
    return text, n


def promote_sluglines(text: str) -> tuple[str, int]:
    n = 0

    def _sub(m):
        nonlocal n
        n += 1
        return f"## {m.group(1).strip()}"

    return RE_SLUGLINE.sub(_sub, text), n


def demote_body_h1(text: str) -> tuple[str, int]:
    """Keep only the first '# ' as the document root; demote later ones to '## '."""
    seen = False
    out, n = [], 0
    for line in text.split("\n"):
        if line.startswith("# "):
            if seen:
                out.append("#" + line)
                n += 1
                continue
            seen = True
        out.append(line)
    return "\n".join(out), n


def split_frontmatter(text: str) -> tuple[str, str]:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[: end + 5], text[end + 5:]
    return "", text


def repair(path: Path, apply: bool, quiet: bool) -> None:
    original = path.read_text(encoding="utf-8")
    front, body = split_frontmatter(original)

    body, pages = strip_page_numbers(body)
    body, demoted = demote_body_h1(body)
    body, chapters = promote_chapters(body)
    sluglines = 0
    if body.count("## ") == 0:
        body, sluglines = promote_sluglines(body)

    body = re.sub(r"\n{3,}", "\n\n", body)
    new = front + body

    changed = new != original
    parts = []
    if pages:     parts.append(f"{pages} page numbers removed")
    if demoted:   parts.append(f"{demoted} stray h1 demoted")
    if chapters:  parts.append(f"{chapters} chapter headings")
    if sluglines: parts.append(f"{sluglines} scene headings")

    if not quiet:
        status = ", ".join(parts) if parts else "no change"
        print(f"{'APPLY ' if (apply and changed) else 'dry   '}{path.name[:56]:58} {status}")

    if apply and changed:
        path.write_text(new, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    files = args.files or [Path(p) for p in sorted(glob.glob("knowledge_base/books/*.md"))]
    for f in files:
        if f.is_file():
            repair(f, args.apply, args.quiet)


if __name__ == "__main__":
    main()
