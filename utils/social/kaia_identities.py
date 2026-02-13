"""
Kaia Identity Manager
=====================

Handles cross-platform identity linking (Discord, Forum, etc).
Stores mappings in knowledge_base/identity_registry.json.
"""

import json
import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime

from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error, log_action

class IdentityRegistry:
    REGISTRY_PATH = Path("./knowledge_base/identity_registry.json")

    def __init__(self):
        self.data: Dict[str, Any] = {
            "discord_to_forum": {},  # discord_id -> forum_id
            "forum_to_discord": {},  # forum_id -> discord_id
            "mappings": {}           # discord_id -> {platform: id, ...}
        }
        self._load()

    def _load(self):
        if self.REGISTRY_PATH.exists():
            try:
                content = self.REGISTRY_PATH.read_text(encoding='utf-8')
                if content.strip():
                    self.data = json.loads(content)
            except Exception as e:
                log_error(f"Failed to load identity registry: {e}")

    def _save(self):
        try:
            self.REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.REGISTRY_PATH.write_text(json.dumps(self.data, indent=4), encoding='utf-8')
        except Exception as e:
            log_error(f"Failed to save identity registry: {e}")

    def link_discord_to_forum(self, discord_id: str, forum_id: int):
        """Link a Discord ID to a Forum ID."""
        fid_str = str(forum_id)
        self.data["discord_to_forum"][discord_id] = forum_id
        self.data["forum_to_discord"][fid_str] = discord_id
        
        if discord_id not in self.data["mappings"]:
            self.data["mappings"][discord_id] = {}
        self.data["mappings"][discord_id]["forum"] = forum_id
        
        self._save()
        log_success(f"Linked Discord {discord_id} to Forum UID {forum_id}")

    def get_forum_id(self, discord_id: str) -> Optional[int]:
        return self.data["discord_to_forum"].get(discord_id)

    def get_discord_id(self, forum_id: int) -> Optional[str]:
        return self.data["forum_to_discord"].get(str(forum_id))

    def get_all_links(self, discord_id: str) -> Dict[str, Any]:
        return self.data["mappings"].get(discord_id, {})

# Singleton instance
registry = IdentityRegistry()
