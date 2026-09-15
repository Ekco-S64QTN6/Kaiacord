#!/usr/bin/env python3
"""Regenerate the frontmatter on the generated troubleshooting guides.

`synthesize_technical_knowledge.py` writes correct title, category and summary,
but its keywords are capitalised fragments scraped out of symptom text with a
regex — "Crashing", "Difficulty", "Experiencing", "Increased", "Missing",
"Original", "Players". The body is good; only the keyword list is filler, and
keywords feed BM25, which is half of how these guides get found at all.

Run this once the synthesis job has finished and written its final guides.

    python tools/maintenance/tidy_troubleshooting.py            # dry run
    python tools/maintenance/tidy_troubleshooting.py --apply

Dry run by default: it rewrites files in knowledge_base/ (CLAUDE.md §10).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

KB = Path("knowledge_base/troubleshooting")

PROMPT = (
    "You are indexing a Project 1999 (EverQuest emulator) troubleshooting guide "
    "so players can find it by search.\n\n"
    "Return ONLY a JSON object:\n"
    '{{"summary": "...", "keywords": ["..."]}}\n\n'
    "summary: two sentences naming the concrete problems this guide covers. "
    "Start at a sentence boundary.\n"
    "keywords: 10-16 search terms a player would actually type — error strings, "
    "file names, program names, symptoms. Include literal tokens like "
    "'DSETUP.dll' or 'error 1017' where the guide mentions them. No generic "
    "words like 'Problems', 'Players', 'Experiencing'.\n\n"
    "GUIDE HEADINGS:\n{headings}\n\nEXCERPT:\n{excerpt}\n"
)


def split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", text
    return text[: end + 4], text[end + 4:].lstrip("\n")


def set_field(front: str, field: str, value: str) -> str:
    pattern = re.compile(rf"^{field}:.*$", re.M)
    line = f"{field}: {value}"
    return pattern.sub(line, front, count=1) if pattern.search(front) \
        else front.replace("---\n", f"---\n{line}\n", 1)


def derive(headings: str, excerpt: str) -> tuple:
    from ollama import Client
    from utils.infrastructure.system.yaml_config import config
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager

    model = config.chat_model
    opts = OllamaGPUManager(model).get_gpu_options(for_chat=True)
    resp = Client().chat(
        model=model, options={**opts, "temperature": 0.2},
        messages=[{"role": "user",
                   "content": PROMPT.format(headings=headings[:2500],
                                            excerpt=excerpt[:2500])}])
    text = resp["message"]["content"].strip()
    if "```" in text:
        text = text.split("```")[1].lstrip("json").strip()
    data = json.loads(text[text.find("{"):text.rfind("}") + 1])
    kws = [str(k).strip() for k in (data.get("keywords") or []) if str(k).strip()]
    return str(data.get("summary", "")).strip(), kws[:16]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    guides = sorted(KB.glob("Troubleshooting_*.md"))
    if not guides:
        print(f"no guides in {KB} yet — run the synthesiser first.")
        return 1

    print(f"{len(guides)} guide(s){'' if args.apply else '  (DRY RUN)'}\n")
    for path in guides:
        text = path.read_text(encoding="utf-8")
        front, body = split_frontmatter(text)
        if not front:
            print(f"  SKIP  {path.name}: no frontmatter")
            continue
        headings = "\n".join(re.findall(r"^#{2,4} .+$", body, re.M))
        try:
            summary, keywords = derive(headings, body)
        except Exception as e:                       # noqa: BLE001
            print(f"  SKIP  {path.name}: {type(e).__name__}: {e}")
            continue
        if not keywords:
            print(f"  SKIP  {path.name}: model returned no keywords")
            continue

        print(f"  {path.name}")
        print(f"    keywords: {keywords}")
        if args.apply:
            front = set_field(front, "keywords", json.dumps(keywords))
            if summary:
                front = set_field(front, "summary", json.dumps(summary))
            tmp = path.with_suffix(".tmp")
            tmp.write_text(front + "\n\n" + body, encoding="utf-8")
            tmp.replace(path)            # atomic, CLAUDE.md §4

    print("\nRe-run with --apply to write." if not args.apply else "\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
