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


def _checkout(tmp_path, monkeypatch):
    """A stand-in checkout under tmp_path; nothing of the repo's is opened."""
    root = tmp_path / "checkout"
    (root / "memory").mkdir(parents=True)
    monkeypatch.setattr(guard, "_root", str(root) + os.sep)
    seen = {}
    monkeypatch.setattr(guard, "offences", seen)
    return root, seen


def test_a_write_through_a_symlink_to_the_checkout_is_recorded(monkeypatch, tmp_path):
    root, seen = _checkout(tmp_path, monkeypatch)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with open(alias / "memory" / "state.json", "w") as f:
        f.write("{}")
    assert list(seen) == [os.path.join("memory", "state.json")]


def test_a_test_named_symlink_to_a_live_file_is_not_an_exemption(monkeypatch, tmp_path):
    root, seen = _checkout(tmp_path, monkeypatch)
    (root / "memory" / "state.json").write_text("{}")
    seen.clear()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "state.test.json").symlink_to(root / "memory" / "state.json")
    with open(scratch / "state.test.json", "w") as f:
        f.write("[]")
    assert list(seen) == [os.path.join("memory", "state.json")]


def test_a_hard_link_to_live_data_is_recorded_when_it_is_made(monkeypatch, tmp_path):
    root, seen = _checkout(tmp_path, monkeypatch)
    (root / "memory" / "state.json").write_text("{}")
    seen.clear()
    (root / "scratch").mkdir()
    os.link(root / "memory" / "state.json", root / "scratch" / "copy.json")
    assert list(seen) == [os.path.join("memory", "state.json")]


def test_the_shared_bot_state_is_redirected():
    from utils.infrastructure.system.bot_state import BotState, bot_state
    assert ".test" in bot_state.state_file
    assert ".test" in BotState().state_file
