"""!skyking and !numbers: parsing the feeds, the embeds, and failing out loud."""
import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.commands import radio_handler as rh
from utils.radio import eam_watch as ew
from utils.radio import fetch, priyom
from utils.radio.fetch import FeedError

NOW = datetime(2026, 9, 24, 6, 0, tzinfo=timezone.utc)


def _eam(t, sender="CUFF LINK", msg="QHHKALCE5QNTXF63T6HIAJAOXXLLQO", rcv="QHHKAL", typ="ALLSTATIONS", rec=()):
    return {"id": "abc", "type": typ, "sender": sender, "receiver": rcv, "message": msg,
            "time": t, "repeats": 0, "comment_count": 2,
            "recordings": [{"id": "r", "link": u} for u in rec], "automated_recordings": []}


PAGE = {"data": [
    _eam("2026-09-23 19:39:00", msg="ACHAVKIZDDSVBITS2YEAPQQJQZCFGE", rcv="ACHAVK"),
    _eam("2026-09-23 19:52:00"),
    _eam("2026-09-22 05:06:00", sender="MAINSAIL", typ="RADIOCHECK", rcv="",
         msg="THIS IS MAINSAIL WITH A TEST COUNT."),
    _eam("2026-09-04 01:06:00", sender="RED LIME", rcv="", msg="ACN3SQOND65S4Y73VNOXLRGS2HU7T5",
         rec=("https://eamwatch-production.s3.amazonaws.com/recordings/x",)),
], "meta": {"last_page": 2400}}


@pytest.fixture(autouse=True)
def _clean_cache():
    for name in (ew.MESSAGES_CACHE, ew.ARCHIVE_CACHE, priyom.CACHE):
        fetch.cache_path(name).unlink(missing_ok=True)
    yield
    for name in (ew.MESSAGES_CACHE, ew.ARCHIVE_CACHE, priyom.CACHE):
        fetch.cache_path(name).unlink(missing_ok=True)


def test_the_cache_is_redirected_under_pytest():
    assert ".test." in fetch.cache_path("eam_messages").name


def test_messages_sort_newest_first_and_split_the_preamble():
    msgs = [ew.parse(i) for i in PAGE["data"]]
    msgs.sort(key=lambda m: m.time, reverse=True)
    eams = ew.latest_eams(msgs)
    assert [m.time.hour for m in eams] == [19, 19, 1]
    assert eams[0].preamble == "QHHKAL" and eams[0].body == "CE5QNTXF63T6HIAJAOXXLLQO"
    assert eams[2].preamble == ""                      # no receiver: the whole text is the body
    assert [m.label for m in ew.net_traffic(msgs)] == ["radio check"]


def test_the_observation_reports_pattern_not_content():
    msgs = sorted((ew.parse(i) for i in PAGE["data"]), key=lambda m: m.time, reverse=True)
    line = ew.observation(msgs, now=NOW)
    assert line == "2 EAMs this week, all from CUFF LINK inside 13 minutes."
    quiet = ew.observation(msgs, now=NOW + timedelta(days=30))
    assert quiet.startswith("quiet week on the net")


def test_skyking_reads_the_way_it_sounded():
    m = ew.parse(_eam("2019-06-28 07:37:00", sender="MACKINAW", typ="SKYKING", rcv="", msg="DURAN DURAN TIME 37 AUTH DY"))
    assert ew.skyking_broadcast(m) == ("SKYKING, SKYKING, DO NOT ANSWER. DURAN DURAN, "
                                       "TIME 37, AUTHENTICATION DELTA YANKEE.")


def test_a_changed_api_is_an_error_not_an_empty_list():
    with patch.object(ew, "get_json", AsyncMock(return_value={"messages": []})):
        with pytest.raises(FeedError):
            asyncio.run(ew.refresh(3600))
    assert not fetch.cache_path(ew.MESSAGES_CACHE).exists(), "a bad answer must not be cached"


def test_the_feed_is_fetched_once_per_poll_window():
    getter = AsyncMock(return_value=PAGE)
    with patch.object(ew, "get_json", getter):
        asyncio.run(ew.refresh(6 * 3600))
        asyncio.run(ew.refresh(6 * 3600))
    assert getter.await_count == 1


def test_the_archive_is_fetched_a_page_at_a_time_and_kept():
    page = {"data": [_eam("2019-06-28 07:37:00", typ="SKYKING", rcv="", msg="DURAN DURAN TIME 37 AUTH DY")],
            "meta": {"last_page": 1}}
    getter = AsyncMock(return_value=page)
    with patch.object(ew, "get_json", getter):
        a = asyncio.run(ew.classic(random.Random(1)))
        b = asyncio.run(ew.classic(random.Random(2)))
    assert a.text == b.text and getter.await_count == 1


def test_priyom_entries_parse_into_station_frequency_and_link():
    t = priyom.parse({"summary": "E11 13470kHz USB", "start": {"dateTime": "2026-09-24T06:45:00.000Z"}})
    assert (t.station, t.khz, t.mode, t.family) == ("E11", 13470.0, "USB", "“Oracle”")
    assert t.listen_url == "http://websdr.ewi.utwente.nl:8901/?tune=13470usb"
    search = priyom.parse({"summary": "XPA2 Search", "start": {"dateTime": "2026-09-24T06:50:00.000Z"}})
    assert search.khz is None and search.listen_url is None


def test_upcoming_keeps_the_window_and_filters_by_station():
    cache = {"items": [
        {"summary": "E11 13470kHz USB", "start": {"dateTime": "2026-09-24T06:45:00.000Z"}},
        {"summary": "S11a 8597kHz USB", "start": {"dateTime": "2026-09-24T07:00:00.000Z"}},
        {"summary": "E11 8423kHz USB", "start": {"dateTime": "2026-09-24T20:00:00.000Z"}},
    ]}
    assert [t.station for t in priyom.upcoming(cache, 6, now=NOW)] == ["E11", "S11a"]
    assert [t.khz for t in priyom.upcoming(cache, 24, now=NOW, station="e11")] == [13470.0, 8423.0]


def _msg(content):
    m = MagicMock()
    m.content = content
    m.channel.send = AsyncMock()
    return m


def _sent(m):
    return m.channel.send.await_args.kwargs["embed"]


def test_skyking_command_lists_and_drills_down():
    with patch.object(ew, "get_json", AsyncMock(return_value=PAGE)):
        m = _msg("!skyking")
        asyncio.run(rh.handle_skyking_command(None, m))
        embed = _sent(m)
        latest = next(f.value for f in embed.fields if f.name == "Latest")
        assert "QHHKAL CE5QNTXF63T6HIAJAOXXLLQO" in latest and "🔊" in latest
        m = _msg("!skyking 3")
        asyncio.run(rh.handle_skyking_command(None, m))
        detail = _sent(m)
        assert "RED LIME" in detail.title
        assert any(f.name == "Recording" for f in detail.fields)


def test_skyking_says_when_the_feed_fails():
    with patch.object(ew, "get_json", AsyncMock(side_effect=FeedError("https://eam.watch answered HTTP 503"))):
        m = _msg("!skyking")
        asyncio.run(rh.handle_skyking_command(None, m))
    assert "didn't answer" in _sent(m).description


def test_numbers_command_links_each_station():
    items = {"items": [{"summary": "E11 13470kHz USB",
                        "start": {"dateTime": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}}]}
    with patch.object(priyom, "get_json", AsyncMock(return_value=items)):
        m = _msg("!numbers")
        asyncio.run(rh.handle_numbers_command(None, m))
    assert "tune=13470usb" in _sent(m).description


def test_each_box_names_the_other_radio_commands_in_its_footer():
    with patch.object(ew, "get_json", AsyncMock(return_value=PAGE)):
        m = _msg("!skyking")
        asyncio.run(rh.handle_skyking_command(None, m))
    footer = _sent(m).footer.text
    assert "!numbers" in footer and "!skyking classic" in footer
    items = {"items": []}
    with patch.object(priyom, "get_json", AsyncMock(return_value=items)):
        m = _msg("!numbers")
        asyncio.run(rh.handle_numbers_command(None, m))
    assert "!skyking" in _sent(m).footer.text


def test_help_lists_the_radio_commands():
    from utils.commands.registry import COMMANDS
    names = {c.name for c in COMMANDS}
    assert {"skyking", "numbers"} <= names
