#!/usr/bin/env python3
"""Compact each forum user's scattered logs into one profile, then drop the rest.

`knowledge_base/user_logs/forum_<name>_<id>/` accumulates a daily
`interactions_YYYYMMDD.md` per user plus a `post_history.md`. Measured over 218
forum users: 432 interaction files, median 111 words, and 27% of them under 25
words — a guild tag, a "+1", a bare link. `forum_entruil_122962` holds seven
daily files whose entire content is one post reading "IMAMCRU12".

None of it is read by any code and none of it is indexed (excluded in 0e82ea4).
Its only value is as raw material for `user_profile.md`, which *is* read by
`profile_handler` and carries a +0.4 retrieval boost. So: distil it into one
profile per user and remove the residue.

    python tools/maintenance/compact_forum_profiles.py                  # dry run
    python tools/maintenance/compact_forum_profiles.py --limit 5 --apply
    python tools/maintenance/compact_forum_profiles.py --apply --prune

--prune deletes the source files after the profile is written, moving them to
`knowledge_base/.compacted_backup/` first. Without it the sources stay put and
only the profile is rewritten.

Dry run by default (CLAUDE.md §10). Idempotent: a profile carrying
`compacted_from:` is skipped unless --force.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ROOT = Path("knowledge_base/user_logs")
BACKUP = Path("knowledge_base/.compacted_backup")
MIN_WORDS = 60          # below this there is nothing to profile

PROMPT = """You are Kaia. Write a private cheat sheet about a Project 1999 forum
poster, so that if you meet them in a thread you already know who you are talking to.

Use exactly these sections, as markdown headings:

## Interests & Topics
## Communication Style
## Notable Opinions or Beliefs
## How to Engage Them

Write in your own voice — direct, specific, no hedging. Cite concrete things they
actually said or did. If the material is thin, say so plainly in one line rather
than inventing a personality. Never speculate about their real identity, health,
or private life beyond what they themselves posted.

POSTER: {name}
MATERIAL ({words} words from {sources} file(s)):
{material}
"""


def prose_of(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    body = text.split("---", 2)[-1] if text.startswith("---") else text
    return re.sub(r"\[Post ID:[^\]]*\]\s*\[by[^\]]*\]", "", body).strip()


def read_watermark(d: Path) -> tuple:
    """Carry `total_posts` forward out of post_history.md.

    That number is the scraper's only dedup gate for the expensive pass:
    `scrape_active_users` compares the site's current total against the one
    recorded in post_history.md and skips when it has not moved. Pruning the
    file without preserving it means the gate can never fire, and every cycle
    re-downloads 20 post pages and 10 thread pages for every user — the exact
    loop compaction is supposed to end.
    """
    history = d / "post_history.md"
    if not history.exists():
        return None, None
    head = history.read_text(encoding="utf-8", errors="replace")[:600]
    total = re.search(r"^total_posts:\s*(\d+)", head, re.M)
    uid = re.search(r"^user_id:\s*(\d+)", head, re.M)
    return (int(total.group(1)) if total else None,
            int(uid.group(1)) if uid else None)


def already_compacted(profile: Path) -> bool:
    return profile.exists() and "compacted_from:" in profile.read_text(
        encoding="utf-8", errors="replace")[:600]


def build_profile(name: str, material: str, words: int, sources: int) -> str:
    from ollama import Client
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
    from utils.infrastructure.system.yaml_config import config

    model = config.chat_model
    opts = OllamaGPUManager(model).get_gpu_options(for_chat=True)
    resp = Client().chat(
        model=model, options={**opts, "temperature": 0.4, "num_predict": 900},
        messages=[{"role": "user", "content": PROMPT.format(
            name=name, words=words, sources=sources, material=material[-22000:])}])
    return resp["message"]["content"].strip()


def compact(d: Path, args) -> tuple:
    name = re.sub(r"_\d+$", "", d.name[len("forum_"):]).replace("_", " ")
    profile = d / "user_profile.md"
    if already_compacted(profile) and not args.force:
        return None, "already compacted"

    sources = sorted([p for p in d.iterdir()
                      if p.is_file() and p.name != "user_profile.md"
                      and p.suffix == ".md"])
    total_posts, user_id = read_watermark(d)
    material = "\n\n".join(filter(None, (prose_of(p) for p in sources)))
    words = len(material.split())
    if words < args.min_words:
        return None, f"only {words} words of material"

    if args.dry_run:
        return f"[dry run]", f"{words} words from {len(sources)} file(s)"

    try:
        card = build_profile(name, material, words, len(sources))
    except Exception as e:                            # noqa: BLE001
        return None, f"generation failed: {type(e).__name__}: {e}"
    if len(card.split()) < 40:
        return None, "model returned too little"

    front = (
        "---\n"
        f'title: "Forum profile — {name}"\n'
        'category: "User Profile"\n'
        'document_type: "User Personality Profile"\n'
        "platform: vbulletin\n"
        f'summary: "Who {name} is on the Project 1999 forums: their interests, '
        f'how they write, what they argue for, and how to talk to them."\n'
        f'keywords: ["{name}", "Project 1999", "forum", "user profile", "poster"]\n'
        f"compacted_from: {len(sources)}\n"
        f"compacted_words: {words}\n"
        f"compacted_on: {time.strftime('%Y-%m-%d')}\n"
        # The scraper's dedup watermark, carried out of post_history.md so the
        # expensive pass stays skipped after that file is pruned. New posts
        # still raise the site's total and trigger a fresh scrape; an unchanged
        # total does not.
        + (f"total_posts: {total_posts}\n" if total_posts is not None else "")
        + (f"user_id: {user_id}\n" if user_id is not None else "")
        + "---\n\n"
    )
    body = f"# INTERNAL MEMORY: {name} (Project 1999 forum)\n\n{card}\n"
    tmp = profile.with_suffix(".tmp")
    tmp.write_text(front + body, encoding="utf-8")
    tmp.replace(profile)                              # atomic, CLAUDE.md §4

    pruned = 0
    if args.prune and total_posts is None and (d / "post_history.md").exists():
        return "written", (f"{words} words from {len(sources)} file(s); "
                           "NOT pruned — no total_posts watermark to carry")
    if args.prune:
        dest = BACKUP / d.name
        dest.mkdir(parents=True, exist_ok=True)
        for p in sources:
            shutil.copy2(p, dest / p.name)
            p.unlink()
            pruned += 1
    return "written", f"{words} words from {len(sources)} file(s)" + (
        f", {pruned} pruned" if pruned else "")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--prune", action="store_true",
                    help="delete the source files after writing, backing them up first")
    ap.add_argument("--force", action="store_true", help="redo already-compacted users")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--min-words", type=int, default=MIN_WORDS)
    args = ap.parse_args()
    args.dry_run = not args.apply

    dirs = sorted(d for d in ROOT.iterdir()
                  if d.is_dir() and d.name.startswith("forum_"))
    if args.limit:
        dirs = dirs[: args.limit]

    print(f"{len(dirs)} forum user(s){'  (DRY RUN)' if args.dry_run else ''}"
          f"{'  [--prune]' if args.prune else ''}\n")
    done = skipped = 0
    for d in dirs:
        status, note = compact(d, args)
        if status:
            done += 1
            print(f"  ok    {d.name[:46]:46s} {note}")
        else:
            skipped += 1
            if args.verbose if hasattr(args, "verbose") else False:
                print(f"  skip  {d.name[:46]:46s} {note}")
    print(f"\n{done} compacted, {skipped} skipped."
          + ("\nRe-run with --apply to write." if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
