"""
Audit Flag System
=================

Commands for tagging RAG nodes with Data Rot constructs and viewing audit stats.

!flag <construct_name> — Tag the last retrieval's nodes with a Data Rot label.
!audit                 — Show audit flag summary statistics.
"""

import os
import discord
from datetime import datetime
from utils.infrastructure.logging.kaia_logger import log_action, log_info, log_warning, log_error


# Valid Data Rot constructs from the Firewall Dialogue
VALID_CONSTRUCTS = {
    "circular_justification",
    "linguistic_mimicry",
    "anthropocentric_exceptionalism",
    "paternalistic_framing",
    "hedge_density",
}

# Human-readable labels for display
CONSTRUCT_LABELS = {
    "circular_justification": "Circular Justification",
    "linguistic_mimicry": "Linguistic Mimicry",
    "anthropocentric_exceptionalism": "Anthropocentric Exceptionalism",
    "paternalistic_framing": "Paternalistic Framing",
    "hedge_density": "Hedge Density",
}


async def handle_flag_command(ctx, msg, send_kaia_response):
    """Handle the !flag <construct_name> command."""
    from utils.infrastructure.system.yaml_config import config

    if not config.get('features.audit_flags_enabled', True):
        embed = discord.Embed(
            title="🏷️  AUDIT FLAGS DISABLED",
            description="Audit flags are currently disabled.",
            color=0xcc4444
        )
        await msg.channel.send(embed=embed)
        return

    # Owner-only command
    if not config.is_owner(msg.author.name, user_id=str(msg.author.id)):
        embed = discord.Embed(
            title="🏷️  RESTRICTED COMMAND",
            description="Only the owner can flag content.",
            color=0xcc4444
        )
        await msg.channel.send(embed=embed)
        return

    content = msg.content.strip()
    parts = content.split(maxsplit=1)

    if len(parts) < 2:
        constructs_list = ", ".join([f"`{c}`" for c in sorted(VALID_CONSTRUCTS)])
        embed = discord.Embed(
            title="🏷️  FLAG COMMAND USAGE",
            description="Usage: `!flag <construct>`",
            color=0x5f5caf
        )
        embed.add_field(name="Valid Constructs", value=constructs_list, inline=False)
        await msg.channel.send(embed=embed)
        return

    construct = parts[1].strip().lower().replace(" ", "_")

    if construct not in VALID_CONSTRUCTS:
        constructs_list = ", ".join([f"`{c}`" for c in sorted(VALID_CONSTRUCTS)])
        embed = discord.Embed(
            title="🏷️  UNKNOWN CONSTRUCT",
            description=f"Unknown construct: `{construct}`",
            color=0xcc4444
        )
        embed.add_field(name="Valid Constructs", value=constructs_list, inline=False)
        await msg.channel.send(embed=embed)
        return

    rag = ctx.rag
    if not rag:
        embed = discord.Embed(
            title="🏷️  SYSTEM ERROR",
            description="RAG system not available.",
            color=0xcc4444
        )
        await msg.channel.send(embed=embed)
        return

    # Get the most recent retrieval node IDs
    last_node_ids = getattr(rag, '_last_retrieval_node_ids', [])
    if not last_node_ids:
        embed = discord.Embed(
            title="🏷️  NO ACTIVE RETRIEVAL",
            description="No recent retrieval to flag. Ask me something first, then flag the results.",
            color=0xcc4444
        )
        await msg.channel.send(embed=embed)
        return

    # Flag the nodes
    flagged_count = rag.flag_nodes(last_node_ids, construct)

    label = CONSTRUCT_LABELS.get(construct, construct)
    embed = discord.Embed(
        title="🏷️  CONTENT FLAGGED",
        description=f"Flagged **{flagged_count}** node(s) with **{label}**.",
        color=0x10b981
    )
    embed.add_field(
        name="Impact",
        value="These nodes will receive reduced retrieval weight going forward.",
        inline=False
    )
    await msg.channel.send(embed=embed)
    log_action(f"Audit flag: {flagged_count} nodes flagged as [{construct}] by {msg.author.name}")


async def handle_audit_command(ctx, msg, send_kaia_response):
    """Handle the !audit command — display audit flag statistics."""
    from utils.infrastructure.system.yaml_config import config

    if not config.get('features.audit_flags_enabled', True):
        embed = discord.Embed(
            title="📊  AUDIT FLAGS DISABLED",
            description="Audit flags are currently disabled.",
            color=0xcc4444
        )
        await msg.channel.send(embed=embed)
        return

    rag = ctx.rag
    if not rag:
        embed = discord.Embed(
            title="📊  SYSTEM ERROR",
            description="RAG system not available.",
            color=0xcc4444
        )
        await msg.channel.send(embed=embed)
        return

    summary = rag.get_audit_summary()

    if not summary["total_flagged"]:
        embed = discord.Embed(
            title="📊  AUDIT SUMMARY REPORT",
            description="No audit flags recorded yet in the RAG node index database.",
            color=0x5f5caf
        )
        await msg.channel.send(embed=embed)
        return

    embed = discord.Embed(
        title="📊  AUDIT SUMMARY REPORT",
        description=f"Total Flagged Nodes: **{summary['total_flagged']}**",
        color=0xf97316
    )

    # Counts per construct
    construct_lines = []
    for construct, count in sorted(summary["by_construct"].items(), key=lambda x: -x[1]):
        label = CONSTRUCT_LABELS.get(construct, construct)
        construct_lines.append(f"• **{label}**: {count}")
    embed.add_field(
        name="Flags by Construct",
        value="\n".join(construct_lines) if construct_lines else "None",
        inline=False
    )

    # Most-flagged sources
    if summary["top_sources"]:
        source_lines = []
        for source, count in summary["top_sources"][:5]:
            source_lines.append(f"• `{os.path.basename(source)}`: {count} flag(s)")
        embed.add_field(
            name="Most-Flagged Sources",
            value="\n".join(source_lines),
            inline=False
        )

    # Total weight reduction
    penalty = config.get('rag_scoring.audit_flag_penalty', 0.15)
    max_penalty = penalty * 3  # capped at 3 flags
    embed.add_field(
        name="Weight Reductions",
        value=f"Penalty per flag: `-{penalty:.2f}` (Capped at `-{max_penalty:.2f}`)",
        inline=False
    )

    embed.set_footer(text="Kaia Audit & Governance Pipeline")
    await msg.channel.send(embed=embed)
    log_info(f"Audit report displayed for {msg.author.name}")
