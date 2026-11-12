"""Records startup must release resources if Discord refuses playback."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from utils.audio import records as R
from utils.audio import setlist, strudel_session
from utils.radio import live


def test_failed_voice_play_cleans_pcm_mixer_deck_and_connection(monkeypatch):
    guild_id = 987654321
    guild = SimpleNamespace(id=guild_id, voice_client=None)
    channel = MagicMock()
    channel.guild = guild
    channel.name = "Test room"

    vc = MagicMock()
    vc.guild = guild
    vc.channel = channel
    vc.is_connected.return_value = True
    vc.is_playing.return_value = False
    vc.play.side_effect = RuntimeError("voice player failed to start")
    vc.disconnect = AsyncMock()
    channel.connect = AsyncMock(return_value=vc)

    record = R.library.Record(
        path="/music/fake-startup.mp3", artist="Test", title="Startup",
        bpm=120, key="8A", genre="House",
    )

    class FakeDeck:
        def __init__(self, *args, **kwargs):
            self.record = record
            self.grid = None
            self.closed = 0

        def close(self):
            self.closed += 1

    class FakeMixer:
        def __init__(self, deck, *args, **kwargs):
            self.current = deck
            self.cleaned = 0

        def cleanup(self):
            self.cleaned += 1
            self.current.close()

    class FakePCM:
        def __init__(self, renderer, **kwargs):
            self.renderer = renderer
            self.buffer_frames = 15
            self.cleaned = 0

        def wait_ready(self, *_args):
            return True

        def cleanup(self):
            self.cleaned += 1

    deck_holder = {}
    mixer_holder = {}
    pcm_holder = {}

    def make_deck(*args, **kwargs):
        deck = FakeDeck(*args, **kwargs)
        deck_holder["value"] = deck
        return deck

    def make_mixer(*args, **kwargs):
        mixer = FakeMixer(*args, **kwargs)
        mixer_holder["value"] = mixer
        return mixer

    def make_pcm(*args, **kwargs):
        pcm = FakePCM(*args, **kwargs)
        pcm_holder["value"] = pcm
        return pcm

    monkeypatch.setattr(R, "probe_seconds", lambda _path: 60.0)
    monkeypatch.setattr(R, "gain_db", lambda _path: 0.0)
    monkeypatch.setattr(R, "Deck", make_deck)
    monkeypatch.setattr(R, "CrossfadeSource", make_mixer)
    monkeypatch.setattr(R, "BufferedRecordsSource", make_pcm)
    monkeypatch.setattr(R, "settle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(R.discord.opus, "is_loaded", lambda: True)
    monkeypatch.setattr(strudel_session, "get_session", lambda _guild_id: None)
    monkeypatch.setattr(live, "free_voice", AsyncMock())
    monkeypatch.setattr(setlist, "load", lambda: {"version": setlist.VERSION})
    monkeypatch.setattr(setlist, "needs_build", lambda *_args: False)

    from utils.audio import beatgrid
    monkeypatch.setattr(beatgrid, "ensure_ticks", lambda *_args: None)
    monkeypatch.setattr(beatgrid, "grid_for", lambda *_args: None)

    import utils.infrastructure.system.yaml_config as yaml_config
    monkeypatch.setattr(yaml_config, "config", SimpleNamespace(get=lambda _key, default=None: default))

    R._sessions.pop(guild_id, None)
    try:
        with pytest.raises(RuntimeError, match="voice player failed to start"):
            asyncio.run(R.start_records(channel, [record], record, requested_by="tester"))

        assert pcm_holder["value"].cleaned == 1
        assert mixer_holder["value"].cleaned == 1
        assert deck_holder["value"].closed == 1
        vc.disconnect.assert_awaited_once_with(force=True)
        assert guild_id not in R._sessions
    finally:
        R._sessions.pop(guild_id, None)


def test_a_second_start_while_one_is_starting_is_refused(monkeypatch):
    """Two overlapping starts share one voice client; the one that failed
    would tear it down under the one that played."""
    gate = asyncio.Event()

    async def slow_start(*args, **kwargs):
        await gate.wait()
        return "session"

    monkeypatch.setattr(R, "_start_records", slow_start)
    channel = SimpleNamespace(guild=SimpleNamespace(id=55))

    async def run():
        first = asyncio.create_task(R.start_records(channel, [], None, requested_by="a"))
        await asyncio.sleep(0)
        with pytest.raises(R.AlreadyStarting):
            await R.start_records(channel, [], None, requested_by="b")
        gate.set()
        assert await first == "session"
        assert 55 not in R._starting               # released for the next start

    asyncio.run(run())


def _records_command_fixture(monkeypatch, start_records):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from utils.audio import library, setlist
    from utils.commands import music_handler as handler

    crate = [
        R.library.Record("/music/one.mp3", "Artist", "One", 124, "8A", "House"),
        R.library.Record("/music/two.mp3", "Artist", "Two", 124, "8A", "House"),
        R.library.Record("/music/three.mp3", "Artist", "Three", 124, "8A", "House"),
        R.library.Record("/music/four.mp3", "Artist", "Four", 124, "8A", "House"),
    ]
    graph = {"sets": [[r.path for r in crate]]}
    chosen = graph["sets"][0]
    calls = []

    monkeypatch.setattr(handler, "config", SimpleNamespace(get=lambda _k, default=None: default))
    monkeypatch.setattr(library, "load", lambda _path: crate)
    monkeypatch.setattr(setlist, "load", lambda: graph)
    monkeypatch.setattr(setlist, "peek_next_set", lambda _g, _crate: chosen)
    monkeypatch.setattr(setlist, "advance_rotation", lambda _g, _crate: calls.append("advance") or True)

    async def start(*_args, **kwargs):
        calls.append("start")
        return await start_records(kwargs)

    monkeypatch.setattr(R, "start_records", start)

    class Typing:
        async def __aenter__(self):
            return None
        async def __aexit__(self, *_args):
            return False

    channel = SimpleNamespace(
        guild=SimpleNamespace(me=object()),
        name="test voice",
        permissions_for=lambda _me: SimpleNamespace(connect=True, speak=True),
    )
    msg = SimpleNamespace(
        author=SimpleNamespace(
            voice=SimpleNamespace(channel=channel),
            display_name="tester",
        ),
        guild=channel.guild,
        channel=SimpleNamespace(typing=lambda: Typing(), send=AsyncMock()),
    )
    return handler, msg, calls, chosen


def test_failed_records_voice_start_does_not_consume_the_set_rotation(monkeypatch):
    from utils.commands import music_handler

    async def fail(_kwargs):
        raise RuntimeError("voice player failed")

    handler, msg, calls, chosen = _records_command_fixture(monkeypatch, fail)
    asyncio.run(handler._records(msg, ""))

    assert calls == ["start"]
    assert msg.channel.send.await_count == 1


def test_successful_records_start_commits_rotation_after_session_start(monkeypatch):
    async def succeed(_kwargs):
        return object()

    handler, msg, calls, chosen = _records_command_fixture(monkeypatch, succeed)
    asyncio.run(handler._records(msg, ""))

    assert calls == ["start", "advance"]
    msg.channel.send.assert_awaited_once()
