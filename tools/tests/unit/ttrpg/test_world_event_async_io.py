"""World-event reads used by async RPG handlers must stay off the event loop."""

import asyncio
import inspect
import threading

import pytest

from utils.ttrpg import broadcast, rpg_social_handler
from utils.core import background_tasks


@pytest.mark.asyncio
async def test_world_event_reader_uses_a_worker_thread(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "memory" / "ttrpg" / "world_events.json"
    path.parent.mkdir(parents=True)
    path.write_text('["A caravan arrived.", "The Shrine glowed."]', encoding="utf-8")

    loop_thread = threading.get_ident()
    reader_threads = []
    original = broadcast._load_world_events_sync

    def tracked_reader():
        reader_threads.append(threading.get_ident())
        return original()

    monkeypatch.setattr(broadcast, "_load_world_events_sync", tracked_reader)

    events = await broadcast.load_world_events()

    assert events == ["A caravan arrived.", "The Shrine glowed."]
    assert reader_threads
    assert reader_threads[0] != loop_thread


@pytest.mark.asyncio
async def test_world_event_reader_returns_empty_for_missing_or_invalid_log(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert await broadcast.load_world_events() == []

    path = tmp_path / "memory" / "ttrpg" / "world_events.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    assert await broadcast.load_world_events() == []

    path.write_text('{"event": "not an array"}', encoding="utf-8")
    assert await broadcast.load_world_events() == []

    path.write_text('["valid event", 42]', encoding="utf-8")
    assert await broadcast.load_world_events() == []


def test_async_rpg_event_consumers_use_the_shared_async_reader():
    consumers = (
        rpg_social_handler._handle_bard_song,
        rpg_social_handler._handle_talk,
        rpg_social_handler._handle_notices,
        background_tasks.run_bard_performance,
    )
    for consumer in consumers:
        source = inspect.getsource(consumer)
        assert "await load_world_events()" in source
        assert "world_events.json" not in source
        assert "with open(" not in source
