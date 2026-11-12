"""Shared lock for RAG index-directory and manifest persistence transactions."""
import threading


_CREATION_GUARD = threading.Lock()


def persistence_transaction_lock(owner):
    """Return one lazily initialized re-entrant persistence lock per RAG instance.

    The guard also supports small test/maintenance doubles that do not execute
    KaiaRAG.__init__. All mixins use this one helper so they cannot accidentally
    create independent locks for the same instance.
    """
    with _CREATION_GUARD:
        lock = getattr(owner, "_persistence_transaction_lock", None)
        if lock is None:
            lock = threading.RLock()
            owner._persistence_transaction_lock = lock
        return lock
