from utils.infrastructure.logging.kaia_logger import log_action

async def handle_cache_command(msg, semantic_cache, config):
    """Handle the !cache command (Admin only)"""
    # Owner exemption - uses configurable owner_ids from config
    is_owner = config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id))
    
    if not is_owner:
        await msg.channel.send("```\nrestricted.\n```")
        return
        
    parts = msg.content.strip().split()
    subcommand = parts[1].lower() if len(parts) > 1 else "stats"
    
    if subcommand == "clear":
        semantic_cache.cache.clear()
        semantic_cache.exact_cache.clear()
        if hasattr(semantic_cache, 'save'): semantic_cache.save()
        await msg.channel.send("```\nsemantic cache purged. starting fresh retrieval.\n```")
        log_action("Manual semantic cache purge requested.")
    else:
        size_semantic = len(semantic_cache.cache)
        size_exact = len(semantic_cache.exact_cache)
        await msg.channel.send(f"```\nCache Stats: Semantic={size_semantic}, Exact={size_exact}\n```")
