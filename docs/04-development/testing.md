# Testing Guide for Kaia

Kaia's test suite uses `pytest` and handles asynchronous code via `pytest-asyncio`.

## Running the Test Suite

The test suite is broken into isolated component-level unit tests and integration tests.

Run tests using the project virtual environment:

### The Quick Commands

1. **Unit Tests** (Fast, isolated component tests — 143 tests):
```bash
venv/bin/python3 -m pytest tools/tests/unit/ -v
```

2. **Integration Tests** (Sanity checks and end-to-end flows):
```bash
venv/bin/python3 -m pytest tools/tests/integration/ -v
```

3. **Running a Specific Test**:
```bash
venv/bin/python3 -m pytest tools/tests/unit/test_phase61_fixes.py -v
```

---

## Test Infrastructure

### `pytest.ini`
The root directory contains a `pytest.ini` file that automatically configures the test runner to handle `async def` testing natively via `asyncio_mode = auto`.

### Directory Structure

```text
tools/tests/
├── unit/                 # Isolated component logic (No network, mocked Ollama/Discord)
│   ├── test_imports.py         # Validates modular imports
│   ├── test_yaml_config.py     # Tests configuration merging and parsing
│   ├── test_phase61_fixes.py   # Timezone, chunking guard, KB grounding
│   ├── test_combat_engine.py   # TTRPG combat formulas & defense soft-caps
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
3. **Async Support**: Simply define your tests as `async def test_my_feature():` and `pytest` will handle the event loop automatically.

### Example

```python
import pytest
from unittest.mock import AsyncMock, patch

from utils.infrastructure.system.yaml_config import YAMLConfig

async def test_my_new_feature():
    # Setup
    config = YAMLConfig("config/kaia.yaml")
    
    # Execution
    result = await do_something_async(config)
    
    # Validation
    assert result is True
```

---

## Pre-Flight Health Check

Before submitting a Pull Request or starting the bot for the first time, you should run the comprehensive health check script. This script verifies your `.env` tokens, local installation of Ollama, connectivity to models, and file permissions.

```bash
python tools/maintenance/health_check.py
```
