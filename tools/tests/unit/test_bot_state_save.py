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
    # A person's record changing mid-copy: the top-level map is copied in one
    # step, so the race that is left is one level down.
    state.relationships = {"user-1": FlakyDeepcopyDict(
        {"topic_counts": {"radio": 3}, "interaction_count": 7})}
    try:
        state.save()
    finally:
        state.close()

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["relationships"]["user-1"]["topic_counts"] == {"radio": 3}
    assert state.relationships["user-1"].calls >= 2
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
    snapshot = source.index("                save()")
    writer_drain = source.index("asyncio.to_thread(close)")
    assert snapshot < writer_drain
    assert "timeout=5.0" in source
    assert 'getattr(app_ctx, "bot_state", None)' in source

def test_parallel_add_ingestion_updates_are_serialized_and_persisted(tmp_path):
    """Parallel RAG workers must not overwrite each other's recent-history entries."""
    from concurrent.futures import ThreadPoolExecutor

    class TrackingLock:
        """Non-reentrant lock that exposes which thread currently owns it."""

        def __init__(self):
            self._lock = threading.Lock()
            self._owner = None

        def acquire(self, *args, **kwargs):
            if self._owner == threading.get_ident():
                raise AssertionError("BotState attempted to reacquire its non-reentrant lock")
            acquired = self._lock.acquire(*args, **kwargs)
            if acquired:
                self._owner = threading.get_ident()
            return acquired

        def release(self):
            self._owner = None
            self._lock.release()

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, *_exc):
            self.release()
            return False

        def held_by_current_thread(self):
            return self._owner == threading.get_ident()

    class LockAwareList(list):
        def __init__(self, values, lock):
            super().__init__(values)
            self._owner_lock = lock

        def __iter__(self):
            assert self._owner_lock.held_by_current_thread(), (
                "recent_ingestions was read for mutation without owning BotState._lock"
            )
            return super().__iter__()

    class LockAwareBotState(BotState):
        def __setattr__(self, name, value):
            if name == "recent_ingestions":
                lock = self.__dict__.get("_lock")
                if lock is not None and hasattr(lock, "held_by_current_thread"):
                    value = LockAwareList(value, lock)
            super().__setattr__(name, value)

    path = tmp_path / "bot_state_ingestion_race.json"
    state = LockAwareBotState(state_file=str(path))
    state._lock = TrackingLock()
    state.recent_ingestions = list(state.recent_ingestions)

    filenames = [f"document-{number}.md" for number in range(8)]
    try:
        with ThreadPoolExecutor(max_workers=len(filenames)) as pool:
            futures = [
                pool.submit(state.add_ingestion, filename, f"snippet for {filename}")
                for filename in filenames
            ]
            for future in futures:
                future.result(timeout=5)

    finally:
        state.close()

    saved = json.loads(path.read_text(encoding="utf-8"))
    saved_filenames = [entry["filename"] for entry in saved["recent_ingestions"]]
    assert len(saved_filenames) == len(filenames)
    assert len(set(saved_filenames)) == len(filenames)
    assert set(saved_filenames) == set(filenames)
