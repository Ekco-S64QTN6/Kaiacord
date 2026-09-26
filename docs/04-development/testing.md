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
# 2026-09-26: 2,407 passed, 1 skipped, 48 deselected, 1 xfailed. Take the count from your own run.
# Re-run rather than trusting this line — the count moves every phase, and it
# has been stale in three files at once. What matters is that nothing failed.
```
Only **2** tests need Ollama or a GPU (26 Sept 2026). The rest of what that invocation deselects
is the ~46 marked `slow`. A bare `pytest -q` runs them, which loads `gemma3:12b` and evicts the production
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

## Pre-Flight Health Check

Before submitting a Pull Request or starting the bot for the first time, you should run the comprehensive health check script. This script verifies your `.env` tokens, local installation of Ollama, connectivity to models, and file permissions.

```bash
venv/bin/python3 tools/maintenance/health_check.py
```
