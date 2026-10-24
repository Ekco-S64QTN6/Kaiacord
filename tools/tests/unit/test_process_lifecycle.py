"""utils/audio/process_lifecycle: one stop sequence for every audio child (issue #46)."""
import io
import signal
import subprocess
import sys
import threading

from utils.audio import process_lifecycle as pl


class Child:
    """A scriptable stand-in for Popen. `waits` are returned or raised in order."""

    def __init__(self, waits=(0,), running=True, has_poll=True):
        self.calls = []
        self._waits = list(waits)
        self._running = running
        self.stdout = io.BytesIO(b"x")
        self.stderr = None
        if not has_poll:
            self.poll = None

    def poll(self):
        self.calls.append("poll")
        return None if self._running else 0

    def terminate(self):
        self.calls.append("terminate")

    def kill(self):
        self.calls.append("kill")

    def send_signal(self, sig):
        self.calls.append(("signal", sig))

    def wait(self, timeout=None):
        assert timeout is not None, "every wait must be bounded"
        self.calls.append("wait")
        value = self._waits.pop(0) if self._waits else 0
        if isinstance(value, BaseException):
            raise value
        return value


def _signals(child):
    return [c for c in child.calls if c not in ("poll", "wait")]


def test_graceful_exit_is_not_killed_and_the_pipe_is_closed():
    child = Child(waits=[0])
    assert pl.stop(child, "capture") is True
    assert _signals(child) == ["terminate"]
    assert child.stdout.closed


def test_timeout_is_killed_then_reaped():
    child = Child(waits=[subprocess.TimeoutExpired("ffmpeg", 3), -9])
    assert pl.stop(child, "capture") is True
    assert _signals(child) == ["terminate", "kill"]
    assert child.calls.count("wait") == 2


def test_an_unexpected_wait_error_still_kills_and_reaps():
    child = Child(waits=[OSError("wait failed"), -9])
    pl.stop(child, "capture")
    assert _signals(child) == ["terminate", "kill"] and child.calls.count("wait") == 2


def test_a_child_that_will_not_reap_is_reported_and_the_pipe_still_closes():
    child = Child(waits=[subprocess.TimeoutExpired("x", 3), subprocess.TimeoutExpired("x", 3)])
    assert pl.stop(child, "capture") is False
    assert child.stdout.closed


def test_a_vanished_child_is_done():
    child = Child()
    child.terminate = lambda: (_ for _ in ()).throw(ProcessLookupError())
    assert pl.stop(child, "capture") is True
    assert "kill" not in child.calls


def test_an_exited_child_is_reaped_without_a_signal():
    child = Child(running=False)
    pl.stop(child, "decoder")
    assert _signals(child) == [] and "wait" in child.calls


def test_policies_send_the_right_first_signal():
    decoder, receiver = Child(), Child()
    pl.stop(decoder, "decoder")
    pl.stop(receiver, "receiver")
    assert _signals(decoder) == ["kill"]
    assert _signals(receiver) == [("signal", signal.SIGINT)]
    # The receiver's stdout belongs to discord.py's reader: left open.
    assert decoder.stdout.closed and not receiver.stdout.closed


def test_a_stream_handed_over_in_place_of_a_process_is_closed():
    stream = io.BytesIO(b"pcm")                  # what the records test factories return
    assert pl.stop(stream, "decoder") is True
    assert stream.closed


def test_owned_process_closes_once_even_from_two_threads():
    child = Child(waits=[0])
    owned = pl.OwnedProcess(child, **pl.POLICIES["capture"])
    threads = [threading.Thread(target=owned.close) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    owned.close()
    assert _signals(child) == ["terminate"]
    assert owned.proc is None


def test_owned_process_as_a_context_manager_keeps_the_original_error():
    child = Child(waits=[0])
    try:
        with pl.OwnedProcess(child, **pl.POLICIES["capture"]):
            raise ValueError("startup failed")
    except ValueError as exc:
        assert str(exc) == "startup failed"
    else:
        raise AssertionError("the original exception was swallowed")
    assert _signals(child) == ["terminate"] and child.stdout.closed


def test_a_real_child_that_ignores_sigterm_is_killed_and_reaped():
    proc = subprocess.Popen(
        [sys.executable, "-c",
         "import signal, sys, time; signal.signal(signal.SIGTERM, signal.SIG_IGN);"
         " sys.stdout.write('ready\\n'); sys.stdout.flush(); time.sleep(30)"],
        stdout=subprocess.PIPE)
    assert proc.stdout.readline() == b"ready\n"
    assert pl.stop(proc, "capture", grace=0.3, kill_wait=5) is True
    assert proc.returncode == -signal.SIGKILL    # reaped: no zombie left behind
    assert proc.stdout.closed
