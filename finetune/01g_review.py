#!/usr/bin/env python3
"""Review the dataset's targets by hand: keep, drop or rewrite each one.

The builder's gate removes every register that can be named; whether the
rest sounds like Kaia takes a person. Each decision is appended to
`dataset/review.jsonl`, keyed by the target's text, and `01_convert_logs.py`
applies it on every rebuild, so a review is never lost to a rebuild.

    python finetune/01g_review.py              # next unreviewed targets, train and eval
    python finetune/01g_review.py --stats      # how far the review has got

Keys: k keep · d drop · e rewrite in $EDITOR · s skip · q quit.
Rebuild afterwards: `01_convert_logs.py --apply` (add `--reviewed-only` to
train on reviewed targets alone).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kaia_quality as q  # noqa: E402


def targets():
    """(context messages, target) for every model turn in train and eval."""
    for name in ("train.jsonl", "eval.jsonl"):
        path = HERE / "dataset" / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            msgs = json.loads(line)["messages"]
            for i, m in enumerate(msgs):
                if m["role"] == "assistant":
                    yield [x for x in msgs[1:i] if x["role"] != "system"], m["content"]


def record(key: str, decision: str, text: str | None = None) -> None:
    q.REVIEW_FILE.parent.mkdir(parents=True, exist_ok=True)
    rec = {"key": key, "decision": decision, "at": int(time.time())}
    if text is not None:
        rec["text"] = text
    with open(q.REVIEW_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def rewrite(text: str) -> str | None:
    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
        f.write(text)
        name = f.name
    try:
        subprocess.call([os.environ.get("EDITOR", "nano"), name])
        new = Path(name).read_text(encoding="utf-8").strip()
    finally:
        os.unlink(name)
    return new if new and new != text.strip() else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    q.quiet()
    reviews = q.load_reviews()
    all_targets = list(targets())
    if args.stats:
        done = sum(1 for _, t in all_targets if q.review_key(t) in reviews)
        by = {}
        for r in reviews.values():
            by[r["decision"]] = by.get(r["decision"], 0) + 1
        print(f"{done} of {len(all_targets)} targets reviewed; decisions on file: {by}")
        return 0

    pending = [(c, t) for c, t in all_targets if q.review_key(t) not in reviews]
    print(f"{len(pending)} targets to review. k keep · d drop · e rewrite · s skip · q quit\n")
    for n, (context, target) in enumerate(pending, 1):
        print("─" * 72)
        for m in context[-4:]:
            who = "them" if m["role"] == "user" else "kaia"
            print(f"  {who}: {m['content'][:400]}")
        print(f"\n  KAIA ▸ {target}\n")
        while True:
            choice = input(f"[{n}/{len(pending)}] k/d/e/s/q: ").strip().lower()
            key = q.review_key(target)
            if choice == "k":
                record(key, "keep")
            elif choice == "d":
                record(key, "drop")
            elif choice == "e":
                new = rewrite(target)
                if new is None:
                    print("  unchanged; choose again")
                    continue
                record(key, "edit", new)
            elif choice == "q":
                return 0
            elif choice != "s":
                continue
            break
    print("\nall reviewed. Rebuild: python finetune/01_convert_logs.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
