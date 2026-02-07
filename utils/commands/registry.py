from utils.commands.news_handler import handle_news_command
from utils.commands.social_handler import handle_quip_command
from utils.commands.dream_handler import handle_dreams_command
from utils.commands.system_handler import handle_cache_command

async def dispatch_command(msg, bot, ollama_client, run_rag, rag, news_manager, dream_engine, bot_state, config, load_persona_async, on_message, send_kaia_response):
    """Route commands to the appropriate handler"""
    content = msg.content.strip()
    
    if content.startswith("!news"):
        await handle_news_command(msg, news_manager, send_kaia_response)
        return True
        
    if content.startswith("!quip"):
        await handle_quip_command(msg, bot, ollama_client, run_rag, rag, bot_state, config, on_message)
        return True
        
    if content.startswith("!dreams"):
        await handle_dreams_command(msg, dream_engine, config, load_persona_async)
        return True
        
    if content.startswith("!cache"):
        await handle_cache_command(msg, config)
        return True
        
    return False
