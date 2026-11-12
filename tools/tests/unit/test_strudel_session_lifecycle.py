"""A failed Strudel watchdog must not strand voice/audio resources."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from utils.audio import strudel_session as ss


def test_watchdog_exception_stops_and_unregisters_the_music_session(monkeypatch):
    import threading

    monkeypatch.setattr(ss, "WATCHDOG_PERIOD_S", 0)
    loop_thread = threading.get_ident()
    call_threads = {}

    def record_thread(name, *, fail=False):
        def call(*_args, **_kwargs):
            call_threads[name] = threading.get_ident()
            if fail:
                raise RuntimeError("fake browser failure")
        return call

    engine = MagicMock()
    engine.alive.side_effect = record_thread("alive", fail=True)
    engine.stop.side_effect = record_thread("stop")
    engine.close.side_effect = record_thread("close")
    source = MagicMock()
    source.cleanup.side_effect = record_thread("source cleanup")

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
    assert set(call_threads) == {"alive", "stop", "source cleanup", "close"}
    assert all(thread_id != loop_thread for thread_id in call_threads.values())


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

        def play(self, _source, after=None, **_kwargs):
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


def test_partial_engine_start_failure_still_closes_engine(monkeypatch):
    """StrudelEngine.start may raise after creating its local server/browser."""
    from types import SimpleNamespace

    events = []

    class PartiallyStartedEngine:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            events.append("engine.start")
            raise RuntimeError("browser failed after server started")

        def close(self):
            events.append("engine.close")

    async def scenario():
        guild = SimpleNamespace(id=6623, voice_client=None)
        channel = SimpleNamespace(guild=guild, name="test-channel")

        monkeypatch.setattr(ss.discord.opus, "is_loaded", lambda: True)
        monkeypatch.setattr(ss, "StrudelEngine", PartiallyStartedEngine)
        monkeypatch.setattr(ss, "_cfg", lambda _key, default: default)

        from utils.audio import records
        monkeypatch.setattr(records, "get_records", lambda _guild_id: None)

        try:
            await ss.start_session(channel, genre="house", requested_by="pytest")
        except RuntimeError as exc:
            assert str(exc) == "browser failed after server started"
        else:
            raise AssertionError("engine startup failure was not propagated")

        assert events == ["engine.start", "engine.close"]
        assert 6623 not in ss._sessions

    asyncio.run(scenario())


def test_failed_startup_leaves_a_reused_connections_playback_alone(monkeypatch):
    """If free_voice() could not stop the radio, startup cleanup must not either."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    events = []

    class FakeEngine:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            pass

        def warm_up(self, _code):
            pass

        def play(self, _code):
            return True

        def close(self):
            events.append("engine.close")

    class FailingSource:
        def __init__(self, _engine):
            raise RuntimeError("capture failed")

    async def scenario():
        radio_vc = SimpleNamespace(
            is_connected=lambda: True,
            is_playing=lambda: True,          # the radio is still on it
            move_to=AsyncMock(),
            stop=MagicMock(),
            disconnect=AsyncMock(),
        )
        guild = SimpleNamespace(id=6624, voice_client=radio_vc)
        channel = SimpleNamespace(guild=guild, name="test-channel")

        monkeypatch.setattr(ss.discord.opus, "is_loaded", lambda: True)
        monkeypatch.setattr(ss, "StrudelEngine", FakeEngine)
        monkeypatch.setattr(ss, "StrudelAudioSource", FailingSource)
        monkeypatch.setattr(ss, "_cfg", lambda _key, default: 0.0 if _key == "prime_seconds" else default)
        monkeypatch.setattr(ss, "build_for_mood", lambda _genre: SimpleNamespace(code=lambda: "test-pattern"))

        from utils.audio import records
        from utils.radio import live
        monkeypatch.setattr(records, "get_records", lambda _guild_id: None)
        monkeypatch.setattr(live, "free_voice", AsyncMock(side_effect=RuntimeError("radio busy")))

        try:
            await ss.start_session(channel, genre="house", requested_by="pytest")
        except RuntimeError as exc:
            assert str(exc) == "capture failed"
        else:
            raise AssertionError("startup failure was not propagated")

        assert events == ["engine.close"]
        radio_vc.stop.assert_not_called()
        radio_vc.disconnect.assert_not_awaited()
        assert 6624 not in ss._sessions

    asyncio.run(scenario())



def test_monitor_loopback_is_shared_between_guild_sessions_and_unloaded_on_last_release(monkeypatch):
    from utils.audio import strudel_engine as engine

    modules = {}
    next_id = [40]
    calls = []

    def pactl(*args):
        calls.append(args)
        if args[:3] == ("list", "short", "modules"):
            return "\n".join(f"{module_id} module-loopback source=kaia_music.monitor" for module_id in modules)
        if args[:2] == ("load-module", "module-loopback"):
            module_id = str(next_id[0])
            next_id[0] += 1
            modules[module_id] = True
            return module_id
        if args[:1] == ("unload-module",):
            modules.pop(str(args[1]), None)
            return ""
        raise AssertionError(args)

    monkeypatch.setattr(engine, "_pactl", pactl)
    monkeypatch.setattr(engine, "_MONITOR_USERS", 0)

    assert engine.monitor_to_speakers(True) is True
    assert engine.monitor_to_speakers(True) is True
    assert len(modules) == 1
    assert sum(c[:2] == ("load-module", "module-loopback") for c in calls) == 1

    assert engine.monitor_to_speakers(False) is True
    assert len(modules) == 1, "the first guild must not mute the second"
    assert engine.monitor_to_speakers(False) is True
    assert modules == {}
    assert engine.monitor_to_speakers(False) is False


def test_first_monitor_acquire_clears_stale_loopbacks_from_an_interrupted_process(monkeypatch):
    from utils.audio import strudel_engine as engine

    modules = {"12": True, "13": True}
    next_id = [14]

    def pactl(*args):
        if args[:3] == ("list", "short", "modules"):
            return "\n".join(f"{module_id} module-loopback source=kaia_music.monitor" for module_id in modules)
        if args[:1] == ("unload-module",):
            modules.pop(str(args[1]), None)
            return ""
        if args[:2] == ("load-module", "module-loopback"):
            module_id = str(next_id[0])
            next_id[0] += 1
            modules[module_id] = True
            return module_id
        raise AssertionError(args)

    monkeypatch.setattr(engine, "_pactl", pactl)
    monkeypatch.setattr(engine, "_MONITOR_USERS", 0)
    assert engine.monitor_to_speakers(True) is True
    assert set(modules) == {"14"}
    assert engine.monitor_to_speakers(False) is True
    assert modules == {}


def test_session_stop_releases_its_speaker_monitor_lease(monkeypatch):
    releases = []
    monkeypatch.setattr(ss, "monitor_to_speakers", lambda enable=True: releases.append(enable) or True)

    async def scenario():
        voice = MagicMock()
        voice.guild.id = 8844
        voice.channel.name = "General"
        voice.disconnect = AsyncMock()
        session = ss.MusicSession(
            voice, MagicMock(), MagicMock(), MagicMock(), "house", "tester",
            monitor_on_speakers=True,
        )
        ss._sessions[8844] = session
        await session.stop()
        await session.stop()

    asyncio.run(scenario())
    assert releases == [False]


def test_failed_startup_releases_the_speaker_monitor_lease(monkeypatch):
    from types import SimpleNamespace

    events = []

    class FakeEngine:
        def __init__(self, **_kwargs):
            pass
        def start(self):
            pass
        def warm_up(self, _code):
            pass
        def play(self, _code):
            return True
        def close(self):
            events.append("engine.close")

    class FakeSource:
        def __init__(self, _engine):
            pass
        def cleanup(self):
            events.append("source.cleanup")

    class FakeVoice:
        def __init__(self):
            self.disconnect = AsyncMock()
            self.connected = True
        def is_connected(self):
            return self.connected
        def play(self, *_args, **_kwargs):
            raise RuntimeError("voice refused")
        def is_playing(self):
            return False

    async def scenario():
        voice = FakeVoice()
        guild = SimpleNamespace(id=8845, voice_client=None)
        channel = SimpleNamespace(guild=guild, name="Test", connect=AsyncMock(return_value=voice))
        monkeypatch.setattr(ss.discord.opus, "is_loaded", lambda: True)
        monkeypatch.setattr(ss, "StrudelEngine", FakeEngine)
        monkeypatch.setattr(ss, "StrudelAudioSource", FakeSource)
        monkeypatch.setattr(ss, "_cfg", lambda key, default: (
            True if key == "monitor_on_speakers" else
            0.0 if key == "prime_seconds" else default
        ))
        monkeypatch.setattr(ss, "build_for_mood", lambda _genre: SimpleNamespace(code=lambda: "test"))
        monkeypatch.setattr(ss, "monitor_to_speakers", lambda enable=True: events.append("monitor_on" if enable else "monitor_off") or True)
        from utils.audio import records
        from utils.radio import live
        monkeypatch.setattr(records, "get_records", lambda _guild_id: None)
        monkeypatch.setattr(live, "free_voice", AsyncMock())
        monkeypatch.setattr(ss, "settle", lambda *_args: None)
        try:
            await ss.start_session(channel, genre="house", requested_by="tester")
        except RuntimeError as exc:
            assert str(exc) == "voice refused"
        else:
            raise AssertionError("startup error did not propagate")
        assert events.count("monitor_on") == 1
        assert events.count("monitor_off") == 1
        assert 8845 not in ss._sessions

    asyncio.run(scenario())


def test_human_editor_query_is_offloaded_from_the_event_loop():
    import threading
    from types import SimpleNamespace

    session = object.__new__(ss.MusicSession)
    query_threads = []
    session._held = 0
    session.engine = SimpleNamespace(
        human_edited=lambda: query_threads.append(threading.get_ident()) or True
    )

    async def go():
        loop_thread = threading.get_ident()
        held = await session._held_for_human()
        return loop_thread, held

    loop_thread, held = asyncio.run(go())
    assert held is True
    assert len(query_threads) == 1
    assert query_threads[0] != loop_thread



def test_cancelled_monitor_acquire_releases_the_lease_before_startup_exits(monkeypatch):
    import threading

    entered = threading.Event()
    release_acquire = threading.Event()
    monitor_calls = []
    engine_events = []

    class FakeEngine:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            engine_events.append("start")

        def warm_up(self, _code):
            engine_events.append("warm_up")

        def play(self, _code):
            engine_events.append("play")
            return True

        def close(self):
            engine_events.append("close")

    def monitor(enable=True):
        monitor_calls.append(enable)
        if enable:
            entered.set()
            assert release_acquire.wait(timeout=3.0), "test did not release monitor acquisition"
            return True
        return True

    async def scenario():
        guild = SimpleNamespace(id=8846, voice_client=None)
        channel = SimpleNamespace(guild=guild, name="test-channel")
        monkeypatch.setattr(ss.discord.opus, "is_loaded", lambda: True)
        monkeypatch.setattr(ss, "StrudelEngine", FakeEngine)
        monkeypatch.setattr(ss, "monitor_to_speakers", monitor)
        monkeypatch.setattr(
            ss, "_cfg",
            lambda key, default: True if key == "monitor_on_speakers" else default,
        )

        startup = asyncio.create_task(
            ss.start_session(channel, genre="house", requested_by="pytest")
        )
        assert await asyncio.to_thread(entered.wait, 1.0), "monitor acquisition did not start"
        startup.cancel()
        release_acquire.set()
        try:
            await startup
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("startup cancellation was not propagated")

        assert monitor_calls == [True, False]
        assert engine_events == ["start", "warm_up", "close"]
        assert 8846 not in ss._sessions

    asyncio.run(scenario())


def test_next_pass_does_not_push_when_session_closes_during_editor_query():
    import threading
    from unittest.mock import Mock

    entered = threading.Event()
    release_query = threading.Event()
    perf = SimpleNamespace(next_pass=Mock(), passes=0, key="C")

    def human_edited():
        entered.set()
        assert release_query.wait(timeout=3.0), "test did not release editor query"
        return False

    session = object.__new__(ss.MusicSession)
    session._closing = False
    session._held = 0
    session._pass_task = None
    session.engine = SimpleNamespace(human_edited=human_edited)
    session.perf = perf
    session.genre = "house"
    session._push = AsyncMock(return_value=True)

    async def scenario():
        task = asyncio.create_task(session._next_pass_at(0.0))
        session._pass_task = task
        assert await asyncio.to_thread(entered.wait, 1.0), "editor query did not start"
        session._closing = True
        release_query.set()
        await task

    asyncio.run(scenario())
    perf.next_pass.assert_not_called()
    session._push.assert_not_awaited()
    assert session._pass_task is None


def test_stop_cancels_the_scheduled_pass_before_engine_teardown():
    from unittest.mock import Mock
    import time

    events = []
    cancelled = asyncio.Event()

    async def scenario():
        voice = SimpleNamespace(
            guild=SimpleNamespace(id=8847),
            is_playing=lambda: False,
            disconnect=AsyncMock(),
        )

        async def pending_pass():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        pass_task = asyncio.create_task(pending_pass())
        await asyncio.sleep(0)
        session = object.__new__(ss.MusicSession)
        session._closing = False
        session._pass_task = pass_task
        session._task = None
        session.vc = voice
        def stop_engine():
            assert cancelled.is_set(), "scheduled pass was not drained before engine shutdown"
            events.append("engine.stop")

        session.engine = SimpleNamespace(
            stop=stop_engine,
            close=lambda: events.append("engine.close"),
        )
        session.source = SimpleNamespace(cleanup=lambda: events.append("source.cleanup"))
        session._monitor_on_speakers = False
        session.started_at = time.time()
        session.listeners_seen = set()
        session.requested_by = "pytest"
        session.requests = 0
        session._remember = AsyncMock()

        await session.stop()
        assert cancelled.is_set()
        assert pass_task.done()
        assert events == ["engine.stop", "source.cleanup", "engine.close"]
        voice.disconnect.assert_awaited_once_with(force=True)

    asyncio.run(scenario())
