"""
Pytest Configuration and Fixtures
==================================

Shared fixtures and configuration for Kaia test suite.
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock


# ============================================================================
# Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest"""
    # Add custom markers
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "gpu: marks tests that require GPU (deselect with '-m \"not gpu\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )


# ============================================================================
# Fixtures - File System
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests"""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    shutil.rmtree(temp_path)


@pytest.fixture
def temp_knowledge_base(temp_dir):
    """Create a temporary knowledge base structure"""
    kb_dir = temp_dir / "knowledge_base"
    kb_dir.mkdir()
    
    # Create subdirectories
    (kb_dir / "news" / "daily").mkdir(parents=True)
    (kb_dir / "user_logs").mkdir()
    (kb_dir / "user_profiles").mkdir()
    (kb_dir / "lore").mkdir()
    
    # Create sample persona
    persona_file = kb_dir / "kaia_persona.md"
    persona_file.write_text("""
# Kaia Persona

Test persona for unit tests.

## Personality
- Helpful and concise
- Technical expertise
""")
    
    yield kb_dir


@pytest.fixture
def temp_storage(temp_dir):
    """Create a temporary storage directory"""
    storage_dir = temp_dir / "storage"
    storage_dir.mkdir()
    yield storage_dir


# ============================================================================
# Fixtures - Configuration
# ============================================================================

@pytest.fixture
def mock_config():
    """Mock configuration object"""
    from bot.managers.config import Config
    
    config = Config()
    config.discord_token = "test_token_12345678901234567890"
    config.knowledge_base_dir = "./test_knowledge_base"
    config.persist_dir = "./test_storage"
    config.max_memory_messages = 10
    config.rag_top_k = 3
    
    return config


@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables"""
    monkeypatch.setenv("DISCORD_TOKEN", "test_token")
    monkeypatch.setenv("BLACKLISTED_CHANNELS", "general,test")
    yield


# ============================================================================
# Fixtures - Bot State
# ============================================================================

@pytest.fixture
def mock_bot_state(temp_storage):
    """Mock bot state"""
    from bot.managers.state import BotState
    
    state_file = temp_storage / "bot_state.json"
    state = BotState(str(state_file))
    
    yield state


# ============================================================================
# Fixtures - Discord
# ============================================================================

@pytest.fixture
def mock_discord_message():
    """Mock Discord message"""
    message = Mock()
    message.content = "test message"
    message.author = Mock()
    message.author.id = 123456789
    message.author.name = "TestUser"
    message.channel = Mock()
    message.channel.id = 987654321
    message.channel.send = Mock(return_value=None)
    message.guild = Mock()
    message.guild.name = "TestGuild"
    
    return message


@pytest.fixture
def mock_discord_user():
    """Mock Discord user"""
    user = Mock()
    user.id = 123456789
    user.name = "TestUser"
    user.discriminator = "1234"
    
    return user


# ============================================================================
# Fixtures - Ollama
# ============================================================================

@pytest.fixture
def mock_ollama_client():
    """Mock Ollama client"""
    client = Mock()
    
    # Mock chat response
    def mock_chat(**kwargs):
        response = Mock()
        response.message = Mock()
        response.message.content = "This is a test response from the AI."
        return response
    
    client.chat = Mock(side_effect=mock_chat)
    
    # Mock list
    def mock_list():
        return {
            "models": [
                {"name": "gemma3:12b"},
                {"name": "llama3.2-vision:11b"},
                {"name": "nomic-embed-text"}
            ]
        }
    
    client.list = Mock(side_effect=mock_list)
    
    return client


# ============================================================================
# Fixtures - GPU
# ============================================================================

@pytest.fixture
def mock_torch():
    """Mock PyTorch module"""
    torch = Mock()
    
    # Mock CUDA availability
    torch.cuda = Mock()
    torch.cuda.is_available = Mock(return_value=True)
    torch.cuda.memory_allocated = Mock(return_value=2 * 1024**3)  # 2 GB
    torch.cuda.memory_reserved = Mock(return_value=3 * 1024**3)  # 3 GB
    torch.cuda.empty_cache = Mock()
    torch.cuda.synchronize = Mock()
    
    # Mock device properties
    device_props = Mock()
    device_props.total_memory = 16 * 1024**3  # 16 GB
    torch.cuda.get_device_properties = Mock(return_value=device_props)
    
    return torch


@pytest.fixture
def mock_gpu_unavailable(monkeypatch, mock_torch):
    """Mock GPU as unavailable"""
    mock_torch.cuda.is_available = Mock(return_value=False)
    monkeypatch.setattr("torch.cuda.is_available", mock_torch.cuda.is_available)
    return mock_torch


# ============================================================================
# Fixtures - RAG
# ============================================================================

@pytest.fixture
def mock_rag_retriever():
    """Mock RAG retriever"""
    retriever = Mock()
    
    def mock_retrieve(query, top_k=5):
        # Return mock documents
        return [
            {
                "text": f"Sample document {i} matching query: {query}",
                "metadata": {"source": f"test_{i}.md"}
            }
            for i in range(top_k)
        ]
    
    retriever.retrieve = Mock(side_effect=mock_retrieve)
    
    return retriever


# ============================================================================
# Fixtures - Stats
# ============================================================================

@pytest.fixture
def mock_stats_poller():
    """Mock stats poller"""
    poller = Mock()
    poller.start = Mock()
    poller.stop = Mock()
    poller.is_running = Mock(return_value=False)
    
    return poller


# ============================================================================
# Fixtures - Dashboard
# ============================================================================

@pytest.fixture
def mock_dashboard():
    """Mock dashboard"""
    from utils.logging_bridge import LoggingBridge
    
    class MockDashboard(LoggingBridge):
        def __init__(self):
            self.logs = []
        
        def log(self, level: str, message: str, metadata: dict = None):
            self.logs.append((level, message, metadata))
        
        def is_available(self) -> bool:
            return True
    
    return MockDashboard()


# ============================================================================
# Fixtures - Async
# ============================================================================

@pytest.fixture
def event_loop():
    """Create an event loop for async tests"""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Helper Functions
# ============================================================================

def create_sample_user_log(user_dir: Path, num_entries: int = 5):
    """Create a sample user log file"""
    log_file = user_dir / f"log_{user_dir.name}.md"
    
    entries = []
    for i in range(num_entries):
        entries.append(f"""
## 2024-01-{i+1:02d}

**User**: Test message {i}

**Kaia**: Test response {i}

---
""")
    
    log_file.write_text("\n".join(entries))
    return log_file


def create_sample_news(news_dir: Path, category: str = "technology"):
    """Create a sample news file"""
    from datetime import datetime
    
    date_str = datetime.now().strftime("%Y%m%d")
    news_file = news_dir / f"{date_str}_{category}.md"
    
    news_file.write_text(f"""
# {category.title()} News - {date_str}

## Headline 1
Test news article 1 content.

## Headline 2
Test news article 2 content.
""")
    
    return news_file
