"""
RAG Reindex Command
===================

!reindex           — Incremental: scan for new/changed/deleted files only.
!reindex --full    — Remove every node and re-embed everything from scratch.
                     Slow; for an index that is orphaned or corrupt.
"""

import time

from utils.commands.embed_style import box, notice
from utils.infrastructure.logging.kaia_logger import log_action, log_error, log_info, log_success


def _wipe(rag) -> int:
    """Delete every node from every index and clear the manifest. Returns nodes removed.

    Clearing the manifest alone made every file look new, and new files are
    indexed without deleting what they already had: a full reindex doubled
    the index.
    """
    removed = 0
    with rag._data_lock:
        for itype, index in rag.indices.items():
            ids = list(index.storage_context.docstore.docs.keys())
            if ids:
                removed += rag._delete_nodes(itype, ids)
            rag.bm25_cache.pop(itype, None)
        rag.indexed_files.clear()
        file_nodes = getattr(rag, '_file_to_nodes', None)
        if file_nodes is not None:
            file_nodes.clear()
        rag.persist_needed = True
    return removed


async def handle_reindex_command(ctx, msg, send_kaia_response):
    """Handle the !reindex command (Admin only)."""
    if not ctx.config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id)):
        await msg.channel.send(embed=notice("restricted. admins only.", error=True))
        return

    rag = ctx.rag
    if not rag or not getattr(rag, '_initialized', False):
        await msg.channel.send(embed=notice("Retrieval isn't initialised yet; try again in a moment.", error=True))
        return
    lock = getattr(rag, '_index_lock', None)
    if lock is not None and lock.locked():
        # refresh_knowledge_base would only queue itself and return, and the
        # command would report a reindex that never ran.
        await msg.channel.send(embed=notice(
            "An index refresh is already running. Try again when it finishes.", error=True))
        return

    full_wipe = "--full" in msg.content.split()
    status = await msg.channel.send(embed=notice(
        "Removing every node and re-embedding all files. This takes several minutes."
        if full_wipe else "Scanning for new, changed and deleted files.",
        title="🔄  Full reindex" if full_wipe else "🔄  Reindex"))
    log_action(f"!reindex triggered by {msg.author.display_name} (full={full_wipe})")

    try:
        import asyncio
        start = time.time()
        if full_wipe:
            removed = await asyncio.to_thread(_wipe, rag)
            log_info(f"Full reindex: {removed} nodes removed, manifest cleared.")
        before = len(rag.indexed_files)

        from utils.core.rag_executor import run_rag
        await run_rag(rag.refresh_knowledge_base)
        if getattr(rag, 'persist_needed', False):
            await rag.persist_async()

        after = len(rag.indexed_files)
        elapsed = int(time.time() - start)
        summary = (f"Full reindex complete in {elapsed}s: {after} files indexed." if full_wipe else
                   f"Incremental reindex complete in {elapsed}s: {after} files in the manifest "
                   f"({max(0, after - before)} new or changed).")
        await status.edit(embed=box("✅  Reindex complete", summary))
        log_success(f"!reindex complete — {summary}")
    except Exception as e:
        log_error(f"!reindex failed: {e}")
        await status.edit(embed=notice(f"The reindex failed: {type(e).__name__}. The log has the details.", error=True))
