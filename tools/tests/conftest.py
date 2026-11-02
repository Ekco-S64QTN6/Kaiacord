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
