import re
import os
import asyncio
import aiohttp
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, unquote

from utils.infrastructure.logging.kaia_logger import log_action, log_error, log_warning, log_debug
from utils.core.sanitizer import is_safe_url

# Max download size: 10MB
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024

# Supported content types
SUPPORTED_TYPES = {
    'text/html': 'html',
    'application/xhtml+xml': 'html',
    'application/pdf': 'pdf',
    'text/plain': 'text',
    'text/markdown': 'text',
    'text/csv': 'text',
}

# Blog domain patterns
BLOG_DOMAINS = ['medium.com', 'substack.com', 'dev.to', 'hashnode.dev', 'wordpress.com', 'blogger.com', 'ghost.io']

# News domain patterns
NEWS_DOMAINS = ['reuters.com', 'apnews.com', 'bbc.com', 'cnn.com', 'arstechnica.com', 
                'theverge.com', 'wired.com', 'techcrunch.com', 'hackernews', 'bleepingcomputer.com']


async def handle_download_command(ctx, msg, send_kaia_response):
    """Handle the !download <url> command — download a document and add it to the knowledge base."""
    parts = msg.content.strip().split(None, 1)
    
    if len(parts) < 2 or not parts[1].strip():
        await msg.channel.send("```\nusage: !download <url>\nsupported: HTML pages, PDFs, plain text files\n```")
        return

    url = parts[1].strip()
    
    # Strip Discord's angle-bracket URL wrapping
    if url.startswith('<') and url.endswith('>'):
        url = url[1:-1]
    
    # Validate URL & SSRF Check
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            await msg.channel.send("```\ninvalid url. needs to be http:// or https://\n```")
            return
        if not parsed.netloc:
            await msg.channel.send("```\nthat doesn't look like a valid url.\n```")
            return
        if not is_safe_url(url):
            await msg.channel.send("```\naccess denied: internal/private IP targets are restricted.\n```")
            return
    except Exception:
        await msg.channel.send("```\ncouldn't parse that url.\n```")
        return

    # Show typing while downloading
    async with msg.channel.typing():
        try:
            result = await _download_and_convert(url, msg.author.display_name, str(msg.author.id))
        except DownloadError as e:
            await msg.channel.send(f"```\ndownload failed: {e}\n```")
            return
        except Exception as e:
            log_error(f"Download command error: {e}")
            await msg.channel.send("```\nsomething went wrong during the download. check the url and try again.\n```")
            return

    # Trigger RAG reindex
    _trigger_reindex()
    
    # Send confirmation
    await msg.channel.send(
        f"```\n"
        f"downloaded and saved.\n"
        f"  file: {result['filename']}\n"
        f"  folder: {result['folder']}\n"
        f"  words: ~{result['word_count']}\n"
        f"  type: {result['content_type']}\n"
        f"```"
    )
    log_action(f"Downloaded {url} -> {result['filepath']} ({result['word_count']} words) by {msg.author.display_name}")


class DownloadError(Exception):
    """Custom error for download failures with user-friendly messages."""
    pass


async def _download_and_convert(url: str, username: str, user_id: str) -> dict:
    """Download URL content, convert to markdown, save to knowledge_base."""
    
    timeout = aiohttp.ClientTimeout(total=30)
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; KaiaBot/1.0; +knowledge-base-ingestion)'
    }
    
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url, allow_redirects=True) as response:
            if response.status != 200:
                raise DownloadError(f"server returned {response.status}")
            
            content_type = response.content_type or ''
            content_length = response.content_length
            
            # Check size before downloading
            if content_length and content_length > MAX_DOWNLOAD_BYTES:
                raise DownloadError(f"file too large ({content_length // 1024 // 1024}MB). max is 10MB.")
            
            # Determine type from content-type header
            file_type = None
            for mime, ftype in SUPPORTED_TYPES.items():
                if mime in content_type:
                    file_type = ftype
                    break
            
            # Fall back to URL extension
            if not file_type:
                ext = Path(urlparse(url).path).suffix.lower()
                ext_map = {'.pdf': 'pdf', '.txt': 'text', '.md': 'text', '.csv': 'text', 
                           '.html': 'html', '.htm': 'html', '.log': 'text'}
                file_type = ext_map.get(ext)
            
            if not file_type:
                raise DownloadError(f"unsupported content type: {content_type}. try HTML, PDF, or plain text.")
            
            # Download content with size guard
            raw_data = bytearray()
            async for chunk in response.content.iter_chunked(8192):
                raw_data.extend(chunk)
                if len(raw_data) > MAX_DOWNLOAD_BYTES:
                    raise DownloadError("file too large (exceeded 10MB during download).")
            
            raw_bytes = bytes(raw_data)

    # Convert based on type
    if file_type == 'html':
        title, markdown_body = await asyncio.to_thread(_convert_html, raw_bytes, url)
    elif file_type == 'pdf':
        title, markdown_body = await asyncio.to_thread(_convert_pdf, raw_bytes, url)
    elif file_type == 'text':
        title, markdown_body = await asyncio.to_thread(_convert_text, raw_bytes, url)
    else:
        raise DownloadError(f"unhandled type: {file_type}")
    
    if not markdown_body or len(markdown_body.strip()) < 50:
        raise DownloadError("couldn't extract meaningful text from that URL.")

    markdown_body = _clean_markdown(markdown_body)

    # Build metadata frontmatter
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    frontmatter = (
        f"---\n"
        f"title: \"\"\n"
        f"summary: \"\"\n"
        f"keywords: []\n"
        f"document_type: article\n"
        f"date: {date_str}\n"
        f"source_url: \"{url}\"\n"
        f"---\n\n"
    )
    
    full_content = frontmatter + markdown_body
    
    # Determine target folder
    folder = _classify_folder(url, title, file_type, len(markdown_body.split()))
    
    # Build filename
    filename = _make_filename(title, now)
    
    # Save
    target_dir = Path("./knowledge_base") / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    filepath = target_dir / filename
    
    filepath.write_text(full_content, encoding='utf-8')
    
    word_count = len(markdown_body.split())
    
    return {
        'filename': filename,
        'folder': folder,
        'filepath': str(filepath),
        'word_count': word_count,
        'content_type': file_type,
        'title': title,
    }


def _convert_html(raw_bytes: bytes, url: str) -> tuple:
    """Convert HTML to markdown. Returns (title, markdown_body)."""
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md
    
    # Try UTF-8, fall back to latin-1
    try:
        html_text = raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        html_text = raw_bytes.decode('latin-1')
    
    soup = BeautifulSoup(html_text, 'html.parser')
    
    # Extract title
    title = ''
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text(strip=True)
    if not title:
        title = _title_from_url(url)
    
    # Remove noise elements
    for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 
                               'aside', 'iframe', 'noscript', 'form']):
        tag.decompose()
    
    # Try to find the main content area
    main = soup.find('main') or soup.find('article') or soup.find(role='main')
    if main:
        target = main
    else:
        # Fall back to body
        target = soup.find('body') or soup
    
    # Convert to markdown
    markdown_body = md(str(target), heading_style="ATX", strip=['img', 'a'], 
                       newline_style="backslash")
    
    # Clean up excessive whitespace
    markdown_body = re.sub(r'\n{3,}', '\n\n', markdown_body)
    markdown_body = markdown_body.strip()
    
    return title, markdown_body


def _convert_pdf(raw_bytes: bytes, url: str) -> tuple:
    """Convert PDF to markdown. Returns (title, markdown_body)."""
    import io
    from pypdf import PdfReader
    
    reader = PdfReader(io.BytesIO(raw_bytes))
    
    # Extract title from metadata or first page
    title = ''
    if reader.metadata and reader.metadata.title:
        title = reader.metadata.title.strip()
    
    pages_text = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text and text.strip():
            pages_text.append(f"## Page {i + 1}\n\n{text.strip()}")
    
    if not title and pages_text:
        # Use first line of first page as title
        first_line = pages_text[0].split('\n')[2] if len(pages_text[0].split('\n')) > 2 else ''
        title = first_line[:100].strip() if first_line else _title_from_url(url)
    
    if not title:
        title = _title_from_url(url)
    
    markdown_body = '\n\n'.join(pages_text)
    
    return title, markdown_body


def _convert_text(raw_bytes: bytes, url: str) -> tuple:
    """Convert plain text to markdown. Returns (title, markdown_body)."""
    try:
        text = raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        text = raw_bytes.decode('latin-1')
    
    # Use first non-empty line as title
    lines = text.strip().split('\n')
    title = ''
    for line in lines:
        if line.strip():
            title = line.strip()[:100]
            break
    
    if not title:
        title = _title_from_url(url)
    
    # If it's already markdown, keep it. Otherwise wrap it.
    ext = Path(urlparse(url).path).suffix.lower()
    if ext in ('.md', '.markdown'):
        markdown_body = text
    else:
        markdown_body = text
    
    return title, markdown_body


def _clean_markdown(text: str) -> str:
    """Clean up markdown output to improve RAG quality."""
    lines = text.split('\n')
    
    # 1. First pass: count short lines for frequency filtering
    from collections import Counter
    short_lines = Counter()
    for line in lines:
        stripped = line.strip()
        if 0 < len(stripped) < 60:
            short_lines[stripped] += 1
            
    filtered_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Strip HTML artifacts
        lower_line = line.lower()
        if any(tag in lower_line for tag in ['<div', '<span', '<script', '<style', '<nav', '<footer', '<header']):
            continue
            
        # If it's pure boilerplate navigation link 
        if re.match(r'^\[.*?\]\(.*?\)$', stripped):
            continue
            
        # If it's a separator line of just symbols
        if stripped and re.match(r'^[\s\|\-\*\+\_\#\=]+$', stripped):
            continue
            
        # If it's a repeated short line (>3 times)
        if 0 < len(stripped) < 60 and short_lines[stripped] > 3:
            continue
            
        filtered_lines.append(line)
        
    # 3. Trim document edges (first 5 and last 5 lines)
    def _is_edge_noise(l: str) -> bool:
        s = l.strip()
        if not s: return True
        if len(s) < 40: return True
        if re.match(r'^\[.*?\]\(.*?\)$', s): return True
        return False

    # Trim start
    trim_start = 0
    for i in range(min(5, len(filtered_lines))):
        if _is_edge_noise(filtered_lines[i]):
            trim_start = i + 1
        else:
            break
            
    filtered_lines = filtered_lines[trim_start:]
    
    # Trim end
    trim_end = len(filtered_lines)
    for i in range(min(5, len(filtered_lines))):
        idx = len(filtered_lines) - 1 - i
        if idx < 0: break
        if _is_edge_noise(filtered_lines[idx]):
            trim_end = idx
        else:
            break
            
    filtered_lines = filtered_lines[:trim_end]
    
    # Reconstruct text
    cleaned_text = '\n'.join(filtered_lines)
    
    # Collapse 3+ consecutive blank lines to a single blank line
    # A blank line is \n\n, so 3+ blank lines is \n\n\n\n
    cleaned_text = re.sub(r'\n{4,}', '\n\n', cleaned_text)
    
    return cleaned_text.strip()


def _classify_folder(url: str, title: str, file_type: str, word_count: int) -> str:
    """Determine which knowledge_base subfolder to save to."""
    url_lower = url.lower()
    title_lower = title.lower()
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    
    # Blog domains
    if any(bd in domain for bd in BLOG_DOMAINS):
        return "blogs"
    if '/blog/' in url_lower or '/blogs/' in url_lower or '/posts/' in url_lower:
        return "blogs"
    
    # News domains
    if any(nd in domain for nd in NEWS_DOMAINS):
        return "news/daily"
    if '/news/' in url_lower and not ('/blogs/' in url_lower or '/blog/' in url_lower):
        return "news/daily"
    
    # Books: PDFs that are long or have "book" in title
    if file_type == 'pdf':
        if word_count > 10000 or 'book' in title_lower or 'manual' in title_lower or 'guide' in title_lower:
            return "Books"
    
    # Research/reports
    if any(kw in title_lower for kw in ['report', 'whitepaper', 'white paper', 'analysis', 'study']):
        return "deep_dive_reports"
    
    # Default
    return "documents"


def _make_filename(title: str, dt: datetime) -> str:
    """Create a filesystem-safe filename from a title."""
    # Sanitize title
    safe = re.sub(r'[^\w\s-]', '', title.lower())
    safe = re.sub(r'[\s_]+', '-', safe).strip('-')
    safe = safe[:80]  # Truncate
    
    if not safe:
        safe = 'untitled'
    
    date_prefix = dt.strftime('%Y-%m-%d')
    return f"{date_prefix}_{safe}.md"


def _title_from_url(url: str) -> str:
    """Extract a readable title from a URL path."""
    path = urlparse(url).path
    # Get last path segment
    segment = path.rstrip('/').split('/')[-1] if path else ''
    if segment:
        # Remove extension, replace separators
        segment = Path(segment).stem
        segment = segment.replace('-', ' ').replace('_', ' ')
        return segment.title()
    
    # Fall back to domain
    return urlparse(url).netloc


def _escape_yaml(text: str) -> str:
    """Escape text for YAML string value."""
    return text.replace('"', '\\"').replace('\n', ' ')


def _trigger_reindex():
    """Touch the .trigger_reindex file so the RAG picks up new content."""
    try:
        trigger_path = Path("./knowledge_base/.trigger_reindex")
        trigger_path.touch()
        log_debug("Touched .trigger_reindex for RAG refresh")
    except Exception as e:
        log_warning(f"Could not trigger reindex: {e}")
