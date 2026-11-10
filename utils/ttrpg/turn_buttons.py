"""Every `!rpg` turn ends on a message with buttons under it.

A turn is one typed command or one button press. Handlers send their cards
through `msg.channel.send` or the `send` callable, and each records the message
here. When the turn ends:

- if its last card already carries buttons, nothing changes;
- if an earlier card of the turn carried them (a combat round, then a quest
  card), they are moved down to the last one, so the buttons are always the
  newest thing in the channel;
- otherwise the last card gets the buttons for where the player is: the fight
  or dungeon they are in, Hunt Again + Status in the wild, Status in town.

A forest event (the Strange Statue) sent its card bare, so the only way on was
to scroll up to an old turn's buttons or type `!rpg` again.
"""
from __future__ import annotations

import asyncio
import contextvars
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field

import discord

from utils.infrastructure.logging.kaia_logger import log_debug

#: A press is answered by its first card. If none is ready this long after
#: the press, it is deferred instead: Discord fails one left unanswered for 3 s.
ANSWER_WITHIN = 2.0

#: How long a fallback set stays live. The turn's own views mostly use 60-120 s,
#: which a player reading a long card outlasts.
FALLBACK_TIMEOUT = 300

_current: contextvars.ContextVar["_Turn | None"] = contextvars.ContextVar("rpg_turn", default=None)


@dataclass
class _Turn:
    ctx: object
    msg: object
    uid: str
    uname: str
    is_owner: bool
    sent: list = field(default_factory=list)      # (message, view or None), in order


def _view_of(kwargs) -> discord.ui.View | None:
    view = kwargs.get("view")
    return view if isinstance(view, discord.ui.View) else None


def record(message, kwargs) -> None:
    """Note a card the current turn sent. Ephemeral replies don't count: only
    the presser sees them, and they can't be the turn's last word."""
    turn = _current.get()
    if turn is None or message is None or kwargs.get("ephemeral"):
        return
    turn.sent.append((message, _view_of(kwargs)))


class TurnChannel:
    """A channel whose sends are recorded; everything else is the channel's."""

    def __init__(self, channel):
        self._channel = channel

    async def send(self, *args, **kwargs):
        message = await self._channel.send(*args, **kwargs)
        record(message, kwargs)
        return message

    def __getattr__(self, name):
        return getattr(self._channel, name)

    def __eq__(self, other):
        return getattr(other, "id", None) == getattr(self._channel, "id", object())

    def __hash__(self):
        return hash(getattr(self._channel, "id", id(self)))


class TurnMessage:
    """A command message whose `.channel` records what the turn sends."""

    def __init__(self, msg):
        self._msg = msg
        self.channel = TurnChannel(msg.channel)

    def __getattr__(self, name):
        return getattr(self._msg, name)


async def fallback_view(ctx, msg, uid, uname, is_owner):
    """The buttons for where the player is now, or None without a character."""
    from utils.ttrpg.character_manager import load
    from utils.ttrpg.world import LOCATION_DATA
    from utils.ttrpg import rpg_views

    sheet = await load(uid)
    if not sheet:
        return None
    view = await rpg_views._get_active_view(ctx, msg, uid, uname, is_owner)
    if view is not None:
        return view
    loc = sheet.get("location", "oakhaven")
    if sheet.get("hp", {}).get("current", 1) > 0 and LOCATION_DATA.get(loc, {}).get("hunting"):
        view = rpg_views._make_hunt_status_view(ctx, msg, uid, uname, is_owner)
    else:
        view = rpg_views._make_status_view(ctx, msg, uid, uname, is_owner)
    view.timeout = FALLBACK_TIMEOUT
    return view


async def _finish(turn: _Turn) -> None:
    if not turn.sent:
        return
    last, last_view = turn.sent[-1]
    if last_view is not None:
        return
    earlier = [(m, v) for m, v in turn.sent[:-1] if v is not None]
    try:
        if earlier:
            message, view = earlier[-1]
            if view.is_finished():
                view = None
            else:
                await message.edit(view=None)
        else:
            view = None
        if view is None:
            view = await fallback_view(turn.ctx, turn.msg, turn.uid, turn.uname, turn.is_owner)
        if view is not None:
            await last.edit(view=view)
    except Exception as exc:          # a card without buttons is not worth failing the turn
        log_debug(f"[rpg] turn buttons not attached: {exc!r}")


@asynccontextmanager
async def turn(ctx, msg, uid, uname, is_owner):
    """Scope one turn. Nested scopes (a handler calling another) are the outer one's."""
    if _current.get() is not None:
        yield msg
        return
    state = _Turn(ctx, msg, str(uid), uname, is_owner)
    token = _current.set(state)
    try:
        yield msg
    finally:
        _current.reset(token)
        await _finish(state)


def in_turn() -> bool:
    return _current.get() is not None


async def run(handler, ctx, msg, send, rest, uid, uname, is_owner):
    """Call a handler from a button as a turn of its own."""
    async with turn(ctx, msg, uid, uname, is_owner):
        return await handler(ctx, msg, send, rest, uid, uname, is_owner)


async def buttons_for(ctx, interaction, uid, uname, is_owner):
    """`fallback_view` for a card a view's callback sends itself."""
    from utils.ttrpg.rpg_views import _InteractionMsg
    return await fallback_view(ctx, _InteractionMsg(interaction), str(uid), uname, is_owner)


# ── Answering a press ─────────────────────────────────────────────────────────
# A press used to be deferred and then followed up: two round trips to Discord,
# one after the other, before the next round appeared. Posting the first card
# as the interaction's response is one. `answering` scopes a press; `reply`
# sends a card through it; `acknowledge` defers a press that has sent nothing.

_reply_locks: dict[int, asyncio.Lock] = {}


def _key(interaction) -> int:
    return getattr(interaction, "id", None) or id(interaction)


def _answered(interaction) -> bool:
    """Whether the press has its response. A stand-in with no `response`
    (a handler's message-shaped fake) only ever had follow-ups."""
    is_done = getattr(getattr(interaction, "response", None), "is_done", None)
    return True if is_done is None else bool(is_done())


def _lock_for(interaction) -> asyncio.Lock:
    return _reply_locks.setdefault(_key(interaction), asyncio.Lock())


async def acknowledge(interaction) -> None:
    """Defer the press if nothing has answered it yet."""
    async with _lock_for(interaction):
        if _answered(interaction):
            return
        with suppress(discord.NotFound, discord.HTTPException):
            await interaction.response.defer()


async def reply(interaction, content=None, *, fallback_channel=None, **kwargs):
    """Send a card for this press: as its response while it has none, as a
    follow-up after. An expired press (NotFound) goes to `fallback_channel`."""
    kwargs.pop("wait", None)
    if kwargs.get("view", ...) is None:
        del kwargs["view"]
    async with _lock_for(interaction):
        try:
            if not _answered(interaction):
                callback = await interaction.response.send_message(content, **kwargs)
                message = getattr(callback, "resource", None)
            else:
                message = await interaction.followup.send(content, wait=True, **kwargs)
        except discord.NotFound:
            if fallback_channel is None or kwargs.get("ephemeral"):
                raise
            kwargs.pop("ephemeral", None)
            message = await fallback_channel.send(content, **kwargs)
    record(message, kwargs)
    return message


@asynccontextmanager
async def answering(interaction, after: float = ANSWER_WITHIN):
    """Scope a press whose cards go through `reply`. Deferred `after` seconds
    in if nothing has answered it, and when it ends having sent nothing."""
    async def _deadline():
        await asyncio.sleep(after)
        await asyncio.shield(acknowledge(interaction))

    deadline = asyncio.create_task(_deadline())
    try:
        yield
    finally:
        deadline.cancel()
        with suppress(asyncio.CancelledError):
            await deadline
        try:
            await acknowledge(interaction)
        finally:
            _reply_locks.pop(_key(interaction), None)
