"""`!rpg help` lists every subcommand `!rpg` dispatches. It had drifted to about
half: class advancement, unequip, the bank, quests, the blockade, the pond and
all of housing were reachable only by knowing them."""
import re
from pathlib import Path

from utils.ttrpg.rpg_reference_handler import RPG_HELP_FIELDS, RPG_HELP_OWNER, rpg_help_embed

OWNER_ONLY = {"give", "heal", "event", "bestiary", "xp"}


def _table():
    src = Path("utils/commands/rpg_handler.py").read_text(encoding="utf-8")
    return dict(re.findall(r'"([a-z_]+)":\s+([A-Za-z_.]+),', src))


def test_rpg_help_lists_every_subcommand():
    table = _table()
    public = " ".join(v for _, v in RPG_HELP_FIELDS)
    owner = RPG_HELP_OWNER[1]
    for sub, handler in table.items():
        if sub in ("status_board", "help"):
            continue
        listed = re.search(rf"`(?:!rpg )?{sub}\b", public if sub not in OWNER_ONLY else owner)
        assert listed, f"!rpg {sub} is dispatched but not in !rpg help"


def test_owner_commands_are_shown_to_owners_only():
    assert "bestiary" not in "".join(f.value for f in rpg_help_embed(False).fields)
    assert "bestiary" in "".join(f.value for f in rpg_help_embed(True).fields)


def test_the_card_fits_discord():
    e = rpg_help_embed(True)
    assert len(e.fields) <= 25 and all(len(f.value) <= 1024 for f in e.fields)
    assert len(e.title) + len(e.description) + sum(len(f.name) + len(f.value) for f in e.fields) + len(e.footer.text) <= 6000
