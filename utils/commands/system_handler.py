import discord
from utils.infrastructure.logging.kaia_logger import log_action

async def handle_cache_command(ctx, msg):
    """Handle the !cache command (Admin only)"""
    # Owner exemption - uses configurable owner_ids from config
    is_owner = ctx.config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id))
    
    if not is_owner:
        await msg.channel.send("```\nrestricted.\n```")
        return
        
    parts = msg.content.strip().split()
    subcommand = parts[1].lower() if len(parts) > 1 else "stats"
    
    if "clear" in msg.content.lower().split():
        embed = discord.Embed(
            title="⚠️  SEMANTIC CACHE DECOMMISSIONED",
            description="No data to clear. The cache database is offline.",
            color=0xeab308
        )
        await msg.channel.send(embed=embed)
        return
        
    embed = discord.Embed(
        title="⚠️  SEMANTIC CACHE DECOMMISSIONED",
        description="Semantic Cache has been permanently disabled.\nAll responses are now generated in real-time for maximum reliability.",
        color=0xeab308
    )
    await msg.channel.send(embed=embed)
