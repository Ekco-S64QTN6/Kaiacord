#!/usr/bin/env python3
"""Clean training targets through Kaia's live response filters.

**Why this stage exists.**

The long-term goal of fine-tuning is that Kaia *is* Kaia by default, so the
runtime guardrails and regex filters become unnecessary. The dataset as built
did the opposite. Measured on `dataset/train.jsonl` (2,858 assistant turns):

    26.5%  open with a bare addressee ("starkind, ...") — the single most
           frequently stripped tic in production
     3.4%  sycophancy ("your observation is remarkably astute")
     3.3%  corporate register ("noted.", "i am adjusting my parameters")
     1.2%  phantom hardware ("server hum", "caffeine levels")
    42.0%  would be MODIFIED by the live filters
     4.0%  would be REJECTED outright and regenerated

Training on those targets teaches the model to produce exactly what its own
runtime then strips. It does not merely fail to remove the guardrails — it
trains the model to need them more.

`finetune/01_convert_logs.py` carries its own 98-entry `BANNED_STRINGS` list,
which is a partial, drifting copy of what `utils/core/response_filter.py`
enforces at runtime. Two implementations of one rule; the same defect class as
the shop-price and `!help` drift fixed elsewhere in this project.

**What this does.** Every assistant turn is passed through the *actual* runtime
filter stack. The cleaned text becomes the training target, so the model learns
to emit what the pipeline would have emitted anyway — and the filters become
redundant rather than load-bearing.

Usage:
    python finetune/01f_clean_targets.py                 # report only
    python finetune/01f_clean_targets.py --apply         # rewrite in place
    python finetune/01f_clean_targets.py --apply --with-corrections
"""
from __future__ import annotations

import argparse
import json
import re
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Quiet the filters: they log a warning per strip, and we are about to make
# tens of thousands of calls.
import logging
logging.disable(logging.CRITICAL)
import utils.core.response_filter as _rf
for _n in ("log_warning", "log_info", "log_debug"):
    if hasattr(_rf, _n):
        setattr(_rf, _n, lambda *a, **k: None)

from utils.core.response_filter import (          # noqa: E402
    BotSpeakFilter,
    EmergencyContaminationFilter,
)

DATASET = Path(__file__).resolve().parent / "dataset"
CORRECTIONS = Path("memory/log_corrections.jsonl")

#: A cleaned target this short is no longer a usable example.
MIN_TARGET_CHARS = 24



# ── Training-only quality gate ───────────────────────────────────────
#
# The runtime filters are deliberately conservative: a false positive costs a
# full regeneration (~15s on the user's turn), so Phase 69 narrowed them until
# they fired on a fraction of a percent of responses. Training data needs the
# opposite disposition — a bad example is not a one-off cost, it is learned and
# amplified — so these patterns are dropped from the dataset even though the
# live filter tolerates them.
#
# Each entry is a register the persona file bans by name. Dropping the whole
# example rather than editing it: these responses are bad end to end, not
# fixable by removing a clause.
TRAINING_REJECT = {
    "sycophancy": re.compile(
        r"\b(remarkably astute|i appreciate your|your (observation|assessment|point|inquiry|"
        r"description|passing)\b[^.]{0,40}\b(is|was)\b[^.]{0,30}\b(astute|insightful|"
        r"incisive|evocative|perceptive)|thank you for (the|your) (insightful|thoughtful)|"
        r"excellent point|well[- ]observed)\b", re.I),
    "corporate_register": re.compile(
        r"(^|\n)\s*(acknowledged|affirmative|understood|noted)\.|"
        r"\bi am (adjusting|recalibrating|initiating|re-?prioritiz)|"
        r"\b(initiating|commencing) (a )?(shift|sequence|analysis|protocol)", re.I),
    "phantom_hardware": re.compile(
        r"\b(server (racks?|hum|resonan)|caffeine level|system entropy|processing cycles|"
        r"my (sensors|filters|parameters) (are|were)|internal (temperature|diagnostics))\b", re.I),
    "stuttered_prose": re.compile(r"(\b\w+\.\s+){3,}\b\w+\."),
}


def training_quality_reject(text: str) -> str | None:
    """Return the name of the register that disqualifies this target, or None."""
    for name, pattern in TRAINING_REJECT.items():
        if pattern.search(text or ""):
            return name
    return None


def clean_target(text: str, strict: bool = False) -> tuple[str | None, str]:
    """Return (cleaned_text_or_None, reason).

    None means the example should be dropped: either the live pipeline would
    have rejected this response and regenerated it, or — under `strict` — it
    carries a register the persona bans that the runtime filter tolerates.
    """
    raw = (text or "").strip()
    if not raw:
        return None, "empty"

    if EmergencyContaminationFilter.filter_response(raw) is None:
        return None, "contamination_rejected"

    cleaned = (BotSpeakFilter.harden(raw) or "").strip()
    if len(cleaned) < MIN_TARGET_CHARS:
        return None, "emptied_by_filters"

    if strict:
        bad = training_quality_reject(cleaned)
        if bad:
            return None, f"strict_{bad}"

    return cleaned, "modified" if cleaned != raw else "unchanged"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def example_signature(example: dict) -> str:
    """Identity of an example, ignoring the shared system prompt."""
    return "\x1f".join(
        f"{m.get('role')}:{(m.get('content') or '').strip()}"
        for m in example.get("messages", [])
        if m.get("role") != "system"
    )


def clean_split(examples: list[dict], strict: bool = False) -> tuple[list[dict], Counter]:
    stats = Counter()
    out = []
    for ex in examples:
        messages = ex.get("messages", [])
        keep = True
        new_messages = []
        for m in messages:
            if m.get("role") != "assistant":
                new_messages.append(m)
                continue
            cleaned, reason = clean_target(m.get("content", ""), strict=strict)
            stats[reason] += 1
            if cleaned is None:
                keep = False
                break
            new_messages.append({**m, "content": cleaned})
        if keep:
            out.append({**ex, "messages": new_messages})
        else:
            stats["examples_dropped"] += 1
    return out, stats


def correction_examples(system_prompt: str, limit: int | None = None,
                        strict: bool = False) -> list[dict]:
    """Turn the audit's bad→good pairs into training examples.

    `memory/log_corrections.jsonl` holds 271 records produced by the September
    persona audit: for each corrected turn, the text Kaia produced and the text
    she should have produced. Only the corrected side is used as a target — a
    preference pair would need DPO, and this is supervised fine-tuning — but
    these are the highest-signal examples available, because a human decided
    each one.
    """
    if not CORRECTIONS.exists():
        return []
    out = []
    for line in CORRECTIONS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        corrected = (rec.get("corrected") or "").strip()
        if len(corrected) < MIN_TARGET_CHARS:
            continue
        cleaned, _reason = clean_target(corrected, strict=strict)
        if cleaned is None:
            continue
        reason = (rec.get("reason") or "").strip()
        prompt = rec.get("prompt") or rec.get("query") or ""
        if not prompt:
            # No user turn was recorded; frame it as the correction it is.
            prompt = f"[continue the conversation]{(' — ' + reason) if reason else ''}"
        out.append({"messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": cleaned},
        ]})
        if limit and len(out) >= limit:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="rewrite the dataset in place")
    ap.add_argument("--with-corrections", action="store_true",
                    help="append examples from memory/log_corrections.jsonl")
    ap.add_argument("--strict", action="store_true",
                    help="also drop registers the persona bans that the runtime "
                         "filter tolerates (sycophancy, corporate register, "
                         "phantom hardware, stuttered prose)")
    args = ap.parse_args()

    train_path, eval_path = DATASET / "train.jsonl", DATASET / "eval.jsonl"
    if not train_path.exists():
        print(f"error: {train_path} not found", file=sys.stderr)
        return 1

    train, evaluation = load(train_path), load(eval_path) if eval_path.exists() else []
    system_prompt = next(
        (m["content"] for m in train[0]["messages"] if m.get("role") == "system"), ""
    )

    print(f"before: train {len(train)}, eval {len(evaluation)}")

    train_clean, train_stats = clean_split(train, strict=args.strict)
    eval_clean, eval_stats = clean_split(evaluation, strict=args.strict)

    # Deduplicate within train, then remove anything that also appears in eval.
    # 59 duplicates existed inside train and 8 examples appeared in both, which
    # inflates eval scores.
    seen, deduped = set(), []
    for ex in train_clean:
        sig = example_signature(ex)
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append(ex)
    dropped_dupes = len(train_clean) - len(deduped)

    eval_sigs = {example_signature(e) for e in eval_clean}
    before_leak = len(deduped)
    deduped = [e for e in deduped if example_signature(e) not in eval_sigs]
    leaked = before_leak - len(deduped)

    added = []
    if args.with_corrections:
        added = correction_examples(system_prompt, strict=args.strict)
        added = [a for a in added if example_signature(a) not in seen and
                 example_signature(a) not in eval_sigs]
        deduped.extend(added)

    print("\nassistant turns:")
    for key in sorted(set(train_stats) | set(eval_stats)):
        if key == "examples_dropped":
            continue
        if train_stats[key] or eval_stats[key]:
            print(f"  {key:24} train {train_stats[key]:>5}   eval {eval_stats[key]:>4}")
    print(f"\nexamples dropped (filters would have rejected): "
          f"train {train_stats['examples_dropped']}, eval {eval_stats['examples_dropped']}")
    print(f"duplicates removed from train: {dropped_dupes}")
    print(f"train examples also present in eval, removed: {leaked}")
    if args.with_corrections:
        print(f"correction examples added: {len(added)}")
    print(f"\nafter: train {len(deduped)}, eval {len(eval_clean)}")

    if not args.apply:
        print("\n(dry run — nothing written. re-run with --apply)")
        return 0

    for path, rows in ((train_path, deduped), (eval_path, eval_clean)):
        if not rows and path == eval_path and not evaluation:
            continue
        shutil.copy2(path, path.with_suffix(".jsonl.pre-clean"))
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
        print(f"wrote {path}  (backup: {path.name}.pre-clean)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
