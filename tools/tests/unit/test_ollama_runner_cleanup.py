"""Ollama runner cleanup: what counts as a runner, what is spared, and when it runs at all."""
from types import SimpleNamespace

from utils.infrastructure.gpu import clear_gpu_memory as C
from utils.infrastructure.system import dashboard_manager as D

CHAT = "de574647d0c3121888e575b7fb632d8c10449"
EMBED = "970aa74c0a90ef7482477cf803618e776e173"


def _proc(pid, name, *cmd):
    return SimpleNamespace(info={"pid": pid, "name": name, "cmdline": list(cmd)})


def _table():
    return [
        _proc(899, "ollama", "/usr/bin/ollama", "serve"),
        _proc(1001, "llama-server", "/usr/lib/ollama/llama-server", "--model",
              f"/var/lib/ollama/blobs/sha256-{CHAT}", "--port", "41001"),
        _proc(1002, "llama-server", "/usr/lib/ollama/llama-server", "--model",
              f"/var/lib/ollama/blobs/sha256-{EMBED}", "--port", "41002"),
        _proc(1003, "ollama", "/usr/bin/ollama", "runner", "--model", "x"),
        _proc(1004, "python", "python", "Kaiacord.py"),
    ]


def test_current_runners_are_llama_server_processes_and_the_daemon_is_not_one():
    """The kill loop looked for "runner" in the command line, which a
    `llama-server` runner never has, so it stopped nothing."""
    assert [p.info["pid"] for p in C._runners_to_stop(_table(), set(), current_pid=1)] == [1001, 1002, 1003]


def test_the_runner_of_a_preserved_model_is_left_running():
    spared = [p.info["pid"] for p in C._runners_to_stop(_table(), {CHAT}, current_pid=1)]
    assert spared == [1002, 1003]


def test_an_incomplete_shutdown_leaves_ollama_alone(monkeypatch):
    calls = []
    monkeypatch.setattr(C, "kill_orphaned_runners", lambda *a, **k: calls.append("runners"))
    D._release_ollama_after_shutdown(False)
    assert calls == []
    D._release_ollama_after_shutdown(True)
    assert calls == ["runners"]


def test_both_dashboard_modes_go_through_the_completion_check():
    import inspect
    source = inspect.getsource(D.DashboardManager)
    assert "kill_orphaned_runners" not in source
    assert source.count("_release_ollama_after_shutdown(") == 2
