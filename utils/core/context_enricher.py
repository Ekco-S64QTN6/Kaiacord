import re
import asyncio
import subprocess
import sys
import threading
import discord
import aiohttp
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from utils.infrastructure.logging.kaia_logger import log_debug, log_warning
from utils.infrastructure.system.yaml_config import config
from utils.core.sanitizer import is_safe_url, public_only_connector, read_capped

# A page is read at most this far before parsing; the prompt keeps far less
# (url_max_content_length). Without a cap a linked multi-gigabyte file served
# as text/html was read whole into memory.
MAX_PAGE_BYTES = 2_000_000
MAX_PDF_PAGES = 20
MAX_PDF_TEXT_CHARS = 16_000
MAX_PDF_PARSE_MEMORY_BYTES = 256 * 1024 * 1024
MAX_PDF_PARSE_CPU_SECONDS = 3
MAX_PDF_PARSE_TIMEOUT_SECONDS = 5
# Two isolated workers cap parser memory at roughly 512 MiB total.
# A queued message waits at most one second before PDF extraction fails closed.
MAX_CONCURRENT_PDF_PARSERS = 2
MAX_PDF_PARSE_QUEUE_WAIT_SECONDS = 1
_PDF_PARSE_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_PDF_PARSERS)
# Each per-enricher cache has a hard entry cap; expired entries are pruned first.
CACHE_MAX_ENTRIES = 256
# A quoted or linked message's embeds are kept up to this many characters:
# a !help page is a few thousand, and the quote is context, not the subject.
QUOTED_EMBED_CHARS = 4000
_TRAILING_PUNCT = '.,;:!?)]}\'"'

# A text attachment is read into the prompt the way a linked page is. Discord
# turns any paste over its message limit into "message.txt", so this is the
# ordinary case, not an upload edge case. Without it a file was invisible and
# a "summarize this" turn answered from whatever RAG happened to retrieve.
MAX_FILE_BYTES = 1_000_000
# ~4k tokens: room beside an ~11k-token system prompt within num_ctx.
FILE_PROMPT_CHARS = 16_000
MAX_FILES_PER_MESSAGE = 3
# "summarize this file" sent after the file, in its own message.
FILE_LOOKBACK_MESSAGES = 5
FILE_LOOKBACK_SECONDS = 15 * 60
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")
_TEXT_SUFFIXES = frozenset((
    ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv", ".json", ".jsonl",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".xml", ".html", ".htm",
    ".srt", ".vtt", ".py", ".js", ".ts", ".sh", ".bash", ".c", ".h", ".cpp",
    ".hpp", ".rs", ".go", ".java", ".kt", ".lua", ".rb", ".php", ".sql", ".css",
    ".diff", ".patch",
))
_TEXT_CONTENT_TYPES = frozenset((
    "application/json", "application/xml", "application/x-yaml", "application/yaml",
    "application/toml", "application/javascript", "application/x-sh",
    "application/sql", "application/x-subrip",
))
_FILE_REFERENCE = re.compile(
    r"\b(?:file|attach(?:ed|ment)?|txt|document|paste|summari[sz]e|tl;?dr"
    r"|read\s+(?:this|that|it))\b",
    re.IGNORECASE,
)
# The pipeline splits enriched text on these markers, and RUNTIME_SCAFFOLDING
# ends a block at the next line that opens with "[". File text is the sender's;
# neither may be able to steer either.
_MARKER_IN_FILE = re.compile(
    r"\[(?=(?:USER_MESSAGE|REPLYING_TO|ORIGINAL_POST|CORE_DIRECTIVE|LINKED_|ATTACHED_"
    r"|SYSTEM WARNING|VISUAL GROUNDING)\b)",
    re.IGNORECASE,
)


_PDF_WORKER_SCRIPT = r"""
import sys

# Set process limits before importing the PDF parser or touching untrusted data.
try:
    import resource
    memory_limit = __MAX_PDF_PARSE_MEMORY_BYTES__
    cpu_limit = __MAX_PDF_PARSE_CPU_SECONDS__
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit + 1))
except Exception:
    # Environments without enforceable OS resource limits fail closed.
    sys.exit(3)

# A worker the limits kill (SIGXCPU) is the guard working, not a crash: no core
# dump, so systemd-coredump does not report it as one. RLIMIT_CORE alone is not
# enough when cores are piped to a handler; a non-dumpable process is never dumped.
try:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    import ctypes
    ctypes.CDLL(None, use_errno=True).prctl(4, 0, 0, 0, 0)   # PR_SET_DUMPABLE, 0
except Exception:
    pass

try:
    from io import BytesIO
    from pypdf import PdfReader

    raw = sys.stdin.buffer.read(2_000_001)
    if len(raw) > 2_000_000 or not raw.startswith(b"%PDF-"):
        sys.exit(2)

    reader = PdfReader(BytesIO(raw), strict=False)
    if reader.is_encrypted:
        sys.exit(2)

    pages = reader.pages
    page_count = len(pages)
    remaining = 16_000
    chunks = []
    truncated_text = False
    for page_index in range(min(page_count, 20)):
        page_text = (pages[page_index].extract_text() or "").strip()
        if not page_text:
            continue
        if len(page_text) > remaining:
            page_text = page_text[:remaining]
            truncated_text = True
        if page_text:
            chunks.append(page_text)
            remaining -= len(page_text)
        if remaining <= 0:
            truncated_text = True
            break

    extracted = "\n\n".join(chunks)
    if page_count > 20:
        extracted += "\n\n[PDF truncated after 20 pages]"
    elif truncated_text:
        extracted += "\n\n[PDF text truncated]"
    sys.stdout.buffer.write(extracted[:16_064].encode("utf-8", errors="replace"))
except Exception:
    # Parser errors, decompression failures, and resource-limit exceptions fail closed.
    sys.exit(4)
""".replace(
    "__MAX_PDF_PARSE_MEMORY_BYTES__", str(MAX_PDF_PARSE_MEMORY_BYTES)
).replace(
    "__MAX_PDF_PARSE_CPU_SECONDS__", str(MAX_PDF_PARSE_CPU_SECONDS)
)


def _extract_pdf_text(raw_bytes: bytes) -> str:
    """Extract PDF text in a disposable worker with hard resource ceilings.

    The raw response cap limits input bytes; the child-process address-space,
    CPU and wall-clock limits bound decompression and parser work. A timed-out
    or resource-killed worker is discarded rather than left running in a thread.
    """
    if not raw_bytes.startswith(b"%PDF-") or len(raw_bytes) > MAX_PAGE_BYTES:
        return ""
    if not _PDF_PARSE_SEMAPHORE.acquire(timeout=MAX_PDF_PARSE_QUEUE_WAIT_SECONDS):
        log_debug("PDF extraction skipped: all parser workers are busy.")
        return ""
    try:
        try:
            completed = subprocess.run(
                [sys.executable, "-I", "-c", _PDF_WORKER_SCRIPT],
                input=raw_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=MAX_PDF_PARSE_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if completed.returncode != 0:
            return ""
        return completed.stdout.decode("utf-8", errors="replace").strip()[:MAX_PDF_TEXT_CHARS + 64]
    finally:
        _PDF_PARSE_SEMAPHORE.release()


def _human_size(size: int) -> str:
    return f"{size} bytes" if size < 1024 else f"{size / 1024:.0f} KB"


def _neutralise_markers(text: str) -> str:
    text = _MARKER_IN_FILE.sub("(", text)
    return re.sub(r"(?m)^\[", " [", text)


class ContextEnricher:
    """
    Enriches user message context by extracting data from embeds,
    resolving message links, and scraping URLs for relevant text.
    """
    
    def __init__(self, bot):
        self.bot = bot
        # Regex for Discord message links
        self.msg_link_pattern = re.compile(
            r'https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)'
        )
        # Regex for standard web links (ignoring discord message links)
        self.external_link_pattern = re.compile(
            r'(?<!<)https?://(?!(?:(?:ptb|canary)\.)?discord(?:app)?\.com/channels/)[^\s>]+'
        )
        
        # Fetch Cache: {id: (timestamp, object)}
        self._channel_cache = {}
        self._message_cache = {}
        # URL Cache: {url: (timestamp, scraped_text)}
        self._url_cache = {}
        self._cache_ttl = 300 # 5 minutes

    async def enrich_content(self, msg: discord.Message) -> str:
        """
        Main entry point to get full context from a message.
        """
        content = msg.content
        if not (content or "").strip():
            # A forward posted straight to her carries its text only in the snapshot.
            content = self._forwarded_text(msg) or content
        
        # 1. Resolve Mentions (Resolve <@ID> to Names)
        content = await self.resolve_mentions(content, msg)

        # 2. Resolve Replies (Highest priority context)
        reply_context = await self.resolve_replies(msg)
        if reply_context:
            content = f"[REPLYING_TO]\n{reply_context}\n\n[USER_MESSAGE]\n{content}"

        # 3. Extract Appendages (Embeds)
        embed_text = self.extract_embed_text(msg)
        if embed_text:
            content += f"\n\n[ATTACHED_EMBED_CONTEXT]\n{embed_text}"

        # 3b. Read attached text files (images go to the vision path instead)
        file_text = await self.resolve_file_attachments(msg)
        if file_text:
            content += f"\n\n[ATTACHED_FILE_CONTEXT]\n{file_text}"

        # 4. Resolve Links
        linked_context = await self.resolve_message_links(msg)
        if linked_context:
            content += f"\n\n[LINKED_MESSAGE_CONTEXT]\n{linked_context}"
            
        # 5. Scrape External URLs
        if config.url_fetching_enabled:
            url_context = await self.resolve_external_urls(msg)
            if url_context:
                # No length instruction here. One ("keep your response brutally
                # concise") sat after the page for months without effect, because
                # the whole message was cut at 2,000 characters before it; once
                # pages arrived whole it reached the model, and replies to links
                # fell to a sentence or two.
                content += f"\n\n[LINKED_WEB_CONTENT]\n{url_context}"
            
        return content

    async def resolve_mentions(self, content: str, msg: discord.Message) -> str:
        """Resolve <@ID> and <@!ID> user mentions and <#ID> channel mentions to readable names."""
        mention_pattern = re.compile(r'<@!?(\d+)>')
        matches = mention_pattern.findall(content)
        
        resolved_content = content
        if matches:
            for user_id_str in set(matches):
                user_id = int(user_id_str)
                display_name = None
                
                # 1. Check message mentions (fastest)
                if msg.mentions:
                    for m in msg.mentions:
                        if m.id == user_id:
                            display_name = m.display_name
                            break
                
                # 2. Check guild cache
                if not display_name and msg.guild:
                    member = msg.guild.get_member(user_id)
                    if member:
                        display_name = member.display_name
                
                # 3. Fetch from API (slowest, fallback)
                if not display_name:
                    try:
                        user = await self.bot.fetch_user(user_id)
                        display_name = user.display_name if user else f"user_{user_id}"
                    except Exception:
                        display_name = f"user_{user_id}"
                
                if display_name:
                    resolved_content = resolved_content.replace(f"<@{user_id_str}>", f"@{display_name}")
                    resolved_content = resolved_content.replace(f"<@!{user_id_str}>", f"@{display_name}")

        # Resolve <#ID> channel mentions
        channel_mention_pattern = re.compile(r'<#(\d+)>')
        channel_matches = channel_mention_pattern.findall(resolved_content)
        if channel_matches:
            for ch_id_str in set(channel_matches):
                ch_id = int(ch_id_str)
                ch_name = None
                
                # 1. Check guild cache
                if msg.guild:
                    ch_obj = msg.guild.get_channel(ch_id)
                    if ch_obj:
                        ch_name = ch_obj.name
                
                # 2. Check bot cache
                if not ch_name and self.bot:
                    ch_obj = self.bot.get_channel(ch_id)
                    if ch_obj:
                        ch_name = ch_obj.name
                
                # 3. Fetch from API (fallback)
                if not ch_name and self.bot:
                    try:
                        ch_obj = await self.bot.fetch_channel(ch_id)
                        ch_name = ch_obj.name if ch_obj else None
                    except Exception:
                        ch_name = None
                
                if ch_name:
                    resolved_content = resolved_content.replace(f"<#{ch_id_str}>", f"#{ch_name}")
                else:
                    resolved_content = resolved_content.replace(f"<#{ch_id_str}>", f"#channel_{ch_id_str}")
                    
        return resolved_content

    @staticmethod
    def _bot_message_recipient(channel, content: str, guild=None):
        """Whom one of her own messages was answering, or None.

        Only from evidence: the user turn her reply followed in channel
        memory, or a name she opened with that belongs to someone here. An
        unprompted post (a quip, an opener, a thought) answered nobody; the
        last person to have spoken before it is not its addressee, and naming
        them in the quoted context made her answer the replier by their name.
        """
        content = (content or "").strip()
        if not content:
            return None
        try:
            from utils.infrastructure.system.bot_state import bot_state
            turns = list(bot_state.channel_memory.get(getattr(channel, "id", None), []))
        except Exception:
            turns = []
        low = content.lower()
        for idx, turn in enumerate(turns):
            said = (turn.get("content") or "").strip().lower()
            # A posted message may carry a label in front of what memory kept.
            if turn.get("role") != "assistant" or not said or not (said == low or (len(said) > 20 and said in low)):
                continue
            if turn.get("unprompted"):
                return None
            prev = turns[idx - 1] if idx > 0 else None
            if prev and prev.get("role") == "user" and ":" in (prev.get("content") or ""):
                return prev["content"].split(":", 1)[0].strip() or None
            return None

        # "<name>, ..." where the name is someone in this server.
        first = content.split(",", 1)[0].strip() if "," in content else ""
        if first and len(first.split()) <= 3:
            name = re.sub(r"[^\w\s\-]", "", first).strip().lower()
            known = {(getattr(m, "display_name", "") or "").lower() for m in (getattr(guild, "members", None) or [])}
            known |= {(t.get("content") or "").split(":", 1)[0].strip().lower()
                      for t in turns if t.get("role") == "user" and ":" in (t.get("content") or "")}
            known.discard("")
            if name in known:
                return first
        return None

    @staticmethod
    def _file_attachments(m) -> list:
        """Attachments that are not images and can be downloaded (forum mocks cannot)."""
        out = []
        for att in getattr(m, "attachments", None) or []:
            name = (getattr(att, "filename", "") or "").lower()
            ctype = (getattr(att, "content_type", None) or "").split(";")[0].strip().lower()
            if name.endswith(_IMAGE_SUFFIXES) or ctype.startswith("image/"):
                continue
            if not callable(getattr(att, "read", None)):
                continue
            out.append(att)
        return out

    async def resolve_file_attachments(self, msg) -> str:
        """The text of files attached to this message — or, when the message asks
        about a file it does not carry, to the message it replies to or to the
        author's own recent messages."""
        attachments = self._file_attachments(msg)

        if not attachments and getattr(msg, "reference", None) is not None:
            try:
                target = msg.reference.resolved
                if not isinstance(target, discord.Message) and msg.reference.message_id:
                    target = await msg.channel.fetch_message(msg.reference.message_id)
                if target is not None:
                    attachments = self._file_attachments(target)
            except Exception as e:
                log_debug(f"Could not read replied-to attachments: {e}")

        if (not attachments and _FILE_REFERENCE.search(getattr(msg, "content", "") or "")
                and hasattr(getattr(msg, "channel", None), "history")):
            try:
                created = getattr(msg, "created_at", None)
                async for prev in msg.channel.history(limit=FILE_LOOKBACK_MESSAGES, before=msg):
                    if getattr(prev.author, "id", None) != getattr(msg.author, "id", None):
                        continue
                    if created and prev.created_at and \
                            (created - prev.created_at).total_seconds() > FILE_LOOKBACK_SECONDS:
                        break
                    found = self._file_attachments(prev)
                    if found:
                        attachments = found
                        break
            except Exception as e:
                log_debug(f"Could not scan recent messages for attachments: {e}")

        blocks = []
        for att in attachments[:MAX_FILES_PER_MESSAGE]:
            block = await self._read_text_attachment(att)
            if block:
                blocks.append(block)
        return "\n\n".join(blocks)

    async def _read_text_attachment(self, att) -> str:
        """One attachment as a block: a header line, then its text — or a plain
        statement that its contents are unknown, so nothing invites a guess."""
        name = getattr(att, "filename", "") or "file"
        size = int(getattr(att, "size", 0) or 0)
        ctype = (getattr(att, "content_type", None) or "").split(";")[0].strip().lower()
        header = f"File: {name} ({_human_size(size)})"
        suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        textual = (ctype.startswith("text/") or ctype in _TEXT_CONTENT_TYPES
                   or suffix in _TEXT_SUFFIXES)
        if not textual:
            kind = ctype or (suffix.lstrip(".") + " file" if suffix else "unknown type")
            return f"{header}\nContents unknown: only plain-text files can be read, and this is {kind}."
        if size > MAX_FILE_BYTES:
            return f"{header}\nContents unknown: larger than {_human_size(MAX_FILE_BYTES)}, not read."
        try:
            data = await att.read()
        except Exception as e:
            log_warning(f"Could not download attachment ({_human_size(size)}): {e}")
            return f"{header}\nContents unknown: the download failed."
        if b"\x00" in data[:8192]:
            return f"{header}\nContents unknown: it is binary, not text."
        text = data.decode("utf-8-sig", errors="replace").strip()
        if not text:
            return f"{header}\nThe file is empty."
        note = ""
        if len(text) > FILE_PROMPT_CHARS:
            note = f" — first {FILE_PROMPT_CHARS:,} of {len(text):,} characters"
            text = text[:FILE_PROMPT_CHARS]
        log_debug(f"Read text attachment: {_human_size(size)}, {len(text):,} chars into the prompt.")
        return f"{header}{note}\n{_neutralise_markers(text)}"

    async def resolve_replies(self, msg: discord.Message) -> str:
        """Fetch the content of the message being replied to."""
        if not msg.reference or not msg.reference.message_id:
            return ""
            
        try:
            # Try to get from channel history/cache
            target_msg = msg.reference.resolved
            if not isinstance(target_msg, discord.Message):
                # Fetch if not resolved
                channel = msg.channel
                target_msg = await channel.fetch_message(msg.reference.message_id)
            
            if target_msg:
                author = target_msg.author.display_name
                # Resolve any <@ID> mentions in the replied-to message's content
                # so Kaia sees "@Ekco" not "<@177011971818782721>"
                resolved_content = self._with_embeds(
                    await self.resolve_mentions(target_msg.content, target_msg), target_msg)
                
                # If target message was sent by the bot, determine whom the bot was addressing
                if target_msg.author.id == self.bot.user.id:
                    recipient_name = self._bot_message_recipient(msg.channel, target_msg.content, msg.guild)

                    if recipient_name:
                        author = f"{author} (replying to {recipient_name})"

                return f"{author}: {resolved_content}"
        except Exception as e:
            log_debug(f"Failed to resolve reply: {e}")
            
        return ""

    def _forwarded_text(self, msg) -> str:
        """What a forwarded message carries. A forward has no text of its own:
        Discord keeps the original in `message_snapshots`, so a reply to one
        quoted only the forwarder's name and she was left with nothing to read."""
        snapshots = getattr(msg, "message_snapshots", None)
        if not isinstance(snapshots, (list, tuple)):
            return ""
        parts = []
        for snapshot in snapshots[:3]:
            text = str(getattr(snapshot, "content", "") or "").strip()
            embeds = self.extract_embed_text(snapshot)[:QUOTED_EMBED_CHARS]
            body = "\n".join(part for part in (text, embeds) if part)
            if body:
                parts.append(body)
        return "(forwarded)\n" + "\n\n".join(parts) if parts else ""

    def _with_embeds(self, content: str, msg) -> str:
        """A quoted message's text with its embeds and anything it forwards.
        Every command of hers answers in an embed with no message text, so
        without them a reply to one quoted her as "Kaia:" and nothing else."""
        parts = [content] if (content or "").strip() else []
        forwarded = self._forwarded_text(msg)
        if forwarded:
            parts.append(forwarded)
        embeds = self.extract_embed_text(msg)
        if embeds:
            parts.append(embeds[:QUOTED_EMBED_CHARS])
        return "\n".join(parts) if parts else content

    def extract_embed_text(self, msg: discord.Message) -> str:
        """Extract titles, descriptions, and fields from Discord embeds."""
        if not getattr(msg, "embeds", None):
            return ""
            
        texts = []
        for i, embed in enumerate(msg.embeds):
            embed_parts = []
            if embed.title:
                embed_parts.append(f"Title: {embed.title}")
            if embed.description:
                embed_parts.append(f"Description: {embed.description}")
            
            for field in embed.fields:
                embed_parts.append(f"Field ({field.name}): {field.value}")
                
            if embed_parts:
                texts.append(f"--- EMBED {i+1} ---\n" + "\n".join(embed_parts))
                
        return "\n\n".join(texts)

    async def resolve_message_links(self, msg: discord.Message) -> str:
        """Find Discord message links and fetch their content concurrently."""
        matches = self.msg_link_pattern.findall(msg.content)
        if not matches:
            return ""
            
        # Limit to 3 links to prevent abuse/latency
        tasks = []
        for guild_id, channel_id, message_id in matches[:3]:
            tasks.append(self._resolve_single_link(int(channel_id), int(message_id),
                                                   requester=msg.author, guild_id=int(guild_id)))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        resolved_texts = []
        for res in results:
            if isinstance(res, str) and res:
                resolved_texts.append(res)
            elif isinstance(res, Exception):
                log_debug(f"Link resolution failed: {res}")
                
        return "\n\n".join(resolved_texts)

    async def _requester_can_read(self, channel, requester, guild_id: int) -> bool:
        """Only what the person who pasted the link could read themselves.

        The bot reads with its own access, which covers private channels, the
        moderation queue and every other server it is in. Resolving a link on
        the bot's authority would put any of that in front of whoever asked.
        """
        guild = getattr(channel, "guild", None)
        if guild is None or guild.id != guild_id or requester is None:
            return False
        member = guild.get_member(requester.id)
        if member is None:
            try:
                member = await guild.fetch_member(requester.id)
            except Exception:
                return False
        try:
            perms = channel.permissions_for(member)
        except Exception:
            return False                       # a thread whose parent is not cached
        if not (perms.view_channel and perms.read_message_history):
            return False
        if isinstance(channel, discord.Thread) and channel.is_private():
            # A thread's permissions are its parent's. A private thread is also
            # closed to everyone not invited to it, short of manage_threads.
            if perms.manage_threads:
                return True
            try:
                await channel.fetch_member(requester.id)
            except Exception:
                return False
        return True

    def _prune(self, cache: dict, now: float) -> None:
        """Remove expired entries, then evict the oldest until the hard cap holds."""
        expired = [
            key for key, (timestamp, _) in cache.items()
            if now - timestamp >= self._cache_ttl
        ]
        for key in expired:
            del cache[key]

        overflow = len(cache) - CACHE_MAX_ENTRIES
        if overflow > 0:
            oldest = sorted(cache, key=lambda key: cache[key][0])[:overflow]
            for key in oldest:
                del cache[key]

    def _cache_store(self, cache: dict, key, value, now: float) -> None:
        """Insert one item and enforce the cache's TTL and hard entry bound."""
        cache[key] = (now, value)
        self._prune(cache, now)

    async def _resolve_single_link(self, channel_id: int, message_id: int,
                                   requester=None, guild_id: int = 0) -> str:
        """Resolve a single message link with caching."""
        now = asyncio.get_running_loop().time()
        
        # 1. Get/Fetch Channel
        channel = self.bot.get_channel(channel_id)
        if not channel:
            # Check cache
            if channel_id in self._channel_cache:
                timestamp, cached_channel = self._channel_cache[channel_id]
                if now - timestamp < self._cache_ttl:
                    channel = cached_channel
            
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                    self._cache_store(self._channel_cache, channel_id, channel, now)
                except Exception as e:
                    log_debug(f"Failed to fetch channel {channel_id}: {e}")
                    return ""

        if not channel:
            return ""

        if not await self._requester_can_read(channel, requester, guild_id):
            log_debug(f"Linked message {message_id} not resolved: the requester cannot read #{getattr(channel, 'name', channel_id)}")
            return ""

        # 2. Get/Fetch Message
        # Check cache first
        if message_id in self._message_cache:
            timestamp, cached_msg = self._message_cache[message_id]
            if now - timestamp < self._cache_ttl:
                author = cached_msg.author.display_name
                return f"Message from {author} in #{channel.name}:\n{self._with_embeds(cached_msg.content, cached_msg)}"

        try:
            linked_msg = await channel.fetch_message(message_id)
            if linked_msg:
                self._cache_store(self._message_cache, message_id, linked_msg, now)
                author = linked_msg.author.display_name
                return f"Message from {author} in #{channel.name}:\n{self._with_embeds(linked_msg.content, linked_msg)}"
        except Exception as e:
            log_debug(f"Failed to fetch message {message_id}: {e}")
            
        return ""

    async def resolve_external_urls(self, msg: discord.Message) -> str:
        """Find external web links and scrape their content concurrently."""
        matches = self.external_link_pattern.findall(msg.content)
        if not matches:
            return ""
            
        # A link at the end of a sentence carries its full stop or bracket.
        matches = [m.rstrip(_TRAILING_PUNCT) for m in matches]
        # A picture's link goes to vision (utils/core/image_links.py), not the scraper.
        from utils.core.image_links import is_image_link
        matches = [m for m in matches if not is_image_link(m)]
        if not matches:
            return ""
        # Remove duplicates and limit to 2 links to prevent abuse/stall
        unique_urls = list(dict.fromkeys(m for m in matches if m))[:2]
        
        tasks = []
        for url in unique_urls:
            tasks.append(self._scrape_single_url(url))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        resolved_texts = []
        failed_urls = []
        for url, res in zip(unique_urls, results):
            if isinstance(res, str) and res.strip():
                resolved_texts.append(res)
            else:
                failed_urls.append(url)
                if isinstance(res, Exception):
                    log_debug(f"URL scraping failed for {url}: {res}")
                else:
                    log_debug(f"URL scraping returned empty/invalid content for {url}")
                
        context_parts = []
        if resolved_texts:
            context_parts.append("\n\n".join(resolved_texts))
        if failed_urls:
            failed_info = "\n".join(f"- {url}" for url in failed_urls)
            context_parts.append(
                f"[SYSTEM WARNING: The following URLs could not be scraped or retrieved:\n{failed_info}\n"
                "You have NO access to their contents. Do not pretend to have read them, and do not hallucinate "
                "their details. If it matters, say plainly that the page wouldn't load for you this time and ask "
                "them to paste the part they mean. You can normally open links; never describe yourself as "
                "restricted or unable to access links.]"
            )
            
        return "\n\n".join(context_parts)

    async def _scrape_single_url(self, url: str) -> str:
        """Scrape text from a single URL with caching and limits."""
        now = asyncio.get_running_loop().time()
        
        # 1. SSRF Guard Check
        # getaddrinfo blocks; keep it off the event loop.
        if not await asyncio.to_thread(is_safe_url, url):
            log_debug(f"URL {url} blocked by SSRF safety guard (private/loopback/metadata IP)")
            return ""

        # 2. Check Cache
        if url in self._url_cache:
            timestamp, cached_text = self._url_cache[url]
            if now - timestamp < self._cache_ttl:
                log_debug(f"URL Cache Hit: {url}")
                return cached_text
                
        # 2. Fetch using aiohttp with strict timeout
        timeout = aiohttp.ClientTimeout(total=config.url_fetch_timeout)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        }
        
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers,
                                             connector=public_only_connector()) as session:
                max_redirects = 5
                current_url = url
                response = None
                for redirect_count in range(max_redirects + 1):
                    resp = await session.get(current_url, allow_redirects=False)
                    if resp.status in (301, 302, 303, 307, 308):
                        redirect_target = resp.headers.get('Location')
                        if not redirect_target:
                            response = resp
                            break
                        from urllib.parse import urljoin
                        redirect_target = urljoin(current_url, redirect_target)
                        if not await asyncio.to_thread(is_safe_url, redirect_target):
                            resp.close()
                            log_debug(f"URL {redirect_target} blocked by SSRF redirect safety guard")
                            return ""
                        current_url = redirect_target
                        resp.close()
                        if redirect_count == max_redirects:
                            log_debug(f"URL {url} exceeded max redirect depth")
                            return ""
                        continue
                    else:
                        response = resp
                        break
                
                async with response:
                    if response.status != 200:
                        log_debug(f"URL {url} returned status {response.status}")
                        return ""
                        
                    content_type = response.headers.get('Content-Type', '').lower()
                    pdf_url = urlparse(current_url).path.lower().endswith(".pdf")
                    is_pdf = "application/pdf" in content_type or (
                        pdf_url and "application/octet-stream" in content_type
                    )
                    if is_pdf:
                        # Read one byte beyond the limit so truncated/chunked
                        # responses are detected and rejected, never parsed as
                        # if they were complete PDFs.
                        raw_pdf = await read_capped(response, MAX_PAGE_BYTES + 1)
                        if len(raw_pdf) > MAX_PAGE_BYTES:
                            log_warning(f"URL PDF {url} exceeded the {MAX_PAGE_BYTES}-byte input limit")
                            return ""
                        try:
                            parsed_text = await asyncio.to_thread(_extract_pdf_text, raw_pdf)
                        except Exception as e:
                            log_debug(f"URL PDF extraction failed {url}: {type(e).__name__}: {e}")
                            return ""
                        if not parsed_text:
                            log_debug(f"URL PDF {url} had no extractable text (encrypted, malformed, or image-only)")
                            return ""
                        max_len = config.url_max_content_length
                        if len(parsed_text) > max_len:
                            parsed_text = parsed_text[:max_len] + "... [TRUNCATED]"
                        final_result = f"Source: {url}\n{parsed_text}"
                        self._cache_store(self._url_cache, url, final_result, now)
                        return final_result

                    if 'text/html' not in content_type and 'text/plain' not in content_type:
                        log_debug(f"URL {url} skipped due to content type: {content_type}")
                        return ""

                    raw = await read_capped(response, MAX_PAGE_BYTES)
                    try:
                        html = raw.decode(response.charset or "utf-8", errors="replace")
                    except LookupError:          # a charset Python does not know
                        html = raw.decode("utf-8", errors="replace")
                    
                    # 3. Parse with BeautifulSoup
                    # Run in an executor since massive HTML trees can block the event loop
                    def parse_html(html_content):
                        soup = BeautifulSoup(html_content, 'html.parser')
                        
                        # Remove scripts, styles, forms, headers, footers
                        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
                            element.decompose()
                            
                        # Get text, strip whitespace
                        text = soup.get_text(separator='\n', strip=True)
                        
                        # Collapse multiple newlines/spaces
                        text = re.sub(r'\n+', '\n', text)
                        text = re.sub(r' +', ' ', text)
                        return text
                        
                    parsed_text = await asyncio.to_thread(parse_html, html)
                    
                    if not parsed_text:
                        return ""
                        
                    # 4. Truncate to save VRAM tokens
                    max_len = config.url_max_content_length
                    if len(parsed_text) > max_len:
                        parsed_text = parsed_text[:max_len] + "... [TRUNCATED]"
                        
                    final_result = f"Source: {url}\n{parsed_text}"
                    self._cache_store(self._url_cache, url, final_result, now)
                    
                    return final_result

                    
        except asyncio.TimeoutError:
            log_warning(f"URL fetch timed out: {url}")
        except Exception as e:
            log_debug(f"URL fetch error {url}: {e}")
            
        return ""
