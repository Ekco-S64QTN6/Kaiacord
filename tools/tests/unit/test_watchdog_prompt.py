"""DECISIONS Q9: a watchdog trip keeps the exact prompt that produced it."""
import json
from types import SimpleNamespace


def test_a_flagged_turn_saves_the_messages_sent(tmp_path, monkeypatch):
    from utils.core import message_processor as mp
    monkeypatch.setattr(mp, "WATCHDOG_PROMPTS_DIR", str(tmp_path / "wd"))
    monkeypatch.setattr(mp, "WATCHDOG_PROMPTS_KEEP", 2)
    ctx = SimpleNamespace(channel_id=5, author_name="Ekco",
                          prompt_messages=[{"role": "system", "content": "persona"},
                                           {"role": "user", "content": "Ekco: do you like jazz?"}])
    for _ in range(3):
        mp._save_watchdog_prompt(ctx, "i don't like jazz", ["Belief conflict on topic 'jazz'"])
    saved = sorted(p for p in tmp_path.iterdir() if p.is_dir())[0].glob("*.json")
    files = list(saved)
    assert len(files) == 2
    record = json.loads(files[-1].read_text(encoding="utf-8"))
    assert record["messages"][1]["content"] == "Ekco: do you like jazz?"
    assert record["reasons"] == ["Belief conflict on topic 'jazz'"]
