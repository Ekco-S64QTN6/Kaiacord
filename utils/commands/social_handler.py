import time
from utils.infrastructure.logging.kaia_logger import log_action, log_error

async def handle_quip_command(msg, bot, ollama_client, run_rag, rag, bot_state, config, on_message):
    """Handle the !quip command"""
    try:
        # Check cooldown (10 minutes = 600 seconds)
        current_time = time.time()
        # Owner exemption - uses configurable owner_ids from config
        is_owner = config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id))
        
        last_quip = getattr(bot_state, 'last_manual_quip_time', 0)
        remaining = 600 - (current_time - last_quip)
        
        if remaining > 0 and not is_owner:
            await msg.channel.send(f"```\nwait {int(remaining/60)}m {int(remaining%60)}s before quipping again.\n```")
            return

        log_action(f"Manual quip request from {msg.author}")
        await msg.channel.send("```\nokay posting a skeet\n```")
        
        # Reset quips counter if manual
        bot_state.reset_quips()
        bot_state.last_manual_quip_time = current_time
        if hasattr(bot_state, 'save'): bot_state.save()
        
        from utils.social.kaia_social_responder import generate_quip
        await generate_quip(bot, ollama_client, run_rag, rag, is_manual=True, target_channel=msg.channel, on_message_func=on_message)
    except Exception as e:
        log_error(f"Manual quip failed: {e}")
        await msg.channel.send("```\nquip failed. check logs.\n```")
