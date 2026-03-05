"""
Bot State Manager
=================

Encapsulates global bot state and persistence.

Extracted from Kaiacord.py to improve modularity.
"""

import os
import json
import time
import threading
import traceback
from typing import Dict, Deque, Optional
from collections import deque
from utils.infrastructure.logging.kaia_logger import log_info, log_warning


class BotState:
    """Encapsulates global bot state and persistence (thread-safe)"""
    def __init__(self, state_file: str = "memory/bot_state.json"):
        self.state_file = state_file
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()  # Prevents concurrent _persist_to_disk writes
        self.channel_memory: Dict[int, Deque[Dict[str, str]]] = {}
        self.last_interaction_time: float = time.time()
        self.last_active_channel_id: Optional[int] = None
        self.consecutive_quips: int = 0
        self.last_manual_quip_time: float = 0.0
        self.last_quip_time: float = 0.0  # Time of last generated quip (manual or idle)
        self.quip_history: Deque[str] = deque(maxlen=10)
        self.is_generating_image: bool = False
        self._boot_complete: bool = False
        self.boot_complete_time: float = 0.0
        self.recent_ingestions: list = []  # List of filenames recently ingested
        self.last_dream_date: str = ""    # YYYY-MM-DD of last nightly dream
        self.mentioned_files: Deque[str] = deque(maxlen=20) # Path of files mentioned
        self.is_generating: bool = False     # Transient: True while LLM is generating a user response
        self.load()

    def load(self):
        """Load persisted bot state from JSON file"""
        try:
            if os.path.exists(self.state_file) and os.path.getsize(self.state_file) > 0:
                with self._lock:
                    with open(self.state_file, 'r') as f:
                        state = json.load(f)
                        self.last_active_channel_id = state.get('last_active_channel_id')
                        self.consecutive_quips = state.get('consecutive_quips', 0)
                        self.last_manual_quip_time = state.get('last_manual_quip_time', 0.0)
                        self.last_quip_time = state.get('last_quip_time', 0.0)
                        self.recent_ingestions = state.get('recent_ingestions', [])
                        self.last_dream_date = state.get('last_dream_date', "")
                        
                        # boot_complete is TRANSIENT - do not load from disk
                        self.boot_complete = False
                        self.boot_complete_time = 0.0
                        
                        # Load quip history
                        history = state.get('quip_history', [])
                        self.quip_history = deque(history, maxlen=10)
                        
                        # Load mentioned files
                        mentions = state.get('mentioned_files', [])
                        self.mentioned_files = deque(mentions, maxlen=20)
                        
                        # Load memory contexts.
                        # Type contract: channel_memory uses int keys (Discord channel IDs).
                        # JSON always serialises keys as strings, so we cast back to int on load.
                        raw_mem = state.get('channel_memory', {})
                        # maxlen must match config.max_memory_messages (default 35).
                        # Was hardcoded to 5, silently truncating history on every restart.
                        from utils.infrastructure.system.yaml_config import config as _cfg
                        _maxlen = getattr(_cfg, 'max_memory_messages', 35)
                        self.channel_memory = {
                            int(k): deque(v, maxlen=_maxlen)
                            for k, v in raw_mem.items()
                            if str(k).isdigit()
                        }

        except Exception as e:
            log_warning(f"Failed to load bot state: {e}\n{traceback.format_exc()}")

    def save(self):
        """Save bot state to JSON file (thread-safe)"""
        try:
            with self._lock:
                # Ensure directory exists if one is specified
                dirname = os.path.dirname(self.state_file)
                if dirname:
                    os.makedirs(dirname, exist_ok=True)

                
                state = {
                    'last_active_channel_id': self.last_active_channel_id,
                    'consecutive_quips': self.consecutive_quips,
                    'last_manual_quip_time': self.last_manual_quip_time,
                    'last_quip_time': self.last_quip_time,
                    'quip_history': list(self.quip_history),
                    'recent_ingestions': self.recent_ingestions,
                    'last_dream_date': self.last_dream_date,
                    # boot_complete is TRANSIENT - do not save to disk
                    'mentioned_files': list(self.mentioned_files),
                    # Explicitly cast int keys to str for JSON serialisation (JSON keys must be strings).
                    'channel_memory': {str(k): list(v) for k, v in self.channel_memory.items()},
                    'saved_at': time.time()
                }
                
                # Offload the actual I/O to a background thread to prevent loop stalls
                threading.Thread(target=self._persist_to_disk, args=(state,), daemon=True).start()
        except Exception as e:
            log_warning(f"Failed to initiate bot state save: {e}")

    def _persist_to_disk(self, state: dict):
        """Actual disk I/O performed in background thread.
        
        Uses a dedicated write lock + atomic temp-file swap to prevent
        concurrent writes from corrupting the file.
        """
        if not self._write_lock.acquire(blocking=False):
            # Another write is already in progress — skip this one.
            # The next save() call will capture fresher state anyway.
            return
        try:
            tmp_path = self.state_file + ".tmp"
            with open(tmp_path, 'w') as f:
                json.dump(state, f, indent=2)
            os.replace(tmp_path, self.state_file)
        except Exception as e:
            log_warning(f"Background save failed for bot state: {e}")
        finally:
            self._write_lock.release()

    def reset_quips(self):
        """Reset consecutive quips counter"""
        self.consecutive_quips = 0
        self.save()

    def increment_quips(self):
        """Increment consecutive quips counter"""
        self.consecutive_quips += 1
        self.save()

    def update_interaction(self, channel_id: int):
        """Update last interaction time and channel"""
        self.last_interaction_time = time.time()
        if self.last_active_channel_id != channel_id:
            self.last_active_channel_id = channel_id
            self.save()

    def add_quip(self, quip: str):
        """Add a quip to history to avoid repetition"""
        self.quip_history.append(quip)
        self.last_manual_quip_time = time.time()
        self.last_quip_time = time.time()
        self.save()

    def get_recent_quips(self) -> list:
        """Get list of recent quips"""
        return list(self.quip_history)

    def add_ingestion(self, filename: str, snippet: str = ""):
        """Track a newly ingested document with an optional content snippet"""
        # Remove old entry if it exists to update it
        self.recent_ingestions = [i for i in self.recent_ingestions if i.get('filename') != filename]
        
        self.recent_ingestions.append({
            'filename': filename,
            'snippet': snippet,
            'timestamp': time.time()
        })
        
        # Keep only the last 10 ingestions
        if len(self.recent_ingestions) > 10:
            self.recent_ingestions.pop(0)
        self.save()

    def clear_ingestions(self):
        """Clear the list of recent ingestions after they've been mentioned"""
        self.recent_ingestions = []
        self.save()

    def add_mentioned_file(self, file_path: str):
        """Track which archive file was mentioned to avoid repetition"""
        if file_path not in self.mentioned_files:
            self.mentioned_files.append(file_path)
            self.save()
    @property
    def boot_complete(self) -> bool:
        return self._boot_complete

    @boot_complete.setter
    def boot_complete(self, value: bool):
        self._boot_complete = value
        if value:
            self.boot_complete_time = time.time()
            log_info("Bot startup marked complete.")


# Global bot_state instance for backward compatibility
bot_state = BotState()
