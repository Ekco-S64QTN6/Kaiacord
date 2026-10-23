"""Stat-growth HP only changes when a CON modifier changes."""
from utils.ttrpg.progression import retroactive_con_hp_gain


def test_plus_one_con_from_even_score_does_not_grant_retroactive_hp():
    # CON 10 -> 11 leaves the modifier at +0.
    assert retroactive_con_hp_gain(current_con=10, con_gain=1, level=12) == 0


def test_plus_one_con_from_odd_score_grants_hp_per_level():
    # CON 11 -> 12 changes the modifier from +0 to +1.
    assert retroactive_con_hp_gain(current_con=11, con_gain=1, level=12) == 12


def test_plus_two_con_grants_hp_when_it_raises_the_modifier_once():
    assert retroactive_con_hp_gain(current_con=10, con_gain=2, level=12) == 12
    assert retroactive_con_hp_gain(current_con=12, con_gain=2, level=12) == 12


def test_con_change_that_does_not_increase_the_modifier_never_removes_hp():
    assert retroactive_con_hp_gain(current_con=11, con_gain=0, level=12) == 0
    assert retroactive_con_hp_gain(current_con=13, con_gain=-1, level=12) == 0
