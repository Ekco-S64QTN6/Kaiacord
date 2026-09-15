"""Her Discord status has to describe the room, not her mood average.

She sat at `kaia_engagement` 0.874 announcing "people are talking." to a server
where nobody had spoken for hours. Three separate defects produced it.
"""
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

import utils.core.kaia_presence as kp
from utils.core.kaia_presence import KaiaPresenceManager


@pytest.fixture(autouse=True)
def _outside_dream_hours(monkeypatch):
    """Pin the clock to midday for every test in this file.

    `get_mood_activity` returns a sleeping status and exits before the decay
    call and the activity bands whenever the hour is inside the dream window
    (03:00-05:00). Without this the file passes all day and fails for two hours
    every night — which is exactly what it did at 04:12.
    """
    real = datetime

    class _Midday(datetime):
        @classmethod
        def now(cls, tz=None):
            return real(2026, 9, 15, 12, 0, 0)

    monkeypatch.setattr(kp, "datetime", _Midday)


def _manager(engagement, minutes_since_message, coherence=0.85, freshness=0.5):
    state = MagicMock()
    state.kaia_engagement = engagement
    state.kaia_coherence = coherence
    state.kaia_dream_freshness = freshness
    state.last_interaction_time = time.time() - minutes_since_message * 60
    state.update_kaia_state = MagicMock()
    manager = KaiaPresenceManager(bot=MagicMock(), bot_state=state)
    manager._override_text = None
    return manager, state


def _claims_activity(manager, samples=250):
    active = set(kp._ACTIVE_TEXTS)
    return sum(1 for _ in range(samples)
               if manager.get_mood_activity()[1] in active)


def test_she_never_claims_activity_on_a_quiet_server():
    """The reported symptom, with the real numbers from bot_state.json."""
    manager, _ = _manager(engagement=0.874, minutes_since_message=180)
    assert _claims_activity(manager) == 0, \
        'status claimed "people are talking." with nobody talking'


def test_she_still_says_so_when_people_are_actually_talking():
    """The fix must not simply silence the active pool."""
    manager, _ = _manager(engagement=0.874, minutes_since_message=1)
    assert _claims_activity(manager) > 0, "status never reports a busy room"


def test_the_middle_band_does_not_bluff():
    """Moderate engagement drew from `_IDLE_TEXTS + _ACTIVE_TEXTS` combined, so
    a coin flip could claim the room was busy with nothing behind it."""
    manager, _ = _manager(engagement=0.5, minutes_since_message=1)
    assert _claims_activity(manager) == 0


def test_presence_runs_the_engagement_decay_itself():
    """`update_kaia_state` holds the passive-decay block and its only callers
    are in the message path — so nothing recomputed engagement while the server
    was quiet, which is exactly when it needed recomputing."""
    manager, state = _manager(engagement=0.874, minutes_since_message=180)
    manager.get_mood_activity()
    assert state.update_kaia_state.called, "engagement decay never runs while quiet"


def test_last_interaction_time_is_persisted():
    """It lived only in memory, so every restart re-stamped it to boot time,
    `hours_idle` was always ~0, and the decay gate could never open —
    engagement only ever went up."""
    import inspect

    from utils.infrastructure.system import bot_state as bs

    src = inspect.getsource(bs)
    assert "'last_interaction_time': self.last_interaction_time" in src, \
        "last_interaction_time is not written to the saved state"
    assert "state.get('last_interaction_time'" in src, \
        "last_interaction_time is not restored from the saved state"


def test_engagement_actually_decays_over_idle_time():
    """End to end on the real object, not a mock."""
    from utils.infrastructure.system.bot_state import BotState

    state = BotState.__new__(BotState)
    state.kaia_engagement = 0.9
    state.kaia_coherence = 0.85
    state.last_interaction_time = time.time() - 48 * 3600
    state.last_dream_date = None
    state.kaia_dream_freshness = 1.0

    state.update_kaia_state()
    assert state.kaia_engagement < 0.9, "engagement did not decay after 48 idle hours"
