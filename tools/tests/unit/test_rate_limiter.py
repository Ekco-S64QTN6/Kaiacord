"""Per-user rate limiting.

The previous version of this file defined its own copy of `RateLimiter`, with
the comment "Mocking the RateLimiter class from Kaiacord.py ... it's embedded
in Kaiacord.py". That has not been true for a long time — the class lives at
`utils/infrastructure/system/rate_limiter.py` and is importable. Testing a
private copy meant the real limiter could break without a single failure here,
and the file asserted nothing anyway.
"""
import time

import pytest

from utils.infrastructure.system.rate_limiter import RateLimiter


def test_allows_up_to_the_limit():
    rl = RateLimiter(requests_per_minute=3)
    assert [rl.is_allowed(1) for _ in range(3)] == [True, True, True]


def test_blocks_past_the_limit():
    rl = RateLimiter(requests_per_minute=3)
    for _ in range(3):
        rl.is_allowed(1)
    assert rl.is_allowed(1) is False


def test_limits_are_per_user():
    rl = RateLimiter(requests_per_minute=2)
    for _ in range(2):
        rl.is_allowed(1)
    assert rl.is_allowed(1) is False, "user 1 is exhausted"
    assert rl.is_allowed(2) is True, "user 2 has their own budget"


def test_blocked_request_is_not_counted():
    """A rejected request must not extend the window, or a user hammering the
    bot would stay locked out indefinitely rather than for 60 seconds."""
    rl = RateLimiter(requests_per_minute=2)
    for _ in range(2):
        rl.is_allowed(1)
    for _ in range(5):
        rl.is_allowed(1)
    assert len(rl.requests[1]) == 2


def test_window_expires(monkeypatch):
    rl = RateLimiter(requests_per_minute=2)
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    assert rl.is_allowed(1) and rl.is_allowed(1)
    assert rl.is_allowed(1) is False

    monkeypatch.setattr(time, "time", lambda: now + 61)
    assert rl.is_allowed(1) is True, "requests older than 60s must fall out"


@pytest.mark.parametrize("limit", [1, 30])
def test_respects_configured_limit(limit):
    rl = RateLimiter(requests_per_minute=limit)
    assert sum(rl.is_allowed(9) for _ in range(limit + 5)) == limit


def test_cleanup_drops_idle_users(monkeypatch):
    rl = RateLimiter(requests_per_minute=5)
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    rl.is_allowed(1)

    monkeypatch.setattr(time, "time", lambda: now + 3600)
    rl.cleanup()
    assert 1 not in rl.requests or not rl.requests[1]
