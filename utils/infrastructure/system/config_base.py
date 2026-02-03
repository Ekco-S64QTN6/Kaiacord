"""
Configuration Manager
=====================

Centralized configuration management for Kaiacord.

Extracted from Kaiacord.py to improve modularity.
"""

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    """Configuration management for Kaiacord"""
    discord_token: str = field(default_factory=lambda: os.getenv('DISCORD_TOKEN'))
    blacklisted_channels: List[str] = field(default_factory=lambda: os.getenv('BLACKLISTED_CHANNELS', 'general,announcements,rules').split(','))
    
    # Models
    chat_model: str = "gemma3:12b"
    vision_model: str = "llama3.2-vision:11b"
    embedding_model: str = "nomic-embed-text"
    
    # RAG
    knowledge_base_dir: str = "./knowledge_base"
    persist_dir: str = "./memory"
    max_log_size_mb: int = 100
    
    # Performance
    max_memory_messages: int = 30  # Increased for better context
    max_consecutive_quips: int = 3
    rag_top_k: int = 8  # Increased to find more relevant history
    
    # Rate Limiting
    requests_per_minute: int = 30
    
    # Startup
    startup_news_update: bool = False  # Set to False to skip news update on startup
    startup_news_timeout: int = 10  # Timeout in seconds for news update

    def should_use_cache(self, query_text: str, query_classification: str) -> bool:
        """Determine if semantic cache should be used for this query"""
        # NEVER use cache for identity questions
        if query_classification in ["IDENTITY", "SELF", "WHOAMI"]:
            return False
        
        # Never use cache for "who are you" or "who am i"
        identity_keywords = ["who are you", "who am i", "what are you", "define yourself"]
        if any(keyword in query_text.lower() for keyword in identity_keywords):
            return False
        
        return True

    @classmethod
    def from_env(cls):
        """Create config from environment variables"""
        return cls()


# Global config instance for backward compatibility
config = Config.from_env()
