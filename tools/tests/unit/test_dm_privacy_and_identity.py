"""A private turn stays out of the diagnostic logs; her own name is not a member's; nothing she sends pings a crowd."""
import ast
from pathlib import Path

import pytest


import pytest

ROOT = Path(__file__).resolve().parents[3]


def test_private_turn_withholds_text_only_while_active():
    from utils.core import private_turn
    assert private_turn.text("hello") == "hello"
    token = private_turn.enter(True)
    try:
        assert private_turn.text("hello") == private_turn.WITHHELD
        assert private_turn.text("") == ""
    finally:
        private_turn.leave(token)
    assert private_turn.text("hello") == "hello"


@pytest.mark.parametrize("name,is_bot", [("Kaia", True), ("KAIA", True), ("Kaia-Autonomous", True),
                                         ("System", True), ("Nexus", True),
                                         ("Kaiara", False), ("Systemd_fan", False), ("Nexus_Fan", False)])
def test_echo_guard_matches_whole_names(name, is_bot):
    from utils.core.kaia_rag_persistence import _BOT_NAME
    assert bool(_BOT_NAME.match(name)) is is_bot


def test_the_bot_disables_everyone_and_role_mentions():
    tree = ast.parse((ROOT / "Kaiacord.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "Bot":
            kw = {k.arg: k.value for k in node.keywords}
            allowed = kw.get("allowed_mentions")
            assert isinstance(allowed, ast.Call)
            flags = {k.arg: getattr(k.value, "value", None) for k in allowed.keywords}
            assert flags["everyone"] is False and flags["roles"] is False
            return
    pytest.fail("no commands.Bot(...) call found")
