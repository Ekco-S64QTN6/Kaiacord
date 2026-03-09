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
from dotenv import load_dotenv
from pathlib import Path



# Legacy default paths
from typing import Any, Dict, Optional
from dataclasses import dataclass, field, fields

# Load environment variables from .env
load_dotenv()


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
        
    if not os.getenv("GEMINI_API_KEY") and not get_nested(config, 'api.gemini_key'):
        errors.append("GEMINI_API_KEY environment variable not set (required for news generation)")
    
    # Model names
    models = get_nested(config, 'models', {})
    if not models.get('chat'):
        errors.append("Chat model not configured (models.chat)")
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
        ('social.max_interval_hours', (int, float), 'number'),
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
    warnings_list = []
    if get_nested(config, 'bluesky.enabled', False):
        if not os.getenv('BLUESKY_HANDLE'):
            warnings_list.append("Bluesky enabled but BLUESKY_HANDLE not set - Bluesky features disabled")
        if not os.getenv('BLUESKY_APP_PASSWORD'):
            warnings_list.append("Bluesky enabled but BLUESKY_APP_PASSWORD not set - Bluesky features disabled")
    
    if get_nested(config, 'x_twitter.enabled', False):
        # Support both official API keys and unofficial twikit credentials
        official_vars = ['X_API_KEY', 'X_API_SECRET', 'X_ACCESS_TOKEN', 'X_ACCESS_SECRET']
        unofficial_vars = ['X_USERNAME', 'X_PASSWORD']
        
        has_official = all(os.getenv(v) for v in official_vars)
        has_unofficial = all(os.getenv(v) for v in unofficial_vars)
        
        if not has_official and not has_unofficial:
            warnings_list.append("X/Twitter enabled but missing both API keys AND X_USERNAME/PASSWORD - X features disabled")
    
    # Log warnings but don't fail
    if warnings_list:
        from utils.infrastructure.logging.kaia_logger import log_warning
        for w in warnings_list:
            log_warning(w)
    
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
    
    def get_path(self, path: str, default=None):
        """Standardized helper for dot-notation configuration access."""
        return self.get(path, default)
    def get(self, path: str, default=None):
        """Get configuration value using dot notation."""
        return get_nested(self._data, path, default)

    def _get(self, path: str, default=None):
        """Internal helper for property access. Alias for get_path()."""
        return self.get_path(path, default)
    
    # Properties for common values
    @property
    def discord_token(self) -> str:
        return self.get_path('discord.token', os.getenv('DISCORD_TOKEN', ''))
    
    @property
    def blacklisted_channels(self) -> list:
        channels = self.get_path('discord.blacklisted_channels', 'general,announcements,rules')
        if isinstance(channels, str):
            return [c.strip().lower() for c in channels.split(',')]
        return [c.lower() for c in channels]
    
    @property
    def whitelisted_channels(self) -> list:
        """List of channel names that are whitelisted"""
        channels = self.get_path('discord.whitelisted_channels', [])
        if channels is None:
            return []
        if isinstance(channels, str):
            return [c.strip().lower() for c in channels.split(',') if c.strip()]
        return [str(c).lower() for c in channels]
    
    @property
    def chat_model(self) -> str:
        return self.get_path('models.chat', 'gemma3:12b')
    
    @property
    def embedding_model(self) -> str:
        return self.get_path('models.embedding', 'nomic-embed-text-cpu')
    
    @property
    def knowledge_base_dir(self) -> str:
        return self.get_path('paths.knowledge_base', './knowledge_base')
    
    @property
    def persist_dir(self) -> str:
        return self.get_path('paths.persist', './memory')
    
    @property
    def max_log_size_mb(self) -> int:
        return self.get_path('performance.max_log_size_mb', 1000)
    
    @property
    def max_memory_messages(self) -> int:
        return self.get_path('performance.max_memory_messages', 35)
    
    @property
    def url_max_content_length(self) -> int:
        return self.get_path('performance.url_max_content_length', 2500)
    
    @property
    def max_consecutive_quips(self) -> int:
        return self.get_path('performance.max_consecutive_quips', 2)
    
    @property
    def rag_top_k(self) -> int:
        return self.get_path('performance.rag_top_k', 12)
    
    @property
    def rag_node_chunk_size(self) -> int:
        return self.get_path('performance.rag_node_chunk_size', 1024)
        
    @property
    def rag_node_chunk_overlap(self) -> int:
        return self.get_path('performance.rag_node_chunk_overlap', 200)

    @property
    def min_rag_tokens(self) -> int:
        return self.get_path('performance.min_rag_tokens', 1024)

    @property
    def rag_query_instruction(self) -> str:
        return self.get_path('rag.query_instruction', 'search_query: ')

    @property
    def rag_text_instruction(self) -> str:
        return self.get_path('rag.text_instruction', 'search_document: ')
    
    @property
    def dream_user_quota(self) -> float:
        """Percentage of dreams dedicated to user logs (0.0 - 1.0)"""
        return self.get_path('dream_mode.user_quota', 0.4)
    
    @property
    def idle_quip_timeout_minutes(self) -> int:
        return self.get_path('performance.idle_quip_timeout_minutes', 55)
    
    @property
    def requests_per_minute(self) -> int:
        return self.get_path('performance.requests_per_minute', 30)

    @property
    def num_thread(self) -> int:
        """Thread count for CPU-bound operations."""
        return self.get_path('performance.num_thread', 12)

    @property
    def embedding_request_seconds(self) -> float:
        return self.get_path('timeouts.embedding_request_seconds', 60.0)
    
    @property
    def max_context_tokens(self) -> int:
        return self.get_path('performance.max_context_tokens', 12000)
    
    @property
    def classification_context_tokens(self) -> int:
        return self.get_path('performance.classification_context_tokens', 2048)
    
    @property
    def embedding_context_tokens(self) -> int:
        return self.get_path('performance.embedding_context_tokens', 2048)
    
    @property
    def summarization_context_tokens(self) -> int:
        """Boosted context window for summarization tasks"""
        return self.get_path('performance.summarization_context_tokens', 12000)
    
    @property
    def startup_news_update(self) -> bool:
        return self.get_path('startup.news_update', False)
    
    @property
    def startup_news_timeout(self) -> int:
        return self.get_path('startup.news_timeout', 10)
    

    # Bluesky configuration
    @property
    def bluesky_enabled(self) -> bool:
        return self.get_path('bluesky.enabled', False)
    
    @property
    def bluesky_handle(self) -> str:
        return os.getenv("BLUESKY_HANDLE", "")
        
    @property
    def bluesky_password(self) -> str:
        return os.getenv("BLUESKY_APP_PASSWORD", "")
    
    @property
    def bluesky_cross_post_quips(self) -> bool:
        return self.get_path('bluesky.cross_post_quips', False)
    
    # X (Twitter) configuration
    @property
    def x_enabled(self) -> bool:
        return self.get_path('x_twitter.enabled', False)
    
    @property
    def x_cross_post_quips(self) -> bool:
        return self.get_path('x_twitter.cross_post_quips', False)
    
    @property
    def bluesky_reply_to_mentions(self) -> bool:
        return self.get_path('bluesky.reply_to_mentions', False)
    
    @property
    def x_reply_to_mentions(self) -> bool:
        return self.get_path('x_twitter.reply_to_mentions', False)
    
    @property
    def news_auto_trigger(self) -> bool:
        """Whether to automatically trigger news retrieval for relevant queries"""
        return self.get_path('features.news_auto_trigger', False)

    @property
    def url_fetching_enabled(self) -> bool:
        """Whether to automatically fetch and scrape URLs posted in chat"""
        return self.get_path('features.url_fetching_enabled', True)

    @property
    def social_max_interval_hours(self) -> float:
        """Maximum hours between social posts before forcing a quip"""
        return self.get_path('social.max_interval_hours', 2.0)
    
    # =========================================================================
    # RAG Threshold Configuration
    # =========================================================================
    @property
    def rag_threshold_persona(self) -> float:
        return self.get_path('performance.rag_thresholds.persona', 0.50)
    
    @property
    def rag_threshold_user_identity(self) -> float:
        return self.get_path('performance.rag_thresholds.user_identity', 0.50)
    
    @property
    def rag_threshold_knowledge(self) -> float:
        return self.get_path('performance.rag_thresholds.knowledge', 0.45)
    
    @property
    def rag_threshold_casual_penalty(self) -> float:
        return self.get_path('performance.rag_thresholds.casual_penalty', 0.10)
    
    # =========================================================================
    # Timeout Configuration (extracted from magic numbers)
    # =========================================================================
    @property
    def classification_timeout(self) -> float:
        """Query classification timeout in seconds"""
        return self.get_path('timeouts.classification_seconds', 35.0)
    
    @property
    def orchestration_classification_timeout(self) -> float:
        """Orchestration wait timeout for classification in seconds"""
        return self.get_path('timeouts.orchestration_classification_seconds', 45.0)
    
    @property
    def prewarm_timeout(self) -> float:
        """Model pre-warm timeout in seconds"""
        return self.get_path('timeouts.prewarm_seconds', 30.0)
    
    @property
    def rag_retrieval_timeout(self) -> float:
        """RAG retrieval timeout in seconds"""
        return self.get_path('timeouts.rag_retrieval_seconds', 30.0)
    
    @property
    def typing_indication_timeout(self) -> float:
        """Typing indication duration in seconds"""
        return self.get_path('timeouts.typing_indication_seconds', 2.0)
    
    @property
    def model_load_timeout(self) -> float:
        """Model load timeout in seconds"""
        return self.get_path('timeouts.model_load_seconds', 300.0)

    @property
    def rag_lock_seconds(self) -> float:
        """RAG internal lock timeout in seconds"""
        return self.get_path('timeouts.rag_lock_seconds', 10.0)

    @property
    def chat_generation_timeout(self) -> float:
        """Chat generation timeout in seconds"""
        return self.get_path('timeouts.chat_generation_seconds', 300.0)

    @property
    def llm_request_seconds(self) -> float:
        """LLM request timeout in seconds"""
        return self.get_path('timeouts.llm_request_seconds', 600.0)

    @property
    def classification_join_seconds(self) -> float:
        """Join timeout for classification task in seconds"""
        return self.get_path('timeouts.classification_join_seconds', 40.0)

    @property
    def shutdown_timeout(self) -> float:
        """Overall shutdown timeout in seconds"""
        return self.get_path('timeouts.shutdown_seconds', 120.0)

    @property
    def url_fetch_timeout(self) -> float:
        """URL fetch timeout in seconds"""
        return self.get_path('timeouts.url_fetch_seconds', 5.0)

    @property
    def shutdown_task_cancel_timeout(self) -> float:
        """Timeout for cancelling async tasks during shutdown in seconds"""
        return self.get_path('timeouts.shutdown_task_cancel_seconds', 5.0)

    @property
    def shutdown_model_unload_timeout(self) -> float:
        """Timeout for unloading models during shutdown in seconds"""
        return self.get_path('timeouts.shutdown_model_unload_seconds', 5.0)

    # =========================================================================
    # RAG Scoring & Boosts
    # =========================================================================
    @property
    def rag_base_score_multiplier(self) -> float:
        return self.get_path('performance.rag_scoring.base_score_multiplier', 60.0)

    @property
    def rag_path_boost(self) -> float:
        return self.get_path('performance.rag_scoring.path_boost', 0.5)

    @property
    def rag_type_boosts(self) -> dict:
        # Fix #3: Fallback must mirror the YAML schema exactly.
        # 'memory' was a dead key — real source_types are 'user_logs' and 'knowledge'.
        return self.get_path('performance.rag_scoring.type_boosts', {
            'persona': 0.40,
            'user_profile': 0.20,
            'dream': 0.10,
            'user_logs': 0.25,
            'knowledge': -0.20
        })

    @property
    def rag_boost_daily_news(self) -> int:
        return self.get_path('performance.rag_boosts.daily_news', 172800)

    @property
    def rag_boost_dreams(self) -> int:
        return self.get_path('performance.rag_boosts.dreams', 64800)

    @property
    def rag_user_scan_interval(self) -> int:
        return self.get_path('performance.rag_boosts.user_scan_interval', 300)

    @property
    def rag_audit_flag_penalty(self) -> float:
        """Score penalty per audit flag on a RAG node"""
        return self.get_path('audit.flag_penalty', 0.15)
    
    # =========================================================================
    # Token Estimation Configuration
    # =========================================================================
    @property
    def token_multiplier(self) -> float:
        """Multiplier for word-to-token estimation (1.3 default for English)"""
        return self.get_path('performance.token_multiplier', 1.6)
    
    @property
    def system_reserve_tokens(self) -> int:
        """Reserved tokens for system reinforcement rules and safety prompts"""
        return self.get_path('performance.system_reserve_tokens', 1250)
    
    # =========================================================================
    # Generation Configuration (Self-Healing Loop)
    # =========================================================================
    @property
    def generation_max_retry_attempts(self) -> int:
        """Maximum retry attempts for failed LLM calls"""
        return self.get_path('generation.max_retry_attempts', 3)
    
    @property
    def generation_base_temperature(self) -> float:
        """Base temperature for generation"""
        return self.get_path('generation.base_temperature', 0.8)
    
    @property
    def generation_temperature_scaling(self) -> float:
        """Temperature increment per retry attempt"""
        return self.get_path('generation.temperature_scaling', 0.15)
    
    @property
    def generation_fallback_num_predict(self) -> int:
        """Fallback num_predict on context reduction"""
        return self.get_path('generation.fallback_num_predict', 512)

    @property
    def max_response_tokens(self) -> int:
        """Maximum number of tokens to generate in a response"""
        return self.get_path('generation.max_response_tokens', 768)

    
    @property
    def ignored_users(self) -> list:
        """List of users to ignore (names or IDs)"""
        users = self.get_path('discord.ignored_users', [])
        if users is None:
            return []
        if isinstance(users, str):
            return [u.strip().lower() for u in users.split(',') if u.strip()]
        return [str(u).lower() for u in users]

    @property
    def owner_ids(self) -> list:
        """List of owner/admin users who bypass cooldowns (names or IDs)"""
        owners = self.get_path('discord.owner_ids', 'ekco')
        if owners is None:
            return ['ekco']
        if isinstance(owners, str):
            return [o.strip().lower() for o in owners.split(',') if o.strip()]
        return [str(o).lower() for o in owners]
    
    def is_owner(self, author_name: str, display_name: str = None, user_id: str = None) -> bool:
        """Check if a user is an owner/admin.
        
        Uses exact matching with trailing-period normalization for Discord
        username compatibility (e.g., 'ekco.' matches 'ekco').
        """
        owner_list = self.owner_ids
        # Normalize: strip trailing periods (Discord adds them to some usernames)
        normalized_owners = {o.rstrip('.') for o in owner_list}
        
        checks = [author_name.lower().rstrip('.')]
        if display_name:
            checks.append(display_name.lower().rstrip('.'))
        if user_id:
            checks.append(str(user_id).lower())
        
        return any(c in normalized_owners for c in checks)

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
