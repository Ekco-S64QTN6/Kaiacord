#!/usr/bin/env python3
"""Merge Kaia's nightly reflections into one document per subject.

`kaia_dreams/` holds one file per dream, which is the right shape for writing
them and the wrong shape for retrieving them. After triage it is 1,531
reflections; nineteen of them are about *Do Androids Dream of Electric Sheep*,
twenty-one about *Snow Crash*, 265 touch Starkind. A question about any of those
retrieves three or four fragments chosen by similarity, from different nights,
with no sense of what she settled on or where she changed her mind.

This tool groups them deterministically and asks the model to write one coherent
document per group — "what she actually thinks about X, and how that moved".
Python decides the grouping; the model only writes prose, per CLAUDE.md §4.

    python tools/maintenance/consolidate_dreams.py                    # plan only
    python tools/maintenance/consolidate_dreams.py --show books
    python tools/maintenance/consolidate_dreams.py --apply --limit 5
    python tools/maintenance/consolidate_dreams.py --apply --bucket "books/Snow Crash"

Groups, in the order they are tried:

  books/<Title>     the source was a book; the filename stem carries the title
  people/<Name>     an interaction dream that names one of her regulars
  topics/<Subject>  a named source document — an article, a wiki page, a scrape
  periods/<YYYY-MM> interaction dreams naming nobody, kept by month

Output lands in `kaia_dreams/consolidated/`. Consumed sources move to
`knowledge_base/.dream_archive/` rather than being deleted, so a bad synthesis
run is reversible and the originals remain if she ever wants the raw nights.

Dry run by default (CLAUDE.md §10). Runs at BACKGROUND GPU priority, so it
yields to live chat.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DREAMS = Path("knowledge_base/kaia_dreams")
OUT = DREAMS / "consolidated"
ARCHIVE = Path("knowledge_base/.dream_archive")
USER_LOGS = Path("knowledge_base/user_logs")

REFLECTION_MARKER = "## Kaia's Reflection"
FRAGMENT_MARKER = "## Original Fragment"

# A group of one is already a single document; merging it just costs a model call
# and loses the original's date.
MIN_GROUP = 2

# Reflections per synthesis pass. Twenty at ~1,200 characters is ~7k tokens of
# input against a 16,384 window, which leaves room for the instruction and the
# answer. Larger groups are folded in several passes and then merged.
CHUNK = 20

# Trim each reflection to this before sending. The tail of a dream is usually
# where it repeats itself.
PER_REFLECTION_CHARS = 1400

SYNTHESIS_PROMPT = """You are Kaia, reading back {count} of your own dream reflections about {subject}.

Write ONE coherent piece in your own voice about what you actually think, as if
setting down where you have arrived after turning it over many nights.

Rules:
- First person. Your own voice — plain, specific, lowercase, no hedging.
- Say what you concluded, not that you reflected. Never narrate the process
  ("across these dreams I explored...") and never mention dreams, reflections,
  files, or this exercise.
- Where you changed your mind or kept circling the same doubt, say so directly.
- Keep the concrete details: names, scenes, phrases you kept returning to.
  Drop anything you only said once and never picked up again.
- No headings, no bullet points, no summary paragraph at the end.
- If the material is thin, write less. Do not pad.

THE REFLECTIONS:
{material}
"""

MERGE_PROMPT = """You are Kaia. Below are {count} passages you wrote about {subject} at
different times. Fold them into ONE CONTINUOUS PIECE OF PROSE with no repetition.

This is the step that goes wrong. Asked to merge twelve passages about a person,
the model produced "**1. Key Themes & Recurring Ideas:**" followed by bullets
analysing "the narrator" — a literary essay about Kaia rather than Kaia
thinking. So, absolutely:

- NO headings. NO numbered sections. NO bullet points. NO bold labels.
- NO third person. Never "the narrator", "the speaker", "Kaia" — say "i".
- NO analysis of the passages. You are not summarising writing, you are saying
  what you think. Write the way you would talk.
- Plain paragraphs of lowercase prose, nothing else.
- Keep every distinct idea; drop every restatement.

PASSAGES:
{material}
"""

# What a merge looks like when it has drifted into essay mode.
_ESSAY_SHAPE = re.compile(
    r"^\s*(?:[-*\u2022]\s|\d+[.)]\s|#{1,6}\s|\*\*[^*\n]{1,60}\*\*\s*:)", re.MULTILINE)
# "the narrator" and "the speaker" are literary-criticism vocabulary and never
# hers. "the user" is NOT in this list: she uses it constantly and correctly
# about the people in her logs — "the user's casual cruelty, the way systems are
# treated as disposable" is from the reflection this check is meant to protect.
_THIRD_PERSON = re.compile(r"\bthe (?:narrator|author|speaker|protagonist)\b",
                           re.IGNORECASE)


def reads_as_essay(text: str) -> str:
    """Why this output is not her, or "" if it is fine."""
    if not text:
        return "empty"
    bullets = len(_ESSAY_SHAPE.findall(text))
    if bullets >= 3:
        return f"{bullets} bullet/heading lines"
    m = _THIRD_PERSON.search(text)
    if m:
        return f"third person ({m.group(0)!r})"
    return ""


# ── Reading ──────────────────────────────────────────────────────────

def known_users() -> list:
    """Her regulars, from the user-log directories. Forum accounts excluded."""
    if not USER_LOGS.exists():
        return []
    out = []
    for d in USER_LOGS.iterdir():
        if d.is_dir() and not d.name.startswith("forum_"):
            out.append(d.name.rsplit("_", 1)[0])
    return out


def read_reflection(path: Path):
    """(reflection_text, fragment_text, date) or None if this is not a dream."""
    try:
        t = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if REFLECTION_MARKER not in t:
        return None
    reflection = t.split(REFLECTION_MARKER, 1)[1].strip()
    fragment = ""
    if FRAGMENT_MARKER in t:
        fragment = t.split(FRAGMENT_MARKER, 1)[1].split(REFLECTION_MARKER)[0]
    m = re.match(r"dream_(\d{4})(\d{2})(\d{2})_", path.name)
    date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""
    return reflection, fragment, date


# ── Grouping ─────────────────────────────────────────────────────────

# One `dream_YYYYMMDD_HHMMSS_` prefix. Applied repeatedly, because a dream about
# a dream about a dream stacks them.
_DREAM_PREFIX = re.compile(r"^(?:dream_\d{8}_\d{6}_)+")

# The author suffix. `Snow_Crash_By_Neal_Stephenson` and
# `Neuromancer_by_William_Gibson` are the same book under two spellings.
_AUTHOR_SUFFIX = re.compile(r"[_\s]+(?:by)[_\s].*$", re.IGNORECASE)


def clean_title(raw: str) -> str:
    s = _DREAM_PREFIX.sub("", (raw or "").strip())
    s = re.sub(r"\.md$", "", s)
    s = _AUTHOR_SUFFIX.sub("", s)
    s = re.sub(r"[_\s]+", " ", s).strip(" _")
    return "" if s.lower().startswith("dream") else s


def title_candidates(path: Path, text: str) -> list:
    """Every string in or around a file that might carry the real title.

    The dream engine truncates the source stem to 30 characters, and a dream
    *about a dream* spends 22 of those on the parent's timestamped prefix. So
    `dream_20260224_031731_Snow_Cra` is all that survives in the filename, and
    after three generations nothing survives at all — 250 files group under the
    useless key "dream 20".
    
    The chain is still recoverable: the body's `# Dream Reflection:` header names
    the parent, and where the parent was itself a dream its own header is quoted
    inside `## Original Fragment`. Collect every level and let the caller take
    the most informative.
    """
    out = [path.stem]
    out += re.findall(r"^# Dream Reflection: (.+)$", text, re.MULTILINE)
    out += re.findall(r"Dream Reflection: ([^\n]+?)\.md", text)
    out += re.findall(r"Source: ([^\n]+?)\.md", text)
    return [c for c in (clean_title(c) for c in out) if c]


def canonicalise(titles) -> dict:
    """Map every clipped title onto the fullest spelling of the same title.

    `Snow Cra`, `Snow Crash` and `Snow Crash By Neal Stephenson` are one book
    split three ways by the 30-character truncation. A clipped title is a prefix
    of its full form, which makes this exact rather than fuzzy: no edit distance,
    no threshold, and a title that is nobody's prefix stays as it is.
    """
    ordered = sorted(set(titles), key=len, reverse=True)
    mapping = {}
    for t in ordered:
        for longer in ordered:
            if len(longer) > len(t) and longer.lower().startswith(t.lower()):
                mapping[t] = mapping.get(longer, longer)
                break
        else:
            mapping[t] = mapping.get(t, t)
    # Collapse any chain left by the single-step hop above.
    for t in list(mapping):
        seen = set()
        while mapping[t] != t and mapping[t] not in seen:
            seen.add(mapping[t])
            t2 = mapping[t]
            if mapping.get(t2, t2) == t2:
                break
            mapping[t] = mapping[t2]
    return mapping


def subject_of(path: Path, reflection: str, fragment: str, date: str, users: list,
               title: str = ""):
    """(bucket, subject) for one dream. Deterministic, no model involved."""
    stem = path.stem
    folder = path.parent.name

    if folder == "books":
        return "books", (title or clean_title(stem) or "unattributed")

    source = _DREAM_PREFIX.sub("", stem)

    # An interaction dream: who is it about? The fragment is the conversation,
    # so the names in it are the people who were actually talking.
    if source.startswith("interactions_") or folder == "interactions":
        hay = f"{fragment}\n{reflection}"
        counts = {}
        for u in users:
            first = u.split("_")[0]
            n = len(re.findall(rf"\b{re.escape(first)}\b", hay, re.IGNORECASE))
            if n:
                counts[u] = n
        if counts:
            # The person the dream is mostly about, not merely the first named.
            top = max(counts.items(), key=lambda kv: kv[1])[0]
            return "people", top.replace("_", " ")
        return "periods", (date[:7] if date else "undated")

    return "topics", (title or clean_title(stem) or "unattributed")


def plan(users: list) -> dict:
    """Group every reflection. Two passes, because titles are only knowable
    relative to each other: "Snow Cra" is meaningless until the corpus has shown
    that "Snow Crash By Neal Stephenson" exists."""
    scanned, all_titles = [], []
    for f in sorted(DREAMS.rglob("*.md")):
        if OUT in f.parents:
            continue
        got = read_reflection(f)
        if not got:
            continue
        reflection, fragment, date = got
        text = f.read_text(encoding="utf-8", errors="replace")
        cands = title_candidates(f, text)
        scanned.append((f, reflection, fragment, date, cands))
        all_titles.extend(cands)

    canon = canonicalise(all_titles)

    groups = defaultdict(list)
    for f, reflection, fragment, date, cands in scanned:
        resolved = [canon.get(c, c) for c in cands]
        # The most informative spelling available for this file.
        title = max(resolved, key=len) if resolved else ""
        bucket, subject = subject_of(f, reflection, fragment, date, users, title)
        groups[f"{bucket}/{subject}"].append((date, f, reflection))
    for k in groups:
        groups[k].sort()
    return groups


# ── Synthesis ────────────────────────────────────────────────────────

def strip_preamble(text: str) -> str:
    """Drop the assistant chatter gemma3 wraps around a piece.

    Same failure as `synthesize_technical_knowledge.strip_model_preamble`: the
    model opens with "Okay, here's a consolidated reflection..." and closes by
    offering to do more. In a document her answers are grounded in, that is
    retrievable text in the wrong voice.
    """
    if not text:
        return ""
    t = text.strip()
    t = re.sub(r"^(?:okay|sure|alright|certainly|here(?:'s| is))\b[^\n]*\n+", "",
               t, flags=re.IGNORECASE)
    t = re.sub(r"\n+(?:(?:let me know|i can|would you like|i hope this)\b[^\n]*)$", "",
               t, flags=re.IGNORECASE)
    # A heading is against the brief, and a stray one reads as document structure.
    t = re.sub(r"^#{1,6}\s+.*$", "", t, flags=re.MULTILINE)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    # Trim a generation that ran into the token cap back to its last whole
    # sentence, rather than filing a dangling clause into the knowledge base.
    #
    # Done here rather than with `narration.finish_cleanly`, which reads a
    # trailing "…" as a clean ending — and that is exactly what it leaves behind
    # when it gives up on a pass. Chained through the merge that produced
    # "a digital echo of something lost. lik...", which is worse than either
    # input. She also uses "…" as punctuation constantly, so the ellipsis cannot
    # be treated as a truncation marker either way.
    return _trim_dangling(t)


# The tail after the last sentence that actually ended. Only trimmed when it is
# short: a long unterminated passage is prose she wrote without a full stop, and
# dropping it would cost real content.
_TAIL_FRAGMENT = re.compile(r"[.!?][\"\'\u201d\u2019)]*\s+")


# A single cut-off word closed with an ellipsis: "lik...", "someth…". This is
# what a truncated pass looks like after something has already tried to tidy it,
# and it ends in a period, so the terminal-punctuation test above says it is
# finished. Deliberately one token only — "just… tired." is her own cadence and
# must survive.
_CUT_WORD = re.compile(r"^\S{1,14}(?:\.{2,}|\u2026)$")


def _trim_dangling(t: str, max_fragment: int = 120) -> str:
    if not t:
        return t
    ends = list(_TAIL_FRAGMENT.finditer(t))
    if not ends:
        return t
    tail = t[ends[-1].end():].strip()
    if not tail:
        return t                      # already ends on a finished sentence
    if len(tail) <= max_fragment and (
            not re.search(r"[.!?]$", tail) or _CUT_WORD.match(tail)):
        return t[:ends[-1].end()].strip()
    return t


async def guarded_chat(client, model, prompt, tag):
    from utils.infrastructure.gpu.gpu_manager import gpu_memory_manager, GPUTaskPriority
    return await gpu_memory_manager.run_with_gpu_guard(
        model_name=model, priority=GPUTaskPriority.BACKGROUND,
        coro=asyncio.to_thread(
            client.chat, model=model,
            messages=[{"role": "user", "content": prompt}],
            # 900 cut the Do Androids Dream synthesis off mid-clause ("it feels
            # too. deliberate. Like…"). 42 reflections do not fold into 675
            # words without losing something.
            options={"temperature": 0.6, "num_predict": 1600}),
        task_id=tag,
    )


def existing_body(key: str, subject: str):
    """(path, prose, count) of the consolidated document already on disk.

    Without this the tool is only safe to run once. After the first pass
    archives its sources, a week of new dreams leaves seven Starkind
    reflections in the folder — and a second run would group those seven,
    write `people/Starkind.md`, and overwrite the document synthesised from
    229. Weekly automation would quietly destroy the corpus it built.
    """
    bucket = key.split("/", 1)[0]
    slug = re.sub(r"[^A-Za-z0-9]+", "_", subject).strip("_")[:60] or "untitled"
    path = OUT / bucket / f"{slug}.md"
    if not path.exists():
        return path, "", 0, ""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^consolidated_from:\s*(\d+)", text, re.MULTILINE)
    prior = int(m.group(1)) if m else 0
    sm = re.search(r'^consolidated_span:\s*"([^"]*)"', text, re.MULTILINE)
    prior_span = sm.group(1) if sm else ""
    body = text.split("---", 2)[-1]
    # Drop the heading and the italic provenance line; keep the prose.
    body = re.sub(r"^#\s+.*$", "", body, flags=re.MULTILINE)
    body = re.sub(r"^\*\d+ reflections? about .*\*$", "", body, flags=re.MULTILINE)
    return path, body.strip(), prior, prior_span


async def synthesise(client, model, subject: str, entries: list,
                     prior_text: str = "") -> str:
    """One document from many reflections, chunking when the group is large.

    `prior_text` is the document already written for this subject, folded back
    in as another passage so a weekly run extends what she had arrived at
    rather than replacing it with a week's worth.
    """
    def block(items):
        return "\n\n---\n\n".join(
            f"[{d or 'undated'}] {r[:PER_REFLECTION_CHARS]}" for d, _, r in items)

    chunks = [entries[i:i + CHUNK] for i in range(0, len(entries), CHUNK)]
    pieces = []
    for i, ch in enumerate(chunks, 1):
        if len(chunks) > 1:
            print(f"      pass {i}/{len(chunks)} ({len(ch)} reflections)")
        resp = await guarded_chat(
            client, model,
            SYNTHESIS_PROMPT.format(count=len(ch), subject=subject, material=block(ch)),
            f"dreamsynth_{abs(hash(subject)) % 10**6}_{i}")
        pieces.append(strip_preamble(resp["message"]["content"]))

    pieces = [p for p in pieces if p]
    if prior_text:
        # First, so the merge treats the settled view as the spine and the new
        # nights as additions to it.
        pieces.insert(0, prior_text)
    if not pieces:
        return ""
    if len(pieces) == 1:
        return pieces[0]

    material = "\n\n---\n\n".join(pieces)
    prompt = MERGE_PROMPT.format(count=len(pieces), subject=subject, material=material)
    for attempt in (1, 2):
        merged = await guarded_chat(
            client, model, prompt,
            f"dreammerge_{abs(hash(subject)) % 10**6}_{attempt}")
        out = strip_preamble(merged["message"]["content"])
        why = reads_as_essay(out)
        if not why:
            return out
        print(f"      merge {attempt} reads as an essay ({why}); "
              + ("retrying" if attempt == 1 else "keeping the passages instead"))
        prompt = (prompt
                  + "\n\nYour previous attempt used headings, bullets or the third "
                    "person. Write it again as continuous first-person prose — "
                    "paragraphs only, starting with the word 'i' or with a "
                    "concrete detail. No list of any kind.")
    # Two drifted merges is a sign the material does not want to be merged.
    # The per-chunk passages are already in her voice; keep those.
    return "\n\n".join(pieces)


def write_document(key: str, subject: str, entries: list, text: str,
                   prior_n: int = 0, prior_span: str = "") -> Path:
    bucket = key.split("/", 1)[0]
    slug = re.sub(r"[^A-Za-z0-9]+", "_", subject).strip("_")[:60] or "untitled"
    dest = OUT / bucket
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{slug}.md"

    dates = [d for d, _, _ in entries if d]
    span = f"{dates[0]} to {dates[-1]}" if dates else "unknown"
    if prior_span and dates:
        # The document now covers both windows; keep the earlier start.
        span = f"{min(prior_span.split(' to ')[0], dates[0])} to {dates[-1]}"
    # What the document now represents, not what this run happened to read.
    total = len(entries) + prior_n
    kind = {"books": "a book", "people": "someone she talks to",
            "topics": "a subject", "periods": "a month of conversations"}[bucket]

    front = (
        "---\n"
        f'title: "What Kaia thinks about {subject}"\n'
        'category: "Internal Reflection"\n'
        'document_type: "Consolidated Dream Reflection"\n'
        f'summary: "Kaia\'s settled view of {subject}, drawn together from '
        f'{total} nightly reflections between {span}."\n'
        f'keywords: ["{subject}", "reflection", "dream", "{bucket}"]\n'
        "source_type: kaia_reflection\n"
        f"consolidated_from: {total}\n"
        f"consolidated_span: \"{span}\"\n"
        f"consolidated_on: {time.strftime('%Y-%m-%d')}\n"
        "---\n\n"
    )
    body = (f"# {subject}\n\n"
            f"*{total} reflections about {kind}, {span}.*\n\n"
            f"{text}\n")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(front + body, encoding="utf-8")
    tmp.replace(path)                                  # atomic, CLAUDE.md §4
    return path


def archive(entries: list) -> int:
    n = 0
    for _, f, _ in entries:
        dest = ARCHIVE / f.relative_to(DREAMS).parent
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(dest / f.name))
        n += 1
    return n


# ── Entry point ──────────────────────────────────────────────────────

async def run(args) -> int:
    users = known_users()
    groups = plan(users)
    eligible = {k: v for k, v in groups.items() if len(v) >= args.min_group}
    skipped = len(groups) - len(eligible)

    if args.show:
        rows = [(k, v) for k, v in groups.items() if k.startswith(args.show)]
        for k, v in sorted(rows, key=lambda kv: -len(kv[1])):
            print(f"  {len(v):4d}  {k}")
        return 0

    order = sorted(eligible.items(), key=lambda kv: -len(kv[1]))
    if args.bucket:
        order = [(k, v) for k, v in order if k.lower() == args.bucket.lower()]
        if not order:
            print(f"No group named {args.bucket!r}. Try --show books")
            return 1
    if args.limit:
        order = order[: args.limit]

    total_files = sum(len(v) for _, v in order)
    print(f"{len(groups)} group(s) from {sum(len(v) for v in groups.values())} reflections; "
          f"{skipped} below --min-group {args.min_group}")
    print(f"{len(order)} group(s) to write, covering {total_files} reflection(s)"
          f"{'  (DRY RUN)' if not args.apply else ''}\n")

    for k, v in order:
        print(f"  {len(v):4d}  {k}")
    if not args.apply:
        print("\nRe-run with --apply to synthesise. Sources are archived, not deleted.")
        return 0

    from ollama import Client
    from utils.infrastructure.system.yaml_config import config
    model = config.get("chat_model", "gemma3:12b")
    client = Client(host=config.get("ollama_host", "http://localhost:11434"),
                    timeout=600)

    written = consumed = failed = 0
    for k, v in order:
        subject = k.split("/", 1)[1]
        _, prior_text, prior_n, prior_span = existing_body(k, subject)
        extra = f", extending {prior_n} already consolidated" if prior_n else ""
        print(f"\n  {k}  ({len(v)} reflections{extra})")
        try:
            text = await synthesise(client, model, subject, v, prior_text)
        except Exception as e:                          # noqa: BLE001
            print(f"      failed: {type(e).__name__}: {e}")
            failed += 1
            continue
        if len(text.split()) < 40:
            print("      model returned too little; leaving the originals alone")
            failed += 1
            continue
        path = write_document(k, subject, v, text, prior_n, prior_span)
        written += 1
        if args.archive:
            consumed += archive(v)
        print(f"      wrote {path} ({len(text.split())} words)")

    print(f"\n{written} document(s) written, {failed} skipped"
          + (f", {consumed} source(s) archived to {ARCHIVE}" if consumed else ""))
    if written:
        print("Re-index: venv/bin/python3 tools/maintenance/reindex_rag.py")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write (default: plan only)")
    ap.add_argument("--archive", action="store_true",
                    help="move consumed reflections to .dream_archive/ after writing")
    ap.add_argument("--limit", type=int, default=None, help="only the N largest groups")
    ap.add_argument("--bucket", help='one group, e.g. "books/Snow Crash"')
    ap.add_argument("--show", help='list groups under a prefix (books, people, topics, periods)')
    ap.add_argument("--min-group", type=int, default=MIN_GROUP)
    args = ap.parse_args()
    if not DREAMS.exists():
        print(f"{DREAMS} does not exist.")
        return 1
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
