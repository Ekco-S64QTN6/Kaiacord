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
            "discord_to_forum": {},  # discord_id -> List[int]
            "forum_to_discord": {},  # forum_id -> discord_id
            "mappings": {},          # discord_id -> {platform: [ids], ...}
            # Kaia's own accounts. Without this her forum account is just
            # another poster: `forum_Kaia_322197/user_profile.md` read
            # "a forum user... haven't formed a strong opinion yet — need to
            # see more of their posts", which is a memory of herself as a
            # stranger, retrievable in conversation.
            "self_forum_ids": [],
            "display_names": {},     # discord_id -> the name a human uses
        }
        self._load()
        # Older files predate these keys.
        for k, default in (("self_forum_ids", []), ("display_names", {})):
            self.data.setdefault(k, default)

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
        """Link a Discord ID to a Forum ID (supports multiple)."""
        fid_str = str(forum_id)
        
        # discord_to_forum (list)
        if discord_id not in self.data["discord_to_forum"]:
            self.data["discord_to_forum"][discord_id] = []
        elif isinstance(self.data["discord_to_forum"][discord_id], int):
            # Migration for old singular integer
            self.data["discord_to_forum"][discord_id] = [self.data["discord_to_forum"][discord_id]]
            
        if forum_id not in self.data["discord_to_forum"][discord_id]:
            self.data["discord_to_forum"][discord_id].append(forum_id)
            
        self.data["forum_to_discord"][fid_str] = discord_id
        
        if discord_id not in self.data["mappings"]:
            self.data["mappings"][discord_id] = {}
        
        if "forum" not in self.data["mappings"][discord_id]:
            self.data["mappings"][discord_id]["forum"] = []
        elif isinstance(self.data["mappings"][discord_id]["forum"], int):
            # Migration
            self.data["mappings"][discord_id]["forum"] = [self.data["mappings"][discord_id]["forum"]]
            
        if forum_id not in self.data["mappings"][discord_id]["forum"]:
            self.data["mappings"][discord_id]["forum"].append(forum_id)
        
        self._save()
        log_success(f"Linked Discord {discord_id} to Forum UID {forum_id}")

    def get_forum_ids(self, discord_id: str) -> List[int]:
        """Get all forum IDs for a discord ID."""
        val = self.data["discord_to_forum"].get(discord_id, [])
        if isinstance(val, int):
            return [val]
        return val

    def get_discord_id(self, forum_id: int) -> Optional[str]:
        return self.data["forum_to_discord"].get(str(forum_id))

    def get_all_links(self, discord_id: str) -> Dict[str, Any]:
        return self.data["mappings"].get(discord_id, {})

    # ── Self ─────────────────────────────────────────────────────────

    def mark_self(self, forum_id: int) -> None:
        """Record a forum account as Kaia's own."""
        fid = int(forum_id)
        if fid not in self.data["self_forum_ids"]:
            self.data["self_forum_ids"].append(fid)
            self._save()
            log_success(f"Forum UID {fid} marked as Kaia's own account")

    def is_self(self, forum_id: Any) -> bool:
        """True if this forum account is Kaia herself.

        Callers use this to avoid building a stranger-profile of her own
        account, and to avoid retrieving one as if it described someone else.
        """
        try:
            return int(forum_id) in self.data.get("self_forum_ids", [])
        except (TypeError, ValueError):
            return False

    # ── Names ────────────────────────────────────────────────────────

    def set_display_name(self, discord_id: str, name: str) -> None:
        if name and self.data["display_names"].get(discord_id) != name:
            self.data["display_names"][discord_id] = name
            self._save()

    def display_name(self, discord_id: str) -> Optional[str]:
        return self.data.get("display_names", {}).get(str(discord_id))

    @staticmethod
    def _is_discord_id(value: Any) -> bool:
        """Discord ids are snowflakes — 17-19 digits.

        The registry also holds synthetic grouping keys like
        `Identity_Brad_Shovel`, which say two *forum* accounts are one person
        without claiming a Discord identity. Presenting one of those as a name
        produced "shovelquest — this is Identity_Brad_Shovel from Discord".
        """
        v = str(value or "")
        return v.isdigit() and 17 <= len(v) <= 19

    def describe_forum_user(self, forum_id: Any) -> Optional[str]:
        """The Discord name behind a forum account, or None for a stranger.

        The profile generator uses this so a person she talks to daily is not
        written up as an unknown poster.
        """
        did = self.get_discord_id(forum_id)
        if not did or not self._is_discord_id(did):
            return None
        return self.display_name(did) or did

    def other_accounts(self, forum_id: Any) -> List[int]:
        """Other forum accounts belonging to whoever owns this one.

        Works for the synthetic groupings too — two forum handles can be known
        to be the same person without either being linked to Discord.
        """
        owner = self.get_discord_id(forum_id)
        if not owner:
            return []
        try:
            fid = int(forum_id)
        except (TypeError, ValueError):
            return []
        return [f for f in self.get_forum_ids(owner) if f != fid]

# Singleton instance
registry = IdentityRegistry()
