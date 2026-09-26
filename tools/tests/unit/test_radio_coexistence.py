"""The radio features share one voice connection, one speech model and one
dongle. Each hands over cleanly instead of colliding."""
import asyncio
import threading
import time
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

from utils.radio import live, scanner, transcribe


def test_model_release_never_waits_on_a_running_transcription():
    """It runs on the event loop; waiting froze the bot for a whole transcription."""
    transcribe._lock.acquire()
    try:
        t = time.time()
        transcribe.release_if_idle()
        assert time.time() - t < 0.5
    finally:
        transcribe._lock.release()


def test_free_voice_ends_a_listen_along_without_hanging_up(monkeypatch):
    vc = MagicMock()
    vc.is_playing.return_value = True
    vc.is_connected.return_value = True
    scanner._along[7] = {"vc": vc, "text": None, "loop": None, "started": time.time()}
    try:
        asyncio.run(live.free_voice(NS(id=7, voice_client=vc)))
        assert 7 not in scanner._along
        vc.stop.assert_called()
        vc.disconnect.assert_not_called()
    finally:
        scanner._along.clear()


def test_off_air_stops_listen_along_too():
    from utils.commands.radio_handler import _off_air
    vc = MagicMock()
    vc.is_playing.return_value = False
    vc.is_connected.return_value = True
    vc.disconnect = AsyncMock()
    scanner._along[8] = {"vc": vc, "text": None, "loop": None, "started": time.time()}
    assert asyncio.run(_off_air(8)) is True and 8 not in scanner._along


def test_a_failed_watch_backs_off(monkeypatch):
    monkeypatch.setattr(scanner.rtl, "available", lambda: True)
    monkeypatch.setattr(scanner, "within_hours", lambda now=None: True)
    monkeypatch.setattr(scanner, "_failed_at", time.time())
    assert scanner.tick() is False


def test_shutdown_stops_the_watcher():
    stop = threading.Event()
    scanner._stop_event = stop
    try:
        asyncio.run(scanner.shutdown())
        assert stop.is_set()
    finally:
        scanner._stop_event = None
