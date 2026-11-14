"""Filing staged documents from knowledge_base/_ingress/ into the corpus.

`!download` and `!youtube` stage a document and file it right away; the hourly
ingress task files whatever is left (a failed attempt, a hand-placed file).
The asyncio lock serializes callers in this process; process_ingress.py also
takes an OS file lock so CLI and bot processes cannot file the same document
concurrently.
"""
import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Optional

from utils.infrastructure.logging.kaia_logger import log_success, log_warning

TIMEOUT = 600
_lock = asyncio.Lock()


async def run(staged: Optional[Path] = None) -> subprocess.CompletedProcess:
    """Run process_ingress over one staged file, or over everything staged.

    The child gets a session of its own, so a timeout or a cancelled task (the
    bot shutting down) ends it and everything it started, and it is reaped before
    this returns. It is a plain Popen waited on in a worker thread rather than
    asyncio's subprocess machinery: a task cancelled while that machinery was
    still starting the child waited on it with no bound, and never finished."""
    cmd = [sys.executable, "tools/maintenance/process_ingress.py", "--quiet"]
    if staged is not None:
        cmd += ["--file", str(staged)]
    async with _lock:
        if staged is not None and not staged.exists():
            # The hourly pass got there first.
            return subprocess.CompletedProcess(cmd, 0, "already filed", "")
        proc = await asyncio.to_thread(
            subprocess.Popen, cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True)
        waiting = asyncio.ensure_future(asyncio.to_thread(_communicate, proc, TIMEOUT))
        try:
            out, err = await asyncio.shield(waiting)
        except asyncio.CancelledError:
            _end_group(proc, grace=0)                  # shutting down: no time for politeness
            try:
                await asyncio.wait_for(waiting, timeout=10)
            except BaseException:
                pass
            raise
        return subprocess.CompletedProcess(cmd, proc.returncode if proc.returncode is not None else -1, out, err)


def _end_group(proc, grace: float = 10) -> None:
    """Terminate the child's process group, escalate to SIGKILL, reap it. Blocking."""
    import os
    import signal
    try:
        if grace:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=grace)
                return
            except subprocess.TimeoutExpired:
                pass
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def _communicate(proc, timeout: float):
    """Wait for the child's output, ending its group if it runs past `timeout`."""
    try:
        return proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _end_group(proc)
        try:
            proc.communicate(timeout=10)
        except Exception:
            pass
        raise


async def file_now(staged: Path, reply) -> None:
    """File one staged document and say where it went on the reply's embed.

    `reply` is the confirmation message the command sent. A failure leaves the
    document staged for the hourly pass, and the embed says so.
    """
    try:
        result = await run(staged)
        note = (result.stdout or "").strip().splitlines()
        if result.returncode == 0:
            where = note[-1] if note else "filed"
            log_success(f"[ingress] {staged.name}: {where}")
            footer = f"{where} · searchable within five minutes"
        else:
            err = (result.stderr or "").strip().splitlines()
            log_warning(f"[ingress] {staged.name}: {err[-1] if err else 'failed'}")
            footer = "couldn't file it yet; the hourly ingest pass will retry"
    except Exception as e:
        log_warning(f"[ingress] {staged.name}: {type(e).__name__}: {e}")
        footer = "couldn't file it yet; the hourly ingest pass will retry"
    try:
        embed = reply.embeds[0]
        embed.set_footer(text=footer[:200])
        await reply.edit(embed=embed)
    except Exception:
        pass


def start_filing(staged: Path, reply) -> None:
    """Start `file_now` as a tracked background task."""
    from utils.infrastructure.monitoring.async_task_registry import task_registry
    task_registry.register(f"ingress_{staged.stem[:40]}", asyncio.create_task(file_now(staged, reply)))
