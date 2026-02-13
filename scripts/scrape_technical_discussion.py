#!/usr/bin/env python3
import asyncio
import os
import json
from pathlib import Path
import sys

# Add project root to path
sys.path.append(os.getcwd())

from utils.social.kaia_forum import get_forum_client, ForumClient
from utils.infrastructure.system.yaml_config import config
from utils.infrastructure.logging.kaia_logger import log_info, log_error

async def scrape_tech_discussion():
    print("--- Scraping Technical Discussion (Forum 40) ---")
    
    client = await get_forum_client()
    if not client:
        print("Forum client not configured.")
        return

    if not await client.login():
        print("Login failed.")
        return

    # Target: Forum 40, first 3 pages
    technical_forum_id = 40
    all_threads = []
    
    for page in range(1, 4):
        print(f"Scraping forum listing page {page}...")
        threads = await client.scrape_forum_listing(page=page, forum_id=technical_forum_id)
        all_threads.extend(threads)
        # Sleep briefly to be nice
        await asyncio.sleep(2)

    print(f"Found {len(all_threads)} threads. Starting deep scrape...")

    # Ensure output directory exists
    output_dir = Path("./knowledge_base/forum_posts/technical")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Deep scrape each thread
    for i, thread in enumerate(all_threads):
        print(f"[{i+1}/{len(all_threads)}] Scrapping thread: {thread.title}")
        
        # Capture the whole thread
        thread_data = await client.scrape_thread(thread.thread_id, full_scrape=True)
        
        if thread_data and thread_data.get('posts'):
            # Save the file
            safe_title = "".join([c if c.isalnum() else "_" for c in thread.title])
            filename = f"thread_{thread.thread_id}_{safe_title}.json"
            file_path = output_dir / filename
            
            # Convert PostInfo objects to dicts for JSON
            json_data = thread_data.copy()
            json_data['posts'] = [p.to_dict() for p in thread_data['posts']]
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            
            # Also save as markdown for RAG
            md_filename = f"thread_{thread.thread_id}_{safe_title}.md"
            md_path = output_dir / md_filename
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(f"# {thread_data['title']}\n\n")
                f.write(f"Thread ID: {thread_data['thread_id']}\n")
                f.write(f"URL: {client.base_url}/showthread.php?t={thread_data['thread_id']}\n\n")
                for post in thread_data['posts']:
                    f.write(f"---\n")
                    f.write(f"Post ID: {post.post_id}\n")
                    f.write(f"Author: {post.author}\n")
                    f.write(f"Date: {post.timestamp}\n\n")
                    f.write(f"{post.content}\n\n")
            
            print(f"  Saved to {filename}")
        else:
            print(f"  No posts captured for {thread.thread_id}")
            
        # Rate limit protection
        await asyncio.sleep(3)

    print("--- Scraping Complete ---")

if __name__ == "__main__":
    asyncio.run(scrape_tech_discussion())
