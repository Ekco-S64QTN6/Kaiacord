#!/usr/bin/env python3
"""
tools/maintenance/clean_hallucinations.py

Scan the user logs for contaminated phrasing and report where it appears.

Reports by default. Nothing is written without `--apply`, and even then only
Kaia's own lines are ever touched — see below for why that matters.

Two bugs made the previous version both broken and dangerous:

  * Every pattern carried an inline `(?i)` flag and was then interpolated into
    the middle of `rf"^.*{keyword}.*$\\n"`. Python 3.11+ rejects a global flag
    that is not at the start of the expression, so the tool crashed with
    `re.error: global flags not at the start of the expression` before doing
    anything. That crash is what the operator reported.
  * The kaia-tools menu invokes it as "Find Contamination (scan only)" with
    `--dry-run`, and the script parsed no arguments at all. Had the regex
    worked it would have silently rewritten user log files, deleting every
    matching line. The crash is the only reason it never did.

And the deletion would have been wrong on the merits. The one line in the
corpus matching the default patterns is a *user* quoting a news article about
Russia — real conversation, not a hallucination. A tool that edits a person's
own words out of their log to clean up the bot's mistakes is doing something
nobody asked for, so it now refuses to consider user-authored lines at all.
"""
import argparse
import re
import sys
from pathlib import Path

LOGS_DIR = Path("./knowledge_base/user_logs")

# Phrasing from a past contamination incident. These are ordinary words in
# ordinary conversation — "Eurasia" is a real place and an Orwell reference —
# so a match is a prompt to look, never a reason to delete on its own.
DEFAULT_PATTERNS = [
    r"\bEurasian?\b",
    r"\bPan-Pacific\b",
]

# Log lines look like: [2026-08-29 15:22:21] Lune: text
SPEAKER = re.compile(r"^\[\d{4}-\d\d-\d\d[^\]]*\]\s*([^:]{1,64}):")


def speaker_of(line: str) -> str | None:
    m = SPEAKER.match(line)
    return m.group(1).strip() if m else None


def scan_file(path: Path, patterns: list[re.Pattern], bot_name: str):
    """Yield (line_no, speaker, line) for every matching line."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        print(f"  ! could not read {path}: {e}", file=sys.stderr)
        return

    current = None
    for i, line in enumerate(lines, 1):
        who = speaker_of(line)
        if who:
            current = who
        if any(p.search(line) for p in patterns):
            yield i, current, line


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="actually remove matching lines (default: report only)")
    ap.add_argument("--dry-run", action="store_true",
                    help="explicit no-op; reporting is already the default")
    ap.add_argument("--bot-name", default="Kaia",
                    help="speaker whose lines may be edited (default: Kaia)")
    ap.add_argument("--pattern", action="append", metavar="REGEX",
                    help="override the default patterns (repeatable)")
    ap.add_argument("--logs-dir", default=str(LOGS_DIR))
    args = ap.parse_args()

    patterns = [re.compile(p, re.IGNORECASE)
                for p in (args.pattern or DEFAULT_PATTERNS)]
    logs = Path(args.logs_dir)
    if not logs.exists():
        print(f"No such directory: {logs}")
        return 1

    files = sorted(logs.rglob("*.md"))
    hits = theirs = ours = changed = 0

    for path in files:
        matches = list(scan_file(path, patterns, args.bot_name))
        if not matches:
            continue
        rel = path.relative_to(logs)
        print(f"\n{rel}")
        removable = []
        for line_no, who, line in matches:
            hits += 1
            is_bot = (who or "").lower() == args.bot_name.lower()
            if is_bot:
                ours += 1
                removable.append(line_no)
            else:
                theirs += 1
            tag = "kaia" if is_bot else f"{who or 'unknown'} — user, left alone"
            print(f"  line {line_no} [{tag}]: {line.strip()[:150]}")

        if args.apply and removable:
            text = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            path.with_suffix(path.suffix + ".bak").write_text(
                "".join(text), encoding="utf-8")
            kept = [l for i, l in enumerate(text, 1) if i not in set(removable)]
            path.write_text("".join(kept), encoding="utf-8")
            print(f"  removed {len(removable)} line(s); backup at {rel}.bak")
            changed += 1

    print(f"\nScanned {len(files)} files. {hits} matching line(s): "
          f"{ours} from {args.bot_name}, {theirs} from users.")
    if theirs:
        print(f"User-authored lines are never modified — a person quoting an "
              f"article is not the bot hallucinating.")
    if not args.apply:
        print("Report only. Re-run with --apply to remove "
              f"{args.bot_name}'s matching lines (a .bak is written first).")
    elif not changed:
        print("Nothing to remove.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
