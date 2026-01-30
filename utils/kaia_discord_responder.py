"""
Kaia Discord Startup Responder
================================

Check for missed Discord mentions and replies on bot startup.

Similar to kaia_social_responder.py but for Discord messages that were 
received while the bot was offline.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
from datetime import datetime, timedelta
from utils.kaia_logger import log_info, log_success, log_warning, log_error, log_action

# Replied mentions tracker (persisted to disk)
_replied_ids_path = Path("storage/discord_replied_ids.json")
_replied_ids: Set[str] = set()
_replied_ids_lock = asyncio.Lock()


def _load_replied_ids():
    """Load set of already-replied Discord message IDs from disk."""
    global _replied_ids
    try:
        if _replied_ids_path.exists():
            with open(_replied_ids_path, 'r') as f:
                data = json.load(f)
                _replied_ids = set(data.get('discord', []))
    except Exception as e:
        log_warning(f"Failed to load Discord replied IDs: {e}")


def _save_replied_ids():
    """Save replied IDs to disk."""
    try:
        _replied_ids_path.parent.mkdir(exist_ok=True)
        with open(_replied_ids_path, 'w') as f:
            json.dump({
                'discord': list(_replied_ids)
            }, f)
    except Exception as e:
        log_warning(f"Failed to save Discord replied IDs: {e}")


def _get_persona() -> str:
    """Load Kaia's persona for response generation."""
    persona_file = Path("knowledge_base/kaia_persona.md")
    try:
        if persona_file.exists():
            return persona_file.read_text().strip()
    except:
        pass
    return "You are Kaia, a blunt and grounded AI. Keep responses short and authentic."


async def _generate_response(message_text: str, author_name: str) -> Optional[str]:
    """Generate a response using Ollama chat model."""
    try:
        import ollama
        from bot.managers.yaml_config import config
        
        persona = _get_persona()
        
        system_prompt = f"""{persona}

You are responding to a Discord message you missed while offline.
Keep your response under 500 characters.
Be conversational, witty, and authentic to your personality.
Respond directly to what they said."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{author_name} said: {message_text}"}
        ]
        
        client = ollama.AsyncClient()
        response = await client.chat(
            model=config.chat_model,
            messages=messages,
            options={
                "temperature": 0.8,
                "num_predict": 150,
            }
        )
        
        reply_text = response['message']['content'].strip()
        
        # Enforce character limit
        if len(reply_text) > 500:
            reply_text = reply_text[:497] + "..."
        
        return reply_text
        
    except Exception as e:
        log_error(f"Failed to generate Discord response: {e}")
        return None


async def check_missed_discord_mentions(bot) -> int:
    """
    Check for Discord mentions and replies that were missed while bot was offline.
    
    Args:
        bot: The Discord bot instance
        
    Returns:
        Number of replies sent
    """
    global _replied_ids
    
    # Load replied IDs if not loaded
    if not _replied_ids:
        _load_replied_ids()
    
    total_replies = 0
    cutoff_time = datetime.utcnow() - timedelta(hours=48)  # Check last 48 hours
    
    try:
        log_action("Checking for missed Discord mentions...")
        
        # Iterate through all guilds (servers) the bot is in
        for guild in bot.guilds:
            # Check each text channel
            for channel in guild.text_channels:
                try:
                    # Check if bot has permission to read message history
                    if not channel.permissions_for(guild.me).read_message_history:
                        continue
                    
                    # Fetch recent messages (last 48 hours, limit 100 per channel)
                    async for message in channel.history(limit=100, after=cutoff_time):
                        message_id = str(message.id)
                        
                        # Skip if already replied to
                        if message_id in _replied_ids:
                            continue
                        
                        # Skip bot's own messages
                        if message.author.id == bot.user.id:
                            continue
                        
                        # Check if message mentions Kaia or is a reply to Kaia's message
                        is_mention = bot.user in message.mentions or "kaia" in message.content.lower()
                        is_reply_to_kaia = False
                        
                        if message.reference:
                            try:
                                replied_msg = await channel.fetch_message(message.reference.message_id)
                                is_reply_to_kaia = replied_msg.author.id == bot.user.id
                            except:
                                pass
                        
                        if is_mention or is_reply_to_kaia:
                            # Found an unresponded mention/reply
                            log_info(f"Found missed message from {message.author.name}: {message.content[:50]}...")
                            
                            # Generate response
                            response = await _generate_response(message.content, message.author.name)
                            if response:
                                # Send reply
                                try:
                                    await message.reply(f"```\n{response}\n```")
                                    
                                    # Mark as replied
                                    async with _replied_ids_lock:
                                        _replied_ids.add(message_id)
                                    
                                    log_success(f"Replied to {message.author.name}'s missed message: {response[:50]}...")
                                    total_replies += 1
                                    
                                    # Limit to prevent spam
                                    if total_replies >= 5:
                                        log_warning("Reached reply limit (5) for startup mentions")
                                        break
                                    
                                except Exception as e:
                                    log_error(f"Failed to send Discord reply: {e}")
                        
                except Exception as e:
                    log_warning(f"Error checking channel {channel.name}: {e}")
                    continue
                
                # Break if reached limit
                if total_replies >= 5:
                    break
            
            # Break if reached limit
            if total_replies >= 5:
                break
        
        # Save replied IDs if any replies were sent
        if total_replies > 0:
            _save_replied_ids()
            log_info(f"Discord startup check complete: {total_replies} replies sent")
        else:
            log_info("Discord startup check complete: No missed mentions found")
        
    except Exception as e:
        log_error(f"Discord mention check failed: {e}")
    
    return total_replies
