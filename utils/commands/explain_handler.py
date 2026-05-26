"""
Knowledge Source Provenance Display
====================================

!explain — Show which RAG nodes informed the last response,
           including their scores, audit flags, and sources.
"""

import os
import time
import discord
from datetime import datetime
from utils.infrastructure.logging.kaia_logger import log_info


async def handle_explain_command(ctx, msg, send_kaia_response):
    """Handle the !explain command — display provenance of last RAG retrieval."""
    rag = ctx.rag
    if not rag:
        embed = discord.Embed(
            title="📚  PROVENANCE ERROR",
            description="RAG retrieval system is currently unavailable.",
            color=0xcc4444
        )
        await msg.channel.send(embed=embed)
        return

    results = getattr(rag, '_last_retrieval_results', [])

    if not results:
        embed = discord.Embed(
            title="📚  KNOWLEDGE SOURCE PROVENANCE",
            description="No recent retrieval to explain. Ask me something first.",
            color=0x5f5caf
        )
        await msg.channel.send(embed=embed)
        return

    # --- Pre-resolve summary values ---

    confidence = getattr(rag, '_last_retrieval_confidence', 0.0)

    # Confidence label
    if confidence >= 0.75:
        conf_label = "high"
    elif confidence >= 0.45:
        conf_label = "moderate"
    else:
        conf_label = "low"

    # Recency stats (newest/oldest)
    all_dates = []
    for node in results:
        fpath = node.get("metadata", {}).get("file_path", "")
        if fpath and os.path.exists(fpath):
            try: all_dates.append(os.path.getmtime(fpath))
            except: pass

    recency_info = "unknown"
    if all_dates:
        newest = datetime.fromtimestamp(max(all_dates)).strftime("%Y-%m-%d")
        oldest = datetime.fromtimestamp(min(all_dates)).strftime("%Y-%m-%d")
        recency_info = f"{oldest} → {newest}"

    # Self-model status
    self_model_path = os.path.join("memory", "kaia_self_model.md")
    if os.path.exists(self_model_path):
        sm_age = (time.time() - os.path.getmtime(self_model_path)) / 86400
        sm_status = f"active ({sm_age:.0f}d ago)"
    else:
        sm_status = "inactive"

    # --- Build Embed ---

    embed = discord.Embed(
        title="📚  KNOWLEDGE SOURCE PROVENANCE",
        description=f"Confidence rating: **{confidence:.2f} ({conf_label})** · Showing top {min(8, len(results))} of {len(results)} nodes.",
        color=0x10b981
    )

    # Show top 8 sources instead of 5
    top_results = results[:8]

    for i, node in enumerate(top_results, 1):
        metadata = node.get("metadata", {})
        score    = node.get("score", 0.0)
        source_type       = metadata.get("source_type", "unknown")
        retrieval_method  = metadata.get("retrieval_method", "unknown")
        audit_flags       = metadata.get("audit_flags", [])
        file_path         = metadata.get("file_path", "")
        basename          = os.path.basename(file_path) if file_path else "unknown"

        flag_str = f"\n⚑ {', '.join(audit_flags)}" if audit_flags else ""
        embed.add_field(
            name=f"#{i}  Score: {score:.3f} ({retrieval_method.upper()})",
            value=f"📄 `{basename}`\nType: `{source_type}`{flag_str}",
            inline=True
        )

    embed.set_footer(text=f"Range: {recency_info}  ·  Self-model: {sm_status}")

    await msg.channel.send(embed=embed)
    log_info(f"Provenance display shown for {msg.author.name}")
