"""!rpg attack picks your own fight before someone else's."""
from utils.ttrpg.rpg_combat_handler import pick_target

M = [{"id": "a-goblin", "key": "goblin", "aggro_uid": "A"}, {"id": "b-goblin", "key": "goblin", "aggro_uid": "B"},
     {"id": "b-wolf", "key": "dire_wolf", "aggro_uid": "B"}]


def _id(uid, name):
    got = pick_target(M, uid, name)
    return got[1]["id"] if got else None


def test_naming_a_monster_prefers_your_own():
    assert _id("B", "goblin") == "b-goblin"


def test_no_name_is_your_own_fight():
    assert _id("B", "") == "b-goblin"


def test_you_can_still_help_with_someone_elses():
    assert _id("C", "goblin") == "a-goblin"
    assert _id("B", "dire") == "b-wolf"
    assert _id("C", "") is None
