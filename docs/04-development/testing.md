# Testing Guide for Kaia

As of Phase 12 (Test Suite Modernization), Kaia's entire test suite has been updated to use `pytest` and automatically handles asynchronous code via `pytest-asyncio`.

## Running the Test Suite

The test suite is broken into component-level unit tests and end-to-end integration/verification tests. 

Since the project uses absolute imports starting from the root directory (e.g., `from utils.core.message_processor`), you **must** run `pytest` with the `PYTHONPATH` set to the project root.

### The Quick Command

To run the entire suite (unit + verification):
```bash
PYTHONPATH=. pytest tools/tests/
```

### Specific Categories

1. **Unit Tests** (Fast, isolated component tests):
```bash
PYTHONPATH=. pytest tools/tests/unit/ -q
```

2. **Verification Tests** (Slower, integration-level sanity checks):
```bash
PYTHONPATH=. pytest tools/tests/verification/ -q
```

3. **Running a Specific Test**:
```bash
PYTHONPATH=. pytest tools/tests/unit/test_yaml_config.py -v
```

---

## Test Infrastructure

### `pytest.ini`
The root directory contains a `pytest.ini` file that automatically configures the test runner to handle `async def` testing natively via `asyncio_mode = auto`. You no longer need to strictly decorate every test with `@pytest.mark.asyncio`.

### Directory Structure

```text
tools/tests/
├── unit/                 # Isolated component logic (No network, heavy mocking)
│   ├── test_imports.py      # Validates the modular `utils/` structure loads cleanly
│   ├── test_yaml_config.py  # Tests configuration merging and parsing
│   ├── test_intelligence.py # Persona anchoring, context shaping
│   └── test_repetition.py   # Hallucination guard and repetitive loop detection
└── verification/         # Integration checks (DB states, end-to-end flows)
    └── verify_kb_logic.py   # Verifies Regex boundary false-negatives
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
