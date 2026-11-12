"""Shared thread- and process-safe lock for RAG persistence transactions.

All RAG instances targeting the same persist_dir share one in-process
re-entrant lock and one advisory lock file. Re-entrancy is tracked per thread
so nested batch helpers do not attempt to flock a second file descriptor.
"""
from __future__ import annotations

import errno
import os
import threading
import time
from pathlib import Path
from typing import Optional


_CREATION_GUARD = threading.Lock()
_LOCKS_BY_PATH: dict[str, "PersistenceTransactionLock"] = {}


class PersistenceTransactionLock:
    """Re-entrant lock spanning threads, RAG instances, and bot processes."""

    def __init__(self, lock_path: Optional[str] = None):
        self._thread_lock = threading.RLock()
        self._local = threading.local()
        self._lock_path = lock_path

    def acquire(self, timeout: Optional[float] = None) -> bool:
        deadline = None if timeout is None or timeout < 0 else time.monotonic() + timeout
        if deadline is None:
            acquired = self._thread_lock.acquire()
        else:
            acquired = self._thread_lock.acquire(timeout=max(0.0, deadline - time.monotonic()))
        if not acquired:
            return False

        depth = getattr(self._local, "depth", 0)
        if depth == 0 and self._lock_path:
            lock_file = None
            try:
                Path(self._lock_path).parent.mkdir(parents=True, exist_ok=True)
                lock_file = open(self._lock_path, "a+b")
                import fcntl

                while True:
                    try:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError as exc:
                        if exc.errno not in (errno.EACCES, errno.EAGAIN):
                            raise
                        if deadline is not None:
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                lock_file.close()
                                self._thread_lock.release()
                                return False
                            time.sleep(min(0.05, remaining))
                        else:
                            time.sleep(0.05)
                self._local.lock_file = lock_file
            except Exception:
                if lock_file is not None and not lock_file.closed:
                    lock_file.close()
                self._thread_lock.release()
                raise

        self._local.depth = depth + 1
        return True

    def release(self) -> None:
        depth = getattr(self._local, "depth", 0)
        if depth <= 0:
            raise RuntimeError("cannot release an un-acquired RAG persistence lock")
        if depth == 1:
            lock_file = getattr(self._local, "lock_file", None)
            try:
                if lock_file is not None:
                    try:
                        import fcntl
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    finally:
                        lock_file.close()
            finally:
                self._local.depth = 0
                self._local.lock_file = None
                self._thread_lock.release()
            return
        self._local.depth = depth - 1
        self._thread_lock.release()

    def __enter__(self):
        if not self.acquire():
            raise TimeoutError("could not acquire RAG persistence transaction lock")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False


def persistence_transaction_lock(owner) -> PersistenceTransactionLock:
    """Return the shared transaction lock for an owner's persistent directory.

    Test and maintenance doubles without persist_dir still receive a
    per-instance lock, while independent KaiaRAG objects targeting the same
    on-disk directory coordinate through the same lock object and lock file.
    """
    persist_dir = getattr(owner, "persist_dir", None)
    if persist_dir:
        key = os.path.realpath(os.path.abspath(os.fspath(persist_dir)))
        lock_path = os.path.join(key, ".rag-persistence.lock")
    else:
        key = f"owner:{id(owner)}"
        lock_path = None

    with _CREATION_GUARD:
        lock = _LOCKS_BY_PATH.get(key)
        if lock is None:
            lock = PersistenceTransactionLock(lock_path)
            _LOCKS_BY_PATH[key] = lock
        return lock
