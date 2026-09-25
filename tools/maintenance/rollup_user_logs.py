#!/usr/bin/env python3
"""
tools/maintenance/rollup_user_logs.py

Roll closed months of daily transcripts into one archive file per month.

Not for tidiness — a day is the wrong unit for chunking. `ConversationTurnSplitter`
builds chunks of 6 turns, and **533 of 1,112 daily files hold fewer than 6
turns**, so roughly half the corpus was being chunked below the intended
granularity: thin chunks, little surrounding context, poor retrieval. Merging a
month gives the splitter enough material to form proper chunks with overlap.

Merging is lossless because every turn carries its own
`[YYYY-MM-DD HH:MM:SS] Speaker: ` marker — the date lives in the line, not the
filename, so date-scoped recall is unaffected.

Only **closed** months are rolled up. Recent days stay as daily files, because
appending a turn to a 6-month archive would re-chunk and re-embed the whole
thing on every message.

The archive takes the mtime of the last day it contains: `kaia_proactive` and
`kaia_dream` both decide what is "new" by mtime, and a freshly written archive
would otherwise look like fresh conversation and re-trigger a pass over months
of old material.

    python tools/maintenance/rollup_user_logs.py               # report
    python tools/maintenance/rollup_user_logs.py --apply
    python tools/maintenance/rollup_user_logs.py --keep-days 30 --apply
"""
import argparse
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# After sys.path.insert: `utils` is not importable until that line runs.
from utils.core.atomic_write import write_atomic  # noqa: E402

USER_LOGS = ROOT / "knowledge_base" / "user_logs"
BACKUP = ROOT / "memory" / "log_rollup_backup"

DAILY = re.compile(r"^interactions_(\d{4})(\d{2})(\d{2})\.md$")
TURN_MARKER = re.compile(r"^\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\] [^:\n]+: ", re.M)


def body_of(text: str) -> str:
    """Everything after the YAML frontmatter."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


def build_archive(user: str, month: str, days: list[Path], existing: str = "") -> tuple[str, int]:
    """The month's archive: an existing archive's body first, then these days.

    Merging matters: without it, days that arrived after a month was rolled
    up would, at the next rollup, replace the archive holding everything
    before them.
    """
    from utils.core.frontmatter import dump_frontmatter
    parts = [body_of(existing).strip()] if existing.strip() else []
    for f in sorted(days):
        body = body_of(f.read_text(encoding="utf-8", errors="replace")).strip()
        if body:
            parts.append(body)
    text = "\n\n".join(p for p in parts if p).strip()
    turns = len(TURN_MARKER.findall(text))
    pretty = f"{month[:4]}-{month[4:]}"
    merged_before = 0
    m = re.search(r"^days_merged:\s*(\d+)", existing, re.M)
    if m:
        merged_before = int(m.group(1))
    front = dump_frontmatter({
        "title": f"{user} — {pretty}", "document_type": "Transcript", "month": pretty,
        "days_merged": merged_before + len(days), "turns": turns, "archived": True,
    })
    return front + "\n" + text + "\n", turns


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--keep-days", type=int, default=7,
                    help="leave this many recent days as daily files (default 7). "
                         "Only today's file is ever appended to, so a week is "
                         "already generous head-room against re-embedding churn.")
    ap.add_argument("--user", help="limit to one user directory (substring match)")
    args = ap.parse_args()

    if not USER_LOGS.exists():
        print(f"No such directory: {USER_LOGS}")
        return 1

    cutoff = datetime.now() - timedelta(days=args.keep_days)
    made = removed = turns_total = 0

    for user_dir in sorted(p for p in USER_LOGS.iterdir() if p.is_dir()):
        if user_dir.name.startswith("forum_"):
            continue
        if args.user and args.user.lower() not in user_dir.name.lower():
            continue

        months = defaultdict(list)
        for f in user_dir.glob("interactions_*.md"):
            m = DAILY.match(f.name)
            if not m:
                continue          # already an archive, or an unusual name
            day = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            months[f"{m.group(1)}{m.group(2)}"].append((day, f))

        this_month = datetime.now().strftime("%Y%m")
        for month, entries in sorted(months.items()):
            days = [f for _, f in entries]
            newest = max(d for d, _ in entries)
            # Closed means over, not merely quiet: a month whose last day was a
            # week ago can still get tomorrow's conversation.
            if month >= this_month or newest > cutoff:
                continue
            archive = user_dir / f"interactions_{month}_archive.md"
            existing = archive.read_text(encoding="utf-8", errors="replace") if archive.exists() else ""
            if len(days) < 2 and not existing:
                continue          # nothing to gain
            text, turns = build_archive(user_dir.name, month, days, existing)
            made += 1
            removed += len(days)
            turns_total += turns

            if args.apply:
                dest = BACKUP / user_dir.name
                dest.mkdir(parents=True, exist_ok=True)
                for f in days:
                    shutil.copy2(f, dest / f.name)
                if existing:
                    shutil.copy2(archive, dest / f"{archive.name}.before-merge")
                write_atomic(archive, text)
                for f in days:
                    f.unlink()
                # Look as old as the conversation it holds, not as new as now.
                stamp = (newest + timedelta(hours=23, minutes=59)).timestamp()
                import os
                os.utime(archive, (stamp, stamp))
            else:
                print(f"  {user_dir.name}/{archive.name}  <- {len(days)} days, {turns} turns")

    verb = "created" if args.apply else "would create"
    print(f"\n{verb} {made} monthly archives from {removed} daily files "
          f"({turns_total} turns preserved)")
    if args.apply:
        print(f"originals copied to {BACKUP}")
        print("Run a reindex (tools/maintenance/reindex_rag.py --trigger) to pick up the new layout.")
    else:
        print("(dry run — nothing written. re-run with --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
