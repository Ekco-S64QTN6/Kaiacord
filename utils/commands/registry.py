from utils.commands.news_handler import handle_news_command
from utils.commands.social_handler import handle_quip_command
from utils.commands.dream_handler import handle_dreams_command
from utils.commands.system_handler import handle_cache_command

async def dispatch_command(ctx, msg, load_persona_async, send_kaia_response):
    """Route commands to the appropriate handler"""
    content = msg.content.strip()
    
    if content.startswith("!news"):
        await handle_news_command(ctx, msg, send_kaia_response)
        return True
        
    if content.startswith("!quip"):
        await handle_quip_command(ctx, msg)
        return True
        
    if content.startswith("!dreams"):
        await handle_dreams_command(ctx, msg, load_persona_async)
        return True
        
    if content.startswith("!cache"):
        await handle_cache_command(ctx, msg)
        return True
        
    return False
