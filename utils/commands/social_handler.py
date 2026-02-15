import time
from utils.infrastructure.logging.kaia_logger import log_action, log_error

async def handle_quip_command(ctx, msg):
    """Handle the !quip command"""
    try:
        # Check cooldown (10 minutes = 600 seconds)
        current_time = time.time()
        # Owner exemption - uses configurable owner_ids from config
        is_owner = ctx.config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id))
        
        last_quip = getattr(ctx.bot_state, 'last_manual_quip_time', 0)
        remaining = 600 - (current_time - last_quip)
        
        if remaining > 0 and not is_owner:
            await msg.channel.send(f"```\nwait {int(remaining/60)}m {int(remaining%60)}s before quipping again.\n```")
            return

        log_action(f"Manual quip request from {msg.author}")
        await msg.channel.send("```\nokay posting a skeet\n```")
        
        # Reset quips counter if manual
        ctx.bot_state.reset_quips()
        ctx.bot_state.last_manual_quip_time = current_time
        if hasattr(ctx.bot_state, 'save'): ctx.bot_state.save()
        
        from utils.social.kaia_social_responder import generate_quip
        success = await generate_quip(ctx, is_manual=True, target_channel=msg.channel, on_message_func=ctx.bot.on_message)
        if not success:
             log_error("Manual quip generation returned False.")
    except Exception as e:
        log_error(f"Manual quip failed: {e}")
        import traceback
        log_debug(traceback.format_exc())
        await msg.channel.send("```\nquip failed. check logs.\n```")
