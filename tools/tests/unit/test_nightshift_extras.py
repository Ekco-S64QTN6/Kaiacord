"""!beacons and the overnight log."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import numpy as np
import pytest

from utils.radio import beacons, overnight


def test_the_beacon_schedule_is_arithmetic():
    t0 = datetime(2026, 9, 24, 0, 0, 0, tzinfo=timezone.utc)          # a cycle boundary
    assert beacons.BEACONS[beacons.on_air(t0, 0)][0] == "4U1UN"        # 14.100 opens with 4U1UN
    assert beacons.BEACONS[beacons.on_air(t0 + timedelta(seconds=10), 1)][0] == "4U1UN"   # 18.110 one slot later
    assert beacons.BEACONS[beacons.on_air(t0 + timedelta(seconds=175), 0)][0] == "YV5B"   # last of 18
    assert len(beacons.now_on_air(t0)) == 5


def test_a_strong_slot_is_heard_and_quiet_ones_are_not():
    """Readings are the receiver's S-meter (dBm), ~6 a second, whole-second stamps."""
    start = datetime(2026, 9, 24, 0, 0, 0, tzinfo=timezone.utc)
    rng = np.random.default_rng(0)
    readings = []
    for sec in range(beacons.CYCLE_S):
        slot = sec // 10
        base = -120.0 + (18.0 if slot in (0, 4) else 0.0)      # 4U1UN and ZL6B come through
        for _ in range(6):
            readings.append((start + timedelta(seconds=sec), base + rng.normal(0, 1.5)))
    heard = {h.call for h in beacons.judge(beacons.slot_levels(readings)) if h.heard}
    assert heard == {"4U1UN", "ZL6B"}


def test_a_short_recording_is_an_error_not_a_verdict():
    from utils.radio.fetch import FeedError
    with pytest.raises(FeedError):
        beacons.judge({0: 1.0, 1: 1.0})


def test_the_overnight_log_may_not_invent_numbers():
    facts = ["asteroid 2026 SC will pass Earth at 1.7 lunar distances (25 Sep 13:47 UTC)"]
    assert overnight.invented_numbers("2026 sc will pass at 1.7 lunar distances, 13:47 utc", facts) == set()
    assert overnight.invented_numbers("it passed at 3.2 lunar distances", facts) == {"3.2"}


def test_the_overnight_log_is_due_once_a_morning():
    from utils.radio import fetch
    fetch.cache_path(overnight.STATE).unlink(missing_ok=True)
    morning = datetime(2026, 9, 24, 8, 45)
    assert overnight.due(morning, "08:30")
    assert not overnight.due(datetime(2026, 9, 24, 7, 0), "08:30")
    fetch.write_cache(overnight.STATE, {"last_posted": morning.timestamp()})
    assert not overnight.due(morning + timedelta(minutes=30), "08:30")
    fetch.cache_path(overnight.STATE).unlink(missing_ok=True)


def test_overnight_is_an_unprompted_source_with_its_own_label():
    from utils.core import unprompted
    assert "overnight" in unprompted.SOURCES
    assert unprompted.KIND_LABELS["overnight"] == ["overnight_log"]
    with patch.object(unprompted, "_config", return_value={}):
        assert unprompted.cross_posts("overnight") is False     # never public unless asked
