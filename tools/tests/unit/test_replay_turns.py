"""The replay tool reads the logs right, never runs in the checkout, and still fits the pipeline it hooks."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("replay_turns", ROOT / "tools/maintenance/replay_turns.py")
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)

LOG = """---
title: x
---
[2026-11-03 10:00:00] Starkind: morning kaia
[2026-11-03 10:00:05] Kaia: morning.
[2026-11-03 10:01:00] Starkind: what are you reading?
it's a two-line question
[2026-11-03 10:01:09] Kaia: gibson again.
[2026-11-03 10:02:00] Starkind: [shared image]
"""


def _tree(tmp_path):
    logs = tmp_path / "user_logs"
    for folder, name in (("Starkind_1", "interactions_20261103.md"), ("Starkind_1", "interactions_20261020.md"),
                         ("forum_someone_2", "interactions_20261103.md")):
        (logs / folder).mkdir(parents=True, exist_ok=True)
        (logs / folder / name).write_text(LOG, encoding="utf-8")
    return logs


def test_a_log_parses_into_turns_with_their_continuation_lines(tmp_path):
    turns = rt.parse_log(_tree(tmp_path) / "Starkind_1" / "interactions_20261103.md")
    assert [t[2] for t in turns] == ["Starkind", "Kaia", "Starkind", "Kaia", "Starkind"]
    assert turns[2][3] == "what are you reading?\nit's a two-line question"


def test_candidates_are_answered_turns_from_discord_logs_since_the_date(tmp_path):
    rows = rt.candidates(_tree(tmp_path), "20261101")
    assert [r["text"] for r in rows] == ["morning kaia", "what are you reading?\nit's a two-line question"]
    assert rows[1]["logged"] == "gibson again." and len(rows[1]["prior"]) == 2
    assert all(r["folder"] == "Starkind_1" for r in rows)        # forum folder and older file left out


def test_kinds_and_the_sample_leave_out_what_cannot_be_replayed():
    assert rt.kind_of("what are you reading?") == "question"
    assert rt.kind_of("morning kaia") == "short"
    assert rt.kind_of(" ".join(["word"] * 45)) == "long"
    rows = [dict(text="[shared image] look"), dict(text="hello there")]
    assert [r["text"] for r in rt.pick(rows, 5, 1)] == ["hello there"]


def test_a_probe_is_scored_on_what_it_must_and_must_not_say():
    probe = {"expect": r"tuxedo", "forbid": r"my apologies"}
    assert rt.score(probe, "no, lucky’s a tuxedo.") is True
    assert rt.score(probe, "my apologies, lucky's a tuxedo") is False
    assert rt.score(probe, "lucky is a calico") is False
    assert rt.score({"expect": None, "forbid": None}, "anything") is None
    assert {p["id"] for p in rt.PROBES} >= {"model", "unattached_photo", "invented_quote", "false_correction"}


def test_the_no_rules_arm_takes_out_exactly_the_block():
    system = "persona" + rt.RULES_START + "- rule\n" + rt.RULES_END + "\n\ntail"
    messages = [{"role": "system", "content": system}, {"role": "user", "content": "hi"}]
    out = rt.without_rules(messages)
    assert out[0]["content"] == "persona\n\ntail" and messages[0]["content"] == system
    assert rt.without_rules([{"role": "system", "content": "no block"}]) is None


def test_the_block_markers_still_match_the_pipeline():
    src = (ROOT / "utils/core/message_processor.py").read_text(encoding="utf-8")
    assert rt.RULES_START.strip("\n") in src and rt.RULES_END in src


def test_the_pipeline_still_has_what_the_replay_hooks():
    from utils.core.message_processor import MessageProcessor
    for name in ("_perform_classification", "_retrieve_and_generate", "_call_ollama_with_retries"):
        assert callable(getattr(MessageProcessor, name))


def test_the_sandbox_is_never_the_checkout(tmp_path):
    with pytest.raises(SystemExit, match="inside the repository"):
        rt.build_sandbox(ROOT / "logs" / "replay_sandbox", fresh_state=False)
    (tmp_path / "someones_dir").mkdir()
    with pytest.raises(SystemExit, match="not a replay sandbox"):
        rt.build_sandbox(tmp_path / "someones_dir", fresh_state=False)


def test_arguments_survive_the_move_into_the_sandbox():
    ap_args = ["--arms", "shipped", "--probes", "--seeds", "7,8", "--out", "/tmp/x.json"]
    seen = {}

    def fake_enter(args, argv):
        seen["argv"] = argv
    original = rt.enter_sandbox
    rt.enter_sandbox = fake_enter
    try:
        rt.main(ap_args)
    finally:
        rt.enter_sandbox = original
    argv = seen["argv"]
    assert argv[argv.index("--seeds") + 1] == "7,8" and "--probes" in argv
    assert argv[argv.index("--out") + 1] == "/tmp/x.json"
