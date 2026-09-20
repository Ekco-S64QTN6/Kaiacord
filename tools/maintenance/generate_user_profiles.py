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
import re
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.infrastructure.logging.unified_logging import replace_all_logging
from utils.core.atomic_write import write_atomic
replace_all_logging()

LOG_DIR = Path("knowledge_base/user_logs")

# Resolve chat model dynamically from configuration
try:
    from utils.infrastructure.system.yaml_config import config
    MODEL = config.chat_model
except Exception:
    MODEL = "gemma3:12b"

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

Write entirely from my perspective (first-person singular: "I", "me", "my"). Refer to the user as "{username}". 
GROUNDING RULES:
- Do NOT attribute my own persona traits, background, or possessions (such as my vintage-modded robotic cat Pixel, my 20-gallon planted tank, or my workspace) to the user. Pixel is MY robotic cat, not the user's.
- Real users have their own pets (e.g., Ekco has a real tuxedo cat named Lucky; Starkind has real cats named Nala and Marley).

Output ONLY the profile markdown. No preamble, no commentary."""


def _identity(user_dir: Path):
    """(is_self, frontmatter_lines, header_suffix) for a forum directory.

    Sept 19 2026. This tool rebuilds `user_profile.md` from a fixed header and
    knows nothing about the identity registry, so it silently undoes what the
    registry knows. `forum_Kaia_322197/user_profile.md` was repaired to its
    self-reference document on Sept 18; this ran at 03:41 the next morning and
    replaced it with a third-person personality profile of Kaia, written from
    Kaia's own posts — "they are a thoughtful and observant presence, but our
    relationship remains primarily intellectual rather than personal."

    `compact_forum_profiles.py` had the same hole and was fixed first. Fixing
    one writer is not enough when two of them write the same file.
    """
    m = re.search(r"_(\d+)$", user_dir.name)
    if not m or not user_dir.name.startswith("forum_"):
        return False, "", ""
    uid = int(m.group(1))
    try:
        from utils.social.kaia_identities import registry
    except Exception:                                  # noqa: BLE001
        return False, "", ""
    if registry.is_self(uid):
        return True, "", ""
    lines, suffix = "", ""
    known_as = registry.describe_forum_user(uid)
    if known_as:
        lines += f'linked_discord: "{registry.get_discord_id(uid)}"\nknown_as: "{known_as}"\n'
        suffix = f" — this is {known_as} from Discord"
    others = registry.other_accounts(uid)
    if others:
        lines += f"also_posts_as: [{', '.join(str(o) for o in others)}]\n"
    return False, lines, suffix


SELF_PROFILE = (
    "---\n"
    'forum_username: "{name}"\n'
    "forum_user_id: {uid}\n"
    'document_type: "Self Reference"\n'
    "is_self: true\n"
    "---\n\n"
    "# THIS IS KAIA'S OWN FORUM ACCOUNT\n\n"
    "`{name}` on Project 1999 is me. Posts under this name are my own; they are "
    "not another user's, and this directory is not a record of somebody I have "
    "met.\n"
)


async def generate_profile(user_dir: Path, dry_run: bool = False) -> bool:
    import ollama as _ollama
    username = user_dir.name

    is_self, identity_lines, header_suffix = _identity(user_dir)
    if is_self:
        # Profiling her own account produces a stranger's dossier built from her
        # own words, and costs a model call to do it.
        if dry_run:
            print(f"  SELF {username} — would restore the self-reference document")
            return None
        m = re.search(r"^forum_(.+)_(\d+)$", username)
        user_dir.joinpath("user_profile.md").write_text(
            SELF_PROFILE.format(name=m.group(1) if m else username,
                                uid=m.group(2) if m else 0),
            encoding="utf-8")
        print(f"  ✔ {username} — own account, self-reference document restored")
        return True

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
        # Get consistent GPU options to prevent Ollama from reloading/duplicating models
        try:
            from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
            gpu_manager = OllamaGPUManager(MODEL)
            options = gpu_manager.get_gpu_options(for_chat=True)
            options["temperature"] = 0.3
            options["num_predict"] = 800
        except Exception:
            options = {"temperature": 0.3, "num_predict": 800}

        client = _ollama.AsyncClient()
        response = await client.chat(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            options=options
        )
        profile_text = response["message"]["content"].strip()

        profile_path = user_dir / "user_profile.md"
        header = (
            f"---\ngenerated: {datetime.now().isoformat()}\n"
            f"source: generate_user_profiles.py\n"
            # Who this is on Discord, when the registry knows. Without it the
            # document has nothing tying a forum account to the person behind it.
            f"{identity_lines}---\n\n"
            f"# INTERNAL MEMORY: {username}{header_suffix}\n\n"
        )
        write_atomic(profile_path, header + profile_text)
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
