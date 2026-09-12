#!/usr/bin/env python3
"""
tools/maintenance/repair_flattened_user_logs.py

Restore the structure that kb_cleanse_user_logs.py removed from the transcripts.

That script asked a model to rewrite each log into a "clean 'User: ...' /
'Kaia: ...' pattern". It did exactly that, and in doing so deleted the three
things the retrieval layer runs on:

  * **Turn markers.** ConversationTurnSplitter splits on
    `[YYYY-MM-DD HH:MM:SS] Name: `. With none present a whole day's
    conversation is one blob, and the indexer falls back to blind 500-character
    sliding windows — 848 of 1,112 files.
  * **Timestamps.** The indexer reads a chunk's timestamp out of that same
    marker. Without it, recency decay falls back to filesystem mtime, which the
    rewrite itself had just set to the day the script ran: a March conversation
    was dated July.
  * **Speaker identity.** "Ekco:" became "User:", so per-user retrieval
    isolation, attribution and relationship memory had nothing to key on.

Some files also carry the model's own preamble ("Okay, here's the cleaned chat
log, adhering to your instructions:").

What this restores, and what it cannot:

  * The date comes from the filename, so it is exact.
  * The clock time within that day is gone for good. Turns are laid out from
    00:00 at one-minute steps, which preserves order and is honest to the day.
    `reconstructed_times: true` is written into the frontmatter so nothing
    downstream mistakes them for original precision.
  * The speaker name comes from the directory, so "User:" resolves correctly.

    python tools/maintenance/repair_flattened_user_logs.py            # report
    python tools/maintenance/repair_flattened_user_logs.py --apply    # repair
"""
import argparse
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

USER_LOGS = ROOT / "knowledge_base" / "user_logs"

TURN_MARKER = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]", re.M)
SPEAKER_LINE = re.compile(r"^(User|Kaia|Assistant)\s*:\s*(.*)$", re.I)
DATE_IN_NAME = re.compile(r"interactions_(\d{4})(\d{2})(\d{2})\.md$")

# The model narrated its own task before answering, in several phrasings:
# "Okay, here's the cleaned chat log, adhering to your instructions:",
# "...focusing on factual information...", "...following your instructions."
# Anchored to a line that both announces a result and names the job.
PREAMBLE = re.compile(
    r"^[ \t]*(?:okay,?\s*)?(?:here'?s|here is|below is)\b[^\n]*"
    r"(?:cleaned|sanitiz|chat log|instructions|focusing on)[^\n]*\n+",
    re.I | re.M)


def speaker_for(directory: str) -> str:
    """"Ekco_177011971818782721" -> "Ekco"."""
    return directory.rsplit("_", 1)[0].replace("_", " ").strip() or "User"


def needs_repair(text: str) -> bool:
    return not TURN_MARKER.search(text)


def split_frontmatter(text: str):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[:end + 4], text[end + 4:]
    return "", text


def repair(text: str, day: datetime, real_name: str) -> tuple[str, int]:
    front, body = split_frontmatter(text)
    body = PREAMBLE.sub("", body.lstrip(), count=1)

    out, turns, clock = [], 0, day
    for raw in body.split("\n"):
        m = SPEAKER_LINE.match(raw.strip())
        if m:
            who, rest = m.group(1), m.group(2)
            name = real_name if who.lower() in ("user",) else "Kaia"
            if who.lower() == "assistant":
                name = "Kaia"
            out.append(f"[{clock:%Y-%m-%d %H:%M:%S}] {name}: {rest}")
            clock += timedelta(minutes=1)
            turns += 1
        else:
            out.append(raw)

    if front:
        if "reconstructed_times:" not in front:
            front = front.rstrip()[:-3].rstrip() + \
                "\nreconstructed_times: true\n---"
    else:
        front = ("---\nsummary: \"\"\nkeywords: []\ndocument_type: Transcript\n"
                 "reconstructed_times: true\n---")

    return front + "\n\n" + "\n".join(out).strip() + "\n", turns


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the repairs")
    ap.add_argument("--backup", default=str(ROOT / "memory" / "log_repair_backup"),
                    help="where the originals are copied before writing")
    args = ap.parse_args()

    if not USER_LOGS.exists():
        print(f"No such directory: {USER_LOGS}")
        return 1

    backup = Path(args.backup)
    scanned = repaired = turns_total = skipped_nostruct = 0

    for f in sorted(USER_LOGS.glob("*/interactions_*.md")):
        if f.parent.name.startswith("forum_"):
            continue
        scanned += 1
        text = f.read_text(encoding="utf-8", errors="replace")
        if not needs_repair(text):
            continue

        m = DATE_IN_NAME.search(f.name)
        if not m:
            continue
        day = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))

        new_text, turns = repair(text, day, speaker_for(f.parent.name))
        if turns == 0:
            # Nothing recognisable as a turn — leave it rather than guess.
            skipped_nostruct += 1
            continue

        repaired += 1
        turns_total += turns
        if args.apply:
            dest = backup / f.parent.name
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest / f.name)
            f.write_text(new_text, encoding="utf-8")
            # Recency decay falls back to mtime; make it the conversation's day.
            import os
            os.utime(f, (day.timestamp(), day.timestamp()))

    print(f"scanned            {scanned}")
    print(f"repairable         {repaired}  ({turns_total} turns restored)")
    print(f"no turn structure  {skipped_nostruct}  (left untouched)")
    if args.apply:
        print(f"\nwritten. originals copied to {backup}")
        print("Run a reindex so the new structure is picked up.")
    else:
        print("\n(dry run — nothing written. re-run with --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
