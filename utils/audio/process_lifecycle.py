"""Stopping the child processes the audio and radio code owns (issue #46).

Records decks (ffmpeg decoders), the Strudel capture (ffmpeg from the pulse
sink) and receiver streams (rtl_fm, kiwirecorder) each stopped their child
with a hand-written sequence, and the sequences drifted: one killed without
reaping, leaving a zombie for the life of the bot; one left its pipe open;
one waited without a bound. This is the one sequence they share:

    first signal → bounded wait → kill (on a timeout or on any other wait
    error) → bounded wait to reap → close the owned pipes, whatever raised

`first` is per child, because the right first signal is: ffmpeg capture takes
SIGTERM; rtl_fm and kiwirecorder take SIGINT so they let go of the dongle or
the remote slot and close their files; a decoder being retired is simply
killed. Threads, restarts and backpressure stay with each owner; they differ
too much to share.

The functions take duck-typed objects, not only `subprocess.Popen`: tests and
the records stream factory pass stand-ins without `poll`, `terminate` or a
`stdout`, and a stand-in that *is* the stream is closed as the pipe.
"""
from __future__ import annotations

import signal
import subprocess
import threading
from typing import Optional, Union

from utils.infrastructure.logging.kaia_logger import log_debug, log_warning

First = Union[str, int]          # "terminate", "kill", or a signal number


def _call(obj, name, *args, **kwargs):
    fn = getattr(obj, name, None)
    return fn(*args, **kwargs) if callable(fn) else None


def _running(proc) -> bool:
    poll = getattr(proc, "poll", None)
    if not callable(poll):
        return True                 # no way to ask: treat it as running
    try:
        return poll() is None
    except Exception:
        return True


def _signal(proc, first: First) -> None:
    if first == "kill":
        _call(proc, "kill")
    elif first == "terminate":
        if callable(getattr(proc, "terminate", None)):
            proc.terminate()
        else:
            _call(proc, "kill")
    else:
        if callable(getattr(proc, "send_signal", None)):
            proc.send_signal(first)
        else:
            _call(proc, "terminate")


def _wait(proc, timeout: float):
    wait = getattr(proc, "wait", None)
    if callable(wait):
        return wait(timeout=timeout)
    return None


def close_pipes(proc, tag: str = "[audio]", name: str = "child") -> None:
    """Close the child's stdout/stderr pipes, or the object itself if it is the stream."""
    pipes = [getattr(proc, "stdout", None), getattr(proc, "stderr", None)]
    if pipes == [None, None] and callable(getattr(proc, "read", None)):
        pipes = [proc]
    for pipe in pipes:
        if pipe is None:
            continue
        try:
            _call(pipe, "close")
        except Exception as exc:
            log_debug(f"{tag} closing {name} pipe: {exc}")


def stop_process(proc, *, first: First = "terminate", grace: float = 3.0,
                 kill_wait: float = 3.0, pipes: bool = True,
                 name: str = "child", tag: str = "[audio]") -> bool:
    """Stop and reap `proc`. Never raises. Returns False only if a child that
    was killed still could not be reaped (logged as a warning)."""
    if proc is None:
        return True
    reaped = True
    try:
        if not _running(proc):
            # Exited already; reap it in case nothing has, but send nothing.
            try:
                _wait(proc, grace)
            except Exception as exc:
                log_debug(f"{tag} reaping exited {name}: {exc}")
            return True
        try:
            _signal(proc, first)
        except ProcessLookupError:
            return True             # gone between the poll and the signal
        except Exception as exc:
            log_debug(f"{tag} signalling {name}: {exc}")
        try:
            _wait(proc, grace)
            return True
        except subprocess.TimeoutExpired:
            pass
        except Exception as exc:
            # Not a timeout, but the child may still be alive: do not abandon it.
            log_debug(f"{tag} waiting for {name}: {exc}")
        # Also after a first "kill" that did not reap in time: kill again.
        try:
            _call(proc, "kill")
        except ProcessLookupError:
            return True
        except Exception as exc:
            log_debug(f"{tag} killing {name}: {exc}")
        try:
            _wait(proc, kill_wait)
        except Exception as exc:
            reaped = False
            log_warning(f"{tag} {name} did not exit after kill: {exc}")
        return reaped
    finally:
        if pipes:
            close_pipes(proc, tag, name)


class OwnedProcess:
    """One child and the right way to stop it. `close()` is idempotent and
    safe from several threads: the handle is detached under a lock and stopped
    outside it, so a close racing a restart can neither stop the same child
    twice nor block the restart while it waits."""

    def __init__(self, proc, **stop_options):
        self._proc = proc
        self._stop = stop_options
        self._lock = threading.Lock()

    @property
    def proc(self):
        return self._proc

    @property
    def stdout(self):
        return getattr(self._proc, "stdout", None)

    def detach(self):
        with self._lock:
            proc, self._proc = self._proc, None
        return proc

    def close(self) -> bool:
        proc = self.detach()
        return stop_process(proc, **self._stop) if proc is not None else True

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False


#: The stop policies of the children this project owns, so a call site names
#: its kind rather than restating the numbers.
POLICIES = {
    "decoder": dict(first="kill", grace=1.0, kill_wait=1.0, pipes=True, name="decoder", tag="[records]"),
    "capture": dict(first="terminate", grace=3.0, kill_wait=3.0, pipes=True, name="ffmpeg capture", tag="[music]"),
    # The stream's stdout belongs to discord.py's reader, which must see
    # end-of-stream and exit on its own (`live.stop`): never close it here.
    "receiver": dict(first=signal.SIGINT, grace=3.0, kill_wait=3.0, pipes=False, name="receiver stream", tag="[radio]"),
}


def stop(proc, kind: str, **overrides) -> bool:
    return stop_process(proc, **{**POLICIES[kind], **overrides})
