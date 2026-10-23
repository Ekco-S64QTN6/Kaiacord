"""CON growth only grants retroactive HP at modifier boundaries."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.ttrpg.progression import retroactive_hp_gain_for_con_change


@pytest.mark.parametrize(
    "old_con,new_con,level,expected",
    [
        (10, 11, 10, 0),   # score rises, modifier stays 0
        (12, 13, 10, 0),   # score rises, modifier stays +1
        (10, 12, 10, 10),  # modifier rises from 0 to +1
        (11, 12, 10, 10),  # odd-to-even crosses the boundary
        (9, 10, 10, 10),   # modifier rises from -1 to 0
        (10, 14, 10, 20),  # modifier rises from 0 to +2
    ],
)
def test_retroactive_hp_uses_the_change_in_con_modifier(old_con, new_con, level, expected):
    assert retroactive_hp_gain_for_con_change(old_con, new_con, level) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "old_con,gain,expected_hp_gain",
    [
        (12, 1, 0),
        (11, 1, 10),
        (10, 1, 0),
        (10, 2, 10),
    ],
)
async def test_stat_choice_applies_only_the_hp_from_real_con_modifier_growth(
    monkeypatch, old_con, gain, expected_hp_gain
):
    from utils.ttrpg import rpg_views

    sheet = {
        "user_id": "42",
        "level": 10,
        "stats": {"str": 10, "dex": 10, "int": 10, "wis": 10, "con": old_con, "cha": 10},
        "hp": {"current": 50, "max": 100},
        "_stat_choice_pending": True,
    }
    monkeypatch.setattr(rpg_views, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(rpg_views, "save", AsyncMock())
    interaction = SimpleNamespace(
        response=SimpleNamespace(edit_message=AsyncMock())
    )
    view = rpg_views.StatChoiceView(
        ctx=SimpleNamespace(), uid="42", uname="Player", is_owner=False, primary_stat="str"
    )

    await view._apply_choice(interaction, {"con": gain})

    assert sheet["stats"]["con"] == old_con + gain
    assert sheet["hp"]["max"] == 100 + expected_hp_gain
    assert sheet["hp"]["current"] == 50 + expected_hp_gain
