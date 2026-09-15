#!/usr/bin/env python3
"""Give badly-named knowledge-base documents a real topic and title.

`knowledge_base/documents/` follows "<Topic> - <Title>.md" (CLAUDE.md §10), and
the topic doubles as the frontmatter `category`. Files that arrive through
`!download` did not get that: `process_ingress` hardcoded `category: Reference`
and named the file after whatever title it could find, which for a pasted block
of text was the opening words. One document ended up as

    Kaia_another_system_worked_on_your_code_today_and_you_should_know_what_
    changed_before_you_notice_it.md

with that same sentence as its title, its summary, and every one of its
keywords. This retitles those files in place.

    python tools/maintenance/retitle_documents.py                  # dry run
    python tools/maintenance/retitle_documents.py --apply
    python tools/maintenance/retitle_documents.py --folder blogs --apply

Dry run by default: it renames files and rewrites frontmatter, and a maintenance
tool that writes across the corpus should never do that on invocation alone.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.maintenance.process_ingress import (  # noqa: E402
    KNOWN_TOPICS, derive_topic_and_title, safe_display_stem,
)

KB = Path("knowledge_base")
# "<Topic> - <Title>.md" with a topic that is words, not a date or a slug.
# The hyphen must be allowed inside the topic or "Sci-Fi - ..." reads as
# non-conforming and gets needlessly renamed on every run.
CONFORMING = re.compile(r"^[A-Z][A-Za-z0-9&'. -]{1,28} - .+\.md$")


def is_conforming(name: str) -> bool:
    return bool(CONFORMING.match(name))


def read_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_including_fences, body)."""
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", text
    return text[: end + 4], text[end + 4:].lstrip("\n")


def rewrite_field(front: str, field: str, value: str) -> str:
    """Replace a scalar frontmatter field, adding it if absent."""
    pattern = re.compile(rf"^{field}:.*$", re.M)
    line = f'{field}: "{value}"'
    if pattern.search(front):
        return pattern.sub(line, front, count=1)
    return front.replace("---\n", f"---\n{line}\n", 1)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", default="documents",
                    help="folder under knowledge_base/ (default: documents)")
    ap.add_argument("--apply", action="store_true",
                    help="actually rename and rewrite (default: dry run)")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    target = KB / args.folder
    if not target.is_dir():
        print(f"no such folder: {target}")
        return 1

    candidates = [p for p in sorted(target.glob("*.md")) if not is_conforming(p.name)]
    if args.limit:
        candidates = candidates[: args.limit]

    if not candidates:
        print(f"{target}: every filename already conforms.")
        return 0

    print(f"{target}: {len(candidates)} file(s) to retitle "
          f"{'(DRY RUN)' if not args.apply else ''}\n")

    changed = 0
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="replace")
        front, body = read_frontmatter(text)
        topic, title, summary, keywords = derive_topic_and_title(body, path.stem.replace("_", " "))
        if not title or topic == "Reference":
            print(f"  SKIP  {path.name[:70]}  (no confident topic)")
            continue

        new_name = safe_display_stem(f"{topic} - {title}") + ".md"
        if new_name == path.name:
            continue
        dest = path.with_name(new_name)
        n = 2
        while dest.exists() and dest != path:
            dest = path.with_name(f"{safe_display_stem(f'{topic} - {title}')} ({n}).md")
            n += 1

        print(f"  {path.name[:64]}")
        print(f"    -> {dest.name}")
        print(f"       topic={topic!r}")

        if args.apply:
            if front:
                front = rewrite_field(front, "title", title)
                front = rewrite_field(front, "category", topic)
                new_text = front + "\n\n" + body
            else:
                new_text = text
            tmp = path.with_suffix(".tmp")
            tmp.write_text(new_text, encoding="utf-8")
            tmp.replace(path)          # atomic content rewrite
            path.rename(dest)
        changed += 1

    print(f"\n{changed} file(s) {'retitled' if args.apply else 'would be retitled'}.")
    if not args.apply:
        print("Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
