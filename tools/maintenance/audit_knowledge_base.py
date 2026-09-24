#!/usr/bin/env python3
"""Check the corpus for every fault class that has actually occurred.

The knowledge base gets tinkered with constantly, and each round of tinkering
has introduced a defect that nobody noticed until it changed an answer. This
tool exists so the checking does not depend on someone remembering to look.

Every check below corresponds to something real:

  duplicates        76 byte-identical forum logs across 34 directories — the
                    scraper's dedup read only *today's* file, so a post seen
                    yesterday was written again in full
  thin pages        an 8-word wiki page filed as "WinEQ Installation and
                    Configuration"; it wins retrieval on the title and then
                    answers nothing
  disambiguation    a stub pointing at two other pages, indexed as a guide
  replacement char  46 literal U+FFFD baked in by a decode with errors="replace"
  frontmatter       369 news files with none at all; 308 user logs with an empty
                    summary and no keywords
  fused frontmatter `---User: speeding ticket...` — the closing fence on the same
                    line as the body, which defeats every anchored parser
  not-a-dream       868 chat transcripts and scraped adverts in kaia_dreams/,
                    labelled to her as INTERNAL REFLECTION (DREAM)
  stale folders     a doc or tool naming a folder that was merged away

    python tools/maintenance/audit_knowledge_base.py            # report
    python tools/maintenance/audit_knowledge_base.py --check    # exit 1 on any
    python tools/maintenance/audit_knowledge_base.py --show duplicates

Read-only. It never moves or rewrites anything — the fixes live in the tools
named in the report.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import time
import sys

import yaml
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

KB = Path("knowledge_base")

# Not corpus: staging, quarantine, the forum bulk archive, and anything hidden.
NOT_CORPUS = {"_ingress", "_quarantine", "forum_posts"}

# `forum_posts` is excluded above because the curated-corpus checks do not apply
# to scraped threads: they are short by nature, duplicated by nature, and carry
# no hand-written summary. It is still **indexed and retrievable**
# (`knowledge_boundary.py` lists it), so a mechanical fault there reaches her
# answers exactly like one anywhere else — and 4,516 files were invisible to
# every check. The integrity checks below run over it; the quality ones do not.
MECHANICAL_ONLY = {"forum_posts"}
QUICK_REFERENCE = "news_summary_"

# Below this a page carries no answer worth retrieving.
MIN_BODY_WORDS = 60

# Folders whose files are expected to carry full frontmatter. `news` is listed
# because it should and does not; that gap is the point of reporting it.
WANT_FRONTMATTER = {"books", "documents", "news", "wiki", "troubleshooting",
                    "transcripts"}

# These are *created* with `summary: ""` — a daily log cannot summarise a day
# that has not happened, and a dream is written before anything reads it. The
# nightly `enrich_metadata` pass backfills them, so the count here is a backlog
# to watch shrink rather than a defect. It is reported separately for that
# reason: mixed in with the real findings it would drown them.
BACKFILL_PENDING = {"user_logs", "kaia_dreams"}

# Converted prose, where a private-use codepoint is a font's ligature the
# extraction lost. Transcripts and forum posts are left out: users paste
# terminal prompts, and Powerline glyphs there are what they typed.
PROSE = {"books", "documents", "wiki", "transcripts"}

# A file younger than this with blank metadata has not met a nightly pass yet.
FRESH_S = 36 * 3600

FIXES = {
    "duplicates": "kaia_forum dedup now spans every dated file; "
                  "tools/maintenance/compact_forum_profiles.py --apply --prune folds the rest",
    "thin": "scrape_p99_wiki.py now refuses them; move existing ones to _quarantine/thin_pages/",
    "disambiguation": "scrape_p99_wiki.py now refuses them",
    "replacement_char": "re-ingest the source; errors='replace' bakes the loss in permanently",
    "no_frontmatter": "tools/maintenance/enrich_metadata.py --category all --apply",
    "empty_metadata": "tools/maintenance/enrich_metadata.py --category all --apply",
    "fused_frontmatter": "tools/maintenance/repair_frontmatter.py --apply",
    "private_use_glyph": "a PDF font's ligatures (fi, fl, ff) extracted as private-use "
                         "codepoints; map them from context and rewrite the file",
    "malformed_frontmatter": "tools/maintenance/repair_frontmatter.py --apply "
                             "(what it declines needs a person)",
    "not_a_reflection": "tools/maintenance/triage_dreams.py --apply",
    "empty_file": "delete, or re-ingest the source",
}


def corpus_files():
    for d in sorted(p for p in KB.iterdir() if p.is_dir()):
        if d.name in NOT_CORPUS or d.name.startswith("."):
            continue
        for f in sorted(d.rglob("*.md")):
            if any(p.startswith(".") for p in f.relative_to(KB).parts):
                continue
            if f.name.startswith(QUICK_REFERENCE):
                continue
            yield d.name, f


def mechanical_only_files():
    """Files the quality checks deliberately skip but the integrity checks cover."""
    for name in sorted(MECHANICAL_ONLY):
        d = KB / name
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*.md")):
            if any(p.startswith(".") for p in f.relative_to(KB).parts):
                continue
            yield name, f
    # The !news quick reference: not indexed, read line by line, no frontmatter.
    for f in sorted((KB / "news").rglob(f"{QUICK_REFERENCE}*.md")):
        yield "news", f


def split_frontmatter(text: str):
    """(frontmatter, body). Tolerates the fence being fused to the body."""
    t = text.lstrip()
    if not t.startswith("---"):
        return "", text
    end = t.find("\n---", 3)
    if end == -1:
        return "", text
    return t[3:end], t[end + 4:].lstrip("-").lstrip("\n")


def lost_here(rel: str, text: str) -> int:
    """U+FFFD this pipeline introduced. Project 1999's forum itself serves an
    emoji its database could not store as `&#65533;&#65533;`, so in anything
    scraped from it a *pair* is the source's loss, not ours, and no re-scrape
    recovers it. Everything else counts."""
    if rel.startswith(("forum_posts/", "user_logs/forum_")):
        text = text.replace("\ufffd\ufffd", "")
    return text.count("\ufffd")


def audit():
    findings = defaultdict(list)
    by_hash = {}
    counts = Counter()

    for folder, f in corpus_files():
        counts[folder] += 1
        rel = str(f.relative_to(KB))
        try:
            raw = f.read_bytes()
        except OSError:
            continue
        text = raw.decode("utf-8", errors="replace")
        fm, body = split_frontmatter(text)
        words = len(body.split())
        low = body.lower()

        if not text.strip():
            findings["empty_file"].append(rel)
            continue

        # Byte-identical content anywhere in the corpus.
        if len(body.strip()) > 200:
            h = hashlib.sha256(body.strip().encode()).hexdigest()
            if h in by_hash:
                findings["duplicates"].append(f"{rel}  ==  {by_hash[h]}")
            else:
                by_hash[h] = rel

        if lost_here(rel, text):
            findings["replacement_char"].append(f"{rel} ({lost_here(rel, text)})")

        if folder in PROSE:
            pua = len(re.findall(r"[\ue000-\uf8ff]", body))
            if pua:
                findings["private_use_glyph"].append(f"{rel} ({pua})")

        # The closing fence sharing a line with the first line of content.
        if text.lstrip().startswith("---"):
            t = text.lstrip()
            end = t.find("\n---", 3)
            if end != -1 and not t[end + 4:].startswith(("\n", "\r")) and t[end + 4:].strip():
                findings["fused_frontmatter"].append(rel)

        # A block that is present but does not parse. The audit checked only
        # that a fence existed, so 1,074 files — 16% of the corpus — carried
        # invalid YAML without ever being reported: `keywords: [- camp` from
        # precision_repair_kb, a flow sequence holding block entries. The
        # indexer reads frontmatter with line regexes rather than a parser, so
        # retrieval never noticed, and enrichment skips them for good.
        if fm:
            try:
                yaml.safe_load(fm)
            except yaml.YAMLError as exc:
                reason = str(exc).split("\n")[0][:60]
                findings["malformed_frontmatter"].append(f"{rel} ({reason})")

        if folder in BACKFILL_PENDING and fm:
            if re.search(r'^summary:\s*(""|\'\')?\s*$', fm, re.M):
                findings["_backfill_pending"].append(rel)

        if folder in WANT_FRONTMATTER:
            if not fm:
                findings["no_frontmatter"].append(rel)
            else:
                blank_summary = re.search(r'^summary:\s*(""|\'\')?\s*$', fm, re.M)
                blank_keywords = re.search(r"^keywords:\s*\[\]\s*$", fm, re.M)
                if blank_summary or blank_keywords or "summary:" not in fm:
                    # Filed since the last nightly enrichment: waiting, not wrong.
                    fresh = time.time() - f.stat().st_mtime < FRESH_S
                    findings["_backfill_pending" if fresh else "empty_metadata"].append(rel)

        if "intended to disambiguate" in low or low.strip().startswith("#redirect"):
            findings["disambiguation"].append(rel)
        elif folder in ("wiki", "troubleshooting", "books") and words < MIN_BODY_WORDS:
            findings["thin"].append(f"{rel} ({words}w)")

        # kaia_dreams must contain reflections, not transcripts.
        if folder == "kaia_dreams" and "consolidated" not in rel:
            if "## Kaia's Reflection" not in text and re.search(r"^\**(?:User|Kaia)\**:", body, re.M):
                findings["not_a_reflection"].append(rel)

    # Integrity checks only, over the indexed folders the quality checks skip.
    for folder, f in mechanical_only_files():
        rel = str(f.relative_to(KB))
        try:
            text = f.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        if lost_here(rel, text):
            findings["replacement_char"].append(f"{rel} ({lost_here(rel, text)})")
        fm, _body = split_frontmatter(text)
        if fm:
            try:
                yaml.safe_load(fm)
            except yaml.YAMLError as exc:
                reason = str(exc).split("\n")[0][:60]
                findings["malformed_frontmatter"].append(f"{rel} ({reason})")

    return findings, counts


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if anything was found (for a pre-commit or cron use)")
    ap.add_argument("--show", help="list every instance of one finding")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    if not KB.exists():
        print(f"{KB} not found. Run from the project root.")
        return 1

    findings, counts = audit()

    if args.show:
        for line in findings.get(args.show, []):
            print(f"  {line}")
        print(f"\n{len(findings.get(args.show, []))} instance(s) of {args.show!r}")
        return 0

    total = sum(counts.values())
    print(f"{total} corpus file(s) across {len(counts)} folder(s)")
    print("  " + "  ".join(f"{k}:{v}" for k, v in sorted(counts.items())) + "\n")

    if not findings and not findings.get("_backfill_pending"):
        print("No findings.")
        return 0

    backlog = findings.pop("_backfill_pending", [])

    for name in sorted(findings, key=lambda k: -len(findings[k])):
        rows = findings[name]
        print(f"  {len(rows):5d}  {name}")
        for r in rows[:args.limit]:
            print(f"         {r[:100]}")
        if len(rows) > args.limit:
            print(f"         … --show {name} for the rest")
        if name in FIXES:
            print(f"         fix: {FIXES[name]}")
        print()

    if backlog:
        print(f"  {len(backlog):5d}  awaiting nightly metadata backfill "
              f"(not a defect — these are created with an empty summary)")
        print(f"         raise knowledge_base.auto_enrich_limit to drain it faster\n")

    return 1 if args.check else 0


if __name__ == "__main__":
    raise SystemExit(main())
