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

def _engine_with_fake_capture(proc):
    from utils.audio.strudel_engine import StrudelEngine

    engine = object.__new__(StrudelEngine)
    engine._ffmpeg = proc
    return engine


def test_close_capture_reaps_process_and_closes_stdout():
    class Decoder:
        def __init__(self):
            self.stdout = io.BytesIO(b"audio")
            self.terminated = 0
            self.killed = 0
            self.waited = 0

        def terminate(self):
            self.terminated += 1

        def kill(self):
            self.killed += 1

        def wait(self, timeout=None):
            assert timeout == 3
            self.waited += 1
            return 0

    decoder = Decoder()
    engine = _engine_with_fake_capture(decoder)

    engine.close_capture()
    engine.close_capture()

    assert decoder.terminated == 1
    assert decoder.killed == 0
    assert decoder.waited == 1
    assert decoder.stdout.closed
    assert engine._ffmpeg is None


def test_close_capture_kills_then_waits_again_after_terminate_timeout():
    import subprocess

    class StubbornDecoder:
        def __init__(self):
            self.stdout = io.BytesIO(b"audio")
            self.terminated = 0
            self.killed = 0
            self.waited = 0

        def terminate(self):
            self.terminated += 1

        def kill(self):
            self.killed += 1

        def wait(self, timeout=None):
            assert timeout == 3
            self.waited += 1
            if self.waited == 1:
                raise subprocess.TimeoutExpired("ffmpeg", timeout)
            return -9

    decoder = StubbornDecoder()
    engine = _engine_with_fake_capture(decoder)

    engine.close_capture()

    assert decoder.terminated == 1
    assert decoder.killed == 1
    assert decoder.waited == 2
    assert decoder.stdout.closed
    assert engine._ffmpeg is None
