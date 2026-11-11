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
    state.close()

    assert not failures, failures[0]
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved["relationships"]) >= 2000


def test_save_retries_when_snapshot_comprehension_races(tmp_path, monkeypatch):
    """A RuntimeError while copying a live mapping must be inside the retry loop."""
    import utils.infrastructure.system.bot_state as mod

    warnings = []
    monkeypatch.setattr(mod, "log_warning", lambda msg, *a, **k: warnings.append(msg))

    class FlakyDict(dict):
        calls = 0

        def items(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("dictionary changed size during iteration")
            return super().items()

    path = tmp_path / "bot_state.json"
    state = BotState(state_file=str(path))
    state.channel_memory = FlakyDict()
    try:
        state.save()
    finally:
        state.close()

    assert state.channel_memory.calls >= 2
    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["channel_memory"] == {}
    assert not warnings, warnings


def test_save_deep_copies_nested_state_and_retries_runtime_race(tmp_path, monkeypatch):
    import utils.infrastructure.system.bot_state as mod

    warnings = []
    monkeypatch.setattr(mod, "log_warning", lambda msg, *a, **k: warnings.append(msg))

    class FlakyDeepcopyDict(dict):
        calls = 0

        def __deepcopy__(self, memo):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("mapping mutated during nested snapshot")
            return {k: dict(v) if isinstance(v, dict) else v for k, v in self.items()}

    path = tmp_path / "bot_state_nested.json"
    state = BotState(state_file=str(path))
    state.relationships = FlakyDeepcopyDict({
        "user-1": {"topic_counts": {"radio": 3}, "interaction_count": 7}
    })
    try:
        state.save()
    finally:
        state.close()

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["relationships"]["user-1"]["topic_counts"] == {"radio": 3}
    assert state.relationships.calls >= 2
    assert not warnings, warnings



def test_save_serializes_the_detached_snapshot_on_the_writer_thread(tmp_path):
    """Only the live-state snapshot belongs on the caller/event-loop thread."""
    path = tmp_path / "bot_state_worker_serialization.json"
    state = BotState(state_file=str(path))
    state.relationships = {"user-1": {"interaction_count": 1}}

    caller_thread = threading.get_ident()
    started = threading.Event()
    release = threading.Event()
    serialization_threads = []
    original_serialize = state._serialize_snapshot

    def tracked_serialize(snapshot):
        serialization_threads.append(threading.get_ident())
        # This value must be detached before the worker begins serializing.
        assert snapshot["relationships"]["user-1"]["interaction_count"] == 1
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test did not release the writer")
        return original_serialize(snapshot)

    state._serialize_snapshot = tracked_serialize
    try:
        state.save()
        assert started.wait(timeout=5), "writer never started snapshot serialization"
        # Mutating the live object after save() returns must not alter its queued snapshot.
        state.relationships["user-1"]["interaction_count"] = 2
    finally:
        release.set()
        state.close()

    assert serialization_threads
    assert serialization_threads[0] != caller_thread
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["relationships"]["user-1"]["interaction_count"] == 1



def test_close_drains_queued_snapshots_and_is_idempotent(tmp_path):
    path = tmp_path / "bot_state_close.json"
    state = BotState(state_file=str(path))
    state.relationships = {"user-1": {"interaction_count": 1}}
    state.save()
    state.relationships["user-1"]["interaction_count"] = 2
    state.save()

    state.close()
    state.close()

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["relationships"]["user-1"]["interaction_count"] == 2
    assert state._writer_closed is True


def test_save_after_close_does_not_overwrite_the_final_snapshot(tmp_path):
    path = tmp_path / "bot_state_closed.json"
    state = BotState(state_file=str(path))
    state.relationships = {"user-1": {"interaction_count": 3}}
    state.save()
    state.close()

    state.relationships["user-1"]["interaction_count"] = 99
    state.save()

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["relationships"]["user-1"]["interaction_count"] == 3
    assert state._writer_closing is True
    assert state._writer_closed is True


def test_close_waits_for_a_snapshot_already_being_serialized(tmp_path):
    path = tmp_path / "bot_state_close_wait.json"
    state = BotState(state_file=str(path))
    state.relationships = {"user-1": {"interaction_count": 1}}
    started = threading.Event()
    release = threading.Event()
    closed = threading.Event()
    original = state._serialize_snapshot

    def blocked_serialize(snapshot):
        started.set()
        if not release.wait(timeout=5.0):
            raise TimeoutError("test did not release the snapshot writer")
        return original(snapshot)

    state._serialize_snapshot = blocked_serialize
    closer = threading.Thread(target=lambda: (state.close(), closed.set()), daemon=True)
    try:
        state.save()
        assert started.wait(timeout=2.0), "writer did not begin serializing"
        closer.start()
        assert not closed.wait(timeout=0.1), "close returned before the queued write finished"
    finally:
        release.set()
        if closer.ident is not None:
            closer.join(timeout=3.0)
    assert closed.is_set(), "close did not finish after the writer was released"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["relationships"]["user-1"]["interaction_count"] == 1


def test_shutdown_drains_bot_state_after_task_cancellation():
    import inspect
    from utils.infrastructure.system.shutdown_fixed import CleanShutdown

    source = inspect.getsource(CleanShutdown.async_shutdown)
    task_cancel = source.index("task_registry.cancel_all")
    state_close = source.index('close = getattr(state, "close", None)')
    model_unload = source.index("OllamaGPUManager.unload_all_models")
    assert task_cancel < state_close < model_unload
    assert "await asyncio.wait_for(asyncio.to_thread(close), timeout=5.0)" in source
    assert 'getattr(app_ctx, "bot_state", None)' in source
