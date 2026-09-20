"""When Kaia is allowed to speak first.

`_is_within_hours` governed the one loop that decides whether she ever
initiates, and its 9-22 default ruled out a third of every day before the
desire gate or the rate limiter were consulted. The log said "declined to
initiate — outside active hours" and nothing else.

Whether she should be quiet at 3am is a judgement about a particular server,
so it is a toggle now, off by default — matching `monologue.respect_quiet_hours`.
"""
from datetime import datetime
from unittest.mock import patch

import pytest

from utils.core.kaia_proactive import ProactiveEngine
from utils.infrastructure.system import yaml_config


@pytest.fixture
def engine():
    return ProactiveEngine.__new__(ProactiveEngine)


def _hours(engine, **cfg):
    """Which of the 24 hours the engine considers speakable."""
    real_get = yaml_config.config.get
    allowed = []

    class Fake:
        @staticmethod
        def get(key, default=None):
            return cfg[key] if key in cfg else real_get(key, default)

    with patch.object(yaml_config, "config", Fake):
        for h in range(24):
            with patch("utils.core.kaia_proactive.datetime") as dt:
                dt.now.return_value = datetime(2026, 9, 20, h, 0)
                if engine._is_within_hours():
                    allowed.append(h)
    return allowed


def test_quiet_hours_are_off_by_default(engine):
    assert _hours(engine) == list(range(24)), (
        "the clock is blocking her again; respect_quiet_hours should default false")


def test_the_default_config_ships_it_off():
    assert yaml_config.config.get("proactive.respect_quiet_hours", None) is False


def test_enabling_it_restores_the_window(engine):
    allowed = _hours(engine, **{"proactive.respect_quiet_hours": True})
    assert allowed == list(range(9, 22))


def test_a_window_that_wraps_midnight_works(engine):
    """The old expression was `start <= hour < end`, which is False for every
    hour when start > end — so "quiet from 22:00 to 06:00" silenced her around
    the clock rather than overnight."""
    allowed = _hours(engine, **{"proactive.respect_quiet_hours": True,
                                "proactive.quiet_hour_start": 22,
                                "proactive.quiet_hour_end": 6})
    assert 23 in allowed and 2 in allowed, "the wrapping window blocks its own range"
    assert 12 not in allowed and 18 not in allowed


def test_equal_start_and_end_means_always(engine):
    allowed = _hours(engine, **{"proactive.respect_quiet_hours": True,
                                "proactive.quiet_hour_start": 0,
                                "proactive.quiet_hour_end": 0})
    assert allowed == list(range(24))


def test_the_public_alias_agrees_with_the_private_one(engine):
    """The observation digest broadcast calls `is_within_hours()`; if the two
    diverge, one channel obeys a window the other ignores."""
    with patch("utils.core.kaia_proactive.datetime") as dt:
        dt.now.return_value = datetime(2026, 9, 20, 3, 0)
        assert engine.is_within_hours() == engine._is_within_hours()
