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
    rules = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "ADDRESSEE" in node.value:
            rules += 1
            rule = next(l for l in node.value.splitlines() if "ADDRESSEE" in l)
            named = [m for m in MEMBERS if m in rule]
            assert not named, f"addressee rule names {named}; one of them may be the speaker"
    # Otherwise a renamed or moved rule passes this by checking nothing.
    assert rules, "no ADDRESSEE rule found in message_processor.py"


def test_the_reply_context_does_not_tell_her_to_use_the_name():
    """"Address <author> by name" contradicted the persona's no-name-opener
    rule; she satisfied it by opening on the name or repeating it through the
    reply (ten times in six turns to one person)."""
    src = (ROOT / "utils/core/message_processor.py").read_text(encoding="utf-8")
    assert "by name" not in src.split("[REPLYING_TO_CONTEXT]", 1)[1].split("context_reminder = (", 2)[1][:600]


def test_no_prompt_line_tells_her_to_use_the_speakers_name():
    """The plain-message turn and the core rules still said "Address them by
    this name" after the reply block stopped: on the agent boards every reply
    opened "neo_konsi_s2bw, …", and the persona bans the name opener."""
    src = (ROOT / "utils/core/message_processor.py").read_text(encoding="utf-8")
    for phrase in ("by this name", "by their name", "Address them"):
        assert phrase not in src, phrase


# ── Answering the person who spoke, by their name ─────────────────────

def test_an_opening_that_names_someone_else_is_put_right():
    from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P
    names = {"starkind", "tenno henka", "ekco"}
    out = P.correct_addressee("acknowledged, starkind.\n\na spirited sentiment.", "Tenno Henka", names,
                              "Kaia, I'm an Irish-ish American, I like to give John Bull ballyhooley.")
    assert out.startswith("acknowledged, tenno henka.")
    # Named by the person speaking: left alone. Not someone in the channel: left alone.
    assert P.correct_addressee("tell starkind, starkind.", "Ekco", names, "say hi to starkind") == "tell starkind, starkind."
    assert P.correct_addressee("a fair point, gandalf.", "Ekco", names, "") == "a fair point, gandalf."
    assert P.correct_addressee("yes, ekco?", "Ekco", names, "") == "yes, ekco?"


def test_her_history_loses_its_greeting_lines():
    from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P
    history = [{"role": "user", "content": "Starkind: Cherenkov radiation during a fission startup."},
               {"role": "assistant", "content": "acknowledged, starkind.\n\nthe blue glow is the giveaway, a charged particle outrunning light in water."},
               {"role": "user", "content": "Tenno Henka: Kaia, hello"}]
    out = P.without_greeting_lines(history)
    assert out[1]["content"].startswith("the blue glow") and out[0] == history[0] and out[2] == history[2]
    assert history[1]["content"].startswith("acknowledged")                 # the log's own copy untouched


def test_pronouns_default_to_they_and_follow_the_list(monkeypatch):
    from utils.core import pronouns
    monkeypatch.setattr(pronouns, "known", lambda: {"robin": "xe/xem"})
    assert "robin — xe/xem" in pronouns.line(["Robin", "Sam"]) and "they/them" in pronouns.line()
    assert pronouns.of("Robin") == "xe/xem" and pronouns.of("Sam") is None
    monkeypatch.setattr(pronouns, "known", lambda: {})
    assert pronouns.line(["Robin"]).startswith("Anyone else: they/them")
