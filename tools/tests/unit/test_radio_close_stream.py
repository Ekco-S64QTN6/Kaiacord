"""kiwi.close_stream must reap the child it kills, and leave stdout to its reader."""
import signal
import subprocess
from unittest.mock import MagicMock

from utils.radio import kiwi


def _proc(*, running=True, wait_effects=()):
    proc = MagicMock()
    proc.poll.return_value = None if running else 0
    proc.wait.side_effect = list(wait_effects)
    return proc


def test_graceful_exit_is_not_killed():
    proc = _proc(wait_effects=[0])
    kiwi.close_stream(proc)
    proc.send_signal.assert_called_once_with(signal.SIGINT)
    proc.kill.assert_not_called()
    proc.stdout.close.assert_not_called()


def test_timeout_is_killed_and_then_reaped():
    proc = _proc(wait_effects=[subprocess.TimeoutExpired("rtl_fm", 3), 0])
    kiwi.close_stream(proc)
    proc.kill.assert_called_once()
    assert proc.wait.call_count == 2          # the second wait is the reap
    proc.stdout.close.assert_not_called()


def test_reap_failure_is_logged_not_raised():
    proc = _proc(wait_effects=[subprocess.TimeoutExpired("rtl_fm", 3),
                               subprocess.TimeoutExpired("rtl_fm", 3)])
    kiwi.close_stream(proc)                   # must not raise
    proc.kill.assert_called_once()


def test_already_exited_or_vanished_child():
    done = _proc(running=False)
    kiwi.close_stream(done)
    done.send_signal.assert_not_called()

    gone = _proc()
    gone.send_signal.side_effect = ProcessLookupError
    kiwi.close_stream(gone)
    gone.kill.assert_not_called()
