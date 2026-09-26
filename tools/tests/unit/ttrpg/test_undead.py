"""Which monsters count as undead for smites and procs."""

def test_a_nickname_does_not_make_a_man_undead():
    from utils.ttrpg.class_advancement import is_undead
    assert not is_undead({"name": 'Felix "Ghost-Hand" Pryce'})
    assert is_undead({"name": "Cairn Wight"}) and is_undead({"name": "The Dracolich"})
