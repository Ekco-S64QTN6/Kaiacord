#!/usr/bin/env python3
"""
tools/maintenance/refresh_forum_profiles.py

Build proper profiles for forum users, on demand.

The periodic scraper only deep-scrapes people it finds in *recent* threads, so
anyone quiet for a few months never gets one — Starkind's forum account had a
placeholder profile and no post history for exactly that reason, despite being
someone Kaia talks to daily in Discord. Waiting for them to post again is not a
plan.

    # everyone linked to a Discord identity (the people she actually knows)
    python tools/maintenance/refresh_forum_profiles.py --linked

    # one account, by forum user id
    python tools/maintenance/refresh_forum_profiles.py --user 228819

    # everyone still on a placeholder profile
    python tools/maintenance/refresh_forum_profiles.py --stubs --limit 20

Kaia's own account is always skipped. Rate-limited between users, because this
is someone else's server.
"""
import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(dotenv_path=ROOT / ".env")

USER_LOGS = ROOT / "knowledge_base" / "user_logs"


def account_dirs():
    """(forum_id, username, directory) for every scraped forum account."""
    for d in sorted(USER_LOGS.glob("forum_*_*")):
        stem = d.name[len("forum_"):]
        name, _, fid = stem.rpartition("_")
        if fid.isdigit():
            yield int(fid), name, d


def is_stub(d: Path) -> bool:
    p = d / "user_profile.md"
    if not p.exists():
        return True
    return 'document_type: "User Personality Profile"' not in \
        p.read_text(encoding="utf-8", errors="replace")[:400]


async def refresh(client, forum_id: int, username: str, directory: Path,
                  max_pages: int, force: bool) -> str:
    from utils.social.kaia_identities import registry

    if registry.is_self(forum_id):
        client._write_self_marker(username, forum_id)
        return "self — marker written, not profiled"

    if not force and not is_stub(directory):
        return "already has a real profile (use --force to redo)"

    metadata = await client.scrape_user_profile(forum_id) or {}
    snippets = await client.scrape_user_post_history(forum_id, username, max_pages=max_pages)
    if not snippets:
        return "no posts found on the forum"

    full = await client.deep_crawl_user_posts(forum_id, username, snippets, limit_threads=5)
    history = (full or []) + snippets
    try:
        client.save_user_post_history(username, forum_id, metadata, history)
    except Exception as e:
        print(f"      (post_history not written: {e})")

    text = await client.generate_personality_profile(username, forum_id, history, metadata)
    if not text:
        return "profile was rejected or emptied by the filters"
    known = registry.describe_forum_user(forum_id)
    return f"profiled from {len(history)} posts" + (f" — known as {known}" if known else "")


async def main_async(args) -> int:
    from utils.social.kaia_forum import get_forum_client, is_forum_configured
    from utils.social.kaia_identities import registry

    if not is_forum_configured():
        print("Forum is not configured (forum.enabled + VBULLETIN_* in .env).")
        return 1
    client = await get_forum_client()
    if not client or not client._logged_in:
        print("Could not log in to the forum.")
        return 1

    accounts = list(account_dirs())
    if args.user:
        accounts = [a for a in accounts if a[0] in args.user]
    elif args.linked:
        accounts = [a for a in accounts if registry.get_discord_id(a[0])]
    elif args.stubs:
        accounts = [a for a in accounts if is_stub(a[2])]
    if args.limit:
        accounts = accounts[:args.limit]

    if not accounts:
        print("Nothing matched.")
        return 0

    print(f"{len(accounts)} account(s) to refresh\n")
    for i, (fid, name, d) in enumerate(accounts, 1):
        try:
            result = await refresh(client, fid, name, d, args.max_pages, args.force)
        except Exception as e:
            result = f"failed: {e}"
        print(f"  [{i}/{len(accounts)}] {name} ({fid}): {result}")
        if i < len(accounts):
            await asyncio.sleep(args.delay)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sel = ap.add_mutually_exclusive_group()
    sel.add_argument("--linked", action="store_true",
                     help="accounts linked to a Discord identity (default)")
    sel.add_argument("--stubs", action="store_true", help="accounts still on a placeholder")
    sel.add_argument("--user", type=int, nargs="+", metavar="FORUM_ID")
    ap.add_argument("--all", action="store_true", help="every scraped account")
    ap.add_argument("--force", action="store_true", help="redo profiles that already exist")
    ap.add_argument("--limit", type=int, help="stop after this many")
    ap.add_argument("--max-pages", type=int, default=10, help="history pages per user (default 10)")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between users (default 2)")
    args = ap.parse_args()
    if not (args.stubs or args.user or args.all):
        args.linked = True
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
