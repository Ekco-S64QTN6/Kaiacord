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
        monkeypatch.setattr(live.kiwi, "close_stream", lambda _proc: None)

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
