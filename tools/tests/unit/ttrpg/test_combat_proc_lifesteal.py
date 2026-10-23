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


def test_paladin_kill_heal_runs_once_after_the_monster_is_defeated(monkeypatch):
    sheet = {
        "user_id": "42",
        "character_name": "Oathkeeper",
        "class": "Warrior",
        "advanced_class": "Paladin",
        "level": 1,
        "stats": {"str": 10, "dex": 10, "con": 10},
        "hp": {"current": 10, "max": 20},
        "equipment": {"weapon": None, "armor": None},
        "conditions": [],
    }
    monster = {
        "id": "skeleton",
        "name": "Skeleton",
        "hp": {"current": 3, "max": 3},
        "attack": 0,
        "defense": 1,
        "tier": "easy",
    }

    # Hit (10), weapon damage (1), and fail the class proc chance (99).
    rolls = iter([9, 0, 99])
    monkeypatch.setattr(combat_engine.secrets, "randbelow", lambda n: next(rolls))

    result = combat_engine._resolve_combat(sheet, monster)

    assert result["monster_defeated"] is True
    assert result["player_damage"] == 3  # 1 base + 2 Paladin smite
    assert result["sheet"]["hp"]["current"] == 13  # one +3 heal-on-kill
    log = "\n".join(result["exchanges"])
    assert log.count("Paladin's smite") == 1
    assert log.count("Holy kill restores 3 HP") == 1


def test_advanced_class_effects_are_not_reapplied_by_the_overworld_handler():
    from pathlib import Path

    source = Path("utils/ttrpg/rpg_combat_handler.py").read_text(encoding="utf-8")
    block = source[source.index("# Combat and kill-specific advanced-class effects"):]
    assert "apply_advanced_class_to_combat(" not in block
