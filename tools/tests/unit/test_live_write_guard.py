"""The guard itself: a write to live data is seen; redirected and read-only ones are not."""
import os

import live_write_guard as guard


def test_it_names_live_paths_and_spares_test_paths():
    assert guard.live_path("memory/bot_state.json") == os.path.join("memory", "bot_state.json")
    assert guard.live_path("knowledge_base/user_logs/x/interactions_1.md")
    assert guard.live_path("logs/kaiacord.log")
    assert guard.live_path("memory/bot_state.test.json") == ""
    assert guard.live_path("memory/rag_storage.test/x.json") == ""
    assert guard.live_path("knowledge_base/.test/a.md") == ""
    assert guard.live_path("/tmp/memory/bot_state.json") == ""
    assert guard.live_path("utils/core/foo.py") == ""


def test_it_tells_a_write_from_a_read():
    assert guard.is_write("w", 0) and guard.is_write("a", 0) and guard.is_write("r+", 0)
    assert guard.is_write(None, os.O_WRONLY | os.O_CREAT)
    assert not guard.is_write("r", os.O_RDONLY)
    assert not guard.is_write("rb", os.O_RDONLY)


def test_a_real_open_for_writing_is_recorded(monkeypatch, tmp_path):
    """Exercises the hook, not a copy of it. The path is outside the repo's live folders
    until the root is pointed at tmp_path, so nothing live is written."""
    (tmp_path / "memory").mkdir()
    monkeypatch.setattr(guard, "_root", str(tmp_path) + os.sep)
    seen = {}
    monkeypatch.setattr(guard, "offences", seen)
    with open(tmp_path / "memory" / "state.json", "w") as f:
        f.write("{}")
    with open(tmp_path / "memory" / "state.json") as f:
        f.read()
    with open(tmp_path / "memory" / "state.test.json", "w") as f:
        f.write("{}")
    assert list(seen) == [os.path.join("memory", "state.json")]


def test_the_shared_bot_state_is_redirected():
    from utils.infrastructure.system.bot_state import BotState, bot_state
    assert ".test" in bot_state.state_file
    assert ".test" in BotState().state_file
