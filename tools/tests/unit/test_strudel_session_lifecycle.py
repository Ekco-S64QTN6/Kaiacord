"""A failed Strudel watchdog must not strand voice/audio resources."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from utils.audio import strudel_session as ss


def test_watchdog_exception_stops_and_unregisters_the_music_session(monkeypatch):
    monkeypatch.setattr(ss, "WATCHDOG_PERIOD_S", 0)

    engine = MagicMock()
    engine.alive.side_effect = RuntimeError("fake browser failure")
    source = MagicMock()

    voice = MagicMock()
    voice.guild.id = 4242
    voice.channel.name = "General"
    voice.is_connected.return_value = True
    voice.is_playing.return_value = False
    voice.is_paused.return_value = False
    voice.disconnect = AsyncMock()

    async def go():
        session = ss.MusicSession(
            voice, engine, source, MagicMock(), "house", "tester", None
        )
        ss._sessions[4242] = session
        await asyncio.wait_for(session._task, timeout=1)
        return session

    session = asyncio.run(go())
    assert session._closing
    assert 4242 not in ss._sessions
    engine.stop.assert_called_once()
    engine.close.assert_called_once()
    source.cleanup.assert_called_once()
    voice.disconnect.assert_awaited_once()
