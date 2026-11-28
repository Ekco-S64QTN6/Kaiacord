"""Live-radio resource cleanup when Discord voice teardown fails."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from utils.radio import live
import utils.radio as radio_package


def test_local_radio_lock_and_watchdog_are_cleaned_up_if_disconnect_fails(monkeypatch):
    async def scenario():
        guild_id = 987654321
        device = asyncio.Lock()
        await device.acquire()

        fake_rtl = SimpleNamespace(DEVICE=device)
        monkeypatch.setattr(radio_package, "rtl", fake_rtl, raising=False)
        monkeypatch.setattr(live.kiwi, "close_stream", lambda _proc: True)

        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.is_playing.return_value = False
        vc.disconnect = AsyncMock(side_effect=RuntimeError("gateway unavailable"))
        watchdog = MagicMock()

        live._sessions[guild_id] = live.LiveSession(
            guild_id=guild_id,
            vc=vc,
            proc=object(),
            receiver=None,
            khz=145_000.0,
            mode="fm",
            label="test",
            requested_by="pytest",
            watchdog=watchdog,
            local=True,
        )

        try:
            assert await live.stop(guild_id) is True
            assert not device.locked(), "disconnect failure leaked the SDR device lock"
            watchdog.cancel.assert_called_once()
            vc.disconnect.assert_awaited_once_with(force=True)
        finally:
            live._sessions.pop(guild_id, None)
            if device.locked():
                device.release()

    asyncio.run(scenario())


def _local_session(guild_id):
    vc = MagicMock()
    vc.is_connected.return_value = False
    vc.is_playing.return_value = False
    return live.LiveSession(guild_id=guild_id, vc=vc, proc=object(), receiver=None, khz=145_000.0,
                            mode="fm", label="test", requested_by="pytest", watchdog=MagicMock(), local=True)


def test_a_stream_that_cannot_be_reaped_keeps_the_rtl_sdr_reserved(monkeypatch):
    async def scenario():
        device = asyncio.Lock()
        await device.acquire()
        monkeypatch.setattr(radio_package, "rtl", SimpleNamespace(DEVICE=device), raising=False)
        monkeypatch.setattr(live.kiwi, "close_stream", lambda _proc: False)
        live._sessions[11] = _local_session(11)
        try:
            assert await live.stop(11) is True
            assert device.locked(), "the dongle was released while rtl_fm may still hold it"
        finally:
            live._sessions.pop(11, None)
            if device.locked():
                device.release()

    asyncio.run(scenario())


def test_a_cancelled_stop_releases_the_rtl_sdr_only_after_rtl_fm_is_reaped(monkeypatch):
    """A cancelled to_thread() let the finally release the dongle while the
    worker was still stopping rtl_fm."""
    import threading

    async def scenario():
        device = asyncio.Lock()
        await device.acquire()
        monkeypatch.setattr(radio_package, "rtl", SimpleNamespace(DEVICE=device), raising=False)
        entered, release = threading.Event(), threading.Event()

        def slow_close(_proc):
            entered.set()
            release.wait(5)
            return True

        monkeypatch.setattr(live.kiwi, "close_stream", slow_close)
        live._sessions[12] = _local_session(12)
        task = asyncio.create_task(live.stop(12))
        try:
            await asyncio.to_thread(entered.wait, 5)
            task.cancel()
            await asyncio.sleep(0.05)
            assert device.locked() and not task.done()
            release.set()
            try:
                await task
                raise AssertionError("the cancellation was swallowed")
            except asyncio.CancelledError:
                pass
            assert not device.locked()
        finally:
            release.set()
            live._sessions.pop(12, None)
            if device.locked():
                device.release()

    asyncio.run(scenario())
