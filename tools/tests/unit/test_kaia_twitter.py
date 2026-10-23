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
    assert not kx.is_x_auth_or_challenge_error(RuntimeError("HTTP 403"))
    assert not kx.is_x_auth_or_challenge_error(RuntimeError("status: 403, message: Cannot find specified user."))
    assert not kx.is_x_auth_or_challenge_error(RuntimeError("tweet is too long"))


def test_a_403_from_posting_invalidates_the_cached_client_and_cookie_file(monkeypatch, tmp_path):
    cookies = tmp_path / "x_cookies.json"
    cookies.write_text('{"auth_token":"secret","ct0":"csrf"}')
    monkeypatch.setattr(kx, "_cookies_path", cookies)
    client = SimpleNamespace(create_tweet=AsyncMock(side_effect=RuntimeError("status: 403, message: Cloudflare challenge page")))
    monkeypatch.setattr(kx, "_client", client)
    monkeypatch.setattr(kx, "get_x_client", AsyncMock(return_value=client))

    ok, _ = asyncio.run(kx.post_to_x("hello"))

    assert not ok
    assert kx._client is None
    assert not cookies.exists()


def test_x_auth_classifier_uses_twikit_exception_names_without_status_code():
    from utils.social.kaia_twitter import is_x_auth_or_challenge_error

    # Twikit errors expose their HTTP meaning via exception class and message;
    # the exception itself does not necessarily expose .status_code.
    Unauthorized = type("Unauthorized", (Exception,), {})
    Forbidden = type("Forbidden", (Exception,), {})
    AccountLocked = type("AccountLocked", (Exception,), {})

    assert is_x_auth_or_challenge_error(Unauthorized("status: 401, message: expired"))
    assert is_x_auth_or_challenge_error(Forbidden("status: 403, message: Cloudflare challenge page"))
    assert not is_x_auth_or_challenge_error(Forbidden("status: 403, message: Cannot find specified user."))
    assert not is_x_auth_or_challenge_error(AccountLocked("account locked"))
    assert is_x_auth_or_challenge_error(RuntimeError("status: 403, message: blocked"))
    assert is_x_auth_or_challenge_error(RuntimeError("HTTP 401 Unauthorized"))
    assert is_x_auth_or_challenge_error(RuntimeError("HTTP 403 Forbidden"))
    assert not is_x_auth_or_challenge_error(RuntimeError("HTTP 403"))
    assert not is_x_auth_or_challenge_error(
        RuntimeError("this post explains what an HTTP 403 response means")
    )
    assert not is_x_auth_or_challenge_error(
        RuntimeError("tweet content includes the digits 403")
    )


def test_account_locked_does_not_delete_cookies_or_invalidate_client(monkeypatch, tmp_path):
    cookies = tmp_path / "x_cookies.json"
    cookies.write_text('{"auth_token":"keep-for-manual-unlock"}')
    monkeypatch.setattr(kx, "_cookies_path", cookies)
    locked = type("AccountLocked", (Exception,), {})
    client = SimpleNamespace(create_tweet=AsyncMock(side_effect=locked("account challenge")))
    monkeypatch.setattr(kx, "_client", client)
    invalidate = AsyncMock()
    monkeypatch.setattr(kx, "invalidate_x_session", invalidate)

    ok, _ = asyncio.run(kx.post_to_x("hello"))

    assert not ok
    assert kx._client is client
    assert cookies.exists()
    invalidate.assert_not_awaited()
