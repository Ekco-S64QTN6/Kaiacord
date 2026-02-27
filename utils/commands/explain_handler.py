"""
Knowledge Source Provenance Display
====================================

!explain — Show which RAG nodes informed the last response,
           including their scores, audit flags, and sources.
"""

import os
from datetime import datetime
from utils.infrastructure.logging.kaia_logger import log_info


async def handle_explain_command(ctx, msg, send_kaia_response):
    """Handle the !explain command — display provenance of last RAG retrieval."""
    rag = ctx.rag
    if not rag:
        await send_kaia_response(msg.channel, "RAG system not available.")
        return

    results = getattr(rag, '_last_retrieval_results', [])

    if not results:
        await send_kaia_response(
            msg.channel,
            "No recent retrieval to explain. Ask me something first."
        )
        return

    # Show top 5 contributing sources
    top_results = results[:5]
    lines = [
        f"PROVENANCE — {len(results)} total source(s) used",
        "—" * 40,
    ]

    for i, node in enumerate(top_results, 1):
        metadata = node.get("metadata", {})
        score = node.get("score", 0.0)
        label = node.get("label", "Unknown")
        file_path = metadata.get("file_path", "")
        source_type = metadata.get("source_type", "unknown")
        audit_flags = metadata.get("audit_flags", [])
        retrieval_method = metadata.get("retrieval_method", "unknown")

        # File info
        basename = os.path.basename(file_path) if file_path else "unknown"

        # Try to get file modification date
        mod_date = "unknown"
        if file_path and os.path.exists(file_path):
            try:
                mtime = os.path.getmtime(file_path)
                mod_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            except Exception:
                pass

        # Format flags
        flags_str = ""
        if audit_flags:
            flags_str = f"\n     Flags: {', '.join(audit_flags)}"

        # Content preview
        content = node.get("content", "")
        preview = content[:100].replace("\n", " ") + ("..." if len(content) > 100 else "")

        lines.append(
            f"\n#{i} [{label}]  score={score:.3f} [{retrieval_method.upper()}]\n"
            f"   Source: {basename} ({source_type})\n"
            f"   Modified: {mod_date}"
            f"{flags_str}\n"
            f"   Preview: {preview}"
        )

    await send_kaia_response(msg.channel, "\n".join(lines))
    log_info(f"Provenance display shown for {msg.author.name}")
