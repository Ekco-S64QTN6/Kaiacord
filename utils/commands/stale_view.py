"""A button pressed after its message's interaction is gone is not a fault."""
from __future__ import annotations

import discord

from utils.infrastructure.logging.kaia_logger import log_debug, log_error

#: Unknown Webhook (the 15-minute token ran out) and Unknown Interaction (the
#: 3 seconds to answer ran out, or the view is left over from before a restart).
_STALE_CODES = {10015, 10062}


class StaleSafeView(discord.ui.View):
    """A view whose expired interactions are one quiet line. Anything else
    raised by a button is still logged, with its traceback, as an error."""

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        if isinstance(error, discord.NotFound) and getattr(error, "code", None) in _STALE_CODES:
            log_debug(f"[view] {type(self).__name__}: stale interaction ({error.code}), ignored")
            return
        import traceback
        trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        log_error(f"[view] {type(self).__name__} button failed: {error!r}\n{trace}")
