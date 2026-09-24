"""!enrich [--category all|knowledge|logs] [--limit N] [--dry-run] — owner only.

Runs tools/maintenance/enrich_metadata.py over the knowledge base and shows its
summary. Ten minutes at most; larger batches belong in a terminal.
"""
import asyncio
import re
import sys
from pathlib import Path

from utils.commands.embed_style import box, notice
from utils.infrastructure.logging.kaia_logger import log_action, log_error, log_info

FENCE = "`" * 3
TIMEOUT = 600.0
MAX_LIMIT = 500
CATEGORIES = ("all", "knowledge", "logs")
SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "maintenance" / "enrich_metadata.py"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _parse(parts):
    """(category, limit, dry_run) from the command words, or an error string."""
    category, limit = "knowledge", 50
    if "--category" in parts:
        i = parts.index("--category")
        category = parts[i + 1].lower() if i + 1 < len(parts) else ""
        if category not in CATEGORIES:
            return "Category must be one of: all, knowledge, logs."
    if "--limit" in parts:
        i = parts.index("--limit")
        value = parts[i + 1] if i + 1 < len(parts) else ""
        if not value.isdigit() or not 1 <= int(value) <= MAX_LIMIT:
            return f"`--limit` takes a number from 1 to {MAX_LIMIT}."
        limit = int(value)
    return category, limit, "--dry-run" in parts


def _summary(stdout: bytes) -> str:
    """The lines after the tool's completion marker, else its last fifteen."""
    lines = [l.strip() for l in _ANSI.sub("", stdout.decode(errors="replace"))
             .replace("\r", "\n").split("\n") if l.strip()]
    marker = next((i for i, l in enumerate(lines) if "--- ENRICHMENT COMPLETED ---" in l), None)
    return "\n".join(lines[marker + 1:] if marker is not None else lines[-15:])


async def handle_enrich_command(ctx, msg, send_kaia_response):
    """Trigger metadata enrichment and report what the tool said."""
    if not ctx.config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id)):
        await msg.channel.send(embed=notice("restricted. this command is for admins only.", error=True))
        return

    parsed = _parse(msg.content.strip().split())
    if isinstance(parsed, str):
        await msg.channel.send(embed=notice(parsed, error=True))
        return
    category, limit, dry_run = parsed
    if not SCRIPT.exists():
        await msg.channel.send(embed=notice("The enrichment script is missing.", error=True))
        return

    mode = "dry run" if dry_run else "writing"
    status = await msg.channel.send(embed=notice(
        f"Category `{category}`, up to {limit} files, {mode}.", title="🔄  Enrichment running"))
    log_action(f"Admin {msg.author.display_name} triggered !enrich "
               f"(category={category}, limit={limit}, dry_run={dry_run})")

    cmd = [sys.executable, str(SCRIPT), "--category", category, "--limit", str(limit),
           "--dry-run" if dry_run else "--apply"]
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=str(SCRIPT.parents[2]))
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=TIMEOUT)
        except (asyncio.TimeoutError, asyncio.CancelledError) as e:
            if process.returncode is None:
                try:
                    process.terminate()
                    await process.wait()
                except (ProcessLookupError, OSError):
                    pass
            if isinstance(e, asyncio.CancelledError):
                raise
            await status.edit(embed=notice(
                f"Stopped after {int(TIMEOUT // 60)} minutes. Run large batches from a terminal.",
                error=True))
            return

        summary = _summary(stdout).replace(FENCE, "ˋˋˋ")[-3800:]
        if process.returncode != 0:
            log_error(f"!enrich exited {process.returncode}: {stderr.decode(errors='replace')[-500:]}")
            await status.edit(embed=notice(
                f"The enrichment tool failed (exit {process.returncode}); the log has its error.",
                error=True))
            return
        body = f"{FENCE}\n{summary}\n{FENCE}" if summary else "Finished; the tool printed nothing."
        await status.edit(embed=box("✅  Enrichment complete", body))
        log_info(f"!enrich completed for {msg.author.display_name}")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log_error(f"Failed to run !enrich command: {e}")
        await status.edit(embed=notice(f"Enrichment failed: {type(e).__name__}.", error=True))
