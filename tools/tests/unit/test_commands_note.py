"""She says what her commands are from the registry, only when a turn asks."""
import pytest

from utils.commands.registry import COMMANDS
from utils.core.commands_note import note_for


def test_the_reported_question_gets_the_public_list():
    note = note_for("Can you tell me about the kaiacord !help function list kaia")
    public = [c for c in COMMANDS if not c.owner_only]
    assert all(c.summary in note for c in public)
    assert not any(c.summary in note for c in COMMANDS if c.owner_only)
    assert "not internal tools" in note


def test_one_named_command_gets_its_own_line():
    note = note_for("Do you know whether we are meant to add custom text to !rpg talk [npc name]?")
    rpg = next(c for c in COMMANDS if c.name == "rpg")
    assert rpg.summary in note
    assert note.count("\n- ") == 1


def test_an_alias_finds_its_command():
    cmd = next(c for c in COMMANDS if c.aliases)
    assert cmd.summary in note_for(f"what does !{cmd.aliases[0]} do exactly")


@pytest.mark.parametrize("said", [
    "that was a good set last night",
    "!help",                                 # a command being run
    "i just yelled !wow at my screen",       # not a command of hers
    "he gave the commands and they left",
    "",
])
def test_nothing_else_carries_it(said):
    assert note_for(said) == ""


def test_asking_what_she_can_do_gets_the_list():
    assert "!help" in note_for("kaia what commands do you have?")
    assert "!help" in note_for("what can you do")
