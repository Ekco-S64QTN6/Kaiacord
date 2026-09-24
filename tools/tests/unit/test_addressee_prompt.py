"""The prompt must never tell Kaia that the person she is talking to is someone else.

The addressee rule once listed server members by name as people *not* to treat
as the current speaker. When one of them spoke, the prompt said "you are talking
to GuardNGnowm" and "do not address GuardNGnowm as the current speaker" at once,
and she called him Ekco.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MEMBERS = ("Tenno Henka", "Starkind", "Jimjam", "Lune", "Cecily", "Toxigen", "GuardNGnowm", "Ekco")


def test_no_prompt_rule_hard_codes_a_member_as_not_the_speaker():
    tree = ast.parse((ROOT / "utils/core/message_processor.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "ADDRESSEE" in node.value:
            rule = next(l for l in node.value.splitlines() if "ADDRESSEE" in l)
            named = [m for m in MEMBERS if m in rule]
            assert not named, f"addressee rule names {named}; one of them may be the speaker"
