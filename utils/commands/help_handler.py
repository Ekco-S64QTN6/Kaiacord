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



def _reference_values():
    """(flag constructs, art palettes), from the modules that accept them.

    Copied by hand they drifted: the copy offered `paraternal_framing`, which
    `!flag` rejects.
    """
    from utils.commands.audit_handler import VALID_CONSTRUCTS
    from utils.core.kaia_art import PALETTES
    return tuple(sorted(VALID_CONSTRUCTS)), tuple(PALETTES)


def _args_of(cmd) -> str:
    """The argument part of a usage string, without repeating the command name.

    `usage` is written as a whole invocation ("!music on [--genre] | off"), which
    makes the line long enough to wrap in an embed field. Splitting the name off
    lets the name stand as the anchor and the arguments trail it quietly.
    """
    usage = (cmd.usage or "").strip()
    if not usage:
        return ""
    head = f"!{cmd.name}"
    return usage[len(head):].strip() if usage.startswith(head) else usage


def _line(cmd) -> str:
    """One command, as a single readable line.

    Discord renders backticks as inline code, so the name reads as something you
    can type and the arguments sit beside it without competing. An em dash
    separates the description; a bullet marks admin.
    """
    args = _args_of(cmd)
    head = f"`!{cmd.name}`" + (f" `{args}`" if args else "")
    marker = " ◆" if cmd.owner_only else ""
    return f"{head}{marker}\n\u2003{cmd.summary}"


def _render_group(commands, group, is_owner):
    """Format one group's commands, hiding what the caller cannot run.

    Everyone's commands first, admin below: a directory that opens with things
    the reader cannot run buries the ones they can.
    """
    mine = [c for c in commands if c.group == group and not c.owner_only]
    admin = [c for c in commands if c.group == group and c.owner_only] if is_owner else []
    return [_line(c) for c in mine] + [_line(c) for c in admin]


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

    total = sum(1 for c in COMMANDS if is_owner or not c.owner_only)

    embed = discord.Embed(
        title="Kaia — Command Directory",
        description=(
            f"{total} commands. Type any of them in chat.\n"
            + ("`◆` marks admin-only." if is_owner
               else "_Admin-only commands are hidden._")
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

    # Reference values, not commands — kept last and kept terse.
    FLAG_CONSTRUCTS, ART_PALETTES = _reference_values()
    embed.add_field(
        name="\u200b",
        value=("**Art palettes** " + " ".join(f"`{p}`" for p in ART_PALETTES)
               + "\n\u2003`!art --palette void`"),
        inline=False,
    )
    if is_owner:
        embed.add_field(
            name="\u200b",
            value=("**Flag constructs** " + " ".join(f"`{c}`" for c in FLAG_CONSTRUCTS)
                   + "\n\u2003`!flag hedge_density`"),
            inline=False,
        )

    embed.set_footer(text="Kaia · self-hosted · gemma3:12b on a single RTX 3060")

    await msg.channel.send(embed=embed)
    log_info(f"Help embed displayed for {msg.author.name} (owner={is_owner})")
