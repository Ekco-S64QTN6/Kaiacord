from utils.infrastructure.logging.kaia_logger import log_action

async def handle_cache_command(msg, config):
    """Reflect that cache is decommissioned."""
    """Handle the !cache command (Admin only)"""
    # Owner exemption - uses configurable owner_ids from config
    is_owner = config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id))
    
    if not is_owner:
        await msg.channel.send("```\nrestricted.\n```")
        return
        
    parts = msg.content.strip().split()
    subcommand = parts[1].lower() if len(parts) > 1 else "stats"
    
    if "clear" in msg.content.lower().split():
        await msg.channel.send("⚠️ **Semantic Cache is decommissioned.** No data to clear.")
        return
        
    await msg.channel.send("⚠️ **Semantic Cache has been permanently disabled.** All responses are now generated in real-time for maximum reliability.")
