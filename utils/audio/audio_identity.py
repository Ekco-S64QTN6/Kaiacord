"""Stable identity for record audio, excluding common MP3 ID3 tags.

This module deliberately uses only the standard library so maintenance tools
running under the system Python can share the same identity algorithm.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import OrderedDict
from typing import Optional


IDENTITY_VERSION = 2
_CHUNK = 1024 * 1024
_CACHE_LIMIT = 1024
# ctime/inode catches ordinary same-mtime/same-size replacement immediately.
# Periodic full revalidation also catches unusual filesystems or tooling that
# can preserve the complete stat tuple while changing the payload.
_RECHECK_SECONDS = 300.0

_cache: OrderedDict[str, tuple[tuple[int, ...], str, float]] = OrderedDict()
_lock = threading.RLock()


def _stat_key(st: os.stat_result) -> tuple[int, ...]:
    return (
        int(st.st_dev), int(st.st_ino), int(st.st_size),
        int(st.st_mtime_ns), int(st.st_ctime_ns),
    )


def audio_signature(path: str, *, refresh: bool = False) -> Optional[str]:
    """Hash the complete audio payload, ignoring leading ID3v2 and trailing ID3v1.

    Unlike a sampled fingerprint, this detects edits anywhere in a same-length
    file even when its path and mtime are preserved. Inode/ctime changes bypass
    the cache immediately; a bounded-age full recheck covers filesystems that
    cannot provide a useful change tuple. The digest is streamed in 1 MiB
    chunks. Call from background/maintenance work, never the 20 ms callback.
    """
    try:
        path_stat = os.stat(path)
        key = _stat_key(path_stat)
    except OSError:
        return None

    now = time.monotonic()
    with _lock:
        held = _cache.get(path)
        if (not refresh and held is not None and held[0] == key
                and now - held[2] < _RECHECK_SECONDS):
            _cache.move_to_end(path)
            return f"v{IDENTITY_VERSION}:{held[1]}"

    try:
        with open(path, "rb") as stream:
            before = os.fstat(stream.fileno())
            if _stat_key(before) != key:
                return None
            head = stream.read(10)
            start = 0
            if len(head) == 10 and head[:3] == b"ID3":
                size = ((head[6] & 0x7F) << 21) | ((head[7] & 0x7F) << 14) | ((head[8] & 0x7F) << 7) | (head[9] & 0x7F)
                start = 10 + size + (10 if head[5] & 0x10 else 0)
            end = before.st_size
            if end - 128 >= start:
                stream.seek(end - 128)
                if stream.read(3) == b"TAG":
                    end -= 128
            if start >= end:
                return None

            digest = hashlib.blake2b(digest_size=32, person=b"kaia-rec-audio")
            digest.update((end - start).to_bytes(8, "big"))
            stream.seek(start)
            remaining = end - start
            while remaining:
                chunk = stream.read(min(_CHUNK, remaining))
                if not chunk:
                    return None
                digest.update(chunk)
                remaining -= len(chunk)

            after = os.fstat(stream.fileno())
            path_after = os.stat(path)
            if _stat_key(after) != key or _stat_key(path_after) != key:
                return None
            signature = digest.hexdigest()
    except OSError:
        return None

    with _lock:
        _cache[path] = (key, signature, time.monotonic())
        _cache.move_to_end(path)
        while len(_cache) > _CACHE_LIMIT:
            _cache.popitem(last=False)
    return f"v{IDENTITY_VERSION}:{signature}"


def clear_audio_signature_cache(path: Optional[str] = None) -> None:
    """Clear one entry or the bounded cache (primarily for focused tests)."""
    with _lock:
        if path is None:
            _cache.clear()
        else:
            _cache.pop(path, None)
