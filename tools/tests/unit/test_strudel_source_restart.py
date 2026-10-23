"""A capture that dies as soon as it opens is retried with a backoff and then
given up on, not restarted in a tight loop forever."""
import io
import time
from unittest.mock import MagicMock, patch

from utils.audio import strudel_source


def test_a_capture_that_keeps_dying_is_given_up_on():
    engine = MagicMock()
    engine.open_capture.side_effect = lambda: MagicMock(stdout=io.BytesIO(b""))
    with patch.object(strudel_source, "MAX_RESTARTS", 3), \
         patch.object(strudel_source.threading.Event, "wait", return_value=False):
        src = strudel_source.StrudelAudioSource(engine, buffer_frames=1)
        src._thread.join(timeout=5)
    assert not src._thread.is_alive()
    assert src.restarts == 4 and engine.open_capture.call_count == 4
    assert src.read() == strudel_source.SILENCE

def test_cleanup_racing_capture_restart_closes_the_replacement():
    """A concurrent cleanup must not miss a process opened by a retry."""
    import threading
    from collections import deque

    class Pipe:
        def __init__(self):
            self.closed = False

        def read(self, _n):
            return b""

        def close(self):
            self.closed = True

    class Process:
        def __init__(self):
            self.stdout = Pipe()

    class RestartingEngine:
        def __init__(self):
            self.first = Process()
            self.current = self.first
            self.processes = [self.first]
            self.open_started = threading.Event()
            self.allow_open = threading.Event()
            self.opens = 0

        def close_capture(self):
            proc, self.current = self.current, None
            if proc is not None:
                proc.stdout.close()

        def open_capture(self):
            # Match StrudelEngine: an open first closes the preceding capture.
            self.close_capture()
            self.opens += 1
            if self.opens == 1:
                self.open_started.set()
                if not self.allow_open.wait(timeout=4):
                    raise TimeoutError("test did not release the fake capture")
            proc = Process()
            self.current = proc
            self.processes.append(proc)
            return proc

    engine = RestartingEngine()
    src = object.__new__(strudel_source.StrudelAudioSource)
    src.engine = engine
    src._frames = deque()
    src._lock = threading.Lock()
    src._stop = threading.Event()
    src._capture_lock = threading.Lock()
    src._target = 1
    src.frames_sent = 0
    src.underruns = 0
    src.restarts = 0
    src._proc = engine.first
    src._thread = threading.Thread(target=src._pump, daemon=True)
    src._thread.start()

    # _pump hits EOF, waits its initial backoff, then pauses while creating
    # the replacement capture. Shutdown starts inside that window.
    assert engine.open_started.wait(timeout=4)
    cleanup = threading.Thread(target=src.cleanup, daemon=True)
    cleanup.start()
    assert src._stop.wait(timeout=1)
    engine.allow_open.set()

    src._thread.join(timeout=4)
    cleanup.join(timeout=4)
    assert not src._thread.is_alive()
    assert not cleanup.is_alive()
    assert engine.current is None
    assert all(proc.stdout.closed for proc in engine.processes)
