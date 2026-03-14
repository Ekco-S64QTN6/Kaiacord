"""
!sysmon Command Handler
=======================

Owner-only. Displays live system metrics, UFW status, open ports,
and recent SSH activity. Also writes a snapshot to the knowledge base
so Kaia can recall historical anomalies via RAG.
"""

import os
import time
from datetime import datetime
from pathlib import Path

from utils.infrastructure.logging.kaia_logger import log_action, log_error
from utils.infrastructure.system.kaia_sysmon import build_sysmon_report, build_sysmon_report_async

# Where snapshots go for RAG indexing
_SYSMON_LOG_DIR = Path("knowledge_base/system_logs")
_MAX_REPORT_CHARS = 1800  # Discord message limit safety margin


async def handle_sysmon_command(ctx, msg, send_kaia_response):
    """Handle the !sysmon command (owner only)."""
    is_owner = ctx.config.is_owner(
        msg.author.name, msg.author.display_name, str(msg.author.id)
    )
    if not is_owner:
        await msg.channel.send("```\nrestricted. admins only.\n```")
        return

    log_action(f"!sysmon requested by {msg.author.display_name}")

    try:
        report = await build_sysmon_report_async()
    except Exception as e:
        log_error(f"!sysmon report generation failed: {e}")
        await send_kaia_response(msg.channel, "system monitor unavailable right now.")
        return

    # Write snapshot to knowledge_base for RAG recall
    _write_sysmon_snapshot(report)

    # Send to Discord — chunk if over limit
    if len(report) <= _MAX_REPORT_CHARS:
        await msg.channel.send(f"```\n{report}\n```")
    else:
        # Split at section breaks
        chunks = _chunk_report(report, _MAX_REPORT_CHARS)
        for chunk in chunks:
            await msg.channel.send(f"```\n{chunk}\n```")


def _write_sysmon_snapshot(report: str):
    """
    Write a timestamped snapshot to knowledge_base/system_logs/
    so Kaia can recall system history through RAG.
    """
    try:
        _SYSMON_LOG_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y%m%d")
        snapshot_path = _SYSMON_LOG_DIR / f"sysmon_{today}.md"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n\n## Snapshot: {timestamp}\n```\n{report}\n```\n"

        with open(snapshot_path, "a", encoding="utf-8") as f:
            if snapshot_path.stat().st_size == 0 if snapshot_path.exists() else False:
                f.write(f"# System Monitor Log — {today}\n")
            f.write(entry)
    except Exception as e:
        log_error(f"Failed to write sysmon snapshot: {e}")


def _chunk_report(report: str, max_chars: int) -> list[str]:
    """Split report at blank lines to respect Discord's message limit."""
    chunks = []
    current = []
    current_len = 0

    for line in report.splitlines():
        line_len = len(line) + 1
        if current_len + line_len > max_chars and current:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))
    return chunks
