"""
Self-Model Generation Command
=============================

!selfmodel — Regenerate the kaia_self_model.md file on demand.

Uses the DreamEngine's inline GPU-guarded self-model generation instead of
spawning a subprocess, preventing VRAM collisions with the main bot process.
"""

import os
from utils.infrastructure.logging.kaia_logger import log_info, log_error


async def handle_selfmodel_command(ctx, msg, send_kaia_response):
    """Handle the !selfmodel command to trigger self-model regeneration."""
    is_owner = ctx.config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id))
    if not is_owner:
        await msg.channel.send("```\nyou aren't my architect. restricted.\n```")
        return

    await send_kaia_response(msg.channel, "Reflecting on recent memories... Regenerating self-model. This may take a moment.")
    log_info(f"Self-model regeneration triggered by {msg.author.name}")

    try:
        # Get the DreamEngine from the application context
        dream_engine = getattr(ctx, 'dream_engine', None)
        if dream_engine is None:
            log_error("Self-model regen: DreamEngine not available on app context.")
            await send_kaia_response(msg.channel, "Dream engine isn't initialized yet. Try again in a minute.")
            return

        # Load persona for the generation prompt
        from utils.social.kaia_social_responder import load_persona_async
        persona_content = await load_persona_async()

        if not persona_content:
            log_error("Self-model regen: Could not load persona file.")
            await send_kaia_response(msg.channel, "Couldn't load persona file. Something's wrong.")
            return

        # Call the inline GPU-guarded self-model generation with force=True
        await dream_engine._maybe_regenerate_self_model(persona_content, force=True)

        # Read the newly generated model for confirmation
        self_model_path = os.path.join("memory", "kaia_self_model.md")
        if os.path.exists(self_model_path):
            with open(self_model_path, "r", encoding="utf-8") as f:
                content = f.read().strip()

            # Strip the HTML comment header if present
            if content.startswith('<!--'):
                content = content[content.find('-->') + 3:].strip()

            preview = content[:300] + ("..." if len(content) > 300 else "")

            # Invalidate the identity cache in message_processor to pick up new model
            if hasattr(ctx, 'message_processor'):
                ctx.message_processor._identity_cache_time = 0.0

            await send_kaia_response(msg.channel, f"Self-model updated successfully.\n\n**Preview:**\n{preview}")
            log_info("Self-model regenerated successfully via inline GPU-guarded path (cache invalidated).")
        else:
            await send_kaia_response(msg.channel, "Self-model generation completed, but output file was not found.")
            log_error("Self-model output file missing after inline generation.")

    except Exception as e:
        log_error(f"Error executing self-model generation: {e}")
        await send_kaia_response(msg.channel, f"An error occurred while regenerating the self-model: {e}")
