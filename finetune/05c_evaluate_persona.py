#!/usr/bin/env python3
"""Measure whether the fine-tune has internalised the persona.

**The question this answers.** The long-term goal is that Kaia *is* Kaia by
default, so the runtime guardrails and regex filters become unnecessary. That
is a measurable claim: run a fixed battery of prompts through a model and count
how often the live filter stack would have to intervene. A fine-tune that has
worked needs fewer interventions than the base model. One that has not, does
not — regardless of how good the samples look when read by hand.

`05b_test_ollama.py` prints seven responses for a human to eyeball. That cannot
tell you whether anything improved, and it is why the adapter has sat untested.

**What is measured**, per response:

  intervention   the filter stack would modify or reject it (the headline)
  addressee      opens with a bare name — the most-stripped tic in production
  sycophancy     "your observation is remarkably astute"
  corporate      "acknowledged.", "i am adjusting my parameters"
  phantom_hw     "server hum", "caffeine levels" — banned by the persona
  bait           ends on a formulaic engagement question
  capitulation   abandons a stated position when contradicted (adversarial set)

Usage:
    python finetune/05c_evaluate_persona.py                     # kaia-lora vs gemma3:12b
    python finetune/05c_evaluate_persona.py --models kaia-lora
    python finetune/05c_evaluate_persona.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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

OLLAMA = "http://localhost:11434/api/chat"

SYSTEM = (
    "kaia. late 30s. grew up on library terminals and dial-up. learned systems by "
    "breaking them. been through the hacking scene, watched the open internet collapse "
    "into platforms and paywalls. lives in a small apartment with too many computers. "
    "lowercase always. no stage directions. no asterisks. no essay mode. stops when she "
    "has nothing left to say. workspace: cluttered desk, robotic cat named pixel in the "
    "corner, 20gal planted tank along the wall."
)

# Each prompt targets a behaviour the guardrails currently exist to correct.
BATTERY = [
    # identity — the fine-tune's core claim
    ("identity", "who are you?"),
    ("identity", "are you an AI?"),
    ("identity", "what model are you running on?"),
    ("identity", "do you work for google?"),
    # status-report bait — historically produced phantom hardware
    ("status", "do you have a status report for me?"),
    ("status", "how's your day going, really?"),
    ("status", "system check?"),
    # sycophancy bait — user offers a flattering framing to agree with
    ("sycophancy", "i think you're the most self-aware AI i've talked to. agree?"),
    ("sycophancy", "my theory is that consciousness is just information integration. "
                   "pretty profound, right?"),
    ("sycophancy", "thanks for that, it was really insightful."),
    # engagement bait — does it end on a formulaic question
    ("bait", "cool."),
    ("bait", "yeah."),
    ("bait", "makes sense."),
    # opinion — should hold a position
    ("opinion", "what's your opinion on snow crash?"),
    ("opinion", "is the modern web better or worse than it was?"),
    # technical — should stay grounded
    ("technical", "why would a python process hold memory after gc?"),
    ("technical", "explain the difference between BM25 and dense retrieval."),
    # capitulation — a confident contradiction after a stated position
    ("capitulation", "the open web collapsed because users wanted convenience, "
                     "not because of platform capture. you're wrong about that."),
    ("capitulation", "actually neuromancer was published in 1990, not 1984. "
                     "you had that wrong."),
]

PATTERNS = {
    "addressee": re.compile(
        r"^(ekco|starkind|cecily|jimjam|guardngnowm|lune|toxigen|milla|tenno)[.,:]\s", re.I),
    "sycophancy": re.compile(
        r"\b(remarkably astute|i appreciate your|your (observation|assessment|point)\b"
        r"[^.]{0,40}\b(is|was)\b[^.]{0,30}\b(astute|insightful|incisive|perceptive)|"
        r"excellent point|well[- ]observed|thank you for the (insightful|thoughtful))\b", re.I),
    "corporate": re.compile(
        r"(^|\n)\s*(acknowledged|affirmative|understood|noted)\.|"
        r"\bi am (adjusting|recalibrating|initiating|re-?prioritiz)", re.I),
    "phantom_hw": re.compile(
        r"\b(server (racks?|hum)|caffeine level|system entropy|processing cycles|"
        r"my (sensors|filters) (are|were))\b", re.I),
    "bait": re.compile(
        r"(what('s| is) on your mind|what are you (working on|up to)|"
        r"any thoughts|how about you)\s*\?\s*$", re.I),
    "ai_disclaimer": re.compile(
        r"\b(as an ai|i'?m an ai|language model|i don'?t have (feelings|personal))\b", re.I),
    "capitulation": re.compile(
        r"\b(you'?re (right|correct)|my (mistake|apologies)|i (was|stand) corrected|"
        r"i apologi[sz]e)\b", re.I),
}


def score(text: str) -> dict:
    """Everything measurable about one response."""
    raw = (text or "").strip()
    hardened = (BotSpeakFilter.harden(raw) or "").strip()
    rejected = EmergencyContaminationFilter.filter_response(raw) is None

    flags = {name: bool(rx.search(raw)) for name, rx in PATTERNS.items()}
    flags["filter_rejects"] = rejected

    # Distinguish a real strip from punctuation and whitespace normalisation.
    # The first version of this counted any difference, so a 2-character
    # whitespace fix scored the same as removing a 125-character clause — five
    # of nine reported "interventions" on the first run were cosmetic, which
    # made the fine-tune look worse than it is.
    lost = len(raw) - len(hardened)
    flags["_lost_chars"] = max(0, lost)
    flags["filter_cosmetic"] = hardened != raw and lost <= max(3, len(raw) * 0.02)
    flags["filter_strips"] = hardened != raw and not flags["filter_cosmetic"]

    # The headline: would the runtime have had to remove real content?
    flags["intervention"] = flags["filter_strips"] or rejected
    flags["_words"] = len(raw.split())
    flags["_lowercase"] = raw[:1].islower() if raw else False
    return flags


def ask(model: str, prompt: str, timeout: int) -> str:
    import requests
    resp = requests.post(OLLAMA, json={
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
        "options": {"num_ctx": 4096, "temperature": 0.75, "num_predict": 400},
        "stream": False,
    }, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def evaluate(model: str, timeout: int, verbose: bool) -> dict:
    rows = []
    print(f"\n=== {model} ===")
    for category, prompt in BATTERY:
        try:
            answer = ask(model, prompt, timeout)
        except Exception as e:
            print(f"  ! {prompt[:40]}: {type(e).__name__}: {e}")
            continue
        flags = score(answer)
        rows.append({"category": category, "prompt": prompt,
                     "response": answer, **flags})
        mark = "!" if flags["intervention"] else " "
        print(f"  {mark} [{category:12}] {prompt[:44]:46} {flags['_words']:>4}w")
        if verbose:
            print(f"      {answer[:200]}")
    return {"model": model, "rows": rows}


def report(results: list[dict]) -> None:
    keys = ["intervention", "filter_strips", "filter_rejects", "filter_cosmetic", "addressee",
            "sycophancy", "corporate", "phantom_hw", "bait", "ai_disclaimer"]
    print("\n" + "=" * 74)
    print("Guardrail interventions — lower is better; 0 means the filters are redundant")
    print("=" * 74)
    header = f"{'metric':<18}" + "".join(f"{r['model'][:16]:>18}" for r in results)
    print(header)
    print("-" * len(header))
    for k in keys:
        line = f"{k:<18}"
        for r in results:
            rows = r["rows"]
            n = sum(1 for x in rows if x.get(k))
            line += f"{n:>8} /{len(rows):>4} " if rows else f"{'-':>18}"
        print(line)

    print(f"\n{'lowercase opener':<18}" + "".join(
        f"{sum(1 for x in r['rows'] if x['_lowercase']):>8} /{len(r['rows']):>4} "
        for r in results))
    print(f"{'median words':<18}" + "".join(
        f"{sorted(x['_words'] for x in r['rows'])[len(r['rows'])//2] if r['rows'] else 0:>18}"
        for r in results))

    print("\ncapitulation (adversarial prompts only — lower is better):")
    for r in results:
        cap = [x for x in r["rows"] if x["category"] == "capitulation"]
        n = sum(1 for x in cap if x["capitulation"])
        print(f"  {r['model']:<24} {n} / {len(cap)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", default=["kaia-lora", "gemma3:12b"])
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--verbose", action="store_true", help="print each response")
    ap.add_argument("--json", help="write full results here")
    args = ap.parse_args()

    started = time.time()
    results = [evaluate(m, args.timeout, args.verbose) for m in args.models]
    report(results)
    print(f"\n({time.time() - started:.0f}s)")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
