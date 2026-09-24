"""Filing staged documents from knowledge_base/_ingress/ into the corpus.

`!download` and `!youtube` stage a document and file it right away; the hourly
ingress task files whatever is left (a failed attempt, a hand-placed file).
Both run tools/maintenance/process_ingress.py under one lock, so two runs never
file the same document twice.
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
    """Run process_ingress over one staged file, or over everything staged."""
    cmd = [sys.executable, "tools/maintenance/process_ingress.py", "--quiet"]
    if staged is not None:
        cmd += ["--file", str(staged)]
    async with _lock:
        if staged is not None and not staged.exists():
            # The hourly pass got there first.
            return subprocess.CompletedProcess(cmd, 0, "already filed", "")
        return await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=TIMEOUT)


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
