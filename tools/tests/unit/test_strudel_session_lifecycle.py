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


def test_failed_startup_closes_source_engine_and_new_voice_connection(monkeypatch):
    """A failed Discord play must not orphan the partially created audio stack."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    events = []

    class FakeEngine:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            events.append("engine.start")

        def warm_up(self, _code):
            events.append("engine.warm_up")

        def play(self, _code):
            events.append("engine.play")
            return True

        def close(self):
            events.append("engine.close")

    class FakeSource:
        def __init__(self, _engine):
            events.append("source.create")

        def cleanup(self):
            events.append("source.cleanup")

    class FakeVoice:
        def __init__(self):
            self.connected = True
            self.playing = False
            self.disconnect = AsyncMock(side_effect=self._disconnect)

        async def _disconnect(self, force=False):
            assert force is True
            events.append("voice.disconnect")
            self.connected = False

        def is_connected(self):
            return self.connected

        def is_playing(self):
            return self.playing

        def stop(self):
            self.playing = False

        def play(self, _source, after=None):
            raise RuntimeError("voice playback refused")

    async def scenario():
        voice = FakeVoice()
        guild = SimpleNamespace(id=6622, voice_client=None)
        channel = SimpleNamespace(
            guild=guild,
            name="test-channel",
            connect=AsyncMock(return_value=voice),
        )

        monkeypatch.setattr(ss.discord.opus, "is_loaded", lambda: True)
        monkeypatch.setattr(ss, "StrudelEngine", FakeEngine)
        monkeypatch.setattr(ss, "StrudelAudioSource", FakeSource)
        monkeypatch.setattr(ss, "_cfg", lambda _key, default: 0.0 if _key == "prime_seconds" else default)
        monkeypatch.setattr(ss, "build_for_mood", lambda _genre: SimpleNamespace(code=lambda: "test-pattern"))

        from utils.audio import records
        from utils.radio import live
        monkeypatch.setattr(records, "get_records", lambda _guild_id: None)
        monkeypatch.setattr(live, "free_voice", AsyncMock())
        monkeypatch.setattr(ss, "settle", lambda _message: None)

        try:
            await ss.start_session(channel, genre="house", requested_by="pytest")
        except RuntimeError as exc:
            assert str(exc) == "voice playback refused"
        else:
            raise AssertionError("startup failure was not propagated")

        assert "source.cleanup" in events
        assert "engine.close" in events
        assert events.index("source.cleanup") < events.index("engine.close")
        voice.disconnect.assert_awaited_once_with(force=True)
        assert not voice.connected
        assert 6622 not in ss._sessions

    asyncio.run(scenario())
