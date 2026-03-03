"""
Think Tag Visibility Mode
=========================

!think on  — Enable raw chain-of-thought visibility for the calling user.
!think off — Disable it.
!think     — Show current status.

When enabled, the model's <think>...</think> reasoning blocks are preserved in
the response as a Discord spoiler section instead of being stripped.
"""

from utils.infrastructure.logging.kaia_logger import log_action, log_info


async def handle_think_command(ctx, msg, send_kaia_response):
    """Handle the !think [on|off] command — toggle chain-of-thought visibility."""
    from utils.infrastructure.system.yaml_config import config

    # Owner-only command
    if not config.is_owner(msg.author.name, author_name=msg.author.display_name, user_id=str(msg.author.id)):
        await send_kaia_response(msg.channel, "Only the owner can toggle think mode.")
        return

    bot_state = ctx.bot_state

    # Ensure the set exists
    if not hasattr(bot_state, 'think_mode_users'):
        bot_state.think_mode_users = set()

    content = msg.content.strip().lower()
    parts = content.split()

    user_id = msg.author.id

    if len(parts) >= 2:
        arg = parts[1]
        if arg == "on":
            bot_state.think_mode_users.add(user_id)
            log_action(f"Think mode enabled for {msg.author.name}")
            await send_kaia_response(
                msg.channel,
                "Think mode ON. You'll see my raw chain-of-thought as spoiler blocks."
            )
            return
        elif arg == "off":
            bot_state.think_mode_users.discard(user_id)
            log_action(f"Think mode disabled for {msg.author.name}")
            await send_kaia_response(msg.channel, "Think mode OFF.")
            return

    # Status check
    is_on = user_id in bot_state.think_mode_users
    status = "ON" if is_on else "OFF"
    await send_kaia_response(
        msg.channel,
        f"Think mode is currently {status}.\n"
        f"Usage: !think on / !think off\n"
        f"Note: think mode is transient — it resets on bot restart."
    )
