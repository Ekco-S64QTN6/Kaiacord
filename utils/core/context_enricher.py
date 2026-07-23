import re
import asyncio
import discord
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Optional
from utils.infrastructure.logging.kaia_logger import log_info, log_debug, log_warning
from utils.infrastructure.system.yaml_config import config
from utils.core.sanitizer import is_safe_url

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
            r'(?<!<)https?://(?!discord(?:app)?\.com/channels/)[^\s>]+'
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
            
        # 4. Resolve Links
        linked_context = await self.resolve_message_links(msg)
        if linked_context:
            content += f"\n\n[LINKED_MESSAGE_CONTEXT]\n{linked_context}"
            
        # 5. Scrape External URLs
        if config.url_fetching_enabled:
            url_context = await self.resolve_external_urls(msg)
            if url_context:
                content += f"\n\n[LINKED_WEB_CONTENT]\n{url_context}\n\n[CORE_DIRECTIVE: Keep your response brutally concise. Do not write a long essay or summarize the entire article unless explicitly asked.]"
            
        return content

    async def resolve_mentions(self, content: str, msg: discord.Message) -> str:
        """Resolve <@ID> and <@!ID> mentions to display names."""
        mention_pattern = re.compile(r'<@!?(\d+)>')
        matches = mention_pattern.findall(content)
        
        if not matches:
            return content
            
        resolved_content = content
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
                
        return resolved_content

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
                resolved_content = await self.resolve_mentions(target_msg.content, target_msg)
                
                # If target message was sent by the bot, determine whom the bot was addressing
                if target_msg.author.id == self.bot.user.id:
                    recipient_name = None
                    
                    # 1. Try to find the message in channel_memory to identify who the bot was responding to
                    try:
                        from utils.infrastructure.system.bot_state import bot_state
                        channel_mem = list(bot_state.channel_memory.get(msg.channel.id, []))
                        for idx, turn in enumerate(channel_mem):
                            if (turn.get('role') == 'assistant' and 
                                turn.get('content', '').strip().lower() == target_msg.content.strip().lower()):
                                if idx > 0 and channel_mem[idx-1].get('role') == 'user':
                                    prev_content = channel_mem[idx-1].get('content', '')
                                    if ':' in prev_content:
                                        recipient_name = prev_content.split(':', 1)[0].strip()
                                        break
                    except Exception as e:
                        log_warning(f"Error lookup in channel_memory for reply recipient: {e}")
                        
                    # 2. Fallback: Parse recipient from start of the bot message content (e.g., "username, ")
                    if not recipient_name:
                        content_str = target_msg.content.strip()
                        if ',' in content_str:
                            first_part = content_str.split(',', 1)[0].strip()
                            words = first_part.split()
                            if 0 < len(words) <= 3:
                                clean_part = re.sub(r'[^\w\s\-\[\]]', '', first_part).strip()
                                if clean_part and not any(w in clean_part.lower() for w in ['actually', 'i', 'we', 'the', 'she', 'he', 'they', 'you', 'it']):
                                    recipient_name = clean_part

                    # 3. Fallback 2: Query channel history for the preceding non-bot message
                    if not recipient_name:
                        try:
                            async for prev_msg in msg.channel.history(limit=5, before=target_msg):
                                if prev_msg.author.id != self.bot.user.id and not prev_msg.author.bot:
                                    recipient_name = prev_msg.author.display_name
                                    break
                        except Exception as e:
                            log_debug(f"Failed to query channel history for preceding message: {e}")

                    if recipient_name:
                        author = f"{author} (replying to {recipient_name})"

                return f"{author}: {resolved_content}"
        except Exception as e:
            log_debug(f"Failed to resolve reply: {e}")
            
        return ""

    def extract_embed_text(self, msg: discord.Message) -> str:
        """Extract titles, descriptions, and fields from Discord embeds."""
        if not msg.embeds:
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
            tasks.append(self._resolve_single_link(int(channel_id), int(message_id)))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        resolved_texts = []
        for res in results:
            if isinstance(res, str) and res:
                resolved_texts.append(res)
            elif isinstance(res, Exception):
                log_debug(f"Link resolution failed: {res}")
                
        return "\n\n".join(resolved_texts)

    async def _resolve_single_link(self, channel_id: int, message_id: int) -> str:
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
                    self._channel_cache[channel_id] = (now, channel)
                except Exception as e:
                    log_debug(f"Failed to fetch channel {channel_id}: {e}")
                    return ""

        if not channel:
            return ""

        # 2. Get/Fetch Message
        # Check cache first
        if message_id in self._message_cache:
            timestamp, cached_msg = self._message_cache[message_id]
            if now - timestamp < self._cache_ttl:
                author = cached_msg.author.display_name
                return f"Message from {author} in #{channel.name}:\n{cached_msg.content}"

        try:
            linked_msg = await channel.fetch_message(message_id)
            if linked_msg:
                self._message_cache[message_id] = (now, linked_msg)
                author = linked_msg.author.display_name
                return f"Message from {author} in #{channel.name}:\n{linked_msg.content}"
        except Exception as e:
            log_debug(f"Failed to fetch message {message_id}: {e}")
            
        return ""

    async def resolve_external_urls(self, msg: discord.Message) -> str:
        """Find external web links and scrape their content concurrently."""
        matches = self.external_link_pattern.findall(msg.content)
        if not matches:
            return ""
            
        # Remove duplicates and limit to 2 links to prevent abuse/stall
        unique_urls = list(dict.fromkeys(matches))[:2]
        
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
                "their details. If the user asks you to summarize or discuss them, politely explain that you "
                "cannot fetch or access the links (e.g., due to access restrictions, dynamic content, or login walls).]"
            )
            
        return "\n\n".join(context_parts)

    async def _scrape_single_url(self, url: str) -> str:
        """Scrape text from a single URL with caching and limits."""
        now = asyncio.get_running_loop().time()
        
        # 1. SSRF Guard Check
        if not is_safe_url(url):
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
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
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
                        if not is_safe_url(redirect_target):
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
                    if 'text/html' not in content_type and 'text/plain' not in content_type:
                        log_debug(f"URL {url} skipped due to content type: {content_type}")
                        return ""
                        
                    html = await response.text()
                    
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
                    self._url_cache[url] = (now, final_result)
                    
                    return final_result

                    
        except asyncio.TimeoutError:
            log_warning(f"URL fetch timed out: {url}")
        except Exception as e:
            log_debug(f"URL fetch error {url}: {e}")
            
        return ""
