"""Complete source-audio identity and cache invalidation for records."""

import os

from utils.audio.audio_identity import audio_signature, clear_audio_signature_cache


def _id3(tag: bytes, payload: bytes) -> bytes:
    size = len(tag)
    syncsafe = bytes([
        (size >> 21) & 0x7F,
        (size >> 14) & 0x7F,
        (size >> 7) & 0x7F,
        size & 0x7F,
    ])
    return b"ID3\x03\x00\x00" + syncsafe + tag + payload


def test_metadata_only_id3_retag_keeps_audio_identity(tmp_path):
    path = tmp_path / "record.mp3"
    audio = bytes(range(256)) * 32
    path.write_bytes(_id3(b"TIT2 original title", audio))
    clear_audio_signature_cache(str(path))
    original = audio_signature(str(path))
    assert original and original.startswith("v2:")
    assert audio_signature(str(path)) == original       # stat-cache hit keeps the same versioned format

    path.write_bytes(_id3(b"TIT2 a much longer replacement title and artist", audio))
    retagged = audio_signature(str(path))
    assert retagged == original


def test_middle_of_same_size_audio_replacement_with_preserved_mtime_changes_identity(tmp_path):
    path = tmp_path / "record.mp3"
    audio = bytearray((bytes(range(251)) * 16384)[: 3 * 1024 * 1024])
    path.write_bytes(_id3(b"TIT2 title", bytes(audio)))
    clear_audio_signature_cache(str(path))
    original = audio_signature(str(path))
    assert original

    before = path.stat()
    # Change only the centre: a fingerprint sampling the beginning/end misses it.
    audio[len(audio) // 2] ^= 0x7F
    path.write_bytes(_id3(b"TIT2 title", bytes(audio)))
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    after = path.stat()

    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns
    assert audio_signature(str(path)) != original


def test_forced_identity_refresh_reads_complete_payload_again(tmp_path):
    path = tmp_path / "record.mp3"
    path.write_bytes(b"A" * (1024 * 1024))
    clear_audio_signature_cache(str(path))
    first = audio_signature(str(path))
    assert first

    path.write_bytes(b"B" * (1024 * 1024))
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns))
    # Explicit refresh also handles filesystems that do not expose a useful
    # inode/ctime change tuple.
    assert audio_signature(str(path), refresh=True) != first
    clear_audio_signature_cache(str(path))
