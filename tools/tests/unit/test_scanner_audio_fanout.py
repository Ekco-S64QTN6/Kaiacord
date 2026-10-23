"""Scanner listen-along fan-out must not split or replay stale audio."""
import queue

import numpy as np

from utils.radio import rx_dashboard, scanner


def _frame(samples: np.ndarray) -> bytes:
    up = np.repeat(samples, 4)
    return np.column_stack([up, up]).astype(np.int16).tobytes()


def _install(monkeypatch, targets):
    monkeypatch.setattr(rx_dashboard, "audio", lambda _chunk: None)
    with scanner._along_audio_lock:
        scanner._along_audio.update(targets)


def _remove(keys):
    with scanner._along_audio_lock:
        for key in keys:
            scanner._along_audio.pop(key, None)


def test_scanner_chunks_are_broadcast_to_every_listener(monkeypatch):
    """Each guild gets the complete stream, rather than competing for one queue."""
    one, two = queue.Queue(maxsize=4), queue.Queue(maxsize=4)
    keys = (991001, 991002)
    _install(monkeypatch, {keys[0]: one, keys[1]: two})
    samples = np.arange(scanner.ScanAudio.FRAME_12K, dtype=np.int16)
    try:
        scanner._sink(samples)
        got_one = scanner.ScanAudio(one).read()
        got_two = scanner.ScanAudio(two).read()
        assert got_one == _frame(samples)
        assert got_two == got_one
    finally:
        _remove(keys)


def test_a_full_listener_queue_drops_oldest_audio_to_stay_live(monkeypatch):
    target = queue.Queue(maxsize=1)
    target.put(np.full(scanner.ScanAudio.FRAME_12K, -7, dtype=np.int16))
    key = 991003
    _install(monkeypatch, {key: target})
    latest = np.arange(scanner.ScanAudio.FRAME_12K, dtype=np.int16) + 200
    try:
        scanner._sink(latest)
        assert scanner.ScanAudio(target).read() == _frame(latest)
    finally:
        _remove((key,))
