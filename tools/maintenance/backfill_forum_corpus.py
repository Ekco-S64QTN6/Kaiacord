#!/usr/bin/env python3
"""
tools/maintenance/backfill_forum_corpus.py

One-time backfill of the Off-Topic corpus Kaia reads before she posts there.

She will not post on a forum she has not been reading — `lurk_progress()`
requires a threshold of scraped threads and user histories, on the principle
that someone whose first act in a community is to post has not read the room.
The periodic scrape task fills that corpus, but it walks only the top five
threads of page one every thirty minutes, so from empty it takes about a day.

This walks several listing pages in one run and clears the gate immediately.

    python tools/maintenance/backfill_forum_corpus.py --pages 4
    python tools/maintenance/backfill_forum_corpus.py --pages 6 --users 60

Rate-limited on purpose: this is someone else's server, and the whole point of
the exercise is not to be a nuisance on it.
"""
import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(dotenv_path=ROOT / ".env")


async def backfill(pages: int, users: int, delay: float, forum_id: int) -> int:
    from utils.social.kaia_forum import get_forum_client, is_forum_configured
    from utils.social.forum_participation import lurk_progress

    if not is_forum_configured():
        print("Forum is not configured — need forum.enabled plus VBULLETIN_USERNAME "
              "and VBULLETIN_PASSWORD in .env.")
        return 1

    client = await get_forum_client()
    if not client or not client._logged_in:
        print("Could not log in to the forum. Check credentials.")
        return 1

    ready, detail = lurk_progress()
    print(f"Before: {detail}{' (already sufficient)' if ready else ''}")

    all_threads, all_posts, saved = [], [], 0
    for page in range(1, pages + 1):
        threads = await client.scrape_forum_listing(page=page, forum_id=forum_id)
        if not threads:
            print(f"  page {page}: nothing returned, stopping.")
            break
        all_threads.extend(threads)
        print(f"  page {page}: {len(threads)} threads")

        for t in threads:
            if t.is_sticky:
                continue
            if not client.is_thread_update_needed(t.thread_id, t.reply_count):
                continue
            data = await client.scrape_thread(t.thread_id, last_n_posts=40)
            if data.get("posts"):
                if client.save_thread_scrape(data):
                    saved += 1
                all_posts.extend(data["posts"])
            await asyncio.sleep(delay)

    print(f"Saved {saved} thread files, {len(all_posts)} posts.")

    if all_posts:
        # Deep-scrape first. update_forum_user_profiles writes a placeholder
        # user_profile.md for every author it sees, and the deep scrape's own
        # 1-hour profile cooldown used to treat those placeholders as "already
        # done" — so running it second scraped nobody at all.
        n = await client.scrape_active_users(all_threads, all_posts, max_users=users)
        print(f"Deep-scraped {n} user histories.")
        client.update_forum_user_profiles(all_posts)

    (ROOT / "knowledge_base" / ".trigger_reindex").touch()

    ready, detail = lurk_progress()
    print(f"After:  {detail}")
    print("Lurk gate cleared — she can post in the next window."
          if ready else "Still short. Run again with more --pages.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pages", type=int, default=4, help="listing pages to walk (default 4)")
    ap.add_argument("--users", type=int, default=40, help="user histories to deep-scrape (default 40)")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between thread fetches (default 1.5)")
    ap.add_argument("--forum-id", type=int, default=19, help="vBulletin forum id (default 19, Off Topic)")
    args = ap.parse_args()
    return asyncio.run(backfill(args.pages, args.users, args.delay, args.forum_id))


if __name__ == "__main__":
    raise SystemExit(main())
