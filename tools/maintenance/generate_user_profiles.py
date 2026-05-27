#!/usr/bin/env python3
"""
Generate / regenerate user profile summaries from interaction logs.
Usage:
    python tools/maintenance/generate_user_profiles.py
    python tools/maintenance/generate_user_profiles.py --user Ekco_177011971818782721
    python tools/maintenance/generate_user_profiles.py --dry-run
"""
import asyncio
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.infrastructure.logging.unified_logging import replace_all_logging
replace_all_logging()

LOG_DIR = Path("knowledge_base/user_logs")
MODEL   = "gemma3:12b"

PROMPT_TEMPLATE = """You are Kaia's memory synthesis engine. Analyze these interaction logs and write my internal, first-person memories of this user.

USER: {username}
LOGS:
{log_content}

Write my memories under these headings (use ## for each):
## Interests & Topics
(What interests me about this user or what topics do we discuss?)
## Communication Style
(How do they communicate with me? Tone, quirks, or patterns I've noticed.)
## Notable Opinions or Beliefs
(What does this user believe or advocate for based on our discussions?)
## Relationship with Me
(How do I feel about my relationship with this user? Am I close to them, skeptical, or still warming up?)
## QUICK REFERENCE
(A 2-3 sentence internal summary I can use at a glance to remember who they are)

Write entirely from my perspective (first-person singular: "I", "me", "my"). Refer to the user as "{username}". Output ONLY the profile markdown. No preamble, no commentary."""


async def generate_profile(user_dir: Path, dry_run: bool = False) -> bool:
    import ollama as _ollama
    username = user_dir.name

    # Gather interaction logs (newest first, cap at ~8000 chars)
    log_files = sorted(user_dir.glob("interactions_*.md"), reverse=True)
    combined = []
    total = 0
    for lf in log_files:
        try:
            text = lf.read_text(encoding="utf-8", errors="replace")
            combined.append(text)
            total += len(text)
            if total >= 8000:
                break
        except Exception:
            continue

    if not combined:
        print(f"  SKIP {username} — no interaction logs found")
        return False

    log_content = "\n\n".join(combined)[:8000]
    prompt = PROMPT_TEMPLATE.format(username=username, log_content=log_content)

    print(f"  Generating profile for {username}...")
    if dry_run:
        print(f"    [DRY RUN] Would call {MODEL} with {len(prompt)} char prompt")
        return True

    try:
        client = _ollama.AsyncClient()
        response = await client.chat(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3, "num_predict": 800}
        )
        profile_text = response["message"]["content"].strip()

        profile_path = user_dir / "user_profile.md"
        header = (
            f"---\ngenerated: {datetime.now().isoformat()}\n"
            f"source: generate_user_profiles.py\n---\n\n"
            f"# INTERNAL MEMORY: {username}\n\n"
        )
        profile_path.write_text(header + profile_text, encoding="utf-8")
        print(f"  ✔ Wrote {profile_path}")
        return True
    except Exception as e:
        print(f"  ✘ Failed for {username}: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="Regenerate user profiles from interaction logs")
    parser.add_argument("--user", help="Only process this user directory name")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no files written")
    args = parser.parse_args()

    if not LOG_DIR.exists():
        print(f"ERROR: {LOG_DIR} not found. Run from project root.")
        sys.exit(1)

    user_dirs = [d for d in sorted(LOG_DIR.iterdir()) if d.is_dir()]
    if args.user:
        user_dirs = [d for d in user_dirs if args.user.lower() in d.name.lower()]
        if not user_dirs:
            print(f"No user directory matching '{args.user}' found.")
            sys.exit(1)

    print(f"Found {len(user_dirs)} user directories.")
    if args.dry_run:
        print("DRY RUN — no files will be written.\n")

    ok = fail = skip = 0
    for d in user_dirs:
        result = await generate_profile(d, dry_run=args.dry_run)
        if result is True:
            ok += 1
        elif result is False:
            # distinguish skip vs fail by checking log existence
            if any(d.glob("interactions_*.md")):
                fail += 1
            else:
                skip += 1

    print(f"\nDone. ✔ {ok} generated  ✘ {fail} failed  — {skip} skipped (no logs)")

if __name__ == "__main__":
    asyncio.run(main())
