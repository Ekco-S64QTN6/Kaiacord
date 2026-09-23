"""When Kaia may post unprompted at all.

The window used to belong to the proactive engine, with its own copy on the
monologue; it is one window for every unprompted post now
(`unprompted.respect_quiet_hours`), read by `unprompted.within_hours` and by
the engine through it.

Whether she should be quiet at 3am is a judgement about a particular server,
so it is a toggle, off by default.
"""
from datetime import datetime
from unittest.mock import patch

import pytest

from utils.core import unprompted
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

    with patch.object(unprompted, "_config", lambda: Fake):
        for h in range(24):
            with patch("utils.core.unprompted.datetime") as dt:
                dt.now.return_value = datetime(2026, 9, 20, h, 0)
                if engine._is_within_hours():
                    allowed.append(h)
    return allowed


def test_quiet_hours_are_off_by_default(engine):
    assert _hours(engine, **{"unprompted.respect_quiet_hours": False}) == list(range(24))


def test_the_default_config_ships_it_off():
    import yaml
    with open("config/default_config.yaml", encoding="utf-8") as f:
        assert yaml.safe_load(f)["unprompted"]["respect_quiet_hours"] is False


def test_enabling_it_restores_the_window(engine):
    allowed = _hours(engine, **{"unprompted.respect_quiet_hours": True,
                                "unprompted.quiet_hour_start": 9,
                                "unprompted.quiet_hour_end": 22})
    assert allowed == list(range(9, 22))


def test_a_window_that_wraps_midnight_works(engine):
    """`start <= hour < end` is False for every hour when start > end — so
    "quiet from 22:00 to 06:00" silenced her around the clock."""
    allowed = _hours(engine, **{"unprompted.respect_quiet_hours": True,
                                "unprompted.quiet_hour_start": 22,
                                "unprompted.quiet_hour_end": 6})
    assert 23 in allowed and 2 in allowed, "the wrapping window blocks its own range"
    assert 12 not in allowed and 18 not in allowed


def test_equal_start_and_end_means_always(engine):
    allowed = _hours(engine, **{"unprompted.respect_quiet_hours": True,
                                "unprompted.quiet_hour_start": 0,
                                "unprompted.quiet_hour_end": 0})
    assert allowed == list(range(24))


def test_the_public_alias_agrees_with_the_private_one(engine):
    with patch("utils.core.unprompted.datetime") as dt:
        dt.now.return_value = datetime(2026, 9, 20, 3, 0)
        assert engine.is_within_hours() == engine._is_within_hours()
