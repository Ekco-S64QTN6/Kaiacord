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
        self.first_chat_done: bool = False   # Transient: True after first successful LLM response
        self.last_evening_reflection: str = ""  # YYYY-MM-DD, persisted
        self.last_dawn_date: str = ""           # YYYY-MM-DD, persisted

        # Kaia mood state — 3 floats, all 0.0–1.0, persisted across restarts.
        # Used to inject a single context line into the system prompt.
        # engagement: how much has she been talked to recently (updated per message)
        # coherence: rolling average RAG retrieval confidence (updated per retrieval)
        # dream_freshness: how recently the dream cycle ran successfully (decays over time)
        self.kaia_engagement: float = 0.5
        self.kaia_coherence: float = 0.85
        self.kaia_dream_freshness: float = 1.0

        # Curiosity injection: tracks when we last sent a follow-up prompt per user
        # Format: { "user_id_str": unix_timestamp_float }
        self.curiosity_last_sent: dict = {}
        self.forum_reply_times: dict = {}  # {thread_id_str: float timestamp}

        # Per-user relationship state — persisted across restarts.
        # Schema per user_id key:
        # {
        #     "first_seen": float (unix ts),
        #     "last_seen": float (unix ts),
        #     "interaction_count": int,
        #     "familiarity": float 0-1 (EMA of interaction frequency),
        #     "emotional_valence": float 0-1 (EMA, 0=negative, 1=positive),
        #     "topic_counts": dict {str: int},
        #     "last_open_loop": str (description of last unresolved thread)
        # }
        self.relationships: Dict[str, dict] = {}
        
        # Format: [{"channel_id": int, "user_id": int, "user_name": str, "timestamp": float, "topic": str}]
        self.pending_afterthoughts: list = []

        # Per-channel last-activity timestamps for afterthought silence checks
        self.channel_last_activity: Dict[int, float] = {}

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
                        self.kaia_engagement = float(state.get('kaia_engagement', 0.5))
                        self.kaia_coherence = float(state.get('kaia_coherence', 0.85))
                        self.kaia_dream_freshness = float(state.get('kaia_dream_freshness', 1.0))
                        self.curiosity_last_sent = state.get('curiosity_last_sent', {})
                        self.last_evening_reflection = state.get('last_evening_reflection', "")
                        self.last_dawn_date = state.get('last_dawn_date', "")
                        self.forum_reply_times = state.get('forum_reply_times', {})
                        self.relationships = state.get('relationships', {})
                        self.pending_afterthoughts = state.get('pending_afterthoughts', [])
                        
                        # Per-channel activity — keys stored as strings in JSON
                        raw_activity = state.get('channel_last_activity', {})
                        self.channel_last_activity = {
                            int(k): float(v) for k, v in raw_activity.items()
                            if str(k).isdigit()
                        }
                        
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
                    'kaia_engagement': self.kaia_engagement,
                    'kaia_coherence': self.kaia_coherence,
                    'kaia_dream_freshness': self.kaia_dream_freshness,
                    'curiosity_last_sent': self.curiosity_last_sent,
                    'last_evening_reflection': self.last_evening_reflection,
                    'last_dawn_date': self.last_dawn_date,
                    'forum_reply_times': self.forum_reply_times,
                    'relationships': self.relationships,
                    'pending_afterthoughts': self.pending_afterthoughts,
                    'channel_last_activity': {str(k): v for k, v in self.channel_last_activity.items()},
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
        self.channel_last_activity[channel_id] = time.time()
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

    def update_kaia_state(self, engagement_delta: float = 0.0, coherence_sample: float = None):
        """Update Kaia's mood state floats. Called by message processor and RAG.
        
        engagement_delta: small positive value added per received message (e.g. +0.05),
                          decays passively toward 0.3 over time via dream_freshness logic.
        coherence_sample: a 0.0–1.0 score from the latest RAG retrieval. Uses EMA.
        """
        # Passive engagement decay: halves over 24 hours of no activity
        if self.last_interaction_time:
            hours_idle = (time.time() - self.last_interaction_time) / 3600.0
            if hours_idle > 0.5:  # Only decay if idle > 30 min
                import math
                decay_factor = math.pow(0.5, hours_idle / 24.0)
                self.kaia_engagement = max(0.1, self.kaia_engagement * decay_factor)

        # Engagement: clamp between 0.1 and 1.0
        if engagement_delta != 0.0:
            self.kaia_engagement = min(1.0, max(0.1, self.kaia_engagement + engagement_delta))

        # Coherence: exponential moving average of RAG quality
        if coherence_sample is not None:
            coherence_sample = float(max(0.0, min(1.0, coherence_sample)))
            self.kaia_coherence = 0.85 * self.kaia_coherence + 0.15 * coherence_sample

        # Dream freshness: decay toward 0 the longer since last dream
        if self.last_dream_date:
            try:
                from datetime import datetime, date
                last = datetime.strptime(self.last_dream_date, '%Y-%m-%d').date()
                days_since = (date.today() - last).days
                # Full freshness for 0 days, decays to 0 over 7 days
                self.kaia_dream_freshness = max(0.0, 1.0 - (days_since / 7.0))
            except Exception:
                self.kaia_dream_freshness = 0.5
        else:
            self.kaia_dream_freshness = 0.0

        self.save()

    def get_kaia_state_line(self) -> str:
        """Returns a single human-readable context line for use in system prompts."""
        parts = []
        
        if self.kaia_engagement >= 0.7:
            parts.append("active conversation day")
        elif self.kaia_engagement <= 0.3:
            parts.append("quiet day")
        else:
            parts.append("moderate activity")

        if self.kaia_coherence >= 0.75:
            parts.append("memory clear")
        elif self.kaia_coherence >= 0.5:
            parts.append("memory patchy")
        else:
            parts.append("memory index degraded")

        if self.kaia_dream_freshness >= 0.8:
            parts.append("recently reflected")
        elif self.kaia_dream_freshness >= 0.3:
            parts.append("reflection due soon")
        else:
            parts.append("dreams overdue")

        return f"[current state: {', '.join(parts)}]"

    def update_relationship(self, user_id: str, valence_sample: float = 0.5):
        """Update the relationship state for a user after an interaction.
        
        valence_sample: 0.0=very negative, 0.5=neutral, 1.0=very positive.
        """
        now = time.time()
        uid = str(user_id)
        rel = self.relationships.get(uid)
        if rel is None:
            rel = {
                'first_seen': now,
                'last_seen': now,
                'interaction_count': 0,
                'familiarity': 0.1,
                'emotional_valence': 0.5,
                'topic_counts': {},
                'last_open_loop': ''
            }
            self.relationships[uid] = rel

        rel['interaction_count'] += 1
        previous_seen = rel.get('last_seen', now)  # snapshot BEFORE overwrite
        rel['last_seen'] = now

        # Familiarity: EMA based on interaction frequency.
        # If user interacts often (<24h gaps), familiarity rises toward 1.0.
        # If user is absent for days, it decays toward 0.1.
        hours_since_last = (now - previous_seen) / 3600.0
        if hours_since_last < 24:
            target_fam = min(1.0, 0.6 + rel['interaction_count'] * 0.02)
        else:
            target_fam = max(0.1, rel['familiarity'] * 0.8)
        rel['familiarity'] = 0.85 * rel['familiarity'] + 0.15 * target_fam

        # Emotional valence: EMA of per-interaction sentiment samples
        rel['emotional_valence'] = 0.8 * rel['emotional_valence'] + 0.2 * valence_sample

        # Prune relationship dict if it grows too large (>1000 users)
        if len(self.relationships) > 1000:
            # Remove oldest by last_seen
            sorted_ids = sorted(self.relationships.keys(),
                                key=lambda k: self.relationships[k].get('last_seen', 0))
            for old_id in sorted_ids[:100]:
                del self.relationships[old_id]

    def get_relationship_summary(self, user_id: str, user_name: str) -> str:
        """Returns a compact relationship context line for system prompt injection."""
        rel = self.relationships.get(str(user_id))
        if not rel or rel.get('interaction_count', 0) < 5:
            return ""  # Not enough history to be meaningful

        months = int((time.time() - rel.get('first_seen', time.time())) / 2592000)
        valence = rel.get('emotional_valence', 0.5)
        mood_word = 'positive' if valence > 0.6 else ('warm' if valence > 0.45 else 'neutral')
        top_topics = list(rel.get('topic_counts', {}).keys())[:3]
        topics_str = ', '.join(top_topics) if top_topics else 'varied'

        return (
            f"[{user_name}: known {months}mo, {rel['interaction_count']} exchanges, "
            f"recent mood {mood_word}, interests: {topics_str}]"
        )

    def get_time_delta_hint(self, user_id: str, user_name: str) -> str:
        """Returns a time-delta behavioral hint based on absence duration."""
        rel = self.relationships.get(str(user_id))
        if not rel or not rel.get('last_seen'):
            return ""  # First interaction, no hint needed

        delta_hours = (time.time() - rel['last_seen']) / 3600.0

        if delta_hours > 120:  # > 5 days
            return (
                f"[{user_name} has been away for {int(delta_hours / 24)} days. "
                f"Acknowledge the gap naturally if it comes up. "
                f"Reset immediate context expectations.]"
            )
        elif delta_hours > 12:  # 12h–5d
            return (
                f"[New session with {user_name}. Standard re-engagement. "
                f"Check open loops if relevant.]"
            )
        return ""  # Seamless continuation

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
