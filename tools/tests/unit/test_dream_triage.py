"""Dream triage weighs what a log is about, not the letters in it."""
import asyncio
from types import SimpleNamespace


def test_salience_counts_whole_words(tmp_path):
    from utils.core.kaia_dream import DreamEngine
    engine = DreamEngine.__new__(DreamEngine)
    logs = tmp_path / "user_logs" / "Ekco_1"
    logs.mkdir(parents=True)
    said = logs / "a.md"
    said.write_text("he said that. she said this. i disagreed, they said." * 3)
    sad = logs / "b.md"
    sad.write_text("i am sad. i agree. " * 3)
    assert asyncio.run(engine._compute_emotional_salience(said)) < asyncio.run(
        engine._compute_emotional_salience(sad))
