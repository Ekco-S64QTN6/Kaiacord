"""
YAML Configuration Loader
==========================

Runtime YAML configuration loading with environment variable override
and validation support.

Hierarchy (highest to lowest priority):
1. Environment variables
2. config/kaia.yaml (user overrides)
3. config/default_config.yaml (defaults)
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field, fields


def load_yaml_file(path: Path) -> Dict[str, Any]:
    """Load YAML file, return empty dict if not found"""
    if not path.exists():
        return {}
    
    with open(path, 'r') as f:
        return yaml.safe_load(f) or {}


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries"""
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result


def get_nested(data: dict, path: str, default=None):
    """Get nested dictionary value using dot notation"""
    keys = path.split('.')
    current = data
    
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    
    return current


def set_nested(data: dict, path: str, value):
    """Set nested dictionary value using dot notation"""
    keys = path.split('.')
    current = data
    
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    current[keys[-1]] = value


def load_hierarchical_config() -> Dict[str, Any]:
    """
    Load configuration with hierarchy:
    1. Load config/default_config.yaml
    2. Merge with config/kaia.yaml (if exists)
    3. Override with environment variables
    """
    # Load default config
    default_path = Path("config/default_config.yaml")
    config = load_yaml_file(default_path)
    
    # Merge user config
    user_path = Path("config/kaia.yaml")
    if user_path.exists():
        user_config = load_yaml_file(user_path)
        config = deep_merge(config, user_config)
    
    # Environment variable overrides
    env_mappings = {
        'DISCORD_TOKEN': 'discord.token',
        'BLACKLISTED_CHANNELS': 'discord.blacklisted_channels',
        'GEMINI_API_KEY': 'api.gemini_key',
        'CHAT_MODEL': 'models.chat',
        'VISION_MODEL': 'models.vision',
        'EMBEDDING_MODEL': 'models.embedding',
    }
    
    for env_var, config_path in env_mappings.items():
        env_value = os.getenv(env_var)
        if env_value:
            # Handle comma-separated lists
            if env_var == 'BLACKLISTED_CHANNELS':
                env_value = env_value.split(',')
            set_nested(config, config_path, env_value)
    
    return config


def validate_config(config: Dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate configuration.
    
    Returns:
        (is_valid, errors)
    """
    errors = []
    
    # Required fields
    if not get_nested(config, 'discord.token'):
        errors.append("Discord token not set (DISCORD_TOKEN environment variable)")
    
    # Model names
    models = get_nested(config, 'models', {})
    if not models.get('chat'):
        errors.append("Chat model not configured")
    if not models.get('vision'):
        errors.append("Vision model not configured")
    if not models.get('embedding'):
        errors.append("Embedding model not configured")
    
    # NOTE: Paths validation is optional - directories will be created if needed
    # No longer error on missing knowledge_base directory
    
    # Performance settings
    perf = get_nested(config, 'performance', {})
    if perf.get('max_memory_messages', 0) < 1:
        errors.append("max_memory_messages must be >= 1")
    
    if perf.get('rag_top_k', 0) < 1:
        errors.append("rag_top_k must be >= 1")
    
    if perf.get('requests_per_minute', 0) < 1:
        errors.append("requests_per_minute must be >= 1")
    
    # GPU settings
    gpu = get_nested(config, 'gpu', {})
    min_vram = gpu.get('image_gen_min_vram_gb', 0)
    if min_vram < 4:
        errors.append(f"image_gen_min_vram_gb too low: {min_vram} (minimum 4.0)")
    
    return len(errors) == 0, errors


@dataclass
class YAMLConfig:
    """Configuration loaded from YAML files"""
    
    # Raw configuration data
    _data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Load configuration on initialization"""
        self._data = load_hierarchical_config()
        
        # Validate
        is_valid, errors = validate_config(self._data)
        if not is_valid:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ValueError(error_msg)
    
    def get(self, path: str, default=None):
        """Get configuration value using dot notation"""
        return get_nested(self._data, path, default)
    
    # Properties for common values
    @property
    def discord_token(self) -> str:
        return self.get('discord.token', os.getenv('DISCORD_TOKEN', ''))
    
    @property
    def blacklisted_channels(self) -> list:
        channels = self.get('discord.blacklisted_channels', 'general,announcements,rules')
        if isinstance(channels, str):
            return channels.split(',')
        return channels
    
    @property
    def chat_model(self) -> str:
        return self.get('models.chat', 'gemma3:12b')
    
    @property
    def vision_model(self) -> str:
        return self.get('models.vision', 'llama3.2-vision:11b')
    
    @property
    def embedding_model(self) -> str:
        return self.get('models.embedding', 'nomic-embed-text')
    
    @property
    def knowledge_base_dir(self) -> str:
        return self.get('paths.knowledge_base', './knowledge_base')
    
    @property
    def persist_dir(self) -> str:
        return self.get('paths.persist', './storage')
    
    @property
    def max_log_size_mb(self) -> int:
        return self.get('performance.max_log_size_mb', 100)
    
    @property
    def max_memory_messages(self) -> int:
        return self.get('performance.max_memory_messages', 30)
    
    @property
    def max_consecutive_quips(self) -> int:
        return self.get('performance.max_consecutive_quips', 3)
    
    @property
    def rag_top_k(self) -> int:
        return self.get('performance.rag_top_k', 8)
    
    @property
    def requests_per_minute(self) -> int:
        return self.get('performance.requests_per_minute', 30)
    
    @property
    def startup_news_update(self) -> bool:
        return self.get('startup.news_update', False)
    
    @property
    def startup_news_timeout(self) -> int:
        return self.get('startup.news_timeout', 10)
    
    def should_use_cache(self, query_text: str, query_classification: str) -> bool:
        """Determine if semantic cache should be used for this query"""
        if not self.get('performance.enable_semantic_cache', True):
            return False
        
        # NEVER use cache for identity questions
        if query_classification in ["IDENTITY", "SELF", "WHOAMI"]:
            return False
        
        # Never use cache for "who are you" or "who am i"
        identity_keywords = ["who are you", "who am i", "what are you", "define yourself"]
        if any(keyword in query_text.lower() for keyword in identity_keywords):
            return False
        
        return True
    
    def reload(self):
        """Reload configuration from files"""
        self._data = load_hierarchical_config()
        
        # Validate
        is_valid, errors = validate_config(self._data)
        if not is_valid:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ValueError(error_msg)
