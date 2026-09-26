"""Only players active in the last 48 hours defend the town. A fallback
drafted every living character whenever fewer than all were active, so
players gone for weeks fought the noon raids; and the sheet's last_updated,
refreshed by the noon event's own save, kept a drafted player 'active' for
as long as there were events."""
import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from utils.ttrpg import character_manager as cm


@pytest.fixture(autouse=True)
def activity_file(tmp_path, monkeypatch):
    path = tmp_path / "last_active.json"
    monkeypatch.setattr(cm, "ACTIVITY_PATH", str(path))
    monkeypatch.setattr(cm, "_activity_stamped", {})
    return path


def _sheet(uid, hours_ago, location="oakhaven", hp=10):
    return {"user_id": uid, "character_name": uid, "location": location, "hp": {"current": hp},
            "last_updated": time.time() - hours_ago * 3600}


def _defenders(sheets):
    with patch.object(cm, "load_all", AsyncMock(return_value=sheets)):
        return [s["character_name"] for s in asyncio.run(cm.get_active_town_defenders())]


def test_only_recently_active_players_defend(activity_file):
    now = time.time()
    activity_file.write_text(json.dumps({"active": now - 7200, "gone": now - 30 * 86400,
                                         "dungeon": now - 3600, "dead": now - 3600}))
    sheets = [_sheet("active", 2), _sheet("gone", 0), _sheet("dungeon", 1, location="whisperwood_deep"),
              _sheet("dead", 1, hp=0)]
    assert _defenders(sheets) == ["active"]      # "gone" was saved just now by an event: not play


def test_nobody_active_means_nobody_is_drafted(activity_file):
    activity_file.write_text(json.dumps({"gone": time.time() - 30 * 86400}))
    assert _defenders([_sheet("gone", 0)]) == []


def test_a_command_or_click_is_what_counts(activity_file):
    activity_file.write_text("{}")
    assert _defenders([_sheet("p", 0)]) == []
    cm.mark_active("p")
    assert _defenders([_sheet("p", 0)]) == ["p"]


def test_the_first_run_seeds_from_the_sheets(activity_file):
    assert not activity_file.exists()
    assert _defenders([_sheet("recent", 3), _sheet("old", 24 * 30)]) == ["recent"]
    assert set(json.loads(activity_file.read_text())) == {"recent", "old"}
