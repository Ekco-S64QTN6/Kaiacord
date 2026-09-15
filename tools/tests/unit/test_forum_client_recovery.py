"""A failed forum login must not disable the forum until restart.

`get_forum_client` assigned the module-level `_client` *before* attempting to
log in, and discarded the boolean `login()` returns. So one transient failure —
the forum down for a minute, a network blip — left an unauthenticated client
cached for the lifetime of the process. Every later call saw
`_client is not None` and handed it back without retrying, so posting and
scraping stayed dead, with a single stale log_error far up the log as the only
clue that anything had happened.
"""
import asyncio
from unittest.mock import patch

import pytest

import utils.social.kaia_forum as kf


@pytest.fixture(autouse=True)
def _clear_client():
    kf._client = None
    yield
    kf._client = None


def _run(login_results):
    attempts = {"n": 0}

    class _Fake:
        def __init__(self, **kwargs):
            pass

        async def login(self):
            i = attempts["n"]
            attempts["n"] += 1
            return login_results[min(i, len(login_results) - 1)]

        async def close(self):
            pass

    async def go():
        got = []
        with patch.object(kf, "ForumClient", _Fake), \
             patch.object(kf, "is_forum_configured", lambda: True):
            for _ in range(len(login_results)):
                got.append(await kf.get_forum_client())
        return got, attempts["n"]

    return asyncio.run(go())


def test_a_failed_login_returns_nothing():
    got, _ = _run([False])
    assert got[0] is None, "an unauthenticated client was handed to a caller"


def test_a_failed_login_is_not_cached():
    """The whole point: the next call must try again."""
    got, attempts = _run([False, False, True])
    assert attempts == 3, f"login was retried only {attempts} time(s)"
    assert got[-1] is not None, "never recovered after a transient failure"


def test_a_successful_login_is_cached():
    """It must still avoid logging in on every single call."""
    got, attempts = _run([True, True, True])
    assert attempts == 1, f"logged in {attempts} times instead of caching"
    assert all(c is not None for c in got)
