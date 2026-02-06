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
        errors.append("Chat model not configured (models.chat)")
    if not models.get('vision'):
        errors.append("Vision model not configured (models.vision)")
    if not models.get('embedding'):
        errors.append("Embedding model not configured (models.embedding)")
    
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
    
    # ==========================================================================
    # Type validation - catch misconfigurations early
    # Added: Feb 2026 for configuration robustness
    # ==========================================================================
    type_checks = [
        ('performance.max_memory_messages', int, 'integer'),
        ('performance.rag_top_k', int, 'integer'),
        ('performance.requests_per_minute', int, 'integer'),
        ('performance.idle_quip_timeout_minutes', int, 'integer'),
        ('performance.max_consecutive_quips', int, 'integer'),
        ('gpu.image_gen_min_vram_gb', (int, float), 'number'),
    ]
    
    for path, expected_type, type_name in type_checks:
        value = get_nested(config, path)
        if value is not None and not isinstance(value, expected_type):
            actual_type = type(value).__name__
            errors.append(f"{path} must be {type_name}, got {actual_type}: {value}")
    
    # ==========================================================================
    # Social media config validation (warnings only - bot should still start)
    # Added: Feb 2026 for early detection of missing credentials
    # NOTE: These are warnings, not errors - social features will be disabled
    # ==========================================================================
    warnings = []
    if get_nested(config, 'bluesky.enabled', False):
        if not os.getenv('BLUESKY_HANDLE'):
            warnings.append("Bluesky enabled but BLUESKY_HANDLE not set - Bluesky features disabled")
        if not os.getenv('BLUESKY_APP_PASSWORD'):
            warnings.append("Bluesky enabled but BLUESKY_APP_PASSWORD not set - Bluesky features disabled")
    
    if get_nested(config, 'x_twitter.enabled', False):
        required_x_vars = ['X_API_KEY', 'X_API_SECRET', 'X_ACCESS_TOKEN', 'X_ACCESS_SECRET']
        missing = [v for v in required_x_vars if not os.getenv(v)]
        if missing:
            warnings.append(f"X/Twitter enabled but missing: {', '.join(missing)} - X features disabled")
    
    # Log warnings but don't fail
    for w in warnings:
        print(f"[CONFIG WARNING] {w}")
    
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
            return [c.strip().lower() for c in channels.split(',')]
        return [c.lower() for c in channels]
    
    @property
    def whitelisted_channels(self) -> list:
        """List of channel names that are whitelisted"""
        channels = self.get('discord.whitelisted_channels', [])
        if channels is None:
            return []
        if isinstance(channels, str):
            return [c.strip().lower() for c in channels.split(',') if c.strip()]
        return [str(c).lower() for c in channels]
    
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
        return self.get('paths.persist', './memory')
    
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
    def idle_quip_timeout_minutes(self) -> int:
        return self.get('performance.idle_quip_timeout_minutes', 15)
    
    @property
    def requests_per_minute(self) -> int:
        return self.get('performance.requests_per_minute', 30)
    
    @property
    def max_context_tokens(self) -> int:
        return self.get('performance.max_context_tokens', 32000)
    
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
    
    # Features
    @property
    def vision_enabled(self) -> bool:
        return self.get('features.vision_enabled', False)
    
    @property
    def image_gen_enabled(self) -> bool:
        return self.get('features.image_gen_enabled', False)

    # Bluesky configuration
    @property
    def bluesky_enabled(self) -> bool:
        return self.get('bluesky.enabled', False)
    
    @property
    def bluesky_cross_post_quips(self) -> bool:
        return self.get('bluesky.cross_post_quips', False)
    
    # X (Twitter) configuration
    @property
    def x_enabled(self) -> bool:
        return self.get('x_twitter.enabled', False)
    
    @property
    def x_cross_post_quips(self) -> bool:
        return self.get('x_twitter.cross_post_quips', False)
    
    @property
    def bluesky_reply_to_mentions(self) -> bool:
        return self.get('bluesky.reply_to_mentions', True)
    
    @property
    def x_reply_to_mentions(self) -> bool:
        return self.get('x_twitter.reply_to_mentions', True)
    
    # =========================================================================
    # Timeout Configuration (extracted from magic numbers)
    # =========================================================================
    @property
    def classification_timeout(self) -> float:
        """Query classification timeout in seconds"""
        return self.get('timeouts.classification_seconds', 15.0)
    
    @property
    def orchestration_classification_timeout(self) -> float:
        """Orchestration wait timeout for classification in seconds"""
        return self.get('timeouts.orchestration_classification_seconds', 18.0)
    
    @property
    def prewarm_timeout(self) -> float:
        """Model pre-warm timeout in seconds"""
        return self.get('timeouts.prewarm_seconds', 30.0)
    
    @property
    def rag_retrieval_timeout(self) -> float:
        """RAG retrieval timeout in seconds"""
        return self.get('timeouts.rag_retrieval_seconds', 30.0)
    
    @property
    def vision_analysis_timeout(self) -> float:
        """Vision analysis timeout in seconds"""
        return self.get('timeouts.vision_analysis_seconds', 90.0)
    
    # =========================================================================
    # Token Estimation Configuration
    # =========================================================================
    @property
    def token_multiplier(self) -> float:
        """Multiplier for word-to-token estimation (1.3 default for English)"""
        return self.get('performance.token_multiplier', 1.3)
    
    @property
    def system_reserve_tokens(self) -> int:
        """Reserved tokens for system reinforcement rules and safety prompts"""
        return self.get('performance.system_reserve_tokens', 1000)
    
    @property
    def ignored_users(self) -> list:
        """List of users to ignore (names or IDs)"""
        users = self.get('discord.ignored_users', [])
        if users is None:
            return []
        if isinstance(users, str):
            return [u.strip().lower() for u in users.split(',') if u.strip()]
        return [str(u).lower() for u in users]

    @property
    def owner_ids(self) -> list:
        """List of owner/admin users who bypass cooldowns (names or IDs)"""
        owners = self.get('discord.owner_ids', 'ekco')
        if owners is None:
            return ['ekco']
        if isinstance(owners, str):
            return [o.strip().lower() for o in owners.split(',') if o.strip()]
        return [str(o).lower() for o in owners]
    
    def is_owner(self, author_name: str, display_name: str = None, user_id: str = None) -> bool:
        """Check if a user is an owner/admin"""
        owner_list = self.owner_ids
        checks = [author_name.lower()]
        if display_name:
            checks.append(display_name.lower())
        if user_id:
            checks.append(str(user_id).lower())
        
        for check in checks:
            if check in owner_list:
                return True
            # Handle common username variations (e.g., "ekco" matches "ekco.")
            for owner in owner_list:
                if check.startswith(owner) or owner.startswith(check):
                    return True
        return False

    def reload(self):
        """Reload configuration from files"""
        self._data = load_hierarchical_config()
        
        # Validate
        is_valid, errors = validate_config(self._data)
        if not is_valid:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ValueError(error_msg)


# Global config instance for easy import
config = YAMLConfig()
