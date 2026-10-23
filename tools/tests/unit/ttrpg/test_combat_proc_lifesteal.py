"""Advanced-class healing must use all damage dealt by a single hit."""
from utils.ttrpg import combat_engine


def test_shadowknight_lifesteal_includes_class_and_weapon_proc_damage(monkeypatch):
    monkeypatch.setattr(combat_engine, "WEAPONS", {
        "test_blade": {
            "attack_bonus": 0,
            "damage_die": 4,
            "damage_bonus": 0,
            "proc": {"name": "Test Edge", "die": 6, "element": "physical"},
        }
    })
    sheet = {
        "user_id": "42",
        "character_name": "Night",
        "class": "Warrior",
        "advanced_class": "Shadowknight",
        "level": 1,
        "stats": {"str": 10, "dex": 10, "con": 10},
        "hp": {"current": 20, "max": 100},
        "equipment": {"weapon": "test_blade", "armor": None},
        "conditions": [],
    }
    monster = {
        "id": "dummy",
        "name": "Training Dummy",
        "hp": {"current": 100, "max": 100},
        "attack": 0,
        "defense": 1,
        "tier": "easy",
    }

    # Player hit roll=10; base weapon damage=1; Shadowknight class proc=1d8
    # rolling 8; weapon proc=1d6 rolling 6; monster then rolls a natural 1.
    rolls = iter([9, 0, 0, 7, 0, 5, 0])
    monkeypatch.setattr(combat_engine.secrets, "randbelow", lambda n: next(rolls))

    result = combat_engine._resolve_combat(sheet, monster)

    # 1 base + 8 class proc + 6 weapon proc = 15 damage.
    # 15% lifesteal gives int(2.25) = 2 HP (minimum 1).
    assert result["player_damage"] == 15
    assert result["monster"]["hp"]["current"] == 85
    assert result["sheet"]["hp"]["current"] == 22
    assert "2 HP" in " ".join(result["exchanges"]) or any(
        "Lifesteal: +2 HP" in line for line in result["exchanges"]
    )
