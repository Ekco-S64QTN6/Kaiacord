#!/usr/bin/env python3
"""Drop stored relationship events the current detector would not have recorded.

`detect_event_type` used to match substrings over the whole enriched turn, so
"actually" was a correction, "fair enough" was friction, and fetched pages and
forum thread dumps counted as the user speaking. Those events are still in
memory/relationships/ and still ranked into her relationship notes.

Repair and friction events are kept only if the detector finds the same type in
the stored summary. Positive events are kept unless the summary is plainly not
the user's words (a thread dump, a scraped page, quoted reply context): the
summary is cut at 120 characters, so a positive signal later in the message
cannot be re-checked and absence of evidence is not evidence here.

Dry run by default. --apply copies each changed file to <file>.bak first.
"""
import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.core.atomic_write import write_atomic  # noqa: E402
from utils.core.relationship_manager import RELATIONSHIPS_DIR, detect_event_type  # noqa: E402

NOT_THE_USER = ("THREAD TITLE:", "[LINKED_WEB_CONTENT]", "[REPLYING_TO]")


def keep(event: dict) -> bool:
    summary = str(event.get("summary", ""))
    kind = event.get("event_type")
    if kind in ("repair", "friction"):
        return detect_event_type(summary.removesuffix("..."), "") == kind
    return not any(marker in summary for marker in NOT_THE_USER)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="rewrite the files (default: report only)")
    args = ap.parse_args()

    tally = Counter()
    for path in sorted(Path(RELATIONSHIPS_DIR).glob("*.json")):
        events = json.loads(path.read_text(encoding="utf-8"))
        kept = [e for e in events if keep(e)]
        for e in events:
            tally[(e.get("event_type"), "kept" if e in kept else "dropped")] += 1
        if len(kept) != len(events):
            print(f"{path.name}: {len(events)} -> {len(kept)}")
            if args.apply:
                shutil.copy2(path, path.with_suffix(".json.bak"))
                write_atomic(path, json.dumps(kept, indent=2))

    for (kind, outcome), n in sorted(tally.items()):
        print(f"  {kind:9} {outcome:8} {n}")
    if not args.apply:
        print("dry run — pass --apply to rewrite (each changed file is backed up as .json.bak)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
