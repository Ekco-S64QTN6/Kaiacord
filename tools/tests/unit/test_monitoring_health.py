"""Loop and queue health shown on the dashboard: stalls, suppress(), GPU queue depth."""
import asyncio
import time
from unittest.mock import patch

from utils.infrastructure.monitoring.watchdog import LoopWatchdog


def _run(block):
    wd = LoopWatchdog(threshold_seconds=0.3, check_interval=0.1)
    with patch("utils.infrastructure.monitoring.watchdog.log_warning") as warn:
        async def main():
            wd.start(asyncio.get_running_loop())
            await asyncio.sleep(0.2)
            block(wd)
            await asyncio.sleep(0.4)
            wd.stop()
        asyncio.run(main())
    return [c.args[0] for c in warn.call_args_list]


def test_a_stall_is_reported_once_and_its_end_once():
    lines = _run(lambda wd: time.sleep(1.0))
    assert len(lines) == 2
    assert "STALL DETECTED" in lines[0] and "ended after" in lines[1]


def test_a_suppressed_block_raises_no_alert():
    def block(wd):
        with wd.suppress():
            time.sleep(1.0)
    assert _run(block) == []


def test_the_queue_size_counts_calls_waiting_for_the_gpu():
    from utils.infrastructure.gpu import gpu_manager as g

    async def main():
        gate = asyncio.Event()

        async def hold():
            await gate.wait()
        first = asyncio.create_task(g.run_with_gpu_guard("m", hold()))
        await asyncio.sleep(0)
        queued = [asyncio.create_task(g.run_with_gpu_guard("m", asyncio.sleep(0))) for _ in range(2)]
        await asyncio.sleep(0.01)
        depth = g.gpu_queue_depth()
        gate.set()
        await asyncio.gather(first, *queued)
        return depth, g.gpu_queue_depth()

    # A fresh semaphore: a contended asyncio.Semaphore binds to its loop, and
    # the module-level one must stay usable by whatever runs next.
    with patch.object(g, "gpu_semaphore", asyncio.Semaphore(1)):
        assert asyncio.run(main()) == (2, 0)


def test_a_traceback_draws_on_one_dashboard_line():
    from utils.infrastructure.monitoring.btop_dashboard_v2 import _one_line
    drawn = _one_line("Traceback (most recent call last):\n  File \"x.py\"\tline 3\x1b[31m\r")
    assert "\n" not in drawn and "\t" not in drawn and "\x1b" not in drawn and "\r" not in drawn
    assert drawn.startswith("Traceback (most recent call last):   File")


def test_sysmon_never_lets_sudo_ask_for_a_password():
    from utils.infrastructure.system.kaia_sysmon import _noninteractive
    assert _noninteractive(["sudo", "tail", "-n", "6", "/var/log/auth.log"])[:2] == ["sudo", "-n"]
    assert _noninteractive(["sudo", "-n", "ss"]) == ["sudo", "-n", "ss"]
    assert _noninteractive(["uptime"]) == ["uptime"]


def test_sysmon_snapshots_stay_out_of_the_knowledge_base():
    """They list ports, firewall state and SSH activity; anything under
    knowledge_base/ can be retrieved into a public reply."""
    from utils.commands import sysmon_handler
    assert "knowledge_base" not in str(sysmon_handler._SYSMON_LOG_DIR)
