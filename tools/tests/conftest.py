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
