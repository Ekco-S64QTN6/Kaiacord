#!/usr/bin/env python3
"""
tools/maintenance/compact_user_logs.py

Normalise user transcripts into something retrieval can actually use.

No model is involved. Everything here is a deterministic rewrite with an exact
inverse in the backup directory, because the last tool that asked a model to
"clean" these files rewrote `[2026-03-12 14:22:01] Ekco:` into `User:` across
774 of them and took the timestamps with it.

The format is the contract. `ConversationTurnSplitter` chunks on
`[YYYY-MM-DD HH:MM:SS] Speaker: `, the indexer reads recency from that same
timestamp, and retrieval scopes a log to its user by that name. Every pass
below preserves all three; a pass that would remove a turn marker is a bug.

Passes, in order:

  1. scaffolding   — drop the blocks context_enricher appends to the *prompt*
                     ([ATTACHED_EMBED_CONTEXT], [LINKED_WEB_CONTENT],
                     [CORE_DIRECTIVE], scrape warnings), keeping the page title
                     as a one-line citation.
  2. link dumps    — the same thing from before those markers existed: a pasted
                     URL followed by the whole scraped article, attributed to
                     whoever pasted it. 249 such turns held 29% of all
                     user-turn text.
  3. preamble      — a previous cleaner narrated its task into the corpus
                     ("Okay, here's the cleaned chat log...").
  4. fragments     — navigation debris left by scraping: lone label lines
                     ("TOPIC:"), orphaned single words, bare punctuation.
  5. whitespace    — collapse the runs the passes above leave behind.

Idempotent: running it twice changes nothing the second time.

    python tools/maintenance/compact_user_logs.py            # report
    python tools/maintenance/compact_user_logs.py --apply
    python tools/maintenance/compact_user_logs.py --user Ekco --apply
"""
import argparse
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

USER_LOGS = ROOT / "knowledge_base" / "user_logs"
BACKUP = ROOT / "memory" / "log_compaction_backup"

TURN = re.compile(r"^(\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\] [^:\n]+: )(.*?)(?=^\[\d{4}-|\Z)",
                  re.M | re.S)
TURN_MARKER = re.compile(r"^\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\] [^:\n]+: ", re.M)
URL = re.compile(r"https?://\S+")

PREAMBLE = re.compile(
    r"^[ \t]*(?:okay,?\s*)?(?:here'?s|here is|below is)\b[^\n]*"
    r"(?:cleaned|sanitiz|chat log|instructions|focusing on)[^\n]*\n+", re.I | re.M)
CLEANED_HEADER = re.compile(r"^\s*\*\*CLEANED LOG\b[^\n]*\*\*\s*\n+", re.I | re.M)

MIN_DUMP = 800          # a person does not type this much around a link


def speaker_of(head: str) -> str:
    return head.rstrip().rstrip(":").split("] ", 1)[-1].strip()


def link_title(lines, url_idx) -> str:
    """The page title: the first substantial line after the URL."""
    for line in lines[url_idx + 1:]:
        s = line.strip()
        if not s or s.startswith("["):
            continue
        if len(s) < 12 or s.endswith(":") or " " not in s:
            continue          # a navigation fragment, not a title
        return re.sub(r"\s+", " ", s)[:120]
    return ""


def compact_link_dump(body: str) -> str:
    # Already compacted: leave it exactly as it is. Without this the pass is
    # not idempotent and, worse, is lossy in the one place it matters. A turn
    # whose text *before* the URL already exceeds MIN_DUMP still qualifies on a
    # second run, and by then the line after the URL is the citation this pass
    # added — which link_title() skips as a bracket line, so the rebuilt turn
    # comes back without it. Running the menu item twice silently deleted the
    # page titles the first run had gone to the trouble of recovering.
    if "[shared link:" in body:
        return body
    if len(body) < MIN_DUMP or not URL.search(body):
        return body
    lines = body.split("\n")
    idx = next((i for i, l in enumerate(lines) if URL.search(l)), None)
    if idx is None:
        return body
    out = "\n".join(lines[:idx + 1]).rstrip()
    title = link_title(lines, idx)
    if title:
        out += f"\n[shared link: {title}]"
    return out + "\n\n"


def drop_fragments(body: str) -> str:
    """Remove scrape debris while leaving anything a person would type.

    Only fires inside a turn that already carries a link citation, so ordinary
    short replies ("yeah", "lol", "Ra willing") are never touched.
    """
    if "[shared link:" not in body:
        return body
    keep = []
    for line in body.split("\n"):
        s = line.strip()
        if not s or s.startswith("[") or URL.search(s):
            keep.append(line)
            continue
        is_label = s.endswith(":") and len(s) < 40
        is_orphan = " " not in s and len(s) < 40
        is_punct = not any(c.isalnum() for c in s)
        if is_label or is_orphan or is_punct:
            continue
        keep.append(line)
    return "\n".join(keep)


def compact_text(text: str) -> tuple[str, Counter]:
    from utils.core.sanitizer import summarize_link_context

    stats = Counter()
    before_markers = len(TURN_MARKER.findall(text))

    text = CLEANED_HEADER.sub("", text)
    new = PREAMBLE.sub("", text)
    if new != text:
        stats["preamble"] += 1
    text = new

    def _turn(m):
        head, body = m.group(1), m.group(2)
        if speaker_of(head).lower() == "kaia":
            return m.group(0)
        # Each pass runs only when its own marker is present, and the turn is
        # left byte-identical otherwise. A cosmetic rewrite of every file is
        # 1,100 needless diffs and a reindex of the whole corpus.
        from utils.core.sanitizer import RUNTIME_SCAFFOLDING

        trailing = body[len(body.rstrip()):]      # preserve the original spacing
        core = body.rstrip()

        if RUNTIME_SCAFFOLDING.search(core):
            core = summarize_link_context(core)
            stats["scaffolding"] += 1

        after = compact_link_dump(core)
        if after.rstrip() != core:
            core = after.rstrip()
            stats["link_dump"] += 1

        after = drop_fragments(core)
        if after != core:
            core = after
            stats["fragments"] += 1

        return head + core + trailing

    text = TURN.sub(_turn, text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    # The contract: never lose a turn marker.
    after_markers = len(TURN_MARKER.findall(text))
    if after_markers != before_markers:
        raise AssertionError(
            f"pass would change turn-marker count {before_markers} -> {after_markers}")
    return text, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the changes")
    ap.add_argument("--user", help="limit to one user directory (substring match)")
    ap.add_argument("--include-forum", action="store_true",
                    help="also process forum_* directories")
    args = ap.parse_args()

    if not USER_LOGS.exists():
        print(f"No such directory: {USER_LOGS}")
        return 1

    totals, files, touched, saved = Counter(), 0, 0, 0
    for f in sorted(USER_LOGS.glob("*/interactions_*.md")):
        if f.parent.name.startswith("forum_") and not args.include_forum:
            continue
        if args.user and args.user.lower() not in f.parent.name.lower():
            continue
        files += 1
        text = f.read_text(encoding="utf-8", errors="replace")
        try:
            new_text, stats = compact_text(text)
        except AssertionError as e:
            print(f"  ! skipped {f.parent.name}/{f.name}: {e}")
            continue
        if new_text == text:
            continue
        touched += 1
        saved += len(text) - len(new_text)
        totals.update(stats)
        if args.apply:
            dest = BACKUP / f.parent.name
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest / f.name)
            f.write_text(new_text, encoding="utf-8")

    print(f"scanned {files} transcripts, {touched} would change" if not args.apply
          else f"scanned {files} transcripts, {touched} changed")
    for k in ("scaffolding", "link_dump", "fragments", "preamble"):
        if totals[k]:
            print(f"  {k:12} {totals[k]} turns")
    print(f"  {saved:,} characters removed")
    if args.apply:
        print(f"\noriginals copied to {BACKUP}")
        print("Run a reindex (tools/trigger_reindex.py) to pick up the changes.")
    else:
        print("\n(dry run — nothing written. re-run with --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
