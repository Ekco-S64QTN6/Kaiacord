# Tests Directory

Organized test suite for Kaiacord v2.0.

## Structure

```
tests/
├── unit/           # Fast, isolated unit tests
├── integration/    # End-to-end integration tests
├── verification/   # System verification scripts
├── archive/        # Deprecated/broken tests
└── conftest.py     # Shared pytest fixtures
```

## Running Tests

### All Tests
```bash
pytest tests/ -v
```

### By Category
```bash
# Unit tests (fast)
pytest tests/unit/ -v

# Integration tests (slower, E2E)
pytest tests/integration/ -v

# Verification scripts (system checks)
python tests/verification/verify_chat_gpu.py
python tests/verification/verify_image_gen.py
```

### Specific Test
```bash
pytest tests/unit/test_yaml_config.py -v
pytest tests/unit/test_stats_helpers.py::test_stats_helpers -v
```

## Test Categories

### Unit Tests (`tests/unit/`)
Fast, isolated tests for individual components:
- `test_stats_helpers.py` - Stats poller helpers
- `test_logging_bridge.py` - Logging bridge
- `test_yaml_config.py` - YAML configuration (10 tests)
- `test_rate_limiter.py` - Rate limiting
- `test_news_manager.py` - News manager
- `test_intelligence.py` - Query classification
- `test_hallucination_patterns.py` - Hallucination detection
- `test_async_task_registry.py` - Async task management

### Integration Tests (`tests/integration/`)
End-to-end tests for complete workflows:
- `test_integration.py` - Comprehensive E2E tests (7 test classes)
- `test_chat_flow.py` - Chat conversation flows
- `test_core.py` - Core bot functionality
- `test_rag.py` - RAG retrieval system

### Verification Scripts (`tests/verification/`)
System validation and health checks:
- `verify_chat_gpu.py` - Chat model GPU loading
- `verify_image_gen.py` - Image generation
- `verify_vision_fix.py` - Vision system
- `verify_vram_fix.py` - VRAM management
- `verify_logging_final.py` - Logging system
- `verify_persona_fixes.py` - Persona compliance
- `verify_quip_logic.py` - Quip system
- `verify_shutdown_fixes.py` - Shutdown process

## Fixtures

See `conftest.py` for shared pytest fixtures:
- `temp_dir` - Temporary directory
- `mock_ollama_client` - Mocked Ollama client
- `mock_discord_message` - Mocked Discord message
- `mock_torch` - Mocked PyTorch for GPU tests
- And more...

## Coverage

Current test coverage:
- **Unit tests**: 12/12 passing ✅
- **Integration tests**: 7 test classes created
- **Verification**: 8 system check scripts

## Adding New Tests

### Unit Test Template
```python
# tests/unit/test_my_feature.py
import pytest

def test_my_feature():
    """Test description"""
    # Arrange
    # Act
    # Assert
    assert True
```

### Integration Test Template
```python
# tests/integration/test_my_flow.py
import pytest

@pytest.mark.asyncio
async def test_my_flow(mock_ollama_client):
    """Test E2E flow"""
    # Test complete workflow
    assert True
```

## Notes

- Unit tests should be fast (<1s each)
- Integration tests may be slower (mocking recommended)
- Verification scripts are for manual system checks
- Archived tests in `archive/` are kept for reference
