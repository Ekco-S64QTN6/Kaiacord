"""
RAG Reindex Command
===================

!reindex           — Incremental: scan for new/changed/deleted files only.
!reindex --full    — Full wipe: clear manifest, re-embed everything from scratch.
                     WARNING: slow. use only to fix orphaned/corrupt index nodes.
"""

import asyncio
import time
from utils.infrastructure.logging.kaia_logger import log_action, log_error, log_info, log_success


async def handle_reindex_command(ctx, msg, send_kaia_response):
    """Handle the !reindex command (Admin only)."""

    is_owner = ctx.config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id))
    if not is_owner:
        await msg.channel.send("```\nrestricted. admins only.\n```")
        return

    rag = ctx.rag
    if not rag or not getattr(rag, '_initialized', False):
        await msg.channel.send("```\nRAG not initialized yet. try again in a moment.\n```")
        return

    parts = msg.content.strip().split()
    full_wipe = "--full" in parts

    if full_wipe:
        status_msg = await msg.channel.send(
            "⚠️ **Full reindex initiated.** Clearing manifest and re-embedding all files. "
            "This will take several minutes..."
        )
    else:
        status_msg = await msg.channel.send(
            "🔄 **Incremental reindex started.** Scanning for new/changed/deleted files..."
        )

    log_action(f"!reindex triggered by {msg.author.display_name} (full={full_wipe})")

    try:
        start_time = time.time()

        if full_wipe:
            # Clear the manifest so _find_changed_files() treats everything as new
            with rag._lock:
                before_count = len(rag.indexed_files)
                rag.indexed_files = {}
                rag._file_to_nodes = {}
            log_info(f"Manifest cleared ({before_count} entries wiped). Starting full re-index...")

        # Capture manifest size before refresh for delta reporting
        before = len(rag.indexed_files)

        # Run the actual refresh (scans disk, indexes new/changed, removes deleted)
        from utils.core.rag_executor import run_rag
        await run_rag(rag.refresh_knowledge_base)

        # Persist updated indices to disk
        if getattr(rag, 'persist_needed', False):
            await rag.persist_async()

        after = len(rag.indexed_files)
        elapsed = int(time.time() - start_time)
        delta = after - before

        if full_wipe:
            summary = (
                f"Full reindex complete in {elapsed}s.\n"
                f"Indexed: {after} files total."
            )
        else:
            added = max(0, delta)
            summary = (
                f"Incremental reindex complete in {elapsed}s.\n"
                f"Files in manifest: {after} (+{added} new/changed)."
            )

        await status_msg.edit(content=f"✅ **Reindex Complete**\n```\n{summary}\n```")
        log_success(f"!reindex complete — {summary.replace(chr(10), ' ')}")

    except Exception as e:
        log_error(f"!reindex failed: {e}")
        await status_msg.edit(content=f"```\nreindex failed: {type(e).__name__}: {e}\n```")
