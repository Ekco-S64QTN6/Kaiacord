#!/usr/bin/env python3
"""Repair knowledge-base frontmatter that does not parse as YAML.

Two faults, both from the same origin.

**Stacked blocks.**

`enrich_metadata.parse_frontmatter` treated a YAML parse error the same as an
absent frontmatter block: it returned the whole file as the body, so the caller
saw an unenriched document and prepended a fresh block on top of the existing
one. One pass produced 60 of these — a valid outer block, then a second broken
block, then the real body.

The broken inner blocks all came from `precision_repair_kb.py`, which builds
`keywords: [{', '.join(keywords)}]` by hand: a block-style list comes back from
its regex as one string carrying its own `- ` dashes and newlines, so the flow
sequence opens and never closes.

Repair keeps the generated outer block, salvages any scalar key the outer block
is missing from the broken inner one, and drops the rest. Dry run unless
--apply, as every corpus writer here must be.

**A flow sequence filled with block entries.** `precision_repair_kb` also wrote
`keywords: [- camp\n- rules\n- project 1999 wiki]`, which no YAML parser will
take — a `[...]` flow sequence cannot contain `- ` entries. 1,074 files across
forum_posts, news, documents, transcripts, wiki and user_logs carry it. The
indexer reads frontmatter with line regexes rather than a YAML parser, so
retrieval still works, but nothing that *does* parse the block can read them:
they are permanently skipped by enrichment and invisible to any metadata pass.

    python tools/maintenance/repair_frontmatter.py
    python tools/maintenance/repair_frontmatter.py --apply
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import yaml

from utils.core.atomic_write import write_atomic

SCALAR = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):[ \t]+(\S.*)$")


def find_stacked(text: str):
    """Return (outer, inner, body) line ranges, or None if not stacked.

    Stacked means: the file opens with a fence, and the line immediately after
    that block closes is another fence opening a second block.
    """
    if not text.startswith("---"):
        return None
    lines = text.split("\n")
    fences = [i for i, l in enumerate(lines[:400]) if l.strip() == "---"]
    if len(fences) < 4 or fences[1] + 1 != fences[2]:
        return None
    return lines, fences


def salvage(inner_lines):
    """Pull whatever unambiguous `key: value` pairs survive in a broken block.

    Line-by-line rather than through the YAML parser, because the block does not
    parse — that is why it is here. Only simple scalars on one line qualify; a
    list or a folded string cannot be read back reliably and is dropped.
    """
    out = {}
    for line in inner_lines:
        m = SCALAR.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if value.startswith(("[", "{", "|", ">")):
            continue
        try:
            parsed = yaml.safe_load(value)
        except yaml.YAMLError:
            continue
        if isinstance(parsed, (str, int, float, bool)) and str(parsed).strip():
            out[key] = parsed
    return out


FLOW_KEYWORDS = re.compile(
    r"^(?P<key>keywords|tags):[ \t]*\[[ \t]*\n?(?P<items>(?:[ \t]*-[ \t]+[^\n]*\n?)+)",
    re.MULTILINE)


def fix_flow_sequence(raw_yaml: str) -> str:
    """Turn `keywords: [- a\n- b]` back into a block list.

    Only this one shape, and only when every line between the bracket and the
    end of the run is a `- ` entry. Anything less regular is left for a person:
    a guess here writes silently wrong metadata into the corpus.
    """
    def _swap(m):
        items = []
        for line in m.group("items").split("\n"):
            line = line.strip()
            if not line.startswith("-"):
                continue
            item = line[1:].strip().rstrip("]").strip().strip('"').strip("'")
            if item:
                items.append(item)
        if not items:
            return m.group(0)
        body = "".join(f"- {i}\n" for i in items)
        return f"{m.group('key')}:\n{body}"

    return FLOW_KEYWORDS.sub(_swap, raw_yaml)


def repair_unparseable(text: str):
    """Repair a single frontmatter block whose YAML does not load."""
    if not text.startswith("---\n"):
        return None
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return None
    raw, body = parts[1], parts[2]
    try:
        yaml.safe_load(raw)
        return None                      # already fine; nothing to do
    except yaml.YAMLError:
        pass

    fixed = fix_flow_sequence(raw)
    if fixed == raw:
        return None                      # a shape this tool does not know
    try:
        data = yaml.safe_load(fixed)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict) or not data:
        return None

    dumped = yaml.safe_dump(data, default_flow_style=False, sort_keys=False,
                            allow_unicode=True)
    return f"---\n{dumped}---\n{body.lstrip(chr(10))}"


def repair(text: str):
    """Return the repaired text, or None if there is nothing this tool fixes."""
    found = find_stacked(text)
    if not found:
        return repair_unparseable(text)
    lines, fences = found

    outer_yaml = "\n".join(lines[fences[0] + 1:fences[1]])
    inner_lines = lines[fences[2] + 1:fences[3]]
    body = "\n".join(lines[fences[3] + 1:])

    try:
        outer = yaml.safe_load(outer_yaml)
    except yaml.YAMLError:
        return None                      # both blocks broken; not ours to guess
    if not isinstance(outer, dict):
        return None

    for key, value in salvage(inner_lines).items():
        if key not in outer or not outer[key]:
            outer[key] = value

    dumped = yaml.safe_dump(outer, default_flow_style=False, sort_keys=False,
                            allow_unicode=True)
    return f"---\n{dumped}---\n{body.lstrip(chr(10))}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="knowledge_base")
    ap.add_argument("--apply", action="store_true",
                    help="write the repairs; without it this only reports")
    args = ap.parse_args()

    root = Path(args.dir)
    repaired = skipped = 0
    for path in sorted(root.rglob("*.md")):
        if any(part.startswith((".", "_")) for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        new = repair(text)
        if new is None:
            continue
        if new == text:
            continue
        repaired += 1
        rel = path.relative_to(root)
        if args.apply:
            write_atomic(path, new)
            print(f"  repaired  {rel}")
        else:
            before = len(text.split("\n"))
            after = len(new.split("\n"))
            print(f"  would fix {rel}  ({before} -> {after} lines)")

    verb = "Repaired" if args.apply else "Would repair"
    print(f"\n{verb} {repaired} file(s).")
    if not args.apply and repaired:
        print("Re-run with --apply to write them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
