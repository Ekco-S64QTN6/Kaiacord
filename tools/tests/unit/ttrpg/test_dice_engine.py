"""Deterministic contract tests for the user-facing dice engine."""
import pytest

from utils.ttrpg import dice_engine as dice


def test_roll_accepts_modifiers_at_the_documented_bounds(monkeypatch):
    monkeypatch.setattr(dice.secrets, "randbelow", lambda sides: 0)

    assert dice.roll("1d6+50")[0] == 51
    assert dice.roll("1d6-50")[0] == -49


@pytest.mark.parametrize("notation", ["1d6+51", "1d6-51", "d20+9999", "2d8-9999"])
def test_roll_rejects_extreme_modifiers(notation):
    with pytest.raises(ValueError, match="modifier out of range"):
        dice.roll(notation)


def test_roll_still_rejects_extreme_dice_counts_and_sides():
    for notation in ("0d6", "21d6", "1d1", "1d101"):
        with pytest.raises(ValueError):
            dice.roll(notation)


def test_advantage_and_disadvantage_cancel_to_one_normal_roll(monkeypatch):
    calls = []

    def roll_one(sides):
        calls.append(sides)
        return 6  # d20 raw result 7

    monkeypatch.setattr(dice.secrets, "randbelow", roll_one)

    success, total, breakdown = dice.stat_check(
        10, dc=7, advantage=True, disadvantage=True
    )

    assert success is True
    assert total == 7
    assert calls == [20]
    assert breakdown.startswith("d20 → 7")
