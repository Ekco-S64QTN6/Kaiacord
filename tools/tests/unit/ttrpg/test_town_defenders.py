"""Only players active in the last 48 hours defend the town. A fallback
drafted every living character whenever fewer than all were active, so
players gone for weeks fought the noon raids."""
import asyncio
import time
from unittest.mock import AsyncMock, patch

from utils.ttrpg import character_manager as cm


def _sheet(name, hours_ago, location="oakhaven", hp=10):
    return {"character_name": name, "location": location, "hp": {"current": hp},
            "last_updated": time.time() - hours_ago * 3600}


def test_only_recently_active_players_defend():
    sheets = [_sheet("active", 2), _sheet("gone", 24 * 30), _sheet("dungeon", 1, location="whisperwood_deep"),
              _sheet("dead", 1, hp=0)]
    with patch.object(cm, "load_all", AsyncMock(return_value=sheets)):
        got = asyncio.run(cm.get_active_town_defenders())
    assert [s["character_name"] for s in got] == ["active"]


def test_nobody_active_means_nobody_is_drafted():
    with patch.object(cm, "load_all", AsyncMock(return_value=[_sheet("gone", 24 * 30)])):
        assert asyncio.run(cm.get_active_town_defenders()) == []
