"""The sky feeds and commands: parsing, the numbers, failing out loud."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.commands import sky_handler as sh
from utils.radio import fetch
from utils.radio.fetch import FeedError
from utils.sky import feeds, passes

CACHES = ("sky_iss", "sky_astros", "sky_apod", "sky_dsn", "sky_dsn_names", "sky_epic", "sky_swpc",
          "sky_cad", "sky_launches", "sky_quakes")


@pytest.fixture(autouse=True)
def _clean():
    for n in CACHES:
        fetch.cache_path(n).unlink(missing_ok=True)
    yield
    for n in CACHES:
        fetch.cache_path(n).unlink(missing_ok=True)


DSN = """<dsn>
 <station name="gdscc" friendlyName="Goldstone" timeUTC="1"/>
 <dish name="DSS14" activity="Engineering Upgrades"><target name="DSN" id="99" downlegRange="-1" rtlt="-1"/></dish>
 <station name="cdscc" friendlyName="Canberra" timeUTC="1"/>
 <dish name="DSS43">
  <downSignal active="true" dataRate="160" band="X" spacecraft="VGR2"/>
  <target name="VGR2" id="32" downlegRange="21000000000" rtlt="140000"/>
 </dish>
</dsn>"""


def test_dsn_links_name_the_spacecraft_and_the_light_time():
    links = feeds.parse_dsn(DSN, {"vgr2": "Voyager 2"})
    assert len(links) == 1                         # the maintenance dish is not a link
    v = links[0]
    assert (v.name, v.station, v.down_bps) == ("Voyager 2", "Canberra", 160.0)
    assert v.light_time == "19.5 light-hours"


def test_asteroid_numbers_are_computed_not_narrated():
    assert feeds.size_from_h("22.0") == "~141 m"
    assert feeds.size_from_h("28.6") == "~7 m"
    with patch.object(feeds, "get_json", AsyncMock(return_value={
            "fields": ["des", "cd", "dist", "v_rel", "h"],
            "data": [["2026 SA8", "2026-Sep-28 06:45", "0.00253925938809526", "6.6", "28.6"]]})):
        rows = asyncio.run(feeds.close_approaches())
    assert round(rows[0]["ld"], 2) == 0.99       # inside the Moon's distance


def test_starman_is_not_counted_as_crew():
    with patch.object(feeds, "get_json", AsyncMock(return_value={"results": [
            {"name": "Jessica Meir", "agency": {"abbrev": "NASA"}},
            {"name": "Starman", "agency": {"abbrev": "SpX"}}]})):
        crew = asyncio.run(feeds.people_in_space())
    assert crew["people"] == {"NASA": ["Jessica Meir"]} and crew["other"] == ["Starman"]


def test_finished_launches_are_not_upcoming():
    soon = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat().replace("+00:00", "Z")
    gone = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
    with patch.object(feeds, "get_json", AsyncMock(return_value={"results": [
            {"name": "Done", "net": gone, "status": {"abbrev": "Success"}},
            {"name": "Next", "net": soon, "status": {"abbrev": "Go"}, "location": "Vandenberg"}]})):
        rows = asyncio.run(feeds.launches())
    assert [r["name"] for r in rows] == ["Next"]


def test_kp_words():
    assert feeds.kp_words(2.3) == "quiet" and "storm" in feeds.kp_words(5.7)


def test_the_observer_comes_from_config_only():
    with patch.object(passes.config, "get", return_value=None):
        assert passes.observer() is None
    with patch.object(passes.config, "get", return_value="51.5, -0.1"):
        assert (passes.observer().lat, passes.observer().lon) == (51.5, -0.1)
    with patch.object(passes.config, "get", return_value="somewhere"):
        assert passes.observer() is None
    assert passes.phase_name(180) == "full moon" and passes.phase_name(2) == "new moon"


def _msg(content):
    m = MagicMock()
    m.content = content
    m.channel.send = AsyncMock()
    return m


def test_a_failing_source_is_reported_not_hidden():
    with patch.object(feeds, "get_json", AsyncMock(side_effect=FeedError("USGS answered HTTP 503"))):
        m = _msg("!quake")
        asyncio.run(sh.handle_quake_command(None, m))
    embed = m.channel.send.await_args.kwargs["embed"]
    assert "didn't answer" in embed.description and "!nightshift" in embed.footer.text


def test_sky_without_a_location_says_how_to_set_one():
    with patch.object(passes, "observer", return_value=None):
        m = _msg("!sky")
        asyncio.run(sh.handle_sky_command(None, m))
    assert "sky.location" in m.channel.send.await_args.kwargs["embed"].description
