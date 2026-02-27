import os
import json
import time
import asyncio
from pathlib import Path
from collections import deque
from typing import Set, Dict, List, Optional, Any
from utils.infrastructure.logging.kaia_logger import log_info, log_debug, log_warning, log_error

class SocialTracker:
    """
    Persistent, high-performance tracker for social media interactions.
    Uses an append-only log for fast writes and a deque for efficient memory management.
    """
    def __init__(self, 
                 log_path: str = "memory/social_replied.log",
                 state_path: str = "memory/social_state.json",
                 max_ids: int = 5000):
        self.log_path = Path(log_path)
        self.state_path = Path(state_path)
        self.max_ids = max_ids
        
        # In-memory storage
        self._replied_ids = set()
        self._replied_deque = deque(maxlen=max_ids)
        self._thread_counts = {} # {root_uri: {user_handle: count}}
        self._lock = asyncio.Lock()
        
        # Ensure directory exists
        self.log_path.parent.mkdir(exist_ok=True)
        
        self._load()

    def _load(self):
        """Initial load from state file and log file."""
        # 1. Load baseline state from JSON (snapshot)
        if self.state_path.exists():
            try:
                with open(self.state_path, 'r') as f:
                    state = json.load(f)
                    
                    raw_thread_counts = state.get('thread_counts', {})
                    # MIGRATION: Ensure thread_counts is Dict[str, Dict[str, int]]
                    if raw_thread_counts and not all(isinstance(v, dict) for v in raw_thread_counts.values()):
                        log_info("[SocialTracker] Migrating legacy (flat) thread counts...")
                        new_counts = {}
                        for k, v in raw_thread_counts.items():
                            if isinstance(v, dict):
                                new_counts[k] = v
                            else:
                                new_counts[k] = {"__legacy_total__": v}
                        self._thread_counts = new_counts
                    else:
                        self._thread_counts = raw_thread_counts
                    
                    initial_ids = state.get('replied_ids', [])
                    for rid in initial_ids[-self.max_ids:]:
                        if rid not in self._replied_ids:
                            self._replied_ids.add(rid)
                            self._replied_deque.append(rid)
                log_debug(f"[SocialTracker] Loaded baseline state: {len(self._replied_ids)} IDs")
            except Exception as e:
                log_warning(f"[SocialTracker] Failed to load state file: {e}")

        # 2. Replay append-only log for any missing IDs
        if self.log_path.exists():
            try:
                count = 0
                with open(self.log_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and line not in self._replied_ids:
                            self._replied_ids.add(line)
                            self._replied_deque.append(line)
                            count += 1
                if count > 0:
                    log_debug(f"[SocialTracker] Replayed {count} IDs from log")
            except Exception as e:
                log_warning(f"[SocialTracker] Failed to replay log: {e}")

    def is_replied(self, mention_id: str) -> bool:
        """Check if an ID has already been replied to."""
        return mention_id in self._replied_ids

    def get_all_replied_ids(self) -> Set[str]:
        """Get all IDs in the current session set."""
        return self._replied_ids.copy()

    def get_thread_count(self, root_uri: str, user_handle: str) -> int:
        """Get number of times we've replied to this user in this thread."""
        return self._thread_counts.get(root_uri, {}).get(user_handle, 0)

    async def mark_replied(self, mention_id: str, platform: str, root_uri: Optional[str], user_handle: str):
        """Mark an ID as replied and update thread counts."""
        async with self._lock:
            if mention_id in self._replied_ids:
                return

            # Update memory
            # If deque is full, remove oldest from set
            if len(self._replied_deque) == self.max_ids:
                oldest = self._replied_deque[0]
                if oldest in self._replied_ids:
                    self._replied_ids.remove(oldest)
            
            self._replied_ids.add(mention_id)
            self._replied_deque.append(mention_id)
            
            if root_uri:
                if root_uri not in self._thread_counts:
                    self._thread_counts[root_uri] = {}
                self._thread_counts[root_uri][user_handle] = self._thread_counts[root_uri].get(user_handle, 0) + 1
            
            # Persist: Append to log (fast but still potentially blocking)
            def _append_to_log():
                try:
                    with open(self.log_path, 'a') as f:
                        f.write(f"{mention_id}\n")
                except Exception as e:
                    log_error(f"[SocialTracker] Failed to append to log: {e}")

            await asyncio.to_thread(_append_to_log)

    async def save_snapshot(self):
        """Save full state snapshot and truncate log."""
        async with self._lock:
            def _write_snapshot():
                try:
                    state = {
                        'replied_ids': list(self._replied_deque),
                        'thread_counts': self._thread_counts,
                        'last_updated': time.time()
                    }
                    with open(self.state_path, 'w') as f:
                        json.dump(state, f, indent=2)
                    
                    # Truncate log as it's now synced to state
                    if self.log_path.exists():
                        self.log_path.unlink()
                    
                    log_info(f"[SocialTracker] Saved state snapshot to {self.state_path}")
                except Exception as e:
                    log_error(f"[SocialTracker] Failed to save state snapshot: {e}")

            await asyncio.to_thread(_write_snapshot)

# Singleton instance
social_tracker = SocialTracker()
