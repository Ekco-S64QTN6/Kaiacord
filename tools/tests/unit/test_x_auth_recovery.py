"""X API authorization/challenge failures get one fresh-session retry."""
import asyncio
from unittest.mock import AsyncMock

from utils.social import kaia_twitter as twitter
from utils.social import social_twitter_polling as polling


class FakeBreaker:
    def __init__(self):
        self.successes = 0
        self.failures = 0
        self.half_open_failures = 0

    def can_proceed(self):
        return True

    def record_success(self):
        self.successes += 1

    def record_failure(self):
        self.failures += 1
        self.half_open_failures += 1


def test_403_during_mentions_fetch_retries_with_a_fresh_client(monkeypatch):
    old_client = type("OldClient", (), {})()
    old_client.get_notifications = AsyncMock(side_effect=RuntimeError("403 Forbidden"))
    new_client = type("NewClient", (), {})()
    new_client.get_notifications = AsyncMock(return_value=[])

    calls = []

    async def get_client(force_new=False):
        calls.append(force_new)
        return new_client if force_new else old_client

    monkeypatch.setattr(twitter, "get_x_client", get_client)
    monkeypatch.setattr(twitter, "is_x_configured", lambda: True)
    breaker = FakeBreaker()
    monkeypatch.setattr(polling, "_x_breaker", breaker)

    mentions = asyncio.run(polling._get_x_mentions(set()))

    assert mentions == []
    assert calls == [False, True]
    assert breaker.successes == 1
    assert breaker.failures == 0


def test_cloudflare_failure_during_reply_retries_once(monkeypatch):
    old_client = type("OldClient", (), {})()
    old_client.create_tweet = AsyncMock(side_effect=RuntimeError("Cloudflare challenge page"))
    new_client = type("NewClient", (), {})()
    new_client.create_tweet = AsyncMock(return_value=object())

    calls = []

    async def get_client(force_new=False):
        calls.append(force_new)
        return new_client if force_new else old_client

    monkeypatch.setattr(twitter, "get_x_client", get_client)

    result = asyncio.run(polling._reply_to_x({"tweet_id": "123"}, "hello"))

    assert result is True
    assert calls == [False, True]
    old_client.create_tweet.assert_awaited_once()
    new_client.create_tweet.assert_awaited_once()


def test_a_missing_client_is_a_failure_not_a_successful_empty_poll(monkeypatch):
    async def no_client(force_new=False):
        return None

    monkeypatch.setattr(twitter, "get_x_client", no_client)
    monkeypatch.setattr(twitter, "is_x_configured", lambda: True)
    breaker = FakeBreaker()
    monkeypatch.setattr(polling, "_x_breaker", breaker)

    assert asyncio.run(polling._get_x_mentions(set())) == []
    assert breaker.successes == 0
    assert breaker.failures == 1


def test_two_failed_half_open_auth_probes_clear_the_x_session(monkeypatch):
    client = type("Client", (), {})()
    client.get_notifications = AsyncMock(side_effect=RuntimeError("403 Forbidden"))
    calls = []

    async def get_client(force_new=False):
        calls.append(force_new)
        return client

    monkeypatch.setattr(twitter, "get_x_client", get_client)
    monkeypatch.setattr(twitter, "is_x_configured", lambda: True)
    invalidate = AsyncMock()
    monkeypatch.setattr(twitter, "invalidate_x_session", invalidate)
    breaker = FakeBreaker()
    breaker.half_open_failures = 1  # one failed half-open probe already occurred
    monkeypatch.setattr(polling, "_x_breaker", breaker)

    assert asyncio.run(polling._get_x_mentions(set())) == []
    assert calls == [False, True]
    assert breaker.failures == 1
    invalidate.assert_awaited_once_with("repeated half-open authentication/challenge failures")
