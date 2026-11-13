"""The process ends after the bot has shut down, and a killed process is seen to be gone."""
import asyncio
import subprocess
import sys
import threading
import time
import types

import psutil
import pytest

from utils.infrastructure.gpu import clear_gpu_memory
from utils.infrastructure.gpu.clear_gpu_memory import stop_and_reap
from utils.infrastructure.system import dashboard_manager as dm
from utils.infrastructure.system.shutdown_fixed import shutdown_manager


class _Logger:
    def __init__(self):
        self.modes = []

    def set_dashboard_mode(self, enabled, queue=None):
        self.modes.append(enabled)


class _Screen:
    """A dashboard process that has already closed, as it does the moment it is asked to."""
    def __init__(self):
        self.joined = False

    def join(self, timeout=None):
        self.joined = True


@pytest.fixture
def complete_flag():
    was_set = shutdown_manager._shutdown_complete.is_set()
    shutdown_manager._shutdown_complete.clear()
    yield shutdown_manager._shutdown_complete
    (shutdown_manager._shutdown_complete.set if was_set else shutdown_manager._shutdown_complete.clear)()


def test_the_screen_closing_does_not_end_the_wait_for_the_bot(complete_flag):
    saved = []

    def bot_shutdown():
        time.sleep(0.4)                       # the state and index save
        saved.append("saved")
        complete_flag.set()

    bot = threading.Thread(target=bot_shutdown, daemon=True)
    bot.start()
    logger, screen = _Logger(), _Screen()
    assert dm.wait_for_bot_shutdown(bot, screen, logger, deadline_s=5.0) is True
    assert saved == ["saved"] and screen.joined
    assert logger.modes == [False]            # the rest of the shutdown is printed, not queued


def test_a_shutdown_past_the_deadline_is_reported_not_called_clean(complete_flag):
    release = threading.Event()
    bot = threading.Thread(target=release.wait, daemon=True)
    bot.start()
    started = time.monotonic()
    try:
        assert dm.wait_for_bot_shutdown(bot, _Screen(), _Logger(), deadline_s=0.2) is False
        assert time.monotonic() - started < 3.0
    finally:
        release.set()


def test_a_bot_that_stopped_without_its_teardown_is_not_called_clean(complete_flag):
    bot = threading.Thread(target=lambda: None)
    bot.start()
    bot.join()
    assert dm.wait_for_bot_shutdown(bot, None, _Logger(), deadline_s=1.0) is False


def test_a_task_that_swallows_its_cancel_cannot_hold_the_bot_thread_open(monkeypatch):
    monkeypatch.setattr(dm, "LOOP_DRAIN_S", 0.2)
    monkeypatch.setattr(dm.task_registry, "register", lambda *a, **k: None)
    release = threading.Event()

    async def stubborn():
        while not release.is_set():
            try:
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                pass

    async def run_bot(stats_poller, stop_event):
        asyncio.get_running_loop().create_task(stubborn())
        await asyncio.sleep(0)

    stop = threading.Event()
    stop.set()
    thread = threading.Thread(
        target=dm._run_bot_in_thread,
        args=({}, None, None, stop, lambda: None, run_bot), daemon=True)
    thread.start()
    thread.join(timeout=5.0)
    try:
        assert not thread.is_alive()
    finally:
        release.set()


def _child(code):
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE)
    proc.stdout.readline()                    # it is up, and its handler is installed
    return proc


def test_a_process_that_ignores_sigterm_is_killed_and_seen_to_be_gone():
    child = _child("import signal,time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                   "print('up', flush=True)\ntime.sleep(60)")
    try:
        assert stop_and_reap(psutil.Process(child.pid), grace=0.3) is True
        assert child.poll() is not None
    finally:
        child.kill()
        child.wait()


def test_a_process_already_gone_counts_as_stopped():
    child = _child("print('up', flush=True)")
    child.wait()
    handle = types.SimpleNamespace(terminate=lambda: (_ for _ in ()).throw(psutil.NoSuchProcess(child.pid)))
    assert stop_and_reap(handle, grace=0.1) is True


class _Unkillable:
    def __init__(self):
        self.calls = []

    def terminate(self):
        self.calls.append("terminate")

    def kill(self):
        self.calls.append("kill")

    def wait(self, timeout=None):
        self.calls.append(f"wait {timeout}")
        raise psutil.TimeoutExpired(timeout)


def test_a_process_that_survives_sigkill_is_reported():
    proc = _Unkillable()
    assert stop_and_reap(proc, grace=0.1, kill_wait=0.2) is False
    assert proc.calls == ["terminate", "wait 0.1", "kill", "wait 0.2"]


def _manager():
    return dm.DashboardManager(ctx=None, bot=None, config=None, bot_state=None,
                               stats_tracker=None, stats_poller=None, logger=_Logger())


def _other_instance(proc):
    proc.info = {"pid": 4242, "ppid": 1, "name": "python3", "exe": "/usr/bin/python3",
                 "cmdline": ["python3", "Kaiacord.py"]}
    return proc


def test_startup_does_not_go_on_beside_an_instance_it_could_not_stop(monkeypatch):
    proc = _other_instance(_Unkillable())
    monkeypatch.setattr(dm.psutil, "process_iter", lambda attrs=None: [proc])
    monkeypatch.setattr(dm, "OTHER_INSTANCE_GRACE_S", 0.05)
    cleared = []
    monkeypatch.setattr(clear_gpu_memory, "clear_gpu_memory", lambda **k: cleared.append(1))
    with pytest.raises(SystemExit):
        _manager().cleanup_on_startup()
    assert cleared == [] and "kill" in proc.calls


def test_startup_waits_for_the_instance_it_replaces_before_touching_the_gpu(monkeypatch):
    order = []

    class Leaving(_Unkillable):
        def wait(self, timeout=None):
            order.append("gone")

    monkeypatch.setattr(dm.psutil, "process_iter", lambda attrs=None: [_other_instance(Leaving())])
    monkeypatch.setattr(clear_gpu_memory, "clear_gpu_memory", lambda **k: order.append("gpu"))
    _manager().cleanup_on_startup()
    assert order == ["gone", "gpu"]


def test_the_forced_exit_writes_out_the_log_first(monkeypatch):
    import os
    from utils.infrastructure.logging import unified_logging
    order = []
    monkeypatch.setattr(unified_logging.logger, "stop", lambda: order.append("log flushed"))
    monkeypatch.setattr(os, "_exit", lambda code: order.append(f"exit {code}"))
    monkeypatch.setattr(shutdown_manager, "restore_terminal", lambda: None)
    shutdown_manager.force_exit(1)
    assert order == ["log flushed", "exit 1"]
