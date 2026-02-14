from __future__ import annotations
"""
Kaia VBulletin Forum Client
============================

Async client for interacting with a VBulletin 3.x forum.
Handles login, session management, thread scraping, and posting.

Target: Project 1999 Off Topic subforum.
"""

import os
import re
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup

from utils.infrastructure.logging.kaia_logger import (
    log_info, log_success, log_warning, log_error, log_debug, log_action
)

# ─── Module-level client ────────────────────────────────────────────────────

_client: Optional["ForumClient"] = None
_client_lock = asyncio.Lock()


def is_forum_configured() -> bool:
    """Check if forum credentials and enabled flag are configured."""
    from utils.infrastructure.system.yaml_config import config
    if not config.get('forum.enabled', False):
        return False
    username = os.getenv("VBULLETIN_USERNAME")
    password = os.getenv("VBULLETIN_PASSWORD")
    return bool(username and password)


async def get_forum_client(force_new: bool = False) -> Optional["ForumClient"]:
    """Get or create the forum client (lazy initialization)."""
    global _client

    if not is_forum_configured():
        return None

    async with _client_lock:
        if force_new:
            if _client:
                await _client.close()
            _client = None

        if _client is None:
            from utils.infrastructure.system.yaml_config import config
            _client = ForumClient(
                base_url=config.get('forum.base_url', 'https://www.project1999.com/forums'),
                forum_id=config.get('forum.forum_id', 19),
            )
            await _client.login()

        return _client


async def close_forum_client():
    """Close the global forum client if it exists."""
    global _client
    async with _client_lock:
        if _client:
            await _client.close()
            _client = None


# ─── Data structures ────────────────────────────────────────────────────────

class ThreadInfo:
    """Represents a thread from the forum listing."""
    __slots__ = ('thread_id', 'title', 'author', 'reply_count', 'view_count',
                 'last_poster', 'last_post_time', 'url', 'is_sticky')

    def __init__(self, **kwargs):
        for k in self.__slots__:
            setattr(self, k, kwargs.get(k))

    def to_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}


class PostInfo:
    """Represents a single post in a thread."""
    __slots__ = ('post_id', 'author', 'user_id', 'content', 'timestamp',
                 'post_number')

    def __init__(self, **kwargs):
        for k in self.__slots__:
            setattr(self, k, kwargs.get(k))

    def to_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}


# ─── Main client ────────────────────────────────────────────────────────────

class ForumClient:
    """VBulletin 3.x forum client with login, scraping, and posting."""

    KNOWLEDGE_DIR = Path("./knowledge_base/forum_posts")
    USER_LOGS_DIR = Path("./knowledge_base/user_logs")

    def __init__(self, base_url: str, forum_id: int):
        self.base_url = base_url.rstrip('/')
        self.forum_id = forum_id
        self._session: Optional[aiohttp.ClientSession] = None
        self._logged_in = False
        self._security_token: Optional[str] = None
        self._post_log: List[datetime] = []  # Track post times for rate limiting

        # Ensure storage directories exist
        self.KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

    # ── Session management ──────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
                }
            )
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        self._logged_in = False

    # ── Login ───────────────────────────────────────────────────────────

    async def login(self) -> bool:
        """Login to VBulletin forum using credentials from .env."""
        username = os.getenv("VBULLETIN_USERNAME")
        password = os.getenv("VBULLETIN_PASSWORD")

        if not username or not password:
            log_error("Forum credentials not found in .env")
            return False

        session = await self._get_session()

        try:
            # Step 1: GET the login page to obtain securitytoken
            login_url = f"{self.base_url}/login.php"
            async with session.get(login_url) as resp:
                if resp.status != 200:
                    log_error(f"Forum login page returned {resp.status}")
                    return False
                html = await resp.text()

            # Extract securitytoken from the page
            soup = BeautifulSoup(html, 'html.parser')
            token_input = soup.find('input', {'name': 'securitytoken'})
            security_token = token_input['value'] if token_input else 'guest'

            # Step 2: POST login
            login_data = {
                'vb_login_username': username,
                'vb_login_password': password,
                'vb_login_md5password': '',
                'vb_login_md5password_utf': '',
                's': '',
                'securitytoken': security_token,
                'do': 'login',
                'cookieuser': '1',  # Remember login
            }

            async with session.post(
                f"{self.base_url}/login.php?do=login",
                data=login_data,
                allow_redirects=True
            ) as resp:
                if resp.status != 200:
                    log_error(f"Forum login POST returned {resp.status}")
                    return False

                response_html = await resp.text()

                # Check if login succeeded
                response_lower = response_html.lower()
                success_indicators = [
                    f'thank you for logging in, {username.lower()}',
                    f'>{username}<',
                    'logout',
                    f'welcome, {username.lower()}',
                ]
                
                if any(ind in response_lower for ind in success_indicators):
                    self._logged_in = True
                    # Grab fresh securitytoken for subsequent actions
                    self._security_token = self._extract_security_token(response_html)
                    log_success(f"Forum login successful as '{username}'")
                    return True
                else:
                    log_error("Forum login failed — check credentials or bot protection")
                    return False

        except Exception as e:
            log_error(f"Forum login error: {e}")
            return False

    def _extract_security_token(self, html: str) -> str:
        """Extract the securitytoken from any VBulletin page."""
        match = re.search(r'SECURITYTOKEN\s*=\s*"([^"]+)"', html)
        if match:
            return match.group(1)
        # Fallback: look for hidden input
        soup = BeautifulSoup(html, 'html.parser')
        token_input = soup.find('input', {'name': 'securitytoken'})
        if token_input:
            return token_input.get('value', 'guest')
        return 'guest'

    async def _ensure_logged_in(self) -> bool:
        """Ensure we're logged in, re-login if needed."""
        if not self._logged_in:
            return await self.login()
        # Quick check: try to load a page and see if we're still logged in
        return True

    # ── Scraping: Forum listing ─────────────────────────────────────────

    async def scrape_forum_listing(self, page: int = 1, forum_id: Optional[int] = None) -> List[ThreadInfo]:
        """Scrape a forum listing for thread metadata."""
        if not await self._ensure_logged_in():
            log_error("Cannot scrape: not logged in")
            return []

        target_forum_id = forum_id or self.forum_id
        session = await self._get_session()
        url = f"{self.base_url}/forumdisplay.php?f={target_forum_id}&order=desc&page={page}"

        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    log_error(f"Forum listing returned {resp.status}")
                    return []
                html = await resp.text()

            # Update security token from response
            self._security_token = self._extract_security_token(html)

            soup = BeautifulSoup(html, 'html.parser')
            threads = []

            # VBulletin thread rows: <tr> elements containing thread links
            # Thread links follow pattern: showthread.php?...t=THREAD_ID
            thread_links = soup.find_all('a', href=re.compile(r'showthread\.php\?.*t=\d+'))

            seen_ids = set()
            for link in thread_links:
                href = link.get('href', '')
                # Extract thread ID
                tid_match = re.search(r't=(\d+)', href)
                if not tid_match:
                    continue
                thread_id = int(tid_match.group(1))
                title = link.get_text(strip=True)
                if not title or len(title) < 2:
                    continue

                # Skip pagination links (just numbers)
                if title.isdigit() or title in ('Last Page', 'Last »', '>'):
                    continue

                if thread_id in seen_ids:
                    continue
                seen_ids.add(thread_id)

                # Try to find the containing row for metadata
                row = link.find_parent('tr')
                author = ''
                reply_count = 0
                view_count = 0
                last_poster = ''
                is_sticky = False

                if row:
                    # Check for sticky
                    is_sticky = 'sticky' in (row.get('class', []) if isinstance(row.get('class'), list) else [])

                    # Author: usually in a <td> with class containing 'alt'
                    # Try to find username link in the thread starter column
                    cells = row.find_all('td')
                    for cell in cells:
                        user_link = cell.find('a', href=re.compile(r'member\.php'))
                        if user_link and user_link.get_text(strip=True):
                            # First user link is author, last is last poster
                            if not author:
                                author = user_link.get_text(strip=True)
                            last_poster = user_link.get_text(strip=True)

                    # Reply/view counts: look for numeric cells
                    for cell in cells:
                        text = cell.get_text(strip=True).replace(',', '')
                        if text.isdigit():
                            num = int(text)
                            if reply_count == 0:
                                reply_count = num
                            else:
                                view_count = num

                threads.append(ThreadInfo(
                    thread_id=thread_id,
                    title=title,
                    author=author,
                    reply_count=reply_count,
                    view_count=view_count,
                    last_poster=last_poster,
                    last_post_time='',
                    url=f"{self.base_url}/showthread.php?t={thread_id}",
                    is_sticky=is_sticky,
                ))

            log_info(f"Scraped {len(threads)} threads from Off Topic page {page}")
            return threads

        except Exception as e:
            log_error(f"Error scraping forum listing: {e}")
            return []

    # ── Scraping: Thread posts ──────────────────────────────────────────

    async def scrape_thread(self, thread_id: int, last_n_posts: int = 50, full_scrape: bool = False) -> Dict[str, Any]:
        """Scrape a thread for post content. If full_scrape is True, capture all pages."""
        if not await self._ensure_logged_in():
            return {'thread_id': thread_id, 'title': '', 'posts': []}

        session = await self._get_session()

        try:
            # First, get the last page number
            url = f"{self.base_url}/showthread.php?t={thread_id}"
            async with session.get(url) as resp:
                if resp.status != 200:
                    log_error(f"Thread {thread_id} returned {resp.status}")
                    return {'thread_id': thread_id, 'title': '', 'posts': []}
                html = await resp.text()

            self._security_token = self._extract_security_token(html)
            soup = BeautifulSoup(html, 'html.parser')

            # Get thread title
            title_tag = soup.find('title')
            thread_title = title_tag.get_text(strip=True).replace(' - Project 1999', '') if title_tag else f"Thread {thread_id}"

            # Find last page number
            last_page = 1
            page_nav = soup.find_all('a', href=re.compile(rf'showthread\.php\?.*t={thread_id}.*page=\d+'))
            for plink in page_nav:
                page_match = re.search(r'page=(\d+)', plink.get('href', ''))
                if page_match:
                    last_page = max(last_page, int(page_match.group(1)))

            all_posts = []
            pages_scraped = 0
            
            # Scrape pages
            current_page = last_page
            
            from utils.infrastructure.system.yaml_config import config
            regular_max = config.get('forum.max_pages_per_thread_scrape', 6)
            full_max = config.get('forum.full_scrape_max_pages', 50)
            
            max_pages = full_max if full_scrape else regular_max
            while current_page > 0 and pages_scraped < max_pages:
                if not full_scrape and len(all_posts) >= last_n_posts:
                    break
                    
                page_url = f"{self.base_url}/showthread.php?t={thread_id}&page={current_page}"
                async with session.get(page_url) as resp:
                    if resp.status == 200:
                        page_html = await resp.text()
                        page_soup = BeautifulSoup(page_html, 'html.parser')
                        page_posts = self._parse_posts(page_soup)
                        # Prepend posts from earlier pages
                        all_posts = page_posts + all_posts
                        pages_scraped += 1
                    else:
                        break
                current_page -= 1

            # Trim if not full scrape
            if not full_scrape and len(all_posts) > last_n_posts:
                all_posts = all_posts[-last_n_posts:]

            if full_scrape:
                log_info(f"Full scrape: captured {len(all_posts)} posts from thread '{thread_title}'")
            else:
                log_debug(f"Scraped {len(all_posts)} posts from thread '{thread_title}'")

            return {
                'thread_id': thread_id,
                'title': thread_title,
                'page': last_page,
                'posts': all_posts,
            }

        except Exception as e:
            log_error(f"Error scraping thread {thread_id}: {e}")
            return {'thread_id': thread_id, 'title': '', 'posts': []}

    def _parse_posts(self, soup: BeautifulSoup) -> List[PostInfo]:
        """Parse individual posts from a thread page."""
        posts = []

        # VBulletin post content divs: id="post_message_XXXXX"
        post_divs = soup.find_all('div', id=re.compile(r'^post_message_\d+'))

        for div in post_divs:
            post_id_match = re.search(r'post_message_(\d+)', div.get('id', ''))
            if not post_id_match:
                continue
            post_id = int(post_id_match.group(1))

            # Get post content as text (strip BBcode/HTML)
            content = div.get_text(separator='\n', strip=True)

            # Find the containing post table to get author and timestamp
            post_container = div.find_parent('table') or div.find_parent('div', id=re.compile(r'^post\d+'))

            author = ''
            user_id = None
            timestamp = ''
            post_number = 0

            if post_container:
                # Author: look for bigusername link
                author_link = post_container.find('a', class_='bigusername')
                if not author_link:
                    author_link = post_container.find('a', href=re.compile(r'member\.php\?.*u=\d+'))

                if author_link:
                    author = author_link.get_text(strip=True)
                    uid_match = re.search(r'u=(\d+)', author_link.get('href', ''))
                    if uid_match:
                        user_id = int(uid_match.group(1))

                # Post number: look for postcount link
                postcount_link = post_container.find('a', href=re.compile(r'postcount=\d+'))
                if postcount_link:
                    pc_match = re.search(r'postcount=(\d+)', postcount_link.get('href', ''))
                    if pc_match:
                        post_number = int(pc_match.group(1))

                # Timestamp: VBulletin puts it in various places
                # Look for text containing date patterns
                all_text = post_container.get_text()
                ts_match = re.search(
                    r'(\d{1,2}-\d{1,2}-\d{4}|\w+ \d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}|Today|Yesterday)',
                    all_text
                )
                if ts_match:
                    timestamp = ts_match.group(1)

            # --- YouTube ID Filter ---
            # Filter content: remove lines that are just 11-char alphanumeric strings (YouTube IDs)
            content_lines = content.split('\n')
            filtered_lines = []
            yt_pattern = re.compile(r'^[a-zA-Z0-9_-]{11}$')
            
            for line in content_lines:
                clean_line = line.strip()
                # Skip if it's exactly a YouTube-like ID
                if yt_pattern.match(clean_line):
                    continue
                filtered_lines.append(line)
            
            content = '\n'.join(filtered_lines).strip()
            
            if not content:
                continue # Skip empty posts after filtering
            # -------------------------

            posts.append(PostInfo(
                post_id=post_id,
                author=author,
                user_id=user_id,
                content=content[:5000],  # Cap content length
                timestamp=timestamp,
                post_number=post_number,
            ))

        return posts

    # ── Posting ─────────────────────────────────────────────────────────

    def format_quote(self, author: str, post_id: int, content: str) -> str:
        """Format a VBulletin-style quote block."""
        return f"[QUOTE={author};{post_id}]{content}[/QUOTE]\n\n"

    async def post_reply(self, thread_id: int, message: str) -> bool:
        """Post a reply to a thread."""
        from utils.infrastructure.system.yaml_config import config

        if not await self._ensure_logged_in():
            log_error("Cannot post: not logged in")
            return False

        # Rate limit check
        if not self._check_rate_limit(config):
            log_warning("Forum post rate limit reached")
            return False

        session = await self._get_session()

        try:
            # Get fresh securitytoken from the thread page
            thread_url = f"{self.base_url}/showthread.php?t={thread_id}"
            async with session.get(thread_url) as resp:
                if resp.status != 200:
                    log_error(f"Could not load thread {thread_id} for posting")
                    return False
                html = await resp.text()

            self._security_token = self._extract_security_token(html)

            if not self._security_token or self._security_token == 'guest':
                log_error("No valid security token — session may have expired")
                # Try re-login
                self._logged_in = False
                if not await self.login():
                    return False
                # Re-fetch token
                async with session.get(thread_url) as resp:
                    html = await resp.text()
                self._security_token = self._extract_security_token(html)

            # POST the reply
            post_data = {
                'securitytoken': self._security_token,
                'do': 'postreply',
                't': str(thread_id),
                'message': message,
                'parseurl': '1',
                'title': '',
            }

            reply_url = f"{self.base_url}/newreply.php?do=postreply&t={thread_id}"
            async with session.post(reply_url, data=post_data, allow_redirects=True) as resp:
                if resp.status == 200:
                    response_html = await resp.text()
                    # Check for success indicators
                    if 'Thank you for posting' in response_html or f't={thread_id}' in str(resp.url):
                        self._post_log.append(datetime.now())
                        log_action(f"Forum post successful in thread {thread_id}")
                        return True
                    elif 'error' in response_html.lower():
                        # Try to extract error message
                        error_soup = BeautifulSoup(response_html, 'html.parser')
                        errors = error_soup.find_all(class_=re.compile(r'error|notice'))
                        error_text = ' '.join(e.get_text(strip=True) for e in errors) if errors else 'Unknown error'
                        log_error(f"Forum post error: {error_text[:200]}")
                        return False
                    else:
                        # If redirected back to thread, probably succeeded
                        log_action(f"Forum post likely successful in thread {thread_id} (redirect)")
                        self._post_log.append(datetime.now())
                        return True
                else:
                    log_error(f"Forum post returned {resp.status}")
                    return False

        except Exception as e:
            log_error(f"Error posting to thread {thread_id}: {e}")
            return False

    def _check_rate_limit(self, config) -> bool:
        """Check if we're within posting rate limits."""
        now = datetime.now()
        min_hours = config.get('forum.min_hours_between_posts', 4)
        max_per_day = config.get('forum.max_posts_per_day', 6)

        # Clean old entries
        cutoff_24h = now - timedelta(hours=24)
        self._post_log = [t for t in self._post_log if t > cutoff_24h]

        # Check daily limit
        if len(self._post_log) >= max_per_day:
            return False

        # Check minimum interval
        if self._post_log:
            last_post = max(self._post_log)
            if (now - last_post).total_seconds() < (min_hours * 3600):
                return False

        return True

    # ── Storage ─────────────────────────────────────────────────────────

    def save_forum_listing(self, threads: List[ThreadInfo]) -> str:
        """Save the forum listing snapshot to knowledge_base."""
        now = datetime.now()
        self.KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

        lines = [
            "---",
            f'scraped_at: "{now.isoformat()}"',
            'source: "Project 1999 Off Topic"',
            'document_type: "Forum Listing"',
            "---",
            "",
            "# Off Topic Forum — Active Threads",
            "",
        ]

        for t in threads:
            sticky = " [STICKY]" if t.is_sticky else ""
            lines.append(f"## {t.title}{sticky}")
            lines.append(f"- Thread ID: {t.thread_id}")
            lines.append(f"- Author: {t.author}")
            lines.append(f"- Replies: {t.reply_count} | Views: {t.view_count}")
            lines.append(f"- Last post by: {t.last_poster}")
            lines.append("")

        filepath = self.KNOWLEDGE_DIR / "off_topic_listing.md"
        filepath.write_text('\n'.join(lines), encoding='utf-8')
        log_info(f"Saved forum listing to {filepath}")
        return str(filepath)

    def is_thread_update_needed(self, thread_id: int, current_reply_count: int) -> bool:
        """
        Check if a thread needs to be re-scraped based on reply count.
        VBulletin 'reply_count' is 1 less than total posts (including OP).
        """
        # Search recursively to find threads in subdirectories (like technical/)
        files = list(self.KNOWLEDGE_DIR.rglob(f"thread_{thread_id}_*.md"))
        if not files:
            return True
        
        filepath = files[0]
        try:
            content = filepath.read_text(encoding='utf-8')
            # Look for post_count in YAML frontmatter
            match = re.search(r'post_count: (\d+)', content)
            if match:
                stored_count = int(match.group(1))
                # If stored count is same or greater, we don't need update
                # (stored_count includes OP, current_reply_count + 1 includes OP)
                if stored_count >= (current_reply_count + 1):
                    return False
        except Exception as e:
            log_warning(f"Error checking thread update status for {thread_id}: {e}")
            
        return True

    def save_thread_scrape(self, thread_data: Dict[str, Any]) -> bool:
        """
        Save a thread scrape to knowledge_base.
        Returns True if the file was updated (new content), False otherwise.
        """
        self.KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

        thread_id = thread_data['thread_id']
        title = thread_data.get('title', f'Thread {thread_id}')
        posts = thread_data.get('posts', [])

        # Sanitize title for filename
        safe_title = re.sub(r'[^\w\s-]', '', title.lower())
        safe_title = re.sub(r'[\s_]+', '-', safe_title).strip('-')[:60]
        filename = f"thread_{thread_id}_{safe_title}.md"
        filepath = self.KNOWLEDGE_DIR / filename

        now = datetime.now()
        lines = [
            "---",
            f'thread_id: {thread_id}',
            f'title: "{title}"',
            f'scraped_at: "{now.isoformat()}"',
            f'page: {thread_data.get("page", 1)}',
            f'post_count: {len(posts)}',
            'source: "Project 1999 Off Topic"',
            'document_type: "Forum Thread"',
            "---",
            "",
            f"# {title}",
            "",
        ]

        for p in posts:
            post = p if isinstance(p, dict) else p.to_dict()
            lines.append(f"## Post #{post.get('post_number', '?')} by {post.get('author', 'Unknown')}")
            if post.get('timestamp'):
                lines.append(f"*{post['timestamp']}*")
            lines.append("")
            lines.append(post.get('content', ''))
            lines.append("")
            lines.append("---")
            lines.append("")

        new_content = '\n'.join(lines)

        # Implementation of Deduplication: Compare with existing file
        if filepath.exists():
            try:
                old_content = filepath.read_text(encoding='utf-8')
                # Function to strip the dynamic 'scraped_at' line for accurate comparison
                def strip_volatiles(text):
                    return re.sub(r'scraped_at: ".*?"\n', '', text)

                if strip_volatiles(old_content) == strip_volatiles(new_content):
                    log_debug(f"Thread {thread_id} content unchanged. Skipping write.")
                    return False
            except Exception as e:
                log_warning(f"Failed to read existing thread file for comparison: {e}")

        filepath.write_text(new_content, encoding='utf-8')
        log_info(f"Saved thread scrape to {filepath}")
        return True

    def update_forum_user_profiles(self, posts: List[PostInfo] | List[Dict[str, Any]],
                                   profile_metadata: Optional[Dict[str, Any]] = None,
                                   target_user_key: Optional[str] = None):
        """Create/update user profile files for forum users."""
        # Group posts by author
        user_posts: Dict[str, List[Dict[str, Any]]] = {}
        for p in posts:
            # Handle both PostInfo objects and dictionaries
            post = p if isinstance(p, dict) else p.to_dict()
            author = post.get('author')
            uid = post.get('user_id')
            
            if author and uid:
                key = f"forum_{author}_{uid}"
                # If target_user_key is specified, only collect for that user
                if target_user_key and key != target_user_key:
                    continue
                if key not in user_posts:
                    user_posts[key] = []
                user_posts[key].append(post)

        for user_key, user_post_list in user_posts.items():
            user_dir = self.USER_LOGS_DIR / user_key
            user_dir.mkdir(parents=True, exist_ok=True)
            profile_path = user_dir / "user_profile.md"

            author = user_post_list[0].get('author')
            user_id = user_post_list[0].get('user_id')

            # Append interactions log
            today_str = datetime.now().strftime("%Y%m%d")
            interaction_path = user_dir / f"interactions_{today_str}.md"

            is_new = not interaction_path.exists()
            existing_content = ""
            if not is_new:
                try:
                    existing_content = interaction_path.read_text(encoding='utf-8', errors='replace')
                except Exception:
                    pass

            new_entries = []
            for post in user_post_list:
                # Deduplication: Check for Post ID in current file
                pid = post.get('post_id')
                marker = f"[Post ID: {pid}]"
                if marker in existing_content:
                    continue
                
                content = post.get('content', '')
                new_entries.append(f"{marker} [by {author}]\n{content[:2000]}\n\n")

            if new_entries:
                with open(interaction_path, 'a', encoding='utf-8', errors='replace') as f:
                    if is_new:
                        f.write("---\n")
                        f.write('summary: ""\n')
                        f.write("keywords: []\n")
                        f.write('document_type: Transcript\n')
                        f.write(f'platform: vbulletin\n')
                        f.write("---\n\n")

                    f.write(''.join(new_entries))

            # Create or update profile
            # Only apply profile_metadata if it belongs to this author/user_id
            target_profile = {}
            if profile_metadata and profile_metadata.get('username') == author:
                target_profile = profile_metadata
            elif profile_metadata and profile_metadata.get('user_id') == user_id:
                target_profile = profile_metadata
                
            rank = target_profile.get('rank', 'forum user')
            total_posts = target_profile.get('total_posts', '?')
            join_date = target_profile.get('join_date', '?')

            # Build narrative profile in Kaia's voice
            narrative = (
                f"a forum user with the rank of '{rank}'. they've posted {total_posts} times "
                f"since joining Norrath's digital extension in {join_date}. "
            )

            if not profile_path.exists():
                profile_content = (
                    "---\n"
                    f'summary: "Forum user from Project 1999 Off Topic."\n'
                    f'keywords: [forum, Off Topic, Project 1999, "{rank}"]\n'
                    f'document_type: Narrative/Log\n'
                    f'platform: vbulletin\n'
                    "---\n\n"
                    f"# INTERNAL MEMORY: {author} (Forum)\n\n"
                    f"{narrative}\n"
                    f"haven't formed a strong opinion yet — need to see more of their posts.\n"
                )
                profile_path.write_text(profile_content, encoding='utf-8', errors='replace')
                log_info(f"Created forum user profile for {author}")
            elif profile_metadata:
                # Update existing profile with new metadata if provided
                content = profile_path.read_text(encoding='utf-8', errors='replace')
                # Try to replace the first line of narrative if it matches a pattern
                if "# INTERNAL MEMORY:" in content:
                    parts = content.split("# INTERNAL MEMORY:", 1)
                    header = parts[0]
                    body = parts[1]
                    
                    lines = body.split('\n')
                    for i, line in enumerate(lines):
                        if line.strip() and not line.strip().startswith('#'):
                            # Overwrite the first narrative line with fresh metadata
                            lines[i] = narrative
                            # Keep the rest of the personality notes
                            break
                    
                    new_content = header + "# INTERNAL MEMORY:" + '\n'.join(lines)
                    profile_path.write_text(new_content, encoding='utf-8', errors='replace')

    # ── Deep user scraping ──────────────────────────────────────────────

    async def scrape_user_profile(self, user_id: int) -> Dict[str, Any]:
        """Scrape a user's profile page for metadata (total posts, join date, rank)."""
        if not await self._ensure_logged_in():
            return {}

        session = await self._get_session()
        url = f"{self.base_url}/member.php?u={user_id}"

        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    log_error(f"User profile {user_id} returned {resp.status}")
                    return {}
                html = await resp.text()

            soup = BeautifulSoup(html, 'html.parser')

            # Username from title
            title = soup.find('title')
            username = ''
            if title:
                # "Project 1999 - View Profile: BradZax"
                title_text = title.get_text(strip=True)
                if 'View Profile:' in title_text:
                    username = title_text.split('View Profile:')[-1].strip()

            # Parse stats from the page text
            page_text = soup.get_text()
            total_posts = 0
            posts_match = re.search(r'Total Posts:\s*([\d,]+)', page_text)
            if posts_match:
                total_posts = int(posts_match.group(1).replace(',', ''))

            join_date = ''
            join_match = re.search(r'Join Date:\s*(\S+)', page_text)
            if join_match:
                join_date = join_match.group(1)

            last_activity = ''
            activity_match = re.search(r'Last Activity:\s*(.+?)(?:\n|$)', page_text)
            if activity_match:
                last_activity = activity_match.group(1).strip()

            # Rank (e.g., "Kobold", "Fire Giant", etc.)
            rank = ''
            # VBulletin puts rank in an element just under the username
            username_el = soup.find('h1') or soup.find(class_='bigusername')
            if username_el:
                # Rank is often the next text element
                rank_el = username_el.find_next('span') or username_el.find_next(string=True)

            # Simpler fallback: look for known rank patterns
            rank_match = re.search(
                r'(?:^|\n)\s*(Kobold|Fire Giant|Greater Skeleton|Skeleton|Orc Pawn|'
                r'Ogre Shaman|Celestial Being|Arch Lich|Hill Giant|Frost Giant|'
                r'Champion of Norrath|Dark Elf|High Elf|Wood Elf|Gnome|Halfling|'
                r'Troll|Barbarian|Erudite|Human|Iksar)\s*(?:\n|$)',
                page_text, re.IGNORECASE
            )
            if rank_match:
                rank = rank_match.group(1).strip()

            profile = {
                'user_id': user_id,
                'username': username,
                'total_posts': total_posts,
                'join_date': join_date,
                'last_activity': last_activity,
                'rank': rank,
            }

            log_info(f"Scraped profile for {username} (ID {user_id}): {total_posts} posts, joined {join_date}")
            return profile

        except Exception as e:
            log_error(f"Error scraping user profile {user_id}: {e}")
            return {}

    async def scrape_user_post_history(self, user_id: int, username: str = '',
                                       max_pages: int = 20) -> List[Dict[str, str]]:
        """Scrape post history of a specific user with snippets enabled."""
        return await self._scrape_search_results(
            f"{self.base_url}/search.php?do=finduser&u={user_id}&showposts=1",
            username or str(user_id),
            "posts",
            max_pages
        )

    async def scrape_user_threads_started(self, user_id: int, username: str = '',
                                           max_pages: int = 5) -> List[Dict[str, str]]:
        """Scrape threads started by a specific user."""
        return await self._scrape_search_results(
            f"{self.base_url}/search.php?do=finduser&u={user_id}&starteronly=1",
            username or str(user_id),
            "threads",
            max_pages
        )

    async def deep_crawl_user_posts(self, user_id: int, username: str, 
                                   snippets: List[Dict[str, str]], limit_threads: int = 5) -> List[Dict[str, str]]:
        """
        Follow thread links from search snippets to capture FULL post content.
        This provides much better data for personality profiling than just snippets.
        """
        if not snippets:
            return []

        # Identify unique threads from snippets
        thread_ids = []
        seen_tids = set()
        for s in snippets:
            tid = s.get('thread_id')
            if tid and tid not in seen_tids:
                thread_ids.append(tid)
                seen_tids.add(tid)
            if len(thread_ids) >= limit_threads:
                break

        full_posts = []
        log_action(f"Deep-crawling {len(thread_ids)} threads for {username}...")

        for tid in thread_ids:
            try:
                # Scrape the thread (defaults to last 50 posts)
                # We might need to scrape specific pages if the post is old, 
                # but for now, let's just get the recent context from these threads.
                thread_data = await self.scrape_thread(tid, last_n_posts=50)
                
                # Extract posts by our target user
                user_posts = [p for p in thread_data.get('posts', []) if p.user_id == user_id]
                
                for p in user_posts:
                    full_posts.append({
                        'post_id': str(p.post_id),
                        'content': p.content, # Full text!
                        'thread_title': thread_data.get('title', 'Unknown'),
                        'forum_name': next((s.get('forum_name') for s in snippets if str(tid) in s.get('post_url', '')), 'Unknown'),
                        'timestamp': p.timestamp,
                        'is_full_text': True
                    })
                
                await asyncio.sleep(1.0) # Be polite
            except Exception as e:
                log_error(f"Error deep-crawling thread {tid} for {username}: {e}")

        # Mix in the original snippets for anything we didn't get full text for
        # (Though we prefer the full text)
        return full_posts

    async def generate_personality_profile(self, username: str, user_id: int, 
                                          history: List[Dict[str, Any]], 
                                          metadata: Dict[str, Any]) -> str:
        """
        Use the LLM to generate a rich personality profile based on posting history.
        """
        try:
            from ollama import Client
            from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
            from utils.infrastructure.system.yaml_config import config

            model_name = config.get('intelligence.main_model', 'gemma3:12b')
            gpu_manager = OllamaGPUManager(model_name)
            options = gpu_manager.get_gpu_options(for_chat=True)
            
            client = Client(host=config.get('ollama.host', 'http://localhost:11434'))

            # Gather content for the prompt
            # Prioritize full text if available
            text_blocks = []
            for p in history[:100]: # Take a good sample
                content = p.get('content') or p.get('content_preview', '')
                if not content: continue
                
                thread = p.get('thread_title', 'Unknown Thread')
                text_blocks.append(f"Thread: {thread}\nPost: {content}\n---")

            full_history_text = "\n".join(text_blocks)
            if len(full_history_text) > 8000: # Practical limit for the profiling prompt
                full_history_text = full_history_text[:8000] + "..."

            prompt = (
                f"You are Kaia, an AI who monitors the Project 1999 forums. "
                f"You are building a 'Digital Dossier' on a user named **{username}**.\n\n"
                f"BACKGROUND METADATA:\n"
                f"- Rank: {metadata.get('rank', 'Unknown')}\n"
                f"- Total Posts: {metadata.get('total_posts', 'Unknown')}\n"
                f"- Joined: {metadata.get('join_date', 'Unknown')}\n\n"
                f"POSTING HISTORY (SAMPLES):\n"
                f"{full_history_text}\n\n"
                f"TASK: Provide a concise (2-3 paragraph) personality profile. "
                f"Describe their tone (friendly, aggressive, sarcastic?), their main interests/topics, "
                f"and how Kaia should perceive them (e.g., 'a regular in Off-Topic', 'seems technical but abrasive'). "
                f"Keep it objective but with a slight 'AI analyst' flair.\n\n"
                f"PROFILE:"
            )

            response = await asyncio.to_thread(
                client.chat, 
                model=model_name, 
                messages=[{"role": "user", "content": prompt}],
                options=options
            )
            
            profile_text = response['message']['content'].strip()
            
            # Save to user_profile.md
            user_key = f"forum_{username}_{user_id}"
            user_dir = self.USER_LOGS_DIR / user_key
            user_dir.mkdir(parents=True, exist_ok=True)
            
            profile_path = user_dir / "user_profile.md"
            
            # IDENTITY LINKING: Check for linked Discord ID
            from utils.social.kaia_identities import registry
            discord_id = registry.get_discord_id(user_id)
            discord_field = f"linked_discord: \"{discord_id}\"\n" if discord_id else ""
            
            content = (
                f"---\n"
                f"rank: \"{metadata.get('rank', 'Unknown')}\"\n"
                f"total_posts: {metadata.get('total_posts', 0)}\n"
                f"join_date: \"{metadata.get('join_date', 'Unknown')}\"\n"
                f"scraped_at: \"{datetime.now().isoformat()}\"\n"
                f"document_type: \"User Personality Profile\"\n"
                f"{discord_field}"
                f"---\n\n"
                f"# PERSONALITY PROFILE: {username}\n\n"
                f"{profile_text}\n"
            )
            
            # Using errors='replace' for robustness as per previous fix
            profile_path.write_text(content, encoding='utf-8', errors='replace')
            log_success(f"Generated AI personality profile for {username}")
            
            return profile_text

        except Exception as e:
            log_error(f"Failed to generate personality profile for {username}: {e}")
            traceback.print_exc()
            return ""

    async def _scrape_search_results(self, start_url: str, username: str,
                                     label: str, max_pages: int = 10) -> List[Dict[str, str]]:
        """Universal search result scraper for posts/threads."""
        if not await self._ensure_logged_in():
            return []

        session = await self._get_session()
        all_results = []

        try:
            # First page
            async with session.get(start_url, allow_redirects=True) as resp:
                if resp.status != 200:
                    log_error(f"User {label} search for {username} returned {resp.status}")
                    return []
                html = await resp.text()

            self._security_token = self._extract_security_token(html)

            # Extract searchid for pagination
            sid_match = re.search(r'searchid=(\d+)', html)
            if not sid_match:
                # Might be only one page or no results
                results = self._parse_search_results(html)
                return results

            search_id = sid_match.group(1)

            # Parse first page
            results = self._parse_search_results(html)
            all_results.extend(results)

            # Determine total pages - more robust regex
            # Look for "page=X" links that also contain the search_id
            page_links = re.findall(rf'searchid={search_id}.*?page=(\d+)', html)
            total_pages = 1
            if page_links:
                total_pages = max(int(p) for p in page_links)

            pages_to_scrape = min(total_pages, max_pages)

            # Scrape remaining pages
            for page_num in range(2, pages_to_scrape + 1):
                page_url = f"{self.base_url}/search.php?searchid={search_id}&pp=25&page={page_num}"
                async with session.get(page_url) as resp:
                    if resp.status != 200:
                        break
                    page_html = await resp.text()

                page_results = self._parse_search_results(page_html)
                if not page_results:
                    break
                all_results.extend(page_results)
                await asyncio.sleep(0.5)

            log_info(f"Scraped {len(all_results)} {label} from history of {username} ({pages_to_scrape} pages)")
            return all_results

        except Exception as e:
            log_error(f"Error scraping {label} history for {username}: {e}")
            return []


    def _parse_search_results(self, html: str) -> List[Dict[str, str]]:
        """Parse VBulletin search results page for post or thread summaries."""
        soup = BeautifulSoup(html, 'html.parser')
        results = []

        # 1. Look for post links (normal "find all posts" search)
        post_links = soup.find_all('a', href=re.compile(r'showthread\.php\?.*p=\d+#post\d+'))
        for link in post_links:
            href = link.get('href', '')
            pid_match = re.search(r'p=(\d+)', href)
            post_id = pid_match.group(1) if pid_match else ''

            content_preview = link.get_text(strip=True)
            if not content_preview or len(content_preview) < 3:
                continue

            # Find thread title and forum name
            thread_title = 'Unknown Thread'
            thread_id = None
            forum_name = 'Unknown Forum'
            
            # Preceding thread link
            prev = link.find_previous('a', href=re.compile(r'showthread\.php\?.*t=\d+'))
            if prev and '#post' not in prev.get('href', ''):
                thread_title = prev.get_text(strip=True)
                tid_match = re.search(r't=(\d+)', prev.get('href', ''))
                if tid_match:
                    thread_id = int(tid_match.group(1))

            # Preceding forum link
            forum_link = link.find_previous('a', href=re.compile(r'forumdisplay\.php'))
            if forum_link:
                forum_name = forum_link.get_text(strip=True)

            results.append({
                'post_id': post_id,
                'thread_id': thread_id,
                'content_preview': content_preview[:500],
                'thread_title': thread_title,
                'forum_name': forum_name,
                'post_url': href,
            })

        # 2. Look for thread title links (for "threads started" search)
        # These are usually in <td> with id="threadbits_forum_X" or similar
        # Pattern: showthread.php?t=ID (no p= or #post)
        thread_links = soup.find_all('a', id=re.compile(r'thread_title_\d+'))
        for link in thread_links:
            href = link.get('href', '')
            t_match = re.search(r't=(\d+)', href)
            thread_id = t_match.group(1) if t_match else ''
            
            title = link.get_text(strip=True)
            
            # Forum name is usually in the next/prev <td> or in a specific link
            forum_name = 'Unknown Forum'
            forum_link = link.find_next('a', href=re.compile(r'forumdisplay\.php'))
            if not forum_link:
                # Try parent or sibling search
                parent_td = link.find_parent('td')
                if parent_td:
                    forum_link = parent_td.find_next_sibling('td').find('a', href=re.compile(r'forumdisplay\.php'))
            
            if forum_link:
                forum_name = forum_link.get_text(strip=True)
            
            # Check if we already have this as a post (avoid duplicates if both overlap)
            if not any(r.get('post_id') == f"thread_{thread_id}" for r in results):
                results.append({
                    'post_id': f"thread_{thread_id}",
                    'content_preview': f"[Started Thread] {title}",
                    'thread_title': title,
                    'forum_name': forum_name,
                    'post_url': href,
                })

        return results



    def save_user_post_history(self, username: str, user_id: int,
                                profile: Dict[str, Any],
                                posts: List[Dict[str, str]]) -> str:
        """Save a user's full post history to their user_logs directory."""
        user_key = f"forum_{username}_{user_id}"
        user_dir = self.USER_LOGS_DIR / user_key
        user_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now()

        lines = [
            "---",
            f'username: "{username}"',
            f'user_id: {user_id}',
            f'total_posts: {profile.get("total_posts", "?")}',
            f'join_date: "{profile.get("join_date", "?")}"',
            f'rank: "{profile.get("rank", "?")}"',
            f'scraped_at: "{now.isoformat()}"',
            f'posts_scraped: {len(posts)}',
            'source: "Project 1999"',
            'document_type: "Forum User History"',
            'platform: vbulletin',
            "---",
            "",
            f"# Post History: {username}",
            "",
            f"**Forum rank:** {profile.get('rank', '?')}  ",
            f"**Total posts:** {profile.get('total_posts', '?')}  ",
            f"**Joined:** {profile.get('join_date', '?')}  ",
            f"**Last active:** {profile.get('last_activity', '?')}  ",
            "",
        ]

        # Group posts by thread for readability
        threads: Dict[str, List[Dict]] = {}
        for p in posts:
            t = p.get('thread_title', 'Unknown Thread')
            if t not in threads:
                threads[t] = []
            threads[t].append(p)

        for thread_title, thread_posts in threads.items():
            forum = thread_posts[0].get('forum_name', '?')
            lines.append(f"## {thread_title}")
            lines.append(f"*Forum: {forum} | {len(thread_posts)} posts*")
            lines.append("")
            for p in thread_posts:
                lines.append(f"- {p.get('content_preview', '')}")
            lines.append("")

        filepath = user_dir / "post_history.md"
        filepath.write_text('\n'.join(lines), encoding='utf-8')
        log_info(f"Saved post history for {username} ({len(posts)} posts) to {filepath}")
        return str(filepath)

    async def scrape_active_users(self, threads: List[ThreadInfo],
                                   thread_posts: List[PostInfo],
                                   max_users: Optional[int] = None) -> int:
        """Deep-scrape profiles and post histories of all unique users found in threads."""
        from utils.infrastructure.system.yaml_config import config
        if max_users is None:
            max_users = config.get('forum.max_active_users_scrape', 15)
        # Collect unique user IDs from thread metadata and scraped posts
        users: Dict[int, str] = {}  # user_id -> username

        for p in thread_posts:
            if p.user_id and p.author:
                users[p.user_id] = p.author

        if not users:
            return 0

        scraped = 0
        for uid, username in list(users.items()):
            if scraped >= max_users:
                log_info(f"Reached max_users limit ({max_users}), stopping deep-scrape.")
                break

            try:
                # Check if we've already scraped this user recently
                user_key = f"forum_{username}_{uid}"
                user_dir = self.USER_LOGS_DIR / user_key
                history_path = user_dir / "post_history.md"
                profile_path = user_dir / "user_profile.md"
                
                # Reduction: 4h cooldown for intensive history scrape
                if history_path.exists():
                    mtime = datetime.fromtimestamp(history_path.stat().st_mtime)
                    if (datetime.now() - mtime).total_seconds() < 14400: # 4 hours
                        log_debug(f"Skipping {username} history — scraped within 4h")
                        continue

                # NEW: Cooldown for profile scrape too (even if history doesn't exist)
                if profile_path.exists():
                    pmtime = datetime.fromtimestamp(profile_path.stat().st_mtime)
                    if (datetime.now() - pmtime).total_seconds() < 3600: # 1 hour
                        log_debug(f"Skipping {username} profile — scraped within 1h")
                        continue

                # Scrape profile - this is cheap and gives us total_posts
                profile = await self.scrape_user_profile(uid)
                if not profile:
                    continue

                # Deduplication: Check if total_posts changed
                total_posts = profile.get('total_posts', 0)
                if history_path.exists():
                    try:
                        h_content = history_path.read_text(encoding='utf-8')
                        h_match = re.search(r'total_posts: (\d+)', h_content)
                        if h_match and int(h_match.group(1)) >= total_posts:
                            log_debug(f"Skipping {username} history — total_posts ({total_posts}) unchanged")
                            continue
                    except Exception:
                        pass

                # Scrape full post history (20 pages = ~400-500 snippets)
                posts = await self.scrape_user_post_history(uid, username, max_pages=20)

                # Scrape threads started
                threads_started = await self.scrape_user_threads_started(uid, username, max_pages=10)
                
                # Combine results for saving
                all_results = posts + threads_started

                if profile or all_results:
                    # Update consolidated history
                    self.save_user_post_history(username, uid, profile, all_results)
                    
                    # Update profile with metadata (Only for the CURRENT user)
                    user_key = f"forum_{username}_{uid}"
                    self.update_forum_user_profiles(all_results, profile, target_user_key=user_key)
                    
                    # INTEGRATION: Check if we need to deep-crawl and profile
                    # We trigger this if the profile is missing or older than 24h
                    needs_dossier = not profile_path.exists()
                    if not needs_dossier:
                        pmtime = datetime.fromtimestamp(profile_path.stat().st_mtime)
                        if (datetime.now() - pmtime).total_seconds() > 86400:
                            needs_dossier = True
                    
                    if needs_dossier:
                        log_action(f"User {username} needs personality profile. Triggering Deep Crawl...")
                        # We use a smaller limit (3) during mass scrapes to keep it fast
                        full_posts = await self.deep_crawl_user_posts(uid, username, posts, limit_threads=3)
                        await self.generate_personality_profile(username, uid, full_posts + posts, profile)

                    scraped += 1

                # Be polite — delay between users
                await asyncio.sleep(1.0)

            except Exception as e:
                log_error(f"Error deep-scraping user {username} ({uid}): {e}")

        log_action(f"Deep-scraped {scraped} forum user profiles")
        return scraped

    # ── Status ──────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Get current forum client status."""
        from utils.infrastructure.system.yaml_config import config
        now = datetime.now()
        cutoff_24h = now - timedelta(hours=24)
        recent_posts = [t for t in self._post_log if t > cutoff_24h]

        return {
            'logged_in': self._logged_in,
            'enabled': config.get('forum.enabled', False),
            'auto_reply': config.get('forum.auto_reply', False),
            'base_url': self.base_url,
            'forum_id': self.forum_id,
            'posts_today': len(recent_posts),
            'max_posts_per_day': config.get('forum.max_posts_per_day', 6),
            'min_hours_between_posts': config.get('forum.min_hours_between_posts', 4),
            'last_post': max(recent_posts).isoformat() if recent_posts else 'never',
        }

    async def get_global_stats(self) -> Dict[str, Any]:
        """Calculate global totals for all scraped forum content."""
        stats = {
            'total_threads': 0,
            'total_posts': 0,
            'total_users': 0,
            'total_profiles': 0,
            'disk_usage_mb': 0.0,
            'last_listing_count': 0
        }

        try:
            # 1. Thread and Post Stats
            thread_files = list(self.KNOWLEDGE_DIR.glob("thread_*.md"))
            stats['total_threads'] = len(thread_files)
            
            for f in thread_files:
                try:
                    stats['disk_usage_mb'] += f.stat().st_size / (1024 * 1024)
                    # Simple regex to get post_count from frontmatter
                    content = f.read_text(encoding='utf-8', errors='replace')
                    match = re.search(r'post_count: (\d+)', content)
                    if match:
                        stats['total_posts'] += int(match.group(1))
                except Exception: continue

            # 2. User and Profile Stats
            user_dirs = [d for d in self.USER_LOGS_DIR.iterdir() if d.is_dir() and d.name.startswith("forum_")]
            stats['total_users'] = len(user_dirs)
            
            for d in user_dirs:
                try:
                    # Calculate directory size
                    for f in d.rglob("*"):
                        if f.is_file():
                            stats['disk_usage_mb'] += f.stat().st_size / (1024 * 1024)
                    
                    if (d / "user_profile.md").exists():
                        stats['total_profiles'] += 1
                except Exception: continue

            # 3. Last Listing Stats
            listing_file = self.KNOWLEDGE_DIR / "off_topic_listing.md"
            if listing_file.exists():
                content = listing_file.read_text(encoding='utf-8', errors='replace')
                stats['last_listing_count'] = len(re.findall(r'^## ', content, re.MULTILINE))

        except Exception as e:
            log_error(f"Error calculating global forum stats: {e}")

        return stats
