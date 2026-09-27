#!/usr/bin/env python3
"""Check the dataset before a GPU hour is spent on it. Read-only.

`run_finetune.sh` runs this and stops if it exits non-zero. It checks what
`01_convert_logs.py` guarantees, against the filters and rules as they are
today, so a dataset built before a rule changed, or edited by hand, cannot
reach training unnoticed:

* every target passes `kaia_quality.clean_target` unchanged (hand-written
  identity answers and reviewed rewrites are trusted);
* no target appears twice, and none appears in both train and eval;
* every example fits the training window in real tokens;
* user turns hold what a person typed: no enricher blocks, no links, no
  placeholder prompts.

    python finetune/01f_check_dataset.py          # report; exit 1 on any finding
    python finetune/01f_check_dataset.py --show 5 # print up to five examples of each finding

The fix for a finding is to rebuild (`01_convert_logs.py --apply`), not to
edit the files: a rebuild applies every rule and every review decision.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kaia_quality as q  # noqa: E402
from utils.core.sanitizer import strip_runtime_scaffolding  # noqa: E402


def _builder():
    spec = importlib.util.spec_from_file_location("ft_builder", HERE / "01_convert_logs.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ft_builder"] = mod
    spec.loader.exec_module(mod)
    return mod


def check(rows: dict[str, list[dict]], trusted: set[str]) -> dict[str, list[str]]:
    findings: dict[str, list[str]] = defaultdict(list)
    where: dict[str, set[str]] = defaultdict(set)
    counts: Counter = Counter()
    for split, examples in rows.items():
        for n, ex in enumerate(examples, 1):
            msgs = ex.get("messages", [])
            label = f"{split}:{n}"
            if q.example_tokens(msgs) > q.TRAIN_MAX_TOKENS:
                findings["over_token_window"].append(label)
            for m in msgs:
                text = m.get("content") or ""
                if m["role"] == "user":
                    if strip_runtime_scaffolding(text) != text.strip() or "[continue the conversation]" in text:
                        findings["user_turn_scaffolding"].append(f"{label} {text[:80]!r}")
                    elif q._URL.search(text):
                        findings["user_turn_link"].append(f"{label} {text[:80]!r}")
                elif m["role"] == "assistant":
                    key = text.strip().lower()
                    counts[key] += 1
                    where[key].add(split)
                    if text.strip() in trusted:
                        continue
                    cleaned, why = q.clean_target(text)
                    if cleaned is None:
                        findings[f"target_{why}"].append(f"{label} {text[:80]!r}")
                    elif cleaned != text.strip():
                        findings["target_changed_by_filters"].append(f"{label} {text[:80]!r}")
    findings["duplicate_target"] = [k[:80] for k, c in counts.items() if c > 1]
    findings["in_train_and_eval"] = [k[:80] for k, s in where.items() if len(s) > 1]
    return {k: v for k, v in findings.items() if v}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--show", type=int, default=3, help="examples to print per finding")
    args = ap.parse_args()

    q.quiet()
    rows = {}
    for split in ("train", "eval"):
        path = HERE / "dataset" / f"{split}.jsonl"
        if not path.exists():
            print(f"error: {path} not found. Build it: python finetune/01_convert_logs.py --apply",
                  file=sys.stderr)
            return 1
        rows[split] = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    trusted = {a for _, a in _builder().IDENTITY}
    trusted |= {r["text"].strip() for r in q.load_reviews().values() if r["decision"] == "edit"}

    print(f"train {len(rows['train'])} examples, eval {len(rows['eval'])}")
    findings = check(rows, trusted)
    if not findings:
        print("OK: every target passes today's rules; no duplicates, leaks or overlong examples.")
        return 0
    for name, items in sorted(findings.items()):
        print(f"\n{name}: {len(items)}")
        for item in items[:args.show]:
            print(f"  {item}")
    print("\nFAIL: rebuild the dataset: python finetune/01_convert_logs.py --apply", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
