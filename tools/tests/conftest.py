"""Shared test setup: the project root on sys.path.

Markers are declared in pytest.ini (under --strict-markers), not here. The
fixtures this file used to carry were used by no test, and several no longer
worked: a bot-state fixture called the `bot_state` instance as if it were the
class, a mock Ollama listed the removed gemma2:2b, and an `event_loop` override
is ignored by pytest-asyncio 1.x. Put a fixture here when a test needs it.
"""

import sys
from pathlib import Path

project_root = str(Path(__file__).parent.parent.parent.absolute())
if project_root not in sys.path:
    sys.path.insert(0, project_root)

sys.path.insert(0, str(Path(__file__).parent))
try:
    import live_write_guard  # Kaiacord only: the standalones share this file, not the guard
except ImportError:
    live_write_guard = None

if live_write_guard:
    live_write_guard.install()


import pytest

#: Shutdown steps that act on the live machine: the model in VRAM and this
#: host's Ollama runners. A test reaching one is recorded like a live write.
_LIVE_TEARDOWN = (
    ("utils.infrastructure.gpu.clear_gpu_memory", None, "kill_orphaned_runners"),
    ("utils.infrastructure.gpu.clear_gpu_memory", None, "force_clear_gpu"),
    ("utils.infrastructure.gpu.gpu_manager", "OllamaGPUManager", "unload_all_models"),
)


@pytest.fixture(autouse=True)
def _no_live_teardown(monkeypatch, request):
    """Replace live teardown with a recorder for every test."""
    if not live_write_guard:
        yield
        return
    import importlib
    for module_name, owner, attr in _LIVE_TEARDOWN:
        try:
            target = importlib.import_module(module_name)
        except Exception:
            continue
        if owner:
            target = getattr(target, owner, None)
            if target is None:
                continue

        def _refuse(*_a, _name=f"{module_name}.{owner + '.' if owner else ''}{attr}", **_k):
            live_write_guard.offences[f"<live teardown> {_name}"] = request.node.nodeid
            return None

        if attr == "unload_all_models":
            async def _refuse_async(*a, _r=_refuse, **k):
                return _r(*a, **k)
            monkeypatch.setattr(target, attr, staticmethod(_refuse_async), raising=False)
        else:
            monkeypatch.setattr(target, attr, _refuse, raising=False)
    yield


def pytest_runtest_logstart(nodeid, location):
    if live_write_guard:
        live_write_guard.current_test = nodeid


def pytest_sessionfinish(session, exitstatus):
    if live_write_guard and live_write_guard.offences and exitstatus == 0:
        session.exitstatus = 1


def pytest_terminal_summary(terminalreporter):
    if live_write_guard and live_write_guard.offences:
        terminalreporter.section("writes to live data")
        for path, test in sorted(live_write_guard.offences.items()):
            terminalreporter.line(f"{path}  <-  {test}")
