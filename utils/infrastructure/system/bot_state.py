"""
Bot State Manager
=================

Encapsulates global bot state and persistence.

Extracted from Kaiacord.py to improve modularity.
"""

import os
import json
import copy
import re
import time
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Deque, Dict, Optional
from collections import deque
from utils.infrastructure.logging.kaia_logger import log_info, log_warning
from utils.infrastructure.monitoring.telemetry_paths import telemetry_path


def _lifecycle_setting(path: str, default: int) -> int:
    """Read a non-negative channel-memory lifecycle setting, with a safe fallback."""
    try:
        from utils.infrastructure.system.yaml_config import config as _cfg
        return max(0, int(_cfg.get_path(path, default)))
    except Exception:
        return default


class BotState:
    """Encapsulates global bot state and persistence (thread-safe)"""
    def __init__(self, state_file: Optional[str] = None):
        # Redirected under pytest: the module-level instance below is shared by every
        # test that touches state, and its save() would land on the running bot's file.
        self.state_file = state_file or telemetry_path("memory/bot_state.json")
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()  # Prevents concurrent _persist_to_disk writes
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='bot_state_writer')
        # save() submits while holding _lock; close() takes the same lock before
        # shutting down the executor, so accepted snapshots are ahead of shutdown.
        self._writer_close_lock = threading.Lock()
        self._writer_closing = False
        self._writer_closed = False
        self.channel_memory: Dict[int, Deque[Dict[str, str]]] = {}
        self.channel_memory_activity: Dict[int, float] = {}
        self.max_memory_channels = _lifecycle_setting("performance.max_memory_channels", 200)
        self.memory_channel_retention_s = 86400.0 * _lifecycle_setting("performance.memory_channel_retention_days", 90)
        self.memory_channel_active_grace_s = 60.0 * _lifecycle_setting("performance.memory_channel_active_grace_minutes", 60)
        self._channel_eviction_listeners: list[Callable[[int], None]] = []
        self._last_channel_prune = 0.0
        self._channel_prune_interval_s = 300.0
        self._channel_evicted_total = 0
        self._last_state_bytes = 0
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
        self.is_generating: bool = False     # Transient: True while LLM is generating a user response
        self.first_chat_done: bool = False   # Transient: True after first successful LLM response
        self.last_evening_reflection: str = ""  # YYYY-MM-DD, persisted
        self.last_dawn_date: str = ""           # YYYY-MM-DD, persisted

        # Kaia mood state — 3 floats, all 0.0-1.0, persisted across restarts.
        # Feeds a single context line in the system prompt.
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

        # The shared allowance for everything she says unprompted
        # (utils/core/unprompted.py): one daily count and one gap for every source.
        # Saved and loaded like everything else here, or a restart resets the gap.
        self.unprompted_last_sent: float = 0.0
        self.unprompted_count: int = 0
        self.unprompted_date: str = ""
        # Each source's own gap and daily count: {source: {"date", "count", "last"}}.
        self.unprompted_sources: Dict[str, dict] = {}

        # Anticipatory context priming and the theory-of-mind user model.
        self.user_states: Dict[str, dict] = {}  # {user_id: {"apparent_mood": str, "energy": str, "likely_intent": str, "updated_at": float}}
        self._dossier_primed_users: Dict[str, float] = {}  # {user_id: last_seen_timestamp_when_primed}

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
                        self.last_interaction_time = float(
                            state.get('last_interaction_time', self.last_interaction_time))
                        self.kaia_coherence = float(state.get('kaia_coherence', 0.85))
                        self.kaia_dream_freshness = float(state.get('kaia_dream_freshness', 1.0))
                        self.curiosity_last_sent = state.get('curiosity_last_sent', {})
                        self.last_evening_reflection = state.get('last_evening_reflection', "")
                        self.last_dawn_date = state.get('last_dawn_date', "")
                        self.forum_reply_times = state.get('forum_reply_times', {})
                        self.relationships = state.get('relationships', {})
                        self.pending_afterthoughts = state.get('pending_afterthoughts', [])
                        self.unprompted_last_sent = float(state.get('unprompted_last_sent', 0.0))
                        self.unprompted_count = int(state.get('unprompted_count', 0))
                        self.unprompted_date = state.get('unprompted_date', '')
                        self.unprompted_sources = dict(state.get('unprompted_sources') or {})
                        
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
                        raw_memory_activity = state.get("channel_memory_activity", {}) or {}
                        self.channel_memory_activity = {int(k): float(v) for k, v in raw_memory_activity.items() if str(k).isdigit() and isinstance(v, (int, float))}
                        saved_at = float(state.get("saved_at", 0.0) or 0.0)
                        for channel_id, turns in self.channel_memory.items():
                            latest = max((self._turn_timestamp(turn) for turn in turns), default=0.0)
                            if channel_id not in self.channel_memory_activity:
                                self.channel_memory_activity[channel_id] = latest or saved_at or time.time()
                        now = time.time()
                        self._prune_channel_memory_locked(now)
                        self._last_channel_prune = now

        except Exception as e:
            log_warning(f"Failed to load bot state: {e}\n{traceback.format_exc()}")


    # ── Channel-scoped conversation lifecycle ────────────────────────────────

    @staticmethod
    def _turn_timestamp(turn) -> float:
        stamp = turn.get("timestamp") if isinstance(turn, dict) else None
        return float(stamp) if isinstance(stamp, (int, float)) and not isinstance(stamp, bool) else 0.0

    def _memory_maxlen(self, requested=None) -> int:
        if requested is not None:
            try: return max(1, int(requested))
            except (TypeError, ValueError): pass
        try:
            from utils.infrastructure.system.yaml_config import config as _cfg
            return max(1, int(_cfg.max_memory_messages))
        except Exception:
            return 35

    def channel_memory_snapshot(self, channel_id: int) -> list:
        with self._lock:
            return list(self.channel_memory.get(channel_id, ()) or ())

    def append_channel_turn(self, channel_id: int, turn: dict, *, maxlen=None) -> bool:
        if channel_id is None or not isinstance(turn, dict): return False
        now = time.time()
        item = dict(turn); item.setdefault("timestamp", now)
        stamp = self._turn_timestamp(item) or now
        capacity = self._memory_maxlen(maxlen)
        with self._lock:
            if self._writer_closing or self._writer_closed: return False
            current = self.channel_memory.get(channel_id)
            if not isinstance(current, deque) or current.maxlen is None or current.maxlen < capacity:
                current = deque(list(current or ()), maxlen=max(capacity, len(current or ())))
                self.channel_memory[channel_id] = current
            current.append(item)
            self.channel_memory_activity[channel_id] = max(float(self.channel_memory_activity.get(channel_id, 0.0) or 0.0), stamp)
        return True

    def append_channel_turns(self, channel_id: int, turns, *, maxlen=None) -> bool:
        if channel_id is None: return False
        now = time.time(); items = []
        for turn in turns or ():
            if isinstance(turn, dict):
                item = dict(turn); item.setdefault("timestamp", now); items.append(item)
        if not items: return False
        capacity = self._memory_maxlen(maxlen)
        latest = max((self._turn_timestamp(item) or now for item in items), default=now)
        with self._lock:
            if self._writer_closing or self._writer_closed: return False
            current = self.channel_memory.get(channel_id)
            if not isinstance(current, deque) or current.maxlen is None or current.maxlen < capacity:
                current = deque(list(current or ()), maxlen=max(capacity, len(current or ())))
                self.channel_memory[channel_id] = current
            current.extend(items)
            self.channel_memory_activity[channel_id] = max(float(self.channel_memory_activity.get(channel_id, 0.0) or 0.0), latest)
        return True

    def replace_channel_memory(self, channel_id: int, turns, *, maxlen=None) -> bool:
        if channel_id is None: return False
        now = time.time(); items = []
        for turn in turns or ():
            if isinstance(turn, dict):
                item = dict(turn); item.setdefault("timestamp", now); items.append(item)
        capacity = max(self._memory_maxlen(maxlen), len(items), 1)
        latest = max((self._turn_timestamp(item) or now for item in items), default=now)
        with self._lock:
            if self._writer_closing or self._writer_closed: return False
            self.channel_memory[channel_id] = deque(items, maxlen=capacity)
            if items: self.channel_memory_activity[channel_id] = latest
            else: self.channel_memory_activity.pop(channel_id, None)
        return True

    def apply_channel_history_summary(self, channel_id: int, expected_prefix: list, summary_turn: dict) -> bool:
        if channel_id is None or not expected_prefix or not isinstance(summary_turn, dict): return False
        with self._lock:
            current = self.channel_memory.get(channel_id)
            if current is None: return False
            live = list(current)
            if live[:len(expected_prefix)] != expected_prefix: return False
            kept = live[len(expected_prefix):]; kept.insert(0, dict(summary_turn))
            self.channel_memory[channel_id] = deque(kept, maxlen=current.maxlen or self._memory_maxlen())
        return True

    def add_channel_eviction_listener(self, callback) -> None:
        if callable(callback):
            with self._lock:
                if callback not in self._channel_eviction_listeners: self._channel_eviction_listeners.append(callback)

    def _prune_channel_memory_locked(self, now: float) -> list:
        pending = {item.get("channel_id") for item in self.pending_afterthoughts if isinstance(item, dict) and item.get("channel_id") is not None}
        activity = {}
        for channel_id, turns in list(self.channel_memory.items()):
            last = float(self.channel_memory_activity.get(channel_id, 0.0) or 0.0)
            if not last: last = max((self._turn_timestamp(t) for t in list(turns)), default=0.0) or now
            self.channel_memory_activity[channel_id] = min(last, now); activity[channel_id] = min(last, now)
        evict: set[int] = set()
        if self.memory_channel_retention_s > 0:
            evict.update(cid for cid,last in activity.items() if now-last > self.memory_channel_retention_s and cid not in pending)
        remaining = [cid for cid in activity if cid not in evict]
        if self.max_memory_channels > 0 and len(remaining) > self.max_memory_channels:
            candidates = sorted((cid for cid in remaining if cid not in pending and now-activity[cid] >= self.memory_channel_active_grace_s), key=lambda cid: activity[cid])
            for cid in candidates:
                if len(remaining) <= self.max_memory_channels: break
                evict.add(cid); remaining.remove(cid)
        for cid in evict:
            self.channel_memory.pop(cid, None); self.channel_memory_activity.pop(cid, None)
        for cid in list(self.channel_memory_activity):
            if cid not in self.channel_memory: self.channel_memory_activity.pop(cid, None)
        self._channel_evicted_total += len(evict)
        return sorted(evict)

    def _notify_channel_evictions(self, evicted: list) -> None:
        if not evicted: return
        with self._lock: listeners = list(self._channel_eviction_listeners)
        for cid in evicted:
            for callback in listeners:
                try: callback(cid)
                except Exception as exc: log_warning(f"[channel_state] eviction listener failed: {exc}")

    def prune_channel_memory(self, now: Optional[float] = None) -> list:
        prune_at = time.time() if now is None else float(now)
        with self._lock:
            evicted = self._prune_channel_memory_locked(prune_at); self._last_channel_prune = prune_at
        self._notify_channel_evictions(evicted)
        return evicted

    def channel_state_stats(self) -> dict:
        with self._lock:
            return {"channels": len(self.channel_memory), "turns": sum(len(x) for x in list(self.channel_memory.values())),
                    "evicted": self._channel_evicted_total, "state_bytes": self._last_state_bytes}

    def save(self):
        """Snapshot live state here; serialize and write the detached snapshot off-loop."""
        try:
            evicted = []
            with self._lock:
                if self._writer_closing or self._writer_closed:
                    return
                # Copying live maps/deques must remain on the caller thread and
                # under the state lock. Serializing the detached snapshot is safe
                # on the single writer thread and avoids JSON work on Discord's loop.
                for attempt in range(20):
                    try:
                        # Pruning participates in the same retry loop as the
                        # detached snapshot. A concurrently mutating mapping may
                        # raise RuntimeError while pruning just as it can while
                        # the snapshot comprehension is being built.
                        now = time.time()
                        if now - self._last_channel_prune >= self._channel_prune_interval_s:
                            evicted = self._prune_channel_memory_locked(now)
                            self._last_channel_prune = now
                        state = {
                            'last_active_channel_id': self.last_active_channel_id,
                            'consecutive_quips': self.consecutive_quips,
                            'last_manual_quip_time': self.last_manual_quip_time,
                            'last_quip_time': self.last_quip_time,
                            'quip_history': list(self.quip_history),
                            'recent_ingestions': copy.deepcopy(self.recent_ingestions),
                            'last_dream_date': self.last_dream_date,
                            'kaia_engagement': self.kaia_engagement,
                            'last_interaction_time': self.last_interaction_time,
                            'kaia_coherence': self.kaia_coherence,
                            'kaia_dream_freshness': self.kaia_dream_freshness,
                            'curiosity_last_sent': copy.deepcopy(self.curiosity_last_sent),
                            'last_evening_reflection': self.last_evening_reflection,
                            'last_dawn_date': self.last_dawn_date,
                            'forum_reply_times': copy.deepcopy(self.forum_reply_times),
                            'relationships': copy.deepcopy(self.relationships),
                            'pending_afterthoughts': copy.deepcopy(self.pending_afterthoughts),
                            'channel_last_activity': {
                                str(k): v for k, v in self.channel_last_activity.items()
                            },
                            'unprompted_last_sent': self.unprompted_last_sent,
                            'unprompted_count': self.unprompted_count,
                            'unprompted_date': self.unprompted_date,
                            'unprompted_sources': copy.deepcopy({
                                k: dict(v) for k, v in self.unprompted_sources.items()
                            }),
                            # boot_complete is TRANSIENT - do not save to disk.
                            'channel_memory': copy.deepcopy({
                                str(k): list(v) for k, v in self.channel_memory.items()
                            }),
                            'channel_memory_activity': {str(k): v for k, v in self.channel_memory_activity.items()},
                            'saved_at': time.time(),
                        }
                        break
                    except RuntimeError:
                        if attempt == 19:
                            raise
                        time.sleep(0)

                # Enqueue while holding _lock so concurrent callers cannot
                # submit snapshots in the reverse order from their snapshot order.
                # The executor has one worker, so serialization and writes remain FIFO.
                self._executor.submit(self._persist_to_disk, state)
            self._notify_channel_evictions(evicted)
        except Exception as e:
            log_warning(f"Failed to initiate bot state save: {e}")

    @staticmethod
    def _serialize_snapshot(state: dict) -> str:
        """Serialize a detached snapshot; never pass live BotState containers here."""
        return json.dumps(state, indent=2)

    def _persist_to_disk(self, state: dict):
        """Serialize and atomically write a detached snapshot on the writer thread."""
        try:
            payload = self._serialize_snapshot(state)
            self._last_state_bytes = len(payload.encode("utf-8"))
            from utils.core.atomic_write import write_atomic
            with self._write_lock:
                write_atomic(self.state_file, payload)
        except Exception as e:
            log_warning(f"Background save failed for bot state: {e}")

    def close(self) -> None:
        """Stop accepting new snapshots and drain every accepted save."""
        with self._writer_close_lock:
            with self._lock:
                if self._writer_closed:
                    return
                self._writer_closing = True
            self._executor.shutdown(wait=True)
            with self._lock:
                self._writer_closed = True

    def reset_quips(self):
        """Reset consecutive quips counter"""
        self.consecutive_quips = 0
        self.save()

    def update_interaction(self, channel_id: Optional[int] = None):
        """Update the interaction clock and, when supplied, the active guild channel."""
        now = time.time()
        self.last_interaction_time = now
        if channel_id is None:
            return
        self.channel_last_activity[channel_id] = now
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

    def update_kaia_state(self, engagement_delta: float = 0.0, coherence_sample: float = None):
        """Update Kaia's mood state floats. Called by message processor and RAG.
        
        engagement_delta: small positive value added per received message (e.g. +0.05),
                          decays passively toward 0.3 over time via dream_freshness logic.
        coherence_sample: a 0.0–1.0 score from the latest RAG retrieval. Uses EMA.
        """
        # Passive engagement decay: halves over 24 hours of no activity.
        #
        # Measured from whichever is later, the last interaction or the last
        # time this decay ran. This runs twice in one turn (on arrival, then
        # with the retrieval's coherence sample) before the interaction clock
        # is stamped, and external-platform turns never stamp it, so measuring
        # from the interaction alone applied the same idle span repeatedly.
        if self.last_interaction_time:
            now = time.time()
            since = max(self.last_interaction_time, getattr(self, '_engagement_decayed_at', 0.0))
            hours_idle = (now - since) / 3600.0
            if hours_idle > 0.5:  # Only decay if idle > 30 min
                import math
                decay_factor = math.pow(0.5, hours_idle / 24.0)
                self.kaia_engagement = max(0.1, self.kaia_engagement * decay_factor)
                self._engagement_decayed_at = now

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
        """Her head, in her terms: how clearly she is remembering (retrieval
        confidence) and whether she has slept on things (the dream). How busy
        the day is lives in the mood line beside it; said here as well, from a
        different counter, the two disagreed ("quiet day" against "very busy day")."""
        if self.kaia_coherence >= 0.75:
            memory = "thinking clearly"
        elif self.kaia_coherence >= 0.5:
            memory = "memory a bit hazy"
        else:
            memory = "memory foggy"
        if self.kaia_dream_freshness >= 0.8:
            sleep = ", slept on things recently"
        elif self.kaia_dream_freshness >= 0.3:
            sleep = ""
        else:
            sleep = ", haven't slept on things in a while"
        return f"[in your head: {memory}{sleep}]"

    def update_relationship(self, user_id: str, valence_sample: float = 0.5, display_name: str = ""):
        """Update the relationship state for a user after an interaction.
        
        valence_sample: 0.0=very negative, 0.5=neutral, 1.0=very positive.
        display_name: the user's current Discord display name (stored for proactive features).
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
                'last_open_loop': '',
                'display_name': '',
            }
            self.relationships[uid] = rel

        rel['interaction_count'] += 1
        previous_seen = rel.get('last_seen', now)  # snapshot BEFORE overwrite
        rel['last_seen'] = now

        # Store display_name if provided (keeps it current across name changes)
        if display_name:
            rel['display_name'] = display_name

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
        tc = rel.get('topic_counts') or {}
        top_topics = [t for t, _ in sorted(tc.items(), key=lambda kv: -kv[1])[:3]]
        interests = f", interests: {', '.join(top_topics)}" if top_topics else ""

        return (
            f"[{user_name}: known {months}mo, {rel['interaction_count']} exchanges, "
            f"recent mood {mood_word}{interests}]"
        )

    def get_relationship_stage(self, user_id: str) -> str:
        """Return the relationship stage name based on interaction count.

        Stages:
            stranger (0-5), acquaintance (6-25), familiar (26-100),
            confidant (101-500), inner_circle (500+)
        """
        rel = self.relationships.get(str(user_id))
        if not rel:
            return "stranger"
        count = rel.get('interaction_count', 0)
        if count <= 5:
            return "stranger"
        elif count <= 25:
            return "acquaintance"
        elif count <= 100:
            return "familiar"
        elif count <= 500:
            return "confidant"
        else:
            return "inner_circle"

    def get_stage_injection(self, user_id: str, user_name: str) -> str:
        """Return a behavioral directive for system prompt based on relationship stage."""
        stage = self.get_relationship_stage(user_id)
        rel = self.relationships.get(str(user_id))
        count = rel.get('interaction_count', 0) if rel else 0

        directives = {
            "stranger": (
                f"[relationship: you don't know {user_name} well yet. "
                f"be polite and welcoming but slightly reserved. shorter responses.]"
            ),
            "acquaintance": (
                f"[relationship: you've talked with {user_name} a few times ({count} exchanges). "
                f"normal warmth. you can reference past conversations if relevant.]"
            ),
            "familiar": (
                f"[relationship: you know {user_name} well ({count} exchanges). "
                f"be casual and direct. you're comfortable disagreeing. use inside references.]"
            ),
            "confidant": (
                f"[relationship: {user_name} is someone you trust ({count} exchanges). "
                f"be blunt and honest. share your real opinions. "
                f"you can volunteer what's been on your mind.]"
            ),
            "inner_circle": (
                f"[relationship: {user_name} is inner circle ({count} exchanges). "
                f"full trust. reference your shared history freely. "
                f"be completely yourself — direct, opinionated, personal.]"
            ),
        }
        return directives.get(stage, "")

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

    def get_user_dossier(self, user_id: str, user_name: str) -> str:
        """Anticipatory context priming.
        
        Compiles a ~200-token returning summary for familiar users returning
        after an absence of > 2 hours. One-shot per session absence.
        """
        uid = str(user_id)
        rel = self.relationships.get(uid)
        if not rel or not rel.get('last_seen'):
            return ""

        # Only trigger for familiar or higher relationship stages
        stage = self.get_relationship_stage(uid)
        if stage not in ('familiar', 'confidant', 'inner_circle'):
            return ""

        now = time.time()
        last_seen = rel['last_seen']
        delta_hours = (now - last_seen) / 3600.0

        if delta_hours <= 2.0:
            return ""

        # Deduplication check: verify if we already primed for this last_seen timestamp
        if self._dossier_primed_users.get(uid) == last_seen:
            return ""

        # Mark as primed for this last_seen timestamp
        self._dossier_primed_users[uid] = last_seen

        # Topics are what a person talked about, counted. A relationship
        # event's `topics` are the words of the one message that raised it,
        # kept to recognise a repeated repair ("i meant pry not pray sorry" gave
        # "begin, meant, sorry"), so they are not used here.
        tc = rel.get('topic_counts') or {}
        top_topics = [t for t, _ in sorted(tc.items(), key=lambda kv: -kv[1])[:3]]

        # Gather last open loop
        open_loop = rel.get('last_open_loop', '').strip()

        # Gather top 2 memory anchors by weight for this user
        top_anchors = []
        try:
            from utils.core.memory_anchors import _load_anchors
            all_anchors = _load_anchors()
            user_anchors = [a for a in all_anchors if str(a.get('user_id')) == uid]
            user_anchors.sort(key=lambda a: a.get('weight', 0.5), reverse=True)
            for a in user_anchors[:2]:
                theme = a.get('theme', '')
                text = a.get('anchor_text', '')
                if theme and text:
                    top_anchors.append(f"{theme}: \"{text}\"")
        except Exception:
            pass

        parts = [f"[returning dossier for {user_name} (absent {int(delta_hours)}h):"]
        if top_topics:
            parts.append(f"recent topics: {', '.join(top_topics)};")
        if open_loop:
            parts.append(f"last open loop: \"{open_loop}\";")
        if top_anchors:
            parts.append(f"memory anchors: {'; '.join(top_anchors)};")
        parts.append("use naturally if relevant]")

        return " ".join(parts)

    def update_user_state(self, user_id: str, message_text: str) -> dict:
        """Theory of mind: a model of the user's current state.
        
        Updates session-bound user state (apparent_mood, energy, likely_intent)
        via lightweight heuristics and metrics. State decays after 2 hours.
        """
        uid = str(user_id)
        now = time.time()
        text = message_text.strip()
        lower_text = text.lower()

        # Whole words and phrases only. Substrings made "whatever" frustrated
        # (h-a-t-e), "later" tired, "definitely" troubleshooting, and any
        # message opening with "you" a greeting ("yo").
        def has(*words):
            return any(re.search(rf"\b{re.escape(w)}\b", lower_text) for w in words)

        def opens_with(*words):
            return any(re.match(rf"{re.escape(w)}\b", lower_text) for w in words)

        # 1. Energy level heuristic
        letters = [c for c in text if c.isalpha()]
        caps_ratio = sum(c.isupper() for c in letters) / len(letters) if len(letters) >= 8 else 0.0
        excl_count = text.count('!')
        if excl_count >= 2 or caps_ratio > 0.5:
            energy = "high"
        elif len(text) < 15 and not excl_count and has("meh", "bored", "tired", "sleepy", "whatever"):
            energy = "low"
        else:
            energy = "moderate"

        # 2. Apparent Mood heuristic
        if has("ugh", "sigh", "dammit", "annoyed", "wrong", "broke", "broken", "error",
               "hate", "stuck", "fail", "failed", "failing", "angry"):
            mood = "frustrated"
        elif has("lol", "lmao", "haha", "yay", "great", "awesome", "nice", "love",
                 "thanks", "cool", "good", "happy"):
            mood = "upbeat"
        elif has("tired", "exhausted", "sleepy", "bored", "goodnight", "meh", "up late"):
            mood = "tired"
        elif has("wondering", "curious", "think", "maybe", "perplexed", "why", "how"):
            mood = "thoughtful"
        else:
            mood = "neutral"

        # 3. Likely Intent heuristic
        if "```" in text or has("traceback", "error", "issue", "bug", "exception"):
            intent = "troubleshooting"
        elif "?" in text or opens_with("how", "what", "why", "where", "can you", "who", "is it"):
            intent = "asking_questions"
        elif opens_with("hi", "hello", "hey", "yo", "good morning", "good evening"):
            intent = "greeting"
        elif has("thanks", "thank you", "good job", "nice work"):
            intent = "giving_feedback"
        else:
            intent = "casual_chat"

        state = {
            "apparent_mood": mood,
            "energy": energy,
            "likely_intent": intent,
            "updated_at": now,
        }
        self.user_states[uid] = state
        return state

    def get_user_state_read(self, user_id: str, user_name: str) -> str:
        """Read the user-state model back for system-prompt injection."""
        uid = str(user_id)
        state = self.user_states.get(uid)
        if not state or (time.time() - state.get('updated_at', 0) > 7200):
            return ""

        # Only what was actually read. "seems neutral, energy moderate, likely
        # intent: casual_chat" is the absence of a reading, and it went into
        # every prompt as if it were one.
        parts = []
        if state.get('apparent_mood') not in (None, "", "neutral"):
            parts.append(f"seems {state['apparent_mood']}")
        if state.get('energy') not in (None, "", "moderate"):
            parts.append(f"energy {state['energy']}")
        if state.get('likely_intent') not in (None, "", "casual_chat"):
            parts.append(f"likely {str(state['likely_intent']).replace('_', ' ')}")
        if not parts:
            return ""
        return f"[your read on {user_name}: {', '.join(parts)}]"

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
