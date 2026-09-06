"""
Help Command
============
!help — List all available commands with descriptions.

Rendered from ``registry.COMMANDS`` rather than a hand-written copy. The
previous version was a literal transcription of the command list and had
already drifted: three dispatched aliases (``!dreams``, ``!halloffame``,
``!score``) were undocumented, and nothing marked which commands are
owner-only, so ordinary users were shown a directory of things they could
not run.
"""

import discord

from utils.infrastructure.logging.kaia_logger import log_info

# registry imports this module to build its table, so the table is fetched
# lazily here to keep the two from importing each other at module scope.

# Discord rejects an embed field whose value exceeds this.
_FIELD_LIMIT = 1024

FLAG_CONSTRUCTS = (
    "anthropocentric_exceptionalism", "circular_justification",
    "hedge_density", "linguistic_mimicry", "paraternal_framing",
)

ART_PALETTES = (
    "electric", "ember", "acid", "void", "aurora",
    "ghost", "deep_ocean", "solar_flare", "biolume", "nebula",
)


def _render_group(commands, group, is_owner):
    """Format one group's commands, hiding what the caller cannot run."""
    lines = []
    for cmd in commands:
        if cmd.group != group:
            continue
        if cmd.owner_only and not is_owner:
            continue
        marker = " *(admin)*" if cmd.owner_only else ""
        lines.append(f"`{cmd.usage}` — {cmd.summary}{marker}")
    return lines


def _chunk(lines):
    """Split a group's lines into embed-field-sized values."""
    chunks, current = [], ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > _FIELD_LIMIT:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def handle_help_command(ctx, msg, send_kaia_response):
    """Handle the !help command — display available commands in a clean embed."""
    from utils.commands.registry import COMMANDS, GROUP_ORDER

    is_owner = ctx.config.is_owner(
        msg.author.name, msg.author.display_name, str(msg.author.id)
    )

    embed = discord.Embed(
        title="📖  KAIA — COMMANDS DIRECTORY",
        description=(
            "Cognitive, operational and gaming command interfaces."
            + ("" if is_owner else "\nAdmin-only commands are not listed.")
        ),
        color=0x5F5CAF,
    )

    for group in GROUP_ORDER:
        lines = _render_group(COMMANDS, group, is_owner)
        if not lines:
            continue
        for i, value in enumerate(_chunk(lines)):
            embed.add_field(
                name=group if i == 0 else f"{group} (cont.)",
                value=value,
                inline=False,
            )

    if is_owner:
        embed.add_field(
            name="🏷️  Flag Constructs",
            value=", ".join(f"`{c}`" for c in FLAG_CONSTRUCTS),
            inline=False,
        )

    embed.add_field(
        name="🎨  Art Palettes",
        value=", ".join(f"`{p}`" for p in ART_PALETTES) + " (e.g., `!art --palette void`)",
        inline=False,
    )

    embed.set_footer(text="Kaia Cognitive System · self-hosted")

    await msg.channel.send(embed=embed)
    log_info(f"Help embed displayed for {msg.author.name} (owner={is_owner})")
