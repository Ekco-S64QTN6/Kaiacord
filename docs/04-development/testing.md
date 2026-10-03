# Testing Guide for Kaia

Kaia's test suite uses `pytest` and handles asynchronous code via `pytest-asyncio`.

## Running the Test Suite

The test suite is broken into isolated component-level unit tests and integration tests.

Run tests using the project virtual environment:

### The Quick Commands

1. **Unit Tests** (fast, isolated component tests):
```bash
venv/bin/python3 -m pytest tools/tests/unit/ -v
```

2. **Integration Tests** (Sanity checks and end-to-end flows):
```bash
venv/bin/python3 -m pytest tools/tests/integration/ -v
```

3. **Running a Specific Test**:
```bash
venv/bin/python3 -m pytest tools/tests/unit/test_phase61_fixes.py -v          # one file
venv/bin/python3 -m pytest tools/tests/unit/test_response_filters.py::test_harden_is_idempotent   # one test
```

4. **Skipping External Services** (the invocation to use by default):
```bash
venv/bin/python3 -m pytest -q -m "not ollama and not gpu and not slow"
# 2026-10-03: 2,736 passed, 1 skipped, 49 deselected, 1 xfailed. Take the count from your own run.
# Re-run rather than trusting this line — the count moves every phase, and it
# has been stale in three files at once. What matters is that nothing failed.
```
Only **2** tests need Ollama or a GPU (28 Sept 2026; `--collect-only -m "ollama or gpu"` gives
today's figure). The rest of what that invocation deselects is the 47 marked `slow`. A bare `pytest -q` runs them, which loads `gemma3:12b` and evicts the production
model from VRAM. A test that reaches the Ollama daemon at all — even just to embed — is marked
`ollama`; two were not, and ran against the bot's own daemon on every run.

Markers are declared in `pytest.ini` under `--strict-markers`, so a typo'd marker is an error
rather than a silently ignored one: `slow`, `gpu`, `ollama`, `network`, `integration`.

---

## Test Infrastructure

### `pytest.ini`
The root directory contains a `pytest.ini` file that sets `testpaths`, declares the markers,
enables `--strict-markers`, and pins the asyncio loop scope.

> [!IMPORTANT]
> `asyncio_mode = strict`, **not** `auto`. An `async def test_...` without an explicit
> `@pytest.mark.asyncio` is never awaited — pytest warns and the test does not run, so it
> "passes" without asserting anything. Always decorate async tests:
>
> ```python
> @pytest.mark.asyncio
> async def test_my_feature():
>     ...
> ```

### Directory Structure

```text
tools/tests/
├── unit/                 # Isolated component logic (No network, mocked Ollama/Discord)
│   ├── test_response_filters.py     # Post-generation guards
│   ├── test_chat_model_calls.py     # Every model call keeps the runner loaded
│   ├── test_monitoring_health.py    # Dashboard numbers, loop watchdog, GPU queue
│   ├── test_radio.py, test_sky.py   # Night-shift feeds and local sky computation
│   ├── ttrpg/                       # Aethelgard: combat, economy, every subcommand
│   └── ...
└── integration/          # Integration checks & end-to-end flows
    ├── test_rag_boot.py        # RAG boot and index hydration
    └── ...
```

---

## Writing New Tests

When contributing to Kaia, follow these guidelines for new tests:

1. **Respect the Architecture**: Imports must source from the correct domains (`utils.core`, `utils.infrastructure`, `utils.social`, `utils.news`). Do not import from the old flat `utils/` structure.
2. **Mocking External Services**: Use `unittest.mock` (`patch`, `MagicMock`, `AsyncMock`) to isolate tests from Discord, X, Bluesky, and Ollama. Tests should not require a running Ollama model to pass.
3. **Async Support**: Mark async tests with `@pytest.mark.asyncio`. The loop scope is pinned in
   `pytest.ini`; the mode is `strict`, so an undecorated `async def` test silently does not run.

### Example

```python
import pytest
from unittest.mock import AsyncMock, patch

from utils.infrastructure.system.yaml_config import config

@pytest.mark.asyncio
async def test_my_new_feature():
    # Setup: the shared config, as the bot sees it
    
    # Execution
    result = await do_something_async(config)
    
    # Validation
    assert result is True
```

---

### Rules the suite has learned

- **A fix's test fails on the old code.** Before trusting a new test, stash the fix
  (`git stash -- <file>`) and run it: a test that passes both ways guards nothing.
- **A test that reads the clock pins it.** Two unprompted-gate tests recorded at `time.time()` and
  checked 70 minutes later, so after about 22:50 they crossed midnight and failed. Anchor to a
  fixed time of day or pass `now` in.
- **A test does not stub what it guards.** A lock test that replaced the handler with a stub could
  never see a deadlock inside the real handler. Run the real path, with a timeout if a hang is the
  risk.
- **Nothing a test writes lands in live state.** `utils/infrastructure/monitoring/telemetry_paths.py`
  redirects telemetry, corpus writes, the RAG store and the TTRPG world state under pytest; a new
  component that persists anything needs the same. To check the whole suite at once, run it under
  a `sys.addaudithook` that records writes, renames and removes under `memory/`, `knowledge_base/`
  and `logs/`, attributed per test — anything without `.test` in its path is a leak. That is how
  the live world state was found carrying a test's `atk_mod: -5`.
- **A test that runs a tool is a tool run.** Import a script's module under any name but
  `__main__` rather than invoking it; several tools have no argument parsing and rewrite the corpus
  whatever they are passed.

## Pre-Flight Health Check

Before submitting a pull request or starting the bot for the first time, run the health check. It
checks that it is running in the project venv with the required packages (including `davey`), the
Discord token, Ollama and the models, the GPU as `nvidia-smi` reports it, the knowledge base and
the directories it writes to.

```bash
venv/bin/python3 tools/maintenance/health_check.py
```
