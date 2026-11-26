"""Records musical requests take precedence over Strudel's separate session."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from utils.audio import records_intent, records as R
from utils.commands import music_handler


def _message(content):
    return SimpleNamespace(
        content=content,
        guild=SimpleNamespace(id=987),
        author=SimpleNamespace(display_name="listener"),
        channel=SimpleNamespace(send=AsyncMock()),
    )


def test_records_request_never_calls_strudel_request_handler(monkeypatch):
    records_session = SimpleNamespace(
        request=AsyncMock(return_value=records_intent.RecordsRequestResult(
            True, "I'll favour more bass in the next pick."
        ))
    )
    monkeypatch.setattr(R, "get_records", lambda _guild: records_session)
    monkeypatch.setattr(music_handler, "get_session",
                        lambda _guild: (_ for _ in ()).throw(AssertionError("Strudel was resolved")))
    monkeypatch.setattr(music_handler, "config", SimpleNamespace(get=lambda _key, default=None: default))

    msg = _message("!music more bass")
    asyncio.run(music_handler.handle_music_command(None, msg, None))

    records_session.request.assert_awaited_once_with("more bass", "listener")
    msg.channel.send.assert_awaited_once()


def test_strudel_request_behavior_is_preserved_when_records_are_not_active(monkeypatch):
    strudel_session = SimpleNamespace(
        request=AsyncMock(return_value=SimpleNamespace(understood=True, reply="darker now"))
    )
    monkeypatch.setattr(R, "get_records", lambda _guild: None)
    monkeypatch.setattr(music_handler, "get_session", lambda _guild: strudel_session)
    monkeypatch.setattr(music_handler, "config", SimpleNamespace(get=lambda _key, default=None: default))

    msg = _message("!music darker")
    asyncio.run(music_handler.handle_music_command(None, msg, None))

    strudel_session.request.assert_awaited_once_with("darker", "listener")
    msg.channel.send.assert_awaited_once()


def test_unsupported_records_request_is_replied_to_without_falling_through(monkeypatch):
    records_session = SimpleNamespace(
        request=AsyncMock(return_value=records_intent.RecordsRequestResult(
            False, "I can't identify vocals: the lead curve is only a midrange/presence proxy."
        ))
    )
    monkeypatch.setattr(R, "get_records", lambda _guild: records_session)
    monkeypatch.setattr(music_handler, "get_session",
                        lambda _guild: (_ for _ in ()).throw(AssertionError("must not fall through")))
    monkeypatch.setattr(music_handler, "config", SimpleNamespace(get=lambda _key, default=None: default))

    msg = _message("!music more vocals")
    asyncio.run(music_handler.handle_music_command(None, msg, None))

    records_session.request.assert_awaited_once_with("more vocals", "listener")
    msg.channel.send.assert_awaited_once()
