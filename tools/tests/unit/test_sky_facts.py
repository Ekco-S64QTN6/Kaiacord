"""Asked "space weather?", she described a G3 storm while NOAA said Kp 4.
A turn that names a sky topic now carries the feeds' real numbers."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from utils.core import sky_facts


@pytest.mark.parametrize("words,expected", [
    ("Kaia space weather and what's on the alien radio?", ["space_weather"]),
    ("can I see the aurora tonight", ["space_weather"]),
    ("how many people are in space right now", ["iss"]),
    ("any launches this week", ["launches"]),
    ("was there an earthquake", ["quakes"]),
    ("what do you think of rhubarb by aphex twin", []),
    ("the kpi dashboard is broken", []),
])
def test_topics_come_from_the_speakers_words(words, expected):
    assert sky_facts.topics(words) == expected


def test_the_note_carries_the_real_reading():
    data = {"kp": 4.0, "flare": {"max_class": "B7.9", "max_time": "2026-09-25T11:26:00Z"},
            "xray": "B4.0", "solar_flux": "112", "sunspots": "125"}
    with patch("utils.sky.feeds.space_weather", AsyncMock(return_value=data)), \
         patch("utils.radio.fetch.read_cache", return_value={"data": data, "fetched_at": 0}):
        note = asyncio.run(sky_facts.note_for("space weather?"))
    assert "Kp 4.0" in note and "B7.9" in note and "do not add storms" in note


def test_no_feed_no_note():
    with patch("utils.sky.feeds.space_weather", AsyncMock(side_effect=RuntimeError)), \
         patch("utils.radio.fetch.read_cache", return_value={}):
        assert asyncio.run(sky_facts.note_for("space weather?")) == ""
    assert asyncio.run(sky_facts.note_for("hello there")) == ""
