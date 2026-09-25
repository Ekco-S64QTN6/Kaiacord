"""!selfmodel — regenerate memory/kaia_self_model.md now (owner only).

Uses the dream engine's GPU-guarded generation in-process, not a subprocess,
so it cannot collide with the bot's own use of the model.
"""
import asyncio
import os

from utils.commands.embed_style import box, clean_block, notice
from utils.infrastructure.logging.kaia_logger import log_error, log_info

SELF_MODEL = os.path.join("memory", "kaia_self_model.md")


def _read_model() -> str:
    try:
        with open(SELF_MODEL, encoding="utf-8") as f:
            text = f.read().strip()
    except OSError:
        return ""
    if text.startswith("<!--"):
        text = text[text.find("-->") + 3:].strip()
    return text


async def handle_selfmodel_command(ctx, msg, send_kaia_response):
    """Regenerate the self-model and show its opening."""
    if not ctx.config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id)):
        await msg.channel.send(embed=notice("you aren't my architect. restricted.", error=True))
        return
    engine = getattr(ctx, "dream_engine", None)
    if engine is None:
        await msg.channel.send(embed=notice("The dream engine isn't running yet; try again in a minute.", error=True))
        return

    status = await msg.channel.send(embed=notice("Rereading recent conversations and dreams…", title="🪞  Self-model"))
    log_info(f"Self-model regeneration triggered by {msg.author.name}")
    try:
        from utils.social.kaia_social_responder import load_persona_async
        persona = await load_persona_async()
        if not persona:
            await status.edit(embed=notice("The persona file couldn't be loaded.", error=True))
            return
        before = await asyncio.to_thread(os.path.getmtime, SELF_MODEL) if os.path.exists(SELF_MODEL) else 0
        await engine._maybe_regenerate_self_model(persona, force=True)
        after = await asyncio.to_thread(os.path.getmtime, SELF_MODEL) if os.path.exists(SELF_MODEL) else 0
        if after <= before:
            # The generator logs and returns on a short or failed draft.
            await status.edit(embed=notice("No new self-model was written; the log has the reason.", error=True))
            return
        # The prompt caches identity blocks; make the next turn read the new one.
        if getattr(ctx, "message_processor", None):
            ctx.message_processor._identity_cache_time = 0.0
        text = await asyncio.to_thread(_read_model)
        await status.edit(embed=box("🪞  Self-model updated", clean_block(text, 900)))
    except Exception as e:
        log_error(f"Error executing self-model generation: {e}")
        await status.edit(embed=notice("Self-model regeneration failed; the log has the reason.", error=True))
