"""Cross-process-safe state for replies made on social platforms."""
import asyncio
import fcntl
import json
import os
import time
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Set, Dict, Optional, Any, Iterator

from utils.infrastructure.logging.kaia_logger import (
    log_info, log_debug, log_warning, log_error,
)
from utils.infrastructure.monitoring.telemetry_paths import telemetry_path


class SocialTracker:
    """Persistent social reply tracker.

    The asyncio lock protects one instance's in-memory state. A separate OS
    advisory lock protects the shared append log and snapshot-compaction cycle
    across processes. The JSONL log carries enough metadata to merge thread
    counts when two processes have independent in-memory snapshots.
    """

    def __init__(
        self,
        log_path: str = "memory/social_replied.log",
        state_path: str = "memory/social_state.json",
        max_ids: int = 5000,
    ):
        # Redirected under pytest so tests cannot mutate production state.
        self.log_path = Path(telemetry_path(log_path))
        self.state_path = Path(telemetry_path(state_path))
        self.max_ids = max(1, int(max_ids))
        # The lock inode is stable: never unlink/replace this file. All tracker
        # instances sharing a log directory coordinate through the same lock.
        self.lock_path = self.log_path.parent / "social_tracker.lock"

        self._replied_ids: set[str] = set()
        self._replied_deque = deque(maxlen=self.max_ids)
        self._thread_counts: Dict[str, Dict[str, int]] = {}
        self._snapshot_generation = 0
        # Only events whose append failed may exist in memory but not on disk.
        # Persist these explicitly; never merge the full stale local deque over
        # newer disk IDs during snapshot compaction.
        self._pending_events: list[dict] = []
        self._lock = asyncio.Lock()

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    @contextmanager
    def _interprocess_lock(self) -> Iterator[None]:
        """Exclusive advisory lock shared by all processes using this tracker."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "a", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            return state if isinstance(state, dict) else {}
        except (OSError, json.JSONDecodeError, TypeError) as e:
            log_warning(f"[SocialTracker] Failed to read state snapshot: {e}")
            return {}

    def _read_log_entries(self) -> list[dict]:
        """Read current JSONL events and legacy one-ID-per-line entries."""
        if not self.log_path.exists():
            return []
        entries: list[dict] = []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        item = None
                    if isinstance(item, dict) and item.get("mention_id"):
                        entries.append(item)
                    else:
                        # Backward compatibility with the old plain-ID log.
                        entries.append({"mention_id": line, "legacy": True})
        except OSError as e:
            log_warning(f"[SocialTracker] Failed to read reply log: {e}")
        return entries

    @staticmethod
    def _normalize_thread_counts(raw: Any) -> Dict[str, Dict[str, int]]:
        counts: Dict[str, Dict[str, int]] = {}
        if not isinstance(raw, dict):
            return counts
        for root, per_user in raw.items():
            if isinstance(per_user, dict):
                counts[str(root)] = {}
                for user, value in per_user.items():
                    try:
                        counts[str(root)][str(user)] = max(0, int(value))
                    except (TypeError, ValueError):
                        continue
            else:
                # Migrate legacy flat {root: total} values without pretending
                # that their user attribution is known.
                try:
                    counts[str(root)] = {"__legacy_total__": max(0, int(per_user))}
                except (TypeError, ValueError):
                    continue
        return counts

    def _remember_id(self, mention_id: str) -> None:
        if not mention_id or mention_id in self._replied_ids:
            return
        if len(self._replied_deque) == self.max_ids:
            oldest = self._replied_deque[0]
            self._replied_ids.discard(oldest)
        self._replied_deque.append(mention_id)
        self._replied_ids.add(mention_id)

    @staticmethod
    def _append_event_count(counts: Dict[str, Dict[str, int]], event: dict) -> None:
        root = event.get("root_uri")
        user = event.get("user_handle")
        if not root or not user:
            return
        root, user = str(root), str(user)
        counts.setdefault(root, {})
        try:
            counts[root][user] = max(0, int(counts[root].get(user, 0))) + 1
        except (TypeError, ValueError):
            counts[root][user] = 1

    def _state_view_locked(self) -> tuple[dict, list[dict]]:
        """Read a consistent snapshot and log while the file lock is held."""
        state = self._read_state()
        return state, self._read_log_entries()

    def _load(self) -> None:
        """Load the compacted snapshot plus events written since that snapshot."""
        with self._interprocess_lock():
            state, entries = self._state_view_locked()
        raw_ids = state.get("replied_ids", [])
        snapshot_ids = [str(x) for x in raw_ids if x] if isinstance(raw_ids, list) else []
        self._snapshot_generation = max(0, int(state.get("log_generation", 0) or 0))
        self._thread_counts = self._normalize_thread_counts(state.get("thread_counts", {}))
        for mention_id in snapshot_ids[-self.max_ids:]:
            self._remember_id(mention_id)

        counted: set[str] = set()
        snapshot_set = set(snapshot_ids)
        for entry in entries:
            mention_id = str(entry.get("mention_id") or "")
            self._remember_id(mention_id)
            if entry.get("legacy"):
                continue
            # A crash between replacing the snapshot and clearing the log can
            # leave old events behind. Generation mismatch makes replay idempotent.
            if int(entry.get("generation", -1)) != self._snapshot_generation:
                continue
            if mention_id in snapshot_set or mention_id in counted:
                continue
            counted.add(mention_id)
            self._append_event_count(self._thread_counts, entry)
        log_debug(f"[SocialTracker] Loaded baseline state: {len(self._replied_ids)} IDs")

    def _refresh_from_disk_sync(self) -> None:
        with self._interprocess_lock():
            state, entries = self._state_view_locked()
        snapshot_ids = state.get("replied_ids", [])
        if not isinstance(snapshot_ids, list):
            snapshot_ids = []
        generation = max(0, int(state.get("log_generation", 0) or 0))
        counts = self._normalize_thread_counts(state.get("thread_counts", {}))
        disk_ids = [str(x) for x in snapshot_ids if x]
        snapshot_set = set(disk_ids)
        counted: set[str] = set()
        logged_ids: list[str] = []
        for entry in entries:
            mention_id = str(entry.get("mention_id") or "")
            if not mention_id:
                continue
            logged_ids.append(mention_id)
            if entry.get("legacy") or int(entry.get("generation", -1)) != generation:
                continue
            if mention_id in snapshot_set or mention_id in counted:
                continue
            counted.add(mention_id)
            self._append_event_count(counts, entry)

        # Never lower a locally reconstructed or locally observed thread count;
        # another process may have advanced the authoritative disk snapshot.
        for root, users in self._thread_counts.items():
            counts.setdefault(root, {})
            for user, value in users.items():
                counts[root][user] = max(int(counts[root].get(user, 0)), int(value))

        current_ids = list(self._replied_deque)
        self._replied_ids.clear()
        self._replied_deque.clear()
        merged_ids = disk_ids + current_ids + logged_ids
        for mention_id in merged_ids[-self.max_ids:]:
            self._remember_id(mention_id)
        self._thread_counts = counts
        self._snapshot_generation = generation

    async def refresh_from_disk(self) -> None:
        """Merge other processes' reply events before a polling pass."""
        async with self._lock:
            await asyncio.to_thread(self._refresh_from_disk_sync)

    def is_replied(self, mention_id: str) -> bool:
        return mention_id in self._replied_ids

    def get_all_replied_ids(self) -> Set[str]:
        return self._replied_ids.copy()

    def get_thread_count(self, root_uri: str, user_handle: str) -> int:
        return self._thread_counts.get(root_uri, {}).get(user_handle, 0)

    def _append_event_locked(self, mention_id: str, platform: str,
                             root_uri: Optional[str], user_handle: str) -> Optional[dict]:
        """Append one unique event. Caller owns _interprocess_lock()."""
        state = self._read_state()
        snapshot_ids = state.get("replied_ids", [])
        known = {str(x) for x in snapshot_ids} if isinstance(snapshot_ids, list) else set()
        entries = self._read_log_entries()
        known.update(str(e.get("mention_id")) for e in entries if e.get("mention_id"))
        if mention_id in known:
            return None
        generation = max(0, int(state.get("log_generation", 0) or 0))
        event = {
            "mention_id": mention_id,
            "platform": platform,
            "root_uri": str(root_uri) if root_uri else None,
            "user_handle": str(user_handle) if user_handle else None,
            "generation": generation,
            "timestamp": time.time(),
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return event

    async def mark_replied(self, mention_id: str, platform: str,
                           root_uri: Optional[str], user_handle: str):
        """Mark a reply once across tracker instances and processes."""
        async with self._lock:
            if mention_id in self._replied_ids:
                return
            try:
                event = await asyncio.to_thread(
                    self._append_event_under_file_lock,
                    mention_id, platform, root_uri, user_handle,
                )
            except Exception as e:
                # Keep the in-memory duplicate guard even when storage is
                # temporarily unavailable; snapshotting may persist it later.
                log_error(f"[SocialTracker] Failed to append reply event: {e}")
                event = {
                    "mention_id": mention_id, "platform": platform,
                    "root_uri": str(root_uri) if root_uri else None,
                    "user_handle": str(user_handle) if user_handle else None,
                    "generation": self._snapshot_generation,
                    "timestamp": time.time(),
                }
                self._pending_events.append(event)
            if event is None:
                await asyncio.to_thread(self._refresh_from_disk_sync)
                return
            self._remember_id(mention_id)
            self._append_event_count(self._thread_counts, event)

    def _append_event_under_file_lock(self, mention_id: str, platform: str,
                                      root_uri: Optional[str], user_handle: str) -> Optional[dict]:
        with self._interprocess_lock():
            return self._append_event_locked(mention_id, platform, root_uri, user_handle)

    def _write_snapshot_sync(self) -> dict:
        """Merge all writers under flock, atomically replace state, then compact log."""
        from utils.core.atomic_write import write_atomic

        with self._interprocess_lock():
            state, entries = self._state_view_locked()
            disk_ids = state.get("replied_ids", [])
            if not isinstance(disk_ids, list):
                disk_ids = []
            disk_ids = [str(x) for x in disk_ids if x]
            disk_id_set = set(disk_ids)
            generation = max(0, int(state.get("log_generation", 0) or 0))
            counts = self._normalize_thread_counts(state.get("thread_counts", {}))
            counted: set[str] = set()
            event_ids: list[str] = []
            observed_events: set[str] = set()
            for entry in entries:
                mention_id = str(entry.get("mention_id") or "")
                if not mention_id or mention_id in disk_id_set or mention_id in observed_events:
                    continue
                if not entry.get("legacy") and int(entry.get("generation", -1)) != generation:
                    # A stale-generation line can remain after a crash between
                    # state replacement and log unlink. Its state was already
                    # represented by the previous snapshot, so it is not new.
                    continue
                observed_events.add(mention_id)
                event_ids.append(mention_id)
                if entry.get("legacy"):
                    continue
                counted.add(mention_id)
                self._append_event_count(counts, entry)

            pending_ids: list[str] = []
            for event in self._pending_events:
                mention_id = str(event.get("mention_id") or "")
                if not mention_id or mention_id in disk_id_set or mention_id in observed_events:
                    continue
                observed_events.add(mention_id)
                pending_ids.append(mention_id)

            # The local count is an upper bound for reconstructed/observed
            # threads, but the local ID deque is not authoritative: another
            # process may have compacted newer IDs since this instance loaded.
            for root, users in self._thread_counts.items():
                counts.setdefault(root, {})
                for user, value in users.items():
                    counts[root][user] = max(int(counts[root].get(user, 0)), int(value))

            # Disk snapshot IDs are the baseline, followed only by un-compacted
            # current-generation log events and events whose append failed.
            ids = []
            seen = set()
            for mention_id in disk_ids + event_ids + pending_ids:
                if mention_id and mention_id not in seen:
                    ids.append(mention_id)
                    seen.add(mention_id)
            ids = ids[-self.max_ids:]

            new_state = dict(state)
            new_state.update({
                "replied_ids": ids,
                "thread_counts": counts,
                "last_updated": time.time(),
                "log_generation": generation + 1,
            })
            write_atomic(self.state_path, json.dumps(new_state, indent=2))

            # Every cooperating writer opens the log only while holding the
            # separate lockfile, so no writer retains an fd to the old inode.
            # Keep the historical behavior: remove the compacted log entirely.
            if self.log_path.exists():
                self.log_path.unlink()
            return new_state

    async def save_snapshot(self):
        """Merge other processes' state and compact the append-only log safely."""
        async with self._lock:
            try:
                state = await asyncio.to_thread(self._write_snapshot_sync)
                ids = state.get("replied_ids", [])
                self._replied_ids.clear()
                self._replied_deque.clear()
                for mention_id in ids[-self.max_ids:]:
                    self._remember_id(str(mention_id))
                self._thread_counts = self._normalize_thread_counts(state.get("thread_counts", {}))
                self._snapshot_generation = max(0, int(state.get("log_generation", 0) or 0))
                self._pending_events.clear()
                log_info(f"[SocialTracker] Saved state snapshot to {self.state_path}")
            except Exception as e:
                log_error(f"[SocialTracker] Failed to save state snapshot: {e}")


# Singleton instance
social_tracker = SocialTracker()
