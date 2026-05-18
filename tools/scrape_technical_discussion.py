#!/usr/bin/env python3
import argparse
import asyncio
import os
import json
from pathlib import Path
import sys
import time

# Add project root to path
sys.path.append(os.getcwd())

from utils.social.kaia_forum import get_forum_client, ForumClient
from utils.infrastructure.logging.kaia_logger import log_info, log_error

WORK_DIR = Path("tools/.tech_scrape_data")
CHECKPOINT_FILE = WORK_DIR / "scrape_checkpoint.json"

def ensure_work_dir():
    WORK_DIR.mkdir(parents=True, exist_ok=True)

def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r') as f:
            return json.load(f)
    return {"last_page": 0, "seen_thread_ids": []}

def save_checkpoint(last_page, seen_thread_ids):
    ensure_work_dir()
    tmp = CHECKPOINT_FILE.with_suffix('.tmp')
    with open(tmp, 'w') as f:
        json.dump({"last_page": last_page, "seen_thread_ids": list(seen_thread_ids)}, f, indent=2)
    os.replace(tmp, CHECKPOINT_FILE)

async def scrape_tech_discussion(max_pages: int = 577):
    print("--- Scraping Technical Discussion (Forum 40) ---")
    
    client = await get_forum_client()
    if not client:
        print("Forum client not configured.")
        return

    if not await client.login():
        print("Login failed.")
        return

    technical_forum_id = 40
    
    checkpoint = load_checkpoint()
    start_page = checkpoint["last_page"] + 1
    seen_thread_ids = set(checkpoint["seen_thread_ids"])
    
    if start_page > max_pages:
        print(f"Scraping already complete up to page {max_pages}.")
        return

    # Ensure output directory exists
    output_dir = Path("./knowledge_base/forum_posts/technical")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Resuming from page {start_page} to {max_pages}...")

    for page in range(start_page, max_pages + 1):
        print(f"\nScraping forum listing page {page}...")
        threads = await client.scrape_forum_listing(page=page, forum_id=technical_forum_id)
        
        # Filter out threads we've already seen (like stickies)
        new_threads = []
        for t in threads:
            if t.thread_id not in seen_thread_ids:
                new_threads.append(t)
        
        print(f"Found {len(new_threads)} new/unseen threads on page {page}.")

        # Deep scrape each thread
        for i, thread in enumerate(new_threads):
            # Optimization: Skip network request if reply count hasn't changed
            if not client.is_thread_update_needed(thread.thread_id, thread.reply_count):
                print(f"  Skipping thread {thread.thread_id} — no new posts detected.")
                seen_thread_ids.add(thread.thread_id)
                continue

            print(f"  [{i+1}/{len(new_threads)}] Scraping thread {thread.thread_id}: {thread.title[:40]}...")
            thread_data = await client.scrape_thread(thread.thread_id, full_scrape=True)
            
            if thread_data and thread_data.get('posts'):
                # Save the file
                safe_title = "".join([c if c.isalnum() else "_" for c in thread.title])
                filename = f"thread_{thread.thread_id}_{safe_title}.json"
                file_path = output_dir / filename
                
                # Convert PostInfo objects to dicts for JSON
                json_data = thread_data.copy()
                json_data['posts'] = [p.to_dict() if hasattr(p, 'to_dict') else p for p in thread_data['posts']]
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False)
                
                # Also save as markdown for RAG
                md_filename = f"thread_{thread.thread_id}_{safe_title}.md"
                md_path = output_dir / md_filename
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(f"# {thread_data['title']}\n\n")
                    f.write(f"Thread ID: {thread_data['thread_id']}\n")
                    f.write(f"URL: {client.base_url}/showthread.php?t={thread_data['thread_id']}\n\n")
                    for post in json_data['posts']:
                        f.write(f"---\n")
                        f.write(f"Post ID: {post.get('post_id', '')}\n")
                        f.write(f"Author: {post.get('author', '')}\n")
                        f.write(f"Date: {post.get('timestamp', '')}\n\n")
                        f.write(f"{post.get('content', '')}\n\n")
                
                seen_thread_ids.add(thread.thread_id)
            else:
                print(f"  No posts captured for {thread.thread_id}")
                
            # Rate limit protection
            await asyncio.sleep(3)

        # Save checkpoint after each page
        save_checkpoint(page, seen_thread_ids)

    print("\n--- Scraping Complete ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape P99 Technical Discussion Forum")
    parser.add_argument("--max-pages", type=int, default=577, help="Maximum number of pages to scrape")
    parser.add_argument("--reset", action="store_true", help="Reset checkpoint and start from page 1")
    args = parser.parse_args()

    if args.reset:
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
        print("Checkpoint reset. Starting from page 1.")

    try:
        asyncio.run(scrape_tech_discussion(max_pages=args.max_pages))
    except KeyboardInterrupt:
        print("\nScraping interrupted by user. Progress has been saved in checkpoints.")
