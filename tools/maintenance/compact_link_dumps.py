#!/usr/bin/env python3
"""
tools/maintenance/compact_link_dumps.py

Replace scraped article bodies inside user turns with a one-line citation.

When a user pasted a URL, `context_enricher` appended the page scrape or the
Discord embed to the message so the model had something to read — and the whole
lot was then written to the transcript as though the user had typed it. In
`interactions_20260629.md` a message reading "Kaia, <cern url>" is followed by
forty lines of the article, including navigation fragments ("TOPIC:",
"Accelerators", a lone em dash) and sentences truncated mid-word.

Across the corpus: **249 user turns, holding 29% of all user-turn text.** For
retrieval this is three problems at once — the article is attributed to the
person who linked it, the conversational content around it is diluted inside
its chunk, and the same article may already be indexed properly under
`knowledge_base/documents`.

What survives is what the user actually contributed: their own words, the URL,
and the page title, which is the only part of a link that carries topic for an
embedding. A bare URL retrieves nothing.

    python tools/maintenance/compact_link_dumps.py          # report
    python tools/maintenance/compact_link_dumps.py --apply
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

USER_LOGS = ROOT / "knowledge_base" / "user_logs"
BACKUP = ROOT / "memory" / "link_dump_backup"

TURN = re.compile(r"^(\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\] [^:\n]+: )(.*?)(?=^\[\d{4}-|\Z)",
                  re.M | re.S)
URL = re.compile(r"https?://\S+")
MIN_DUMP = 800          # a person does not type this much around a link


def pick_title(lines: list[str], url_line_idx: int) -> str:
    """The page title: the first substantial line after the URL."""
    for line in lines[url_line_idx + 1:]:
        s = line.strip()
        if not s or s.startswith("["):
            continue
        # Skip navigation fragments: single words, bare punctuation, labels.
        if len(s) < 12 or s.endswith(":") or " " not in s:
            continue
        return re.sub(r"\s+", " ", s)[:120]
    return ""


def compact_turn(body: str) -> tuple[str, bool]:
    # Superseded by compact_user_logs.py, which runs this pass alongside the
    # others. Kept for the one-shot case, with the same idempotency guard: on a
    # re-run the line after the URL is the citation this added, pick_title()
    # skips it as a bracket line, and the turn is rebuilt without it — so a
    # second run deleted the page titles the first run recovered.
    if "[shared link:" in body:
        return body, False
    if len(body) < MIN_DUMP or not URL.search(body):
        return body, False

    lines = body.split("\n")
    url_idx = next((i for i, l in enumerate(lines) if URL.search(l)), None)
    if url_idx is None:
        return body, False

    # Everything up to and including the line carrying the URL is the user's.
    kept = [l for l in lines[:url_idx + 1]]
    title = pick_title(lines, url_idx)
    out = "\n".join(kept).rstrip()
    if title:
        out += f"\n[shared link: {title}]"
    return out + "\n\n", True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    files = touched = turns = 0
    saved = 0
    for f in sorted(USER_LOGS.glob("*/interactions_*.md")):
        if f.parent.name.startswith("forum_"):
            continue
        files += 1
        text = f.read_text(encoding="utf-8", errors="replace")
        changed = False
        local = 0

        def _sub(m):
            nonlocal changed, local, saved
            head, body = m.group(1), m.group(2)
            if head.rstrip().endswith("Kaia:"):
                return m.group(0)
            new_body, did = compact_turn(body)
            if did:
                changed = True
                local += 1
                saved += len(body) - len(new_body)
                return head + new_body
            return m.group(0)

        new_text = TURN.sub(_sub, text)
        if changed:
            touched += 1
            turns += local
            if args.apply:
                dest = BACKUP / f.parent.name
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest / f.name)
                f.write_text(new_text, encoding="utf-8")

    print(f"scanned {files} transcripts")
    print(f"  {turns} link-dump turns in {touched} files")
    print(f"  {saved:,} characters of scraped article text removed from user turns")
    if args.apply:
        print(f"\nwritten. originals copied to {BACKUP}")
    else:
        print("\n(dry run — nothing written. re-run with --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
