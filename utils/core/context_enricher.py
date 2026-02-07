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
        # https://discord.com/channels/GUILD_ID/CHANNEL_ID/MESSAGE_ID
        self.msg_link_pattern = re.compile(
            r'https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)'
        )

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
        """Find Discord message links and fetch their content."""
        matches = self.msg_link_pattern.findall(msg.content)
        if not matches:
            return ""
            
        resolved_texts = []
        # Limit to 3 links to prevent abuse/latency
        for guild_id, channel_id, message_id in matches[:3]:
            try:
                guild_id, channel_id, message_id = int(guild_id), int(channel_id), int(message_id)
                
                # Try to get from cache first
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    # Fallback to fetch
                    channel = await self.bot.fetch_channel(channel_id)
                
                if channel:
                    linked_msg = await channel.fetch_message(message_id)
                    if linked_msg:
                        author = linked_msg.author.display_name
                        text = linked_msg.content
                        resolved_texts.append(f"Message from {author} in #{channel.name}:\n{text}")
            except Exception as e:
                log_debug(f"Failed to resolve message link {message_id}: {e}")
                
        return "\n\n".join(resolved_texts)
