"""BotState.save() must snapshot on the caller's thread.

The state dict holds the live relationship, curiosity and afterthought
containers. When the writer thread serialised it, a mutation on the event loop
mid-dump raised "dictionary changed size during iteration" and the save was lost.
"""
import json
import threading

from utils.infrastructure.system.bot_state import BotState


def test_save_survives_concurrent_mutation(tmp_path, monkeypatch):
    import utils.infrastructure.system.bot_state as mod
    failures = []
    monkeypatch.setattr(mod, "log_warning", lambda msg, *a, **k: failures.append(msg))
    path = tmp_path / "bot_state.json"
    state = BotState(state_file=str(path))
    state.relationships = {str(i): {"n": i} for i in range(2000)}
    stop = threading.Event()

    def churn():
        i = 0
        while not stop.is_set():
            state.relationships[str(10000 + i % 500)] = {"n": i}
            state.relationships.pop(str(10000 + (i + 250) % 500), None)
            i += 1

    t = threading.Thread(target=churn)
    t.start()
    try:
        for _ in range(100):
            state.save()
    finally:
        stop.set()
        t.join()
    state._executor.shutdown(wait=True)

    assert not failures, failures[0]
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved["relationships"]) >= 2000
