#!/usr/bin/env python3
"""Validate in-page markdown anchor links against GitHub's slug rules.

Written after Phase 73 claimed the audit report's table of contents was
verified and it was not: that check collapsed runs of hyphens, which GitHub
does not do. A heading containing an em dash or an ampersand loses the
character but keeps the spaces around it, so the anchor gets *two* hyphens.
All 18 links in audit_report.md were broken as a result.

Usage:
    python tools/maintenance/check_md_anchors.py [FILE ...]
    python tools/maintenance/check_md_anchors.py --fix docs/reports/audit_report.md

With no arguments, checks every .md file under docs/ plus the repo-root ones.
Exits non-zero if any link is broken, so it can gate a commit.
"""
import argparse
import glob
import re
import sys
from pathlib import Path

HEADING = re.compile(r'^#{1,6}\s+(.*?)\s*$')
LINK = re.compile(r'\[([^\]]+)\]\(#([^)]+)\)')
EMPHASIS = re.compile(r'[`*_]')


def slug(heading: str) -> str:
    """GitHub's algorithm: lowercase, drop everything that is not a word
    character, whitespace or hyphen, then turn spaces into hyphens.

    Crucially it does NOT collapse the resulting runs: "A — B" becomes
    "a--b", because removing the em dash leaves both of its spaces behind.
    """
    s = heading.strip().lower()
    s = re.sub(r'[^\w\s-]', '', s, flags=re.UNICODE)
    return s.replace(' ', '-')


def anchors_of(text: str) -> dict:
    """Map heading text -> anchor, numbering duplicates the way GitHub does."""
    out, seen = {}, {}
    for line in text.splitlines():
        m = HEADING.match(line)
        if not m:
            continue
        title = m.group(1)
        base = slug(title)
        n = seen.get(base, 0)
        seen[base] = n + 1
        out.setdefault(title, base if n == 0 else f"{base}-{n}")
    return out


def check(path: Path, fix: bool = False) -> int:
    text = path.read_text(encoding="utf-8")
    by_title = anchors_of(text)
    valid = set(by_title.values())
    plain = {EMPHASIS.sub('', t): a for t, a in by_title.items()}

    broken = [(lbl, tgt) for lbl, tgt in LINK.findall(text) if tgt not in valid]
    if not broken:
        print(f"OK   {path}: {len(LINK.findall(text))} in-page links resolve")
        return 0

    if fix:
        def repl(m):
            label, target = m.group(1), m.group(2)
            correct = plain.get(EMPHASIS.sub('', label))
            return f"[{label}](#{correct})" if correct else m.group(0)

        path.write_text(LINK.sub(repl, text), encoding="utf-8")
        remaining = [t for _, t in LINK.findall(path.read_text(encoding="utf-8"))
                     if t not in valid]
        print(f"FIX  {path}: repaired {len(broken) - len(remaining)} of {len(broken)}")
        return 1 if remaining else 0

    print(f"FAIL {path}: {len(broken)} broken in-page link(s)")
    for label, target in broken:
        suggestion = plain.get(EMPHASIS.sub('', label))
        hint = f" -> #{suggestion}" if suggestion else " (no matching heading)"
        print(f"       #{target}{hint}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="markdown files (default: docs/ and repo root)")
    ap.add_argument("--fix", action="store_true",
                    help="rewrite links whose label matches a heading")
    args = ap.parse_args()

    paths = [Path(f) for f in args.files] or [
        Path(p) for p in sorted(glob.glob("docs/**/*.md", recursive=True) + glob.glob("*.md"))
    ]
    return max((check(p, args.fix) for p in paths if p.is_file()), default=0)


if __name__ == "__main__":
    sys.exit(main())
