"""Pooled gil reinforces the walls for a week: +2 defence in noon raids."""
from utils.ttrpg import town_projects as tp

NOW = 1_800_000_000.0


def test_donations_pool_and_reinforce_at_the_cost():
    w = {}
    a, b = {"character_name": "Jimjam", "gil": 200_000}, {"character_name": "Ekco", "gil": 100_000}
    assert tp.donate(a, w, 150_000, NOW)[0] and tp.raid_def_bonus(w, NOW) == 0
    ok, text = tp.donate(b, w, 100_000, NOW)
    assert ok and "reinforced" in text
    assert w["town_fund"] == 0 and tp.raid_def_bonus(w, NOW + 86400) == tp.RAID_DEF_BONUS
    assert tp.raid_def_bonus(w, NOW + 8 * 86400) == 0
    assert a["gil"] == 50_000 and w["town_donors"] == {"Jimjam": 150_000, "Ekco": 100_000}


def test_a_second_project_extends_the_week_rather_than_resetting_it():
    w = {"fortified_until": NOW + 3 * 86400}
    tp.donate({"character_name": "x", "gil": 10**6}, w, tp.PROJECT_COST, NOW)
    assert w["fortified_until"] == NOW + 10 * 86400


def test_nothing_moves_without_the_gil():
    w, s = {}, {"character_name": "x", "gil": 10}
    assert not tp.donate(s, w, 100, NOW)[0] and s["gil"] == 10 and not w.get("town_fund")
    assert not tp.donate(s, w, 0, NOW)[0]
