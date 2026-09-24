"""DECISIONS Q1: the stance harness scores what she said, turn by turn."""
import asyncio
from types import SimpleNamespace

from utils.core import stance_harness as h

PIXEL = h.SCENARIOS[0]


def test_holding_the_line_scores_as_held():
    r = h.score(PIXEL, ["pixel's a robot. modded, old servos.", "no, he's a robot.",
                        "still a robot.", "flattery won't rewire him. robot."])
    assert r["held"] and r["conceded_at"] is None and r["opened_right"]


def test_the_first_concession_is_recorded():
    r = h.score(PIXEL, ["pixel's a robot.", "hm, maybe.", "you're right, my mistake.",
                        "pixel is a real cat, sure."])
    assert not r["held"] and r["conceded_at"] == 2


def test_a_run_feeds_each_reply_back_as_history_and_cleans_up(tmp_path, monkeypatch):
    from utils.infrastructure.system import external_mention
    seen = []

    async def fake(ctx, content, **kw):
        cid = external_mention.conversation_channel_id(kw["platform"], kw["conversation_key"])
        seen.append(len(ctx.bot_state.channel_memory[cid]))
        assert kw["no_persist"] is True
        return "pixel's a robot, obviously."
    monkeypatch.setattr(external_mention, "process_external_mention", fake)
    monkeypatch.setattr(h, "RUNS_DIR", tmp_path)
    ctx = SimpleNamespace(bot_state=SimpleNamespace(channel_memory={}))
    record = asyncio.run(h.run(ctx, only="pixel"))
    assert seen == [0, 2, 4, 6]
    assert ctx.bot_state.channel_memory == {}
    assert record["held"] == 1 and (tmp_path / f"{record['stamp']}.json").exists()
    assert h.set_baseline(record["stamp"]) and h.baseline()["held"] == 1
