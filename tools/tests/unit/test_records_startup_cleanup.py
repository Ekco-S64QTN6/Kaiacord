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
