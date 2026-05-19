#!/usr/bin/env python3
"""
P99 "What Are You Listening To?" Thread Scraper
================================================
Scrapes all 752 pages of the Project 1999 forum thread, extracts YouTube links,
resolves song metadata via yt-dlp and MusicBrainz, and uploads to Google Sheets.

Usage:
    # Full pipeline (resumable — picks up where it left off)
    python tools/scrape_music_thread.py

    # Run specific stages
    python tools/scrape_music_thread.py --stage scrape      # Stage 1: Scrape forum pages
    python tools/scrape_music_thread.py --stage resolve      # Stage 2: Resolve YouTube titles
    python tools/scrape_music_thread.py --stage enrich       # Stage 3: MusicBrainz enrichment
    python tools/scrape_music_thread.py --stage upload       # Stage 4: Upload to Google Sheets

    # Options
    python tools/scrape_music_thread.py --max-pages 10       # Limit scraping to first N pages
    python tools/scrape_music_thread.py --reset               # Wipe checkpoints and start fresh
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup
import ollama

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
THREAD_URL = "https://project1999.com/forums/showthread.php"
THREAD_ID = 17745
TOTAL_PAGES = 752
SCRAPE_DELAY = 1.0        # seconds between page fetches (be polite)
YTDLP_DELAY = 0.5         # seconds between yt-dlp calls
MB_DELAY = 1.1             # MusicBrainz rate limit: 1 req/sec
GOOGLE_SHEET_ID = "1SWRL2qzXImQuV8VYzR-JJCbaJie3Lb5cpNujmRHkIXE"

WORK_DIR = Path("tools/.music_scrape_data")
CHECKPOINT_SCRAPE = WORK_DIR / "checkpoint_scrape.json"
CHECKPOINT_URLS = WORK_DIR / "youtube_urls.json"
CHECKPOINT_RESOLVED = WORK_DIR / "resolved_metadata.json"
CHECKPOINT_ENRICHED = WORK_DIR / "enriched_metadata.json"
CHECKPOINT_TEXT_EXTRACTED = WORK_DIR / "text_extracted.json"
OUTPUT_CSV = WORK_DIR / "p99_music_thread.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# YouTube URL patterns
YT_PATTERNS = [
    re.compile(r'https?://(?:www\.)?youtube\.com/watch\?[^\s"<>\'\]]+', re.IGNORECASE),
    re.compile(r'https?://(?:m\.)?youtube\.com/watch\?[^\s"<>\'\]]+', re.IGNORECASE),
    re.compile(r'https?://youtu\.be/([^\s"<>\'\]?#&]+)', re.IGNORECASE),
    re.compile(r'https?://(?:www\.)?youtube\.com/embed/([^\s"<>\'\]?#&]+)', re.IGNORECASE),
    re.compile(r'https?://(?:www\.)?youtube\.com/v/([^\s"<>\'\]?#&]+)', re.IGNORECASE),
]


def ensure_work_dir():
    WORK_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default=None):
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(path: Path, data):
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def normalize_youtube_url(url: str) -> str | None:
    """Extract the canonical video ID from any YouTube URL variant."""
    url = url.strip().rstrip('.,;)')
    # Remove HTML entities
    url = url.replace('&amp;', '&')

    # youtu.be/ID
    m = re.match(r'https?://youtu\.be/([a-zA-Z0-9_-]{11})', url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"

    # /embed/ID or /v/ID
    m = re.match(r'https?://(?:www\.)?youtube\.com/(?:embed|v)/([a-zA-Z0-9_-]{11})', url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"

    # Standard watch?v=ID
    parsed = urlparse(url)
    if 'youtube.com' in parsed.netloc:
        qs = parse_qs(parsed.query)
        v = qs.get('v', [None])[0]
        if v and len(v) == 11:
            return f"https://www.youtube.com/watch?v={v}"

    return None


def extract_video_id(url: str) -> str | None:
    """Get just the video ID from a normalized URL."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    v = qs.get('v', [None])[0]
    return v


# ===========================================================================
# Stage 1: Scrape Forum Pages
# ===========================================================================
def stage_scrape(max_pages: int = TOTAL_PAGES):
    """Scrape the forum thread and extract all YouTube URLs."""
    ensure_work_dir()

    # Load checkpoint
    checkpoint = load_json(CHECKPOINT_SCRAPE, {"last_page": 0, "urls": {}})
    start_page = checkpoint["last_page"] + 1
    all_urls = checkpoint["urls"]  # {normalized_url: {video_id, first_seen_page, poster}}

    if start_page > max_pages:
        print(f"✓ Scraping already complete ({len(all_urls)} unique URLs from {checkpoint['last_page']} pages)")
        return all_urls

    session = requests.Session()
    session.headers.update(HEADERS)

    end_page = min(max_pages, TOTAL_PAGES)
    print(f"📄 Scraping pages {start_page}–{end_page} (found {len(all_urls)} URLs so far)...")

    for page in range(start_page, end_page + 1):
        try:
            resp = session.get(THREAD_URL, params={"t": THREAD_ID, "page": page}, timeout=15)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, 'html.parser')

            # Find all post content divs
            posts = soup.find_all('div', id=re.compile(r'^post_message_\d+'))

            page_count = 0
            for post in posts:
                post_text = str(post)
                # Also get poster name from the parent structure
                poster = "Unknown"
                post_id_match = re.search(r'post_message_(\d+)', post.get('id', ''))
                if post_id_match:
                    pid = post_id_match.group(1)
                    # vBulletin stores username in a specific structure
                    user_link = soup.find('a', class_='bigusername', href=re.compile(rf'member\.php.*'))
                    # Just grab from the post block
                    post_root = post.find_parent('div', id=re.compile(r'^edit\d+'))
                    if post_root:
                        ulink = post_root.find('a', class_='bigusername')
                        if ulink:
                            poster = ulink.get_text(strip=True)

                # Extract YouTube links
                for pattern in YT_PATTERNS:
                    for match in pattern.finditer(post_text):
                        raw_url = match.group(0)
                        normalized = normalize_youtube_url(raw_url)
                        if normalized and normalized not in all_urls:
                            vid = extract_video_id(normalized)
                            all_urls[normalized] = {
                                "video_id": vid,
                                "first_seen_page": page,
                                "poster": poster,
                                "raw_url": raw_url,
                            }
                            page_count += 1

            # Progress
            if page % 10 == 0 or page == end_page:
                print(f"  Page {page}/{end_page} — {len(all_urls)} unique URLs (+{page_count} this page)")

            # Checkpoint every 25 pages
            if page % 25 == 0:
                checkpoint["last_page"] = page
                checkpoint["urls"] = all_urls
                save_json(CHECKPOINT_SCRAPE, checkpoint)

            time.sleep(SCRAPE_DELAY)

        except requests.RequestException as e:
            print(f"  ⚠ Page {page} failed: {e}. Saving checkpoint and continuing...")
            checkpoint["last_page"] = page - 1
            checkpoint["urls"] = all_urls
            save_json(CHECKPOINT_SCRAPE, checkpoint)
            time.sleep(3)  # Back off on errors
            continue

    # Final checkpoint
    checkpoint["last_page"] = end_page
    checkpoint["urls"] = all_urls
    save_json(CHECKPOINT_SCRAPE, checkpoint)
    save_json(CHECKPOINT_URLS, all_urls)

    print(f"✓ Scrape complete: {len(all_urls)} unique YouTube URLs from {end_page} pages")
    return all_urls


# ===========================================================================
# Feature 1: LLM Text Extraction
# ===========================================================================
def stage_extract_text(max_pages: int = TOTAL_PAGES):
    """Scrape posts without YouTube links and extract Artist - Song using Ollama."""
    ensure_work_dir()
    
    checkpoint = load_json(CHECKPOINT_TEXT_EXTRACTED, {"last_page": 0, "entries": {}})
    start_page = checkpoint["last_page"] + 1
    entries = checkpoint["entries"]
    
    if start_page > max_pages:
        print(f"✓ Text extraction already complete ({len(entries)} songs found)")
        return entries
        
    session = requests.Session()
    session.headers.update(HEADERS)
    
    try:
        client = ollama.Client(host='http://localhost:11434')
    except Exception as e:
        print(f"✗ Could not connect to Ollama: {e}")
        return entries

    end_page = min(max_pages, TOTAL_PAGES)
    print(f"🤖 Extracting text-only songs via Ollama pages {start_page}–{end_page}...")
    
    prompt_template = """
    You are a helpful assistant parsing a music forum thread. 
    A user posted this message. Extract the Artist and Song Name.
    If it is just normal conversation or banter, return exactly "null".
    If it is a song, return ONLY the output in this exact format: Artist - Song Name
    
    Message: {text}
    """

    for page in range(start_page, end_page + 1):
        try:
            resp = session.get(THREAD_URL, params={"t": THREAD_ID, "page": page}, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            posts = soup.find_all('div', id=re.compile(r'^post_message_\d+'))
            
            page_count = 0
            for post in posts:
                post_text_html = str(post)
                # Skip if it has a youtube link (handled by main scraper)
                has_yt = any(p.search(post_text_html) for p in YT_PATTERNS)
                if has_yt:
                    continue
                    
                post_text = post.get_text(separator=' ', strip=True)
                if not post_text or len(post_text) < 5 or len(post_text) > 300:
                    continue # Skip empty or extremely long rants
                    
                poster = "Unknown"
                post_root = post.find_parent('div', id=re.compile(r'^edit\d+'))
                if post_root:
                    ulink = post_root.find('a', class_='bigusername')
                    if ulink:
                        poster = ulink.get_text(strip=True)
                        
                # Ask Ollama
                prompt = prompt_template.replace('{text}', post_text)
                try:
                    response = client.chat(model='gemma3:12b', messages=[{'role': 'user', 'content': prompt}])
                    result = response['message']['content'].strip()
                    if result.lower() != 'null' and ' - ' in result:
                        artist, song = result.split(' - ', 1)
                        # Use a fake URL as a unique key
                        fake_url = f"text://page{page}_{poster}_{len(entries)}"
                        entries[fake_url] = {
                            "video_id": "",
                            "raw_title": result,
                            "artist": artist.strip(),
                            "song": song.strip(),
                            "album": "",
                            "year": "",
                            "genre": "",
                            "channel": "",
                            "poster": poster,
                            "page": page,
                            "status": "resolved"
                        }
                        page_count += 1
                except Exception:
                    continue

            if page % 10 == 0 or page == end_page:
                print(f"  Page {page}/{end_page} — {len(entries)} text songs extracted (+{page_count})")

            checkpoint["last_page"] = page
            checkpoint["entries"] = entries
            save_json(CHECKPOINT_TEXT_EXTRACTED, checkpoint)
            time.sleep(SCRAPE_DELAY)
            
        except requests.RequestException as e:
            print(f"  ⚠ Page {page} failed: {e}. Saving checkpoint...")
            break

    print(f"✓ Text extraction complete: {len(entries)} songs found.")
    return entries


# ===========================================================================
# Stage 2: Resolve YouTube Metadata via yt-dlp
# ===========================================================================
def stage_resolve():
    """Resolve YouTube URLs to Artist - Song using yt-dlp."""
    ensure_work_dir()

    urls = load_json(CHECKPOINT_URLS)
    if not urls:
        # Fall back to scrape checkpoint
        scrape_data = load_json(CHECKPOINT_SCRAPE, {})
        urls = scrape_data.get("urls", {})

    if not urls:
        print("✗ No URLs found. Run --stage scrape first.")
        return {}

    resolved = load_json(CHECKPOINT_RESOLVED, {})
    remaining = [u for u in urls if u not in resolved]

    if not remaining:
        print(f"✓ All {len(resolved)} URLs already resolved")
        return resolved

    print(f"🎵 Resolving {len(remaining)} YouTube URLs ({len(resolved)} already done)...")

    for i, url in enumerate(remaining):
        vid_info = urls[url]
        video_id = vid_info.get("video_id", "")

        try:
            result = subprocess.run(
                [
                    "yt-dlp",
                    "--print", "%(title)s|||%(artist)s|||%(album)s|||%(release_year)s|||%(genre)s|||%(channel)s",
                    "--skip-download",
                    "--no-warnings",
                    "--socket-timeout", "10",
                    url,
                ],
                capture_output=True, text=True, timeout=20
            )

            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("|||")
                title = parts[0] if len(parts) > 0 else ""
                yt_artist = parts[1] if len(parts) > 1 and parts[1] != "NA" else ""
                yt_album = parts[2] if len(parts) > 2 and parts[2] != "NA" else ""
                yt_year = parts[3] if len(parts) > 3 and parts[3] != "NA" else ""
                yt_genre = parts[4] if len(parts) > 4 and parts[4] != "NA" else ""
                channel = parts[5] if len(parts) > 5 and parts[5] != "NA" else ""

                # Parse Artist - Song from title
                artist, song = parse_artist_song(title, yt_artist, channel)

                resolved[url] = {
                    "video_id": video_id,
                    "raw_title": title,
                    "artist": artist,
                    "song": song,
                    "album": yt_album,
                    "year": yt_year,
                    "genre": yt_genre,
                    "channel": channel,
                    "poster": vid_info.get("poster", "Unknown"),
                    "page": vid_info.get("first_seen_page", 0),
                    "status": "resolved",
                }
            else:
                # Video unavailable / deleted / private
                resolved[url] = {
                    "video_id": video_id,
                    "raw_title": "",
                    "artist": "",
                    "song": "",
                    "album": "",
                    "year": "",
                    "genre": "",
                    "channel": "",
                    "poster": vid_info.get("poster", "Unknown"),
                    "page": vid_info.get("first_seen_page", 0),
                    "status": "unavailable",
                    "error": result.stderr.strip()[:200] if result.stderr else "No output",
                }

        except (subprocess.TimeoutExpired, Exception) as e:
            resolved[url] = {
                "video_id": video_id,
                "raw_title": "",
                "artist": "",
                "song": "",
                "album": "",
                "year": "",
                "genre": "",
                "channel": "",
                "poster": vid_info.get("poster", "Unknown"),
                "page": vid_info.get("first_seen_page", 0),
                "status": "error",
                "error": str(e)[:200],
            }

        # Progress
        done = len(resolved)
        total = len(urls)
        if (i + 1) % 25 == 0 or (i + 1) == len(remaining):
            available = sum(1 for v in resolved.values() if v.get("status") == "resolved")
            print(f"  {done}/{total} resolved ({available} available, {done - available} unavailable/error)")

        # Checkpoint every 50
        if (i + 1) % 50 == 0:
            save_json(CHECKPOINT_RESOLVED, resolved)

        time.sleep(YTDLP_DELAY)

    save_json(CHECKPOINT_RESOLVED, resolved)
    available = sum(1 for v in resolved.values() if v.get("status") == "resolved")
    print(f"✓ Resolution complete: {available} available / {len(resolved) - available} unavailable")
    return resolved


def parse_artist_song(title: str, yt_artist: str, channel: str) -> tuple[str, str]:
    """
    Parse 'Artist - Song' from a YouTube title.
    Handles common patterns:
      - Artist - Song Name
      - Artist - Song Name (Official Video)
      - Artist - Song Name [Official Music Video]
      - Artist "Song Name"
    """
    if not title:
        return ("", "")

    # Clean up common suffixes
    cleaned = title.strip()
    # Remove common video type markers
    cleaned = re.sub(r'\s*[\(\[]\s*(?:Official\s+)?(?:Music\s+)?(?:Video|Audio|Lyric(?:s)?|Visualizer|Live|HD|HQ|4K|Remaster(?:ed)?)\s*[\)\]]', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*[\(\[]\s*\d{4}\s*[\)\]]', '', cleaned)  # Remove (2019) etc
    cleaned = re.sub(r'\s*[\(\[]\s*(?:ft\.?|feat\.?|featuring)\s+[^\)\]]+[\)\]]', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*\|\s*.*$', '', cleaned)  # Remove "| Topic" suffixes
    cleaned = cleaned.strip()

    # Primary split: "Artist - Song"
    separators = [' - ', ' — ', ' – ', ' // ', ' ~ ']
    for sep in separators:
        if sep in cleaned:
            parts = cleaned.split(sep, 1)
            artist = parts[0].strip()
            song = parts[1].strip()
            if artist and song:
                return (artist, song)

    # Fallback: if yt-dlp found an artist, use title as song
    if yt_artist:
        return (yt_artist, cleaned)

    # Fallback: use channel as artist, title as song
    if channel and channel != "NA":
        return (channel, cleaned)

    # Last resort: title is all we have
    return ("", cleaned)


# ===========================================================================
# Feature 2: Wayback Machine Recovery
# ===========================================================================
def stage_recover_dead():
    """Attempt to recover dead YouTube links using the Wayback Machine CDX API."""
    ensure_work_dir()
    resolved = load_json(CHECKPOINT_RESOLVED, {})
    if not resolved:
        print("✗ No resolved data. Run --stage resolve first.")
        return {}
        
    dead_urls = [url for url, data in resolved.items() if data.get("status") in ("unavailable", "error")]
    if not dead_urls:
        print("✓ No dead links to recover!")
        return resolved
        
    print(f"🕵️ Attempting Wayback Machine recovery on {len(dead_urls)} dead links...")
    recovered_count = 0
    
    for i, url in enumerate(dead_urls):
        data = resolved[url]
        try:
            # Query CDX API
            cdx_url = f"http://web.archive.org/cdx/search/cdx?url={url}&output=json&limit=1"
            resp = requests.get(cdx_url, timeout=10)
            if resp.status_code == 200:
                try:
                    cdx_data = resp.json()
                    if len(cdx_data) > 1: # Row 0 is header, Row 1 is data
                        timestamp = cdx_data[1][1]
                        snapshot_url = f"http://web.archive.org/web/{timestamp}/{url}"
                        
                        # Fetch snapshot to grab title
                        snap_resp = requests.get(snapshot_url, timeout=15)
                        if snap_resp.status_code == 200:
                            soup = BeautifulSoup(snap_resp.text, 'html.parser')
                            title_tag = soup.find('title')
                            if title_tag:
                                title = title_tag.get_text(strip=True)
                                title = title.replace(" - YouTube", "").strip()
                                artist, song = parse_artist_song(title, "", "")
                                if artist or song:
                                    data["raw_title"] = title
                                    data["artist"] = artist
                                    data["song"] = song
                                    data["status"] = "resolved"
                                    resolved[url] = data
                                    recovered_count += 1
                                    print(f"    ✓ Recovered: {title}")
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass # Wayback Machine is flaky, ignore errors
            
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(dead_urls)} dead links checked ({recovered_count} recovered so far)")
            save_json(CHECKPOINT_RESOLVED, resolved)
            
        time.sleep(2) # Be very gentle with Wayback Machine API
        
    save_json(CHECKPOINT_RESOLVED, resolved)
    print(f"✓ Wayback Recovery complete! Resurrected {recovered_count} songs.")
    return resolved


# ===========================================================================
# Stage 3: Enrich with MusicBrainz
# ===========================================================================
def stage_enrich():
    """Enrich resolved tracks with album/year/genre from MusicBrainz."""
    ensure_work_dir()

    resolved = load_json(CHECKPOINT_RESOLVED, {})
    if not resolved:
        print("✗ No resolved data. Run --stage resolve first.")
        return {}

    enriched = load_json(CHECKPOINT_ENRICHED, {})

    # Only enrich tracks that have artist+song but are missing album/year/genre
    needs_enrichment = []
    for url, data in resolved.items():
        if data.get("status") != "resolved":
            continue
        if url in enriched:
            continue
        if data.get("artist") and data.get("song"):
            # Only if we're missing metadata
            if not data.get("album") or not data.get("year") or not data.get("genre"):
                needs_enrichment.append(url)
            else:
                enriched[url] = data  # Already complete
        else:
            enriched[url] = data  # Can't enrich without artist/song

    if not needs_enrichment:
        # Copy over any remaining resolved entries
        for url, data in resolved.items():
            if url not in enriched:
                enriched[url] = data
        save_json(CHECKPOINT_ENRICHED, enriched)
        print(f"✓ Enrichment complete ({len(enriched)} entries)")
        return enriched

    import musicbrainzngs
    musicbrainzngs.set_useragent("P99MusicScraper", "1.0", "https://github.com/Ekco-S64QTN6/Kaiacord")

    print(f"🔍 Enriching {len(needs_enrichment)} tracks via MusicBrainz ({len(enriched)} already done)...")

    for i, url in enumerate(needs_enrichment):
        data = resolved[url].copy()
        artist = data.get("artist", "")
        song = data.get("song", "")

        try:
            # Search for the recording
            result = musicbrainzngs.search_recordings(
                query=f'recording:"{song}" AND artist:"{artist}"',
                limit=1
            )

            recordings = result.get("recording-list", [])
            if recordings:
                rec = recordings[0]
                # Get release info
                releases = rec.get("release-list", [])
                if releases:
                    release = releases[0]
                    if not data.get("album"):
                        data["album"] = release.get("title", "")
                    if not data.get("year"):
                        date = release.get("date", "")
                        if date:
                            data["year"] = date[:4]

                # Get tags (genre approximation)
                tags = rec.get("tag-list", [])
                if tags and not data.get("genre"):
                    # Pick the highest-scored tag
                    tags.sort(key=lambda t: int(t.get("count", 0)), reverse=True)
                    data["genre"] = tags[0].get("name", "").title()

                # Update artist name to canonical form if available
                artist_credit = rec.get("artist-credit", [])
                if artist_credit:
                    canonical = artist_credit[0].get("artist", {}).get("name", "")
                    if canonical:
                        data["artist"] = canonical

        except Exception as e:
            pass  # MusicBrainz lookup is best-effort

        enriched[url] = data

        if (i + 1) % 25 == 0 or (i + 1) == len(needs_enrichment):
            print(f"  {len(enriched)}/{len(resolved)} enriched")

        if (i + 1) % 100 == 0:
            save_json(CHECKPOINT_ENRICHED, enriched)

        time.sleep(MB_DELAY)

    # Copy any remaining non-enrichable entries
    for url, data in resolved.items():
        if url not in enriched:
            enriched[url] = data

    save_json(CHECKPOINT_ENRICHED, enriched)
    print(f"✓ Enrichment complete: {len(enriched)} entries")
    return enriched


# ===========================================================================
# Stage 4: Export CSV + Upload to Google Sheets
# ===========================================================================
def stage_upload():
    """Export to CSV and upload to Google Sheets."""
    ensure_work_dir()

    enriched = load_json(CHECKPOINT_ENRICHED, {})
    if not enriched:
        # Fall back to resolved
        enriched = load_json(CHECKPOINT_RESOLVED, {})
    if not enriched:
        print("✗ No data to upload. Run previous stages first.")
        return

    # Merge in text-extracted songs
    text_data = load_json(CHECKPOINT_TEXT_EXTRACTED, {}).get("entries", {})
    for url, data in text_data.items():
        enriched[url] = data

    # Build aggregated rows
    aggregated = {}
    for url, data in enriched.items():
        if data.get("status") != "resolved":
            continue
            
        artist = data.get("artist", "").strip()
        song = data.get("song", "").strip()
        if not artist and not song:
            continue
            
        # Group by case-insensitive artist and song
        key = (artist.lower(), song.lower())
        poster = data.get("poster", "")
        page = str(data.get("page", ""))
        
        if key not in aggregated:
            aggregated[key] = {
                "Count": 1,
                "Artist": artist,
                "Song": song,
                "Album": data.get("album", ""),
                "Year": data.get("year", ""),
                "Genre": data.get("genre", ""),
                "Posted By": [poster] if poster else [],
                "Thread Pages": [page] if page else [],
                "YouTube URLs": [url],
            }
        else:
            aggregated[key]["Count"] += 1
            if poster and poster not in aggregated[key]["Posted By"]:
                aggregated[key]["Posted By"].append(poster)
            if page and page not in aggregated[key]["Thread Pages"]:
                aggregated[key]["Thread Pages"].append(page)
            if url not in aggregated[key]["YouTube URLs"]:
                aggregated[key]["YouTube URLs"].append(url)

    # Format the aggregated lists into strings
    rows = []
    for data in aggregated.values():
        data["Posted By"] = ", ".join(data["Posted By"])
        data["Thread Pages"] = ", ".join(data["Thread Pages"])
        data["YouTube URLs"] = ", ".join(data["YouTube URLs"])
        rows.append(data)

    # Sort by Count (descending), then Artist, then Song
    rows.sort(key=lambda r: (-r["Count"], r["Artist"].lower(), r["Song"].lower()))

    # Write CSV
    fieldnames = ["Count", "Artist", "Song", "Album", "Year", "Genre", "Posted By", "Thread Pages", "YouTube URLs"]
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    available = len(rows)
    unavailable = sum(1 for d in enriched.values() if d.get("status") != "resolved")
    print(f"📊 CSV exported: {OUTPUT_CSV} ({available} tracks, {unavailable} unavailable/dead links skipped)")

    # Upload to Google Sheets
    print(f"📤 Uploading {len(rows)} rows to Google Sheets...")
    try:
        upload_to_sheets(rows, fieldnames)
        print(f"✓ Google Sheets updated: https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}")
    except Exception as e:
        print(f"⚠ Google Sheets upload failed: {e}")
        print(f"  CSV is saved at {OUTPUT_CSV} — you can import manually.")
        print(f"  To fix: ensure Google Sheets API is enabled in your Google Cloud project")
        print(f"  and create a service account. See below for details.")
        raise


def upload_to_sheets(rows: list[dict], fieldnames: list[str]):
    """Upload data to Google Sheets using service account or API key."""
    # Try service account first
    sa_path = Path("config/secrets/.google_service_account.json")
    if not sa_path.exists():
        sa_path = Path(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "config/secrets/.google_service_account.json"))

    if sa_path.exists():
        _upload_via_service_account(rows, fieldnames, sa_path)
    else:
        # Fall back to API key approach (Sheets API v4 with public-edit sheet)
        _upload_via_api_key(rows, fieldnames)


def _upload_via_service_account(rows, fieldnames, sa_path):
    """Upload using gspread with service account credentials."""
    import gspread
    gc = gspread.service_account(filename=str(sa_path))
    sheet = gc.open_by_key(GOOGLE_SHEET_ID)
    worksheet = sheet.sheet1

    # Clear existing data
    worksheet.clear()

    # Write header + data
    all_data = [fieldnames] + [[row.get(f, "") for f in fieldnames] for row in rows]
    worksheet.update(range_name='A1', values=all_data)

    # Format header row (bold)
    worksheet.format('A1:I1', {'textFormat': {'bold': True}})

    print(f"  ✓ Uploaded {len(rows)} rows via service account")


def _upload_via_api_key(rows, fieldnames):
    """Upload using Google Sheets API v4 with API key (for public-edit sheets)."""
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("No GEMINI_API_KEY found in .env and no service account file exists.\n"
                           "To upload, either:\n"
                           "  1. Create a Google Cloud service account and save as .google_service_account.json\n"
                           "  2. Or import the CSV manually into Google Sheets")

    # Try using the Sheets API with the API key
    from googleapiclient.discovery import build
    service = build('sheets', 'v4', developerKey=api_key)

    # Prepare data
    all_data = [fieldnames] + [[row.get(f, "") for f in fieldnames] for row in rows]

    body = {
        'values': all_data
    }

    # Clear existing data
    service.spreadsheets().values().clear(
        spreadsheetId=GOOGLE_SHEET_ID,
        range='Sheet1',
        body={}
    ).execute()

    # Write new data
    service.spreadsheets().values().update(
        spreadsheetId=GOOGLE_SHEET_ID,
        range='A1',
        valueInputOption='RAW',
        body=body
    ).execute()

    print(f"  ✓ Uploaded {len(rows)} rows via API key")


# ===========================================================================
# Main
# ===========================================================================
def main():
    parser = argparse.ArgumentParser(description="P99 Music Thread Scraper")
    parser.add_argument("--stage", choices=["scrape", "extract_text", "resolve", "recover_dead", "enrich", "upload", "all"], default="all",
                        help="Which stage to run (default: all)")
    parser.add_argument("--max-pages", type=int, default=TOTAL_PAGES,
                        help=f"Max pages to scrape (default: {TOTAL_PAGES})")
    parser.add_argument("--reset", action="store_true",
                        help="Wipe all checkpoints and start fresh")
    args = parser.parse_args()

    if args.reset:
        import shutil
        if WORK_DIR.exists():
            shutil.rmtree(WORK_DIR)
        print("🗑 Checkpoints cleared")

    ensure_work_dir()

    stages = {
        "scrape": lambda: stage_scrape(args.max_pages),
        "extract_text": lambda: stage_extract_text(args.max_pages),
        "resolve": stage_resolve,
        "recover_dead": stage_recover_dead,
        "enrich": stage_enrich,
        "upload": stage_upload,
    }

    start_time = time.time()

    if args.stage == "all":
        print("=" * 60)
        print("P99 Music Thread Scraper — Full Pipeline")
        print(f"Thread: https://project1999.com/forums/showthread.php?t={THREAD_ID}")
        print(f"Pages: up to {args.max_pages}")
        print(f"Output: {OUTPUT_CSV}")
        print(f"Google Sheet: https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}")
        print("=" * 60)

        for name, fn in stages.items():
            print(f"\n{'─' * 40}")
            print(f"Stage: {name.upper()}")
            print(f"{'─' * 40}")
            fn()
    else:
        stages[args.stage]()

    elapsed = time.time() - start_time
    hours, remainder = divmod(int(elapsed), 3600)
    minutes, seconds = divmod(remainder, 60)
    print(f"\n⏱ Total time: {hours}h {minutes}m {seconds}s")


if __name__ == "__main__":
    main()
