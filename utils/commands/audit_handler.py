"""
Audit Flag System
=================

!flag <construct> — tag the sources behind this channel's last reply with a
                    Data Rot label; flagged nodes lose retrieval weight.
!audit            — flag counts by construct and by source.

Both owner-only. `!flag` flags what `!explain` shows: the nodes the reply
actually drew on, from the retrieval trace for the channel it is typed in.
"""

import asyncio
import os

from utils.commands.embed_style import COLOR_SOURCES, add_field, box, notice
from utils.infrastructure.logging.kaia_logger import log_action, log_info

# Valid Data Rot constructs from the Firewall Dialogue, with display labels.
CONSTRUCT_LABELS = {
    "circular_justification": "Circular Justification",
    "linguistic_mimicry": "Linguistic Mimicry",
    "anthropocentric_exceptionalism": "Anthropocentric Exceptionalism",
    "paternalistic_framing": "Paternalistic Framing",
    "hedge_density": "Hedge Density",
}
VALID_CONSTRUCTS = set(CONSTRUCT_LABELS)
_CONSTRUCT_LIST = ", ".join(f"`{c}`" for c in sorted(VALID_CONSTRUCTS))


async def _unavailable(ctx, msg) -> bool:
    """Send the reason and return True when the audit flags can't be used now."""
    if not ctx.config.get('features.audit_flags_enabled', True):
        await msg.channel.send(embed=notice("Audit flags are switched off.", error=True))
        return True
    if not ctx.rag:
        await msg.channel.send(embed=notice("Retrieval is unavailable right now.", error=True))
        return True
    return False


async def handle_flag_command(ctx, msg, send_kaia_response):
    """Handle !flag <construct>."""
    if not ctx.config.is_owner(msg.author.name, user_id=str(msg.author.id)):
        await msg.channel.send(embed=notice("restricted. only the owner can flag content.", error=True))
        return
    if await _unavailable(ctx, msg):
        return

    parts = msg.content.strip().split(maxsplit=1)
    if len(parts) < 2:
        await msg.channel.send(embed=notice(
            f"Usage: `!flag <construct>`\nConstructs: {_CONSTRUCT_LIST}", title="🏷️  Flag"))
        return
    construct = parts[1].strip().lower().replace(" ", "_")
    if construct not in VALID_CONSTRUCTS:
        await msg.channel.send(embed=notice(
            f"Unknown construct. Use one of: {_CONSTRUCT_LIST}", error=True))
        return

    from utils.infrastructure.monitoring.retrieval_trace import recent
    last = recent(1, channel_id=msg.channel.id)
    node_ids = [n["id"] for n in (last[0]["nodes"] if last else []) if n.get("id")]
    if not node_ids:
        await msg.channel.send(embed=notice(
            "Nothing retrieved in this channel to flag. Ask me something first.", error=True))
        return

    # Flagging persists the index; that is seconds of disk work.
    flagged = await asyncio.to_thread(ctx.rag.flag_nodes, node_ids, construct)
    label = CONSTRUCT_LABELS[construct]
    await msg.channel.send(embed=box(
        "🏷️  Flagged",
        f"**{flagged}** of {len(node_ids)} source passage(s) flagged **{label}**"
        + (" (the rest already were)." if flagged < len(node_ids) else ".")
        + "\nThey carry less weight in retrieval from now on.", COLOR_SOURCES))
    log_action(f"Audit flag: {flagged} nodes flagged as [{construct}] by {msg.author.name}")


async def handle_audit_command(ctx, msg, send_kaia_response):
    """Handle !audit — flag statistics."""
    if not ctx.config.is_owner(msg.author.name, user_id=str(msg.author.id)):
        await msg.channel.send(embed=notice("restricted. only the owner can view the audit.", error=True))
        return
    if await _unavailable(ctx, msg):
        return

    summary = await asyncio.to_thread(ctx.rag.get_audit_summary)
    if not summary["total_flagged"]:
        await msg.channel.send(embed=notice("No passages have been flagged yet.", title="📊  Audit"))
        return

    embed = box("📊  Audit", f"Flagged passages: **{summary['total_flagged']}**", COLOR_SOURCES)
    add_field(embed, "By construct", "\n".join(
        f"• **{CONSTRUCT_LABELS.get(c, c)}**: {n}"
        for c, n in sorted(summary["by_construct"].items(), key=lambda x: -x[1])))
    if summary["top_sources"]:
        add_field(embed, "Most-flagged sources", "\n".join(
            f"• `{os.path.basename(src)}`: {n}" for src, n in summary["top_sources"][:5]))
    penalty = ctx.config.get('audit.flag_penalty', 0.15)
    add_field(embed, "Weight", f"−{penalty:.2f} per flag, at most −{penalty * 3:.2f}")
    await msg.channel.send(embed=embed)
    log_info(f"Audit report displayed for {msg.author.name}")
