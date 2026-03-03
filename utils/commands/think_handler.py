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
    await send_kaia_response(msg.channel, "Think mode is not available on the current model.")
    return
