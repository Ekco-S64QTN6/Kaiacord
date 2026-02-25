"""
Audit Flag System
=================

Commands for tagging RAG nodes with Data Rot constructs and viewing audit stats.

!flag <construct_name> — Tag the last retrieval's nodes with a Data Rot label.
!audit                 — Show audit flag summary statistics.
"""

import os
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
        await send_kaia_response(msg.channel, "Audit flags are currently disabled.")
        return

    # Owner-only command
    if not config.is_owner(msg.author.name, user_id=str(msg.author.id)):
        await send_kaia_response(msg.channel, "Only the owner can flag content.")
        return

    content = msg.content.strip()
    parts = content.split(maxsplit=1)

    if len(parts) < 2:
        constructs_list = ", ".join(sorted(VALID_CONSTRUCTS))
        await send_kaia_response(
            msg.channel,
            f"Usage: !flag <construct>\n\nValid constructs:\n{constructs_list}"
        )
        return

    construct = parts[1].strip().lower().replace(" ", "_")

    if construct not in VALID_CONSTRUCTS:
        constructs_list = ", ".join(sorted(VALID_CONSTRUCTS))
        await send_kaia_response(
            msg.channel,
            f"Unknown construct: '{construct}'\n\nValid constructs:\n{constructs_list}"
        )
        return

    rag = ctx.rag
    if not rag:
        await send_kaia_response(msg.channel, "RAG system not available.")
        return

    # Get the most recent retrieval node IDs
    last_node_ids = getattr(rag, '_last_retrieval_node_ids', [])
    if not last_node_ids:
        await send_kaia_response(
            msg.channel,
            "No recent retrieval to flag. Ask me something first, then flag the results."
        )
        return

    # Flag the nodes
    flagged_count = rag.flag_nodes(last_node_ids, construct)

    label = CONSTRUCT_LABELS.get(construct, construct)
    await send_kaia_response(
        msg.channel,
        f"Flagged {flagged_count} node(s) with [{label}].\n"
        f"These nodes will receive reduced retrieval weight going forward."
    )
    log_action(f"Audit flag: {flagged_count} nodes flagged as [{construct}] by {msg.author.name}")


async def handle_audit_command(ctx, msg, send_kaia_response):
    """Handle the !audit command — display audit flag statistics."""
    from utils.infrastructure.system.yaml_config import config

    if not config.get('features.audit_flags_enabled', True):
        await send_kaia_response(msg.channel, "Audit flags are currently disabled.")
        return

    rag = ctx.rag
    if not rag:
        await send_kaia_response(msg.channel, "RAG system not available.")
        return

    summary = rag.get_audit_summary()

    if not summary["total_flagged"]:
        await send_kaia_response(msg.channel, "No audit flags recorded yet.")
        return

    # Format the report
    lines = [
        f"AUDIT REPORT — {summary['total_flagged']} flagged node(s)",
        f"{'—' * 40}",
    ]

    # Counts per construct
    lines.append("\nFlags by construct:")
    for construct, count in sorted(summary["by_construct"].items(), key=lambda x: -x[1]):
        label = CONSTRUCT_LABELS.get(construct, construct)
        lines.append(f"  {label}: {count}")

    # Most-flagged sources
    if summary["top_sources"]:
        lines.append("\nMost-flagged sources:")
        for source, count in summary["top_sources"][:5]:
            lines.append(f"  {os.path.basename(source)}: {count} flag(s)")

    # Total weight reduction
    penalty = config.get('rag_scoring.audit_flag_penalty', 0.15)
    max_penalty = penalty * 3  # capped at 3 flags
    lines.append(f"\nPenalty per flag: -{penalty:.2f} (max -{max_penalty:.2f})")

    await send_kaia_response(msg.channel, "\n".join(lines))
    log_info(f"Audit report displayed for {msg.author.name}")
