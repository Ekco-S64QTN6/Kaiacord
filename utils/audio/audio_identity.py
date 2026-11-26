"""Stable identity for record audio, excluding common MP3 ID3 tags.

This module deliberately uses only the standard library so maintenance tools
running under the system Python can share the same identity algorithm.
"""

from __future__ import annotations

import hashlib
import os
from typing import Optional


_CHUNK = 1024 * 1024


def audio_signature(path: str) -> Optional[str]:
    """Hash the complete audio payload, ignoring leading ID3v2 and trailing ID3v1.

    Unlike a sampled fingerprint, this detects edits anywhere in a same-length
    file even when its path, size and timestamps are preserved. Reading is
    streamed and bounded in memory. Call from background/maintenance work,
    never from the 20 ms audio-render callback.
    """
    try:
        with open(path, "rb") as stream:
            before = os.fstat(stream.fileno())
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

            digest = hashlib.blake2b(digest_size=32, person=b"kaia-record-audio")
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
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
            ):
                return None
            return digest.hexdigest()
    except OSError:
        return None
