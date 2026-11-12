"""
Kaia Identity Manager
=====================

Handles cross-platform identity linking (Discord, Forum, etc).
Stores mappings in knowledge_base/identity_registry.json.
"""

import json
import copy
import hmac
import threading
import time
from pathlib import Path
from typing import Optional, Dict, List, Any

from utils.infrastructure.logging.kaia_logger import log_success, log_error
from utils.core.atomic_write import write_atomic

class IdentityRegistry:
    REGISTRY_PATH = Path("./knowledge_base/identity_registry.json")

    def __init__(self):
        self._lock = threading.RLock()
        # Short-lived proof challenges are process-local and never persisted.
        # A restart invalidates them; claim tokens are not written to disk.
        self._pending_forum_links: Dict[str, Dict[str, Any]] = {}
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
        # Older files predate some keys; a file missing one raised KeyError on
        # the first link or lookup.
        for k, default in (("discord_to_forum", {}), ("forum_to_discord", {}), ("mappings", {}),
                           ("self_forum_ids", []), ("display_names", {})):
            self.data.setdefault(k, default)

    def _load(self):
        if self.REGISTRY_PATH.exists():
            try:
                content = self.REGISTRY_PATH.read_text(encoding='utf-8')
                if content.strip():
                    self.data = json.loads(content)
            except Exception as e:
                log_error(f"Failed to load identity registry: {e}")

    def _save(self) -> bool:
        try:
            self.REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(self.REGISTRY_PATH, json.dumps(self.data, indent=4))
            return True
        except Exception as e:
            log_error(f"Failed to save identity registry: {e}")
            return False

    def _link_discord_to_forum_locked(self, discord_id: str, forum_id: int) -> None:
        """Update both directions consistently; caller holds _lock."""
        fid = int(forum_id)
        fid_str = str(fid)
        current_owner = self.data["forum_to_discord"].get(fid_str)
        # Previous versions stored "<display_name>_<snowflake>". Only a fresh
        # proof from that exact numeric Discord account may canonicalize its
        # own legacy entry; never import it as verified without the challenge.
        legacy_same_owner = bool(
            current_owner
            and current_owner != discord_id
            and str(current_owner).endswith("_" + discord_id)
        )
        if current_owner and current_owner != discord_id and not legacy_same_owner:
            raise ValueError("forum account is already linked to another Discord account; unlink it first")

        # Repair stale forward references left by older unconditional overwrites.
        for owner, account_ids in list(self.data["discord_to_forum"].items()):
            normalized = [account_ids] if isinstance(account_ids, int) else list(account_ids or [])
            if owner != discord_id and fid in normalized:
                normalized = [value for value in normalized if int(value) != fid]
                if normalized:
                    self.data["discord_to_forum"][owner] = normalized
                else:
                    self.data["discord_to_forum"].pop(owner, None)
                other = self.data["mappings"].get(owner, {}).get("forum", [])
                other = [other] if isinstance(other, int) else list(other or [])
                other = [value for value in other if int(value) != fid]
                if other:
                    self.data["mappings"][owner]["forum"] = other
                elif owner in self.data["mappings"]:
                    self.data["mappings"][owner].pop("forum", None)

        accounts = self.data["discord_to_forum"].setdefault(discord_id, [])
        if isinstance(accounts, int):
            accounts = [accounts]
            self.data["discord_to_forum"][discord_id] = accounts
        if fid not in accounts:
            accounts.append(fid)

        mapping = self.data["mappings"].setdefault(discord_id, {})
        forum_accounts = mapping.setdefault("forum", [])
        if isinstance(forum_accounts, int):
            forum_accounts = [forum_accounts]
            mapping["forum"] = forum_accounts
        if fid not in forum_accounts:
            forum_accounts.append(fid)
        self.data["forum_to_discord"][fid_str] = discord_id

    def begin_pending_forum_link(self, discord_id: str, forum_id: int,
                                 challenge: str, expires_at: float) -> None:
        """Create a short-lived, single-use proof request without activating a link."""
        discord_id = str(discord_id)
        fid_str = str(int(forum_id))
        if not self._is_discord_id(discord_id):
            raise ValueError("Discord identity must be a numeric snowflake")
        if not challenge or float(expires_at) <= time.time():
            raise ValueError("invalid or expired proof challenge")

        with self._lock:
            current_owner = self.data["forum_to_discord"].get(fid_str)
            if current_owner == discord_id:
                raise ValueError("this forum account is already linked to you")
            legacy_same_owner = bool(
                current_owner
                and str(current_owner).endswith("_" + discord_id)
            )
            if current_owner and current_owner != discord_id and not legacy_same_owner:
                raise ValueError("this forum account is already linked; its current owner must unlink it first")
            pending = self._pending_forum_links.get(fid_str)
            if pending and pending["expires_at"] > time.time() and pending["discord_id"] != discord_id:
                raise ValueError("another Discord member already has a pending proof request for this forum account")
            self._pending_forum_links[fid_str] = {
                "discord_id": discord_id,
                "challenge": str(challenge),
                "expires_at": float(expires_at),
            }

    def pending_forum_link_challenge(self, discord_id: str, forum_id: int) -> Optional[str]:
        """Return the challenge only to its requester and only before expiry."""
        fid_str = str(int(forum_id))
        with self._lock:
            pending = self._pending_forum_links.get(fid_str)
            if not pending:
                return None
            if pending["expires_at"] <= time.time():
                self._pending_forum_links.pop(fid_str, None)
                return None
            if pending["discord_id"] != str(discord_id):
                return None
            return pending["challenge"]

    def cancel_pending_forum_link(self, discord_id: str, forum_id: int) -> bool:
        """Discard a pending challenge when private delivery fails."""
        fid_str = str(int(forum_id))
        with self._lock:
            pending = self._pending_forum_links.get(fid_str)
            if not pending or pending["discord_id"] != str(discord_id):
                return False
            self._pending_forum_links.pop(fid_str, None)
            return True

    def complete_pending_forum_link(self, discord_id: str, forum_id: int,
                                    challenge: str) -> bool:
        """Activate a pending link only when its exact one-use challenge matches."""
        fid_str = str(int(forum_id))
        discord_id = str(discord_id)
        with self._lock:
            pending = self._pending_forum_links.get(fid_str)
            if not pending or pending["discord_id"] != discord_id:
                return False
            if pending["expires_at"] <= time.time():
                self._pending_forum_links.pop(fid_str, None)
                return False
            if not hmac.compare_digest(pending["challenge"], str(challenge or "")):
                return False

            before = copy.deepcopy(self.data)
            self._link_discord_to_forum_locked(discord_id, int(forum_id))
            if not self._save():
                self.data = before
                raise RuntimeError("identity registry could not be saved; link was not activated")
            self._pending_forum_links.pop(fid_str, None)
            return True

    def unlink_forum_from_discord(self, discord_id: str, forum_id: int) -> bool:
        """Remove both sides of an existing mapping; caller must authorize this action."""
        discord_id = str(discord_id)
        fid = int(forum_id)
        fid_str = str(fid)
        with self._lock:
            if self.data["forum_to_discord"].get(fid_str) != discord_id:
                return False
            before = copy.deepcopy(self.data)
            self.data["forum_to_discord"].pop(fid_str, None)
            accounts = self.data["discord_to_forum"].get(discord_id, [])
            accounts = [accounts] if isinstance(accounts, int) else list(accounts or [])
            accounts = [value for value in accounts if int(value) != fid]
            if accounts:
                self.data["discord_to_forum"][discord_id] = accounts
            else:
                self.data["discord_to_forum"].pop(discord_id, None)
            mapping = self.data["mappings"].get(discord_id, {})
            forum_accounts = mapping.get("forum", [])
            forum_accounts = [forum_accounts] if isinstance(forum_accounts, int) else list(forum_accounts or [])
            forum_accounts = [value for value in forum_accounts if int(value) != fid]
            if forum_accounts:
                mapping["forum"] = forum_accounts
            else:
                mapping.pop("forum", None)
            if not self._save():
                self.data = before
                raise RuntimeError("identity registry could not be saved; mapping was not removed")
            return True

    def link_discord_to_forum(self, discord_id: str, forum_id: int):
        """Link a Discord ID to a Forum ID; never silently reassign an owner."""
        with self._lock:
            before = copy.deepcopy(self.data)
            self._link_discord_to_forum_locked(str(discord_id), int(forum_id))
            if not self._save():
                self.data = before
                raise RuntimeError("identity registry could not be saved; link was not activated")
        log_success(f"Linked Discord {discord_id} to Forum UID {forum_id}")

    def get_forum_ids(self, discord_id: str) -> List[int]:
        """Get all forum IDs for a discord ID."""
        with self._lock:
            val = self.data["discord_to_forum"].get(str(discord_id), [])
            if isinstance(val, int):
                return [val]
            return list(val or [])

    def get_discord_id(self, forum_id: int) -> Optional[str]:
        with self._lock:
            return self.data["forum_to_discord"].get(str(forum_id))

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
        if not name:
            return
        with self._lock:
            key = str(discord_id)
            previous = self.data["display_names"].get(key)
            if previous == name:
                return
            self.data["display_names"][key] = name
            if not self._save():
                if previous is None:
                    self.data["display_names"].pop(key, None)
                else:
                    self.data["display_names"][key] = previous
                raise RuntimeError("identity registry could not save the display name")

    def display_name(self, discord_id: str) -> Optional[str]:
        with self._lock:
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
