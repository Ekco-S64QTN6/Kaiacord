"""The X client cache: a failed session must not be handed to the next caller."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import utils.social.kaia_twitter as kx


def test_a_failed_login_leaves_no_client_behind(monkeypatch, tmp_path):
    """One failed login used to end X posting until a restart: the client
    that never logged in stayed cached and was returned to every caller."""
    monkeypatch.setattr(kx, "is_x_configured", lambda: True)
    monkeypatch.setattr(kx, "_cookies_path", tmp_path / "x_cookies.json")
    monkeypatch.setattr(kx, "_client", None)
    fake = MagicMock()
    fake.login = AsyncMock(side_effect=RuntimeError("bad password"))
    monkeypatch.setattr(kx, "Client", lambda *a: fake)
    assert asyncio.run(kx.get_x_client()) is None
    assert kx._client is None


def test_an_auth_error_drops_the_cached_session(monkeypatch, tmp_path):
    cookies = tmp_path / "x_cookies.json"
    cookies.write_text("{}")
    monkeypatch.setattr(kx, "_cookies_path", cookies)
    dead = SimpleNamespace(create_tweet=AsyncMock(side_effect=RuntimeError("401 Unauthorized")))
    monkeypatch.setattr(kx, "_client", dead)
    monkeypatch.setattr(kx, "get_x_client", AsyncMock(return_value=dead))
    ok, _ = asyncio.run(kx.post_to_x("hello"))
    assert not ok and kx._client is None and not cookies.exists()
