"""Configuration regression tests for optional integrations."""

from utils.infrastructure.system import yaml_config


def test_gemini_key_is_optional_for_core_bot_startup(monkeypatch):
    """A missing Gemini key must disable news generation, not core startup."""
    monkeypatch.setenv("DISCORD_TOKEN", "test-discord-token")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    core_config = {
        "discord": {"token": "test-discord-token"},
        "models": {"chat": "test-chat-model", "embedding": "test-embedding-model"},
        "performance": {
            "max_memory_messages": 35,
            "rag_top_k": 12,
            "requests_per_minute": 30,
        },
    }
    monkeypatch.setattr(yaml_config, "load_hierarchical_config", lambda: core_config)

    loaded = yaml_config.YAMLConfig()

    assert loaded.chat_model == "test-chat-model"
    assert loaded.embedding_model == "test-embedding-model"
