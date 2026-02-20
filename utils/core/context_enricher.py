import re
import asyncio
import discord
from typing import List, Optional
from utils.infrastructure.logging.kaia_logger import log_info, log_debug, log_warning

class ContextEnricher:
    """
    Enriches user message context by extracting data from embeds 
    and resolving message links.
    """
    
    def __init__(self, bot):
        self.bot = bot
        # Regex for Discord message links
        self.msg_link_pattern = re.compile(
            r'https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)'
        )
        # Fetch Cache: {id: (timestamp, object)}
        self._channel_cache = {}
        self._message_cache = {}
        self._cache_ttl = 300 # 5 minutes

    async def enrich_content(self, msg: discord.Message) -> str:
        """
        Main entry point to get full context from a message.
        """
        content = msg.content
        
        # 1. Resolve Replies (Highest priority context)
        reply_context = await self.resolve_replies(msg)
        if reply_context:
            content = f"[REPLYING_TO]\n{reply_context}\n\n[USER_MESSAGE]\n{content}"

        # 2. Extract Appendages (Embeds)
        embed_text = self.extract_embed_text(msg)
        if embed_text:
            content += f"\n\n[ATTACHED_EMBED_CONTEXT]\n{embed_text}"
            
        # 3. Resolve Links
        linked_context = await self.resolve_message_links(msg)
        if linked_context:
            content += f"\n\n[LINKED_MESSAGE_CONTEXT]\n{linked_context}"
            
        return content

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
                return f"{author}: {target_msg.content}"
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
        now = asyncio.get_event_loop().time()
        
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
