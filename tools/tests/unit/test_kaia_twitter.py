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


def test_x_auth_classifier_recognizes_structured_403_and_cloudflare_challenges():
    class HttpError(Exception):
        def __init__(self, status_code, message):
            super().__init__(message)
            self.status_code = status_code

    assert kx.is_x_auth_or_challenge_error(HttpError(401, "Unauthorized"))
    assert kx.is_x_auth_or_challenge_error(HttpError(403, "Forbidden"))
    assert kx.is_x_auth_or_challenge_error(RuntimeError("Cloudflare challenge page"))
    assert kx.is_x_auth_or_challenge_error(RuntimeError("HTTP 403"))
    assert not kx.is_x_auth_or_challenge_error(RuntimeError("tweet is too long"))


def test_a_403_from_posting_invalidates_the_cached_client_and_cookie_file(monkeypatch, tmp_path):
    cookies = tmp_path / "x_cookies.json"
    cookies.write_text('{"auth_token":"secret","ct0":"csrf"}')
    monkeypatch.setattr(kx, "_cookies_path", cookies)
    client = SimpleNamespace(create_tweet=AsyncMock(side_effect=RuntimeError("403 Forbidden")))
    monkeypatch.setattr(kx, "_client", client)
    monkeypatch.setattr(kx, "get_x_client", AsyncMock(return_value=client))

    ok, _ = asyncio.run(kx.post_to_x("hello"))

    assert not ok
    assert kx._client is None
    assert not cookies.exists()
