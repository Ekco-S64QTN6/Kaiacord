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
