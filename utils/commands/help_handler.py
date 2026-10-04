"""
Help Command
============
!help — a landing page with a button per section; a press swaps the page in
place, so the directory is one message however much is in it.
!help <section | command> opens a section, or one command's card.

Rendered from ``registry.COMMANDS`` rather than a hand-written copy, which had
drifted (three dispatched aliases undocumented, owner-only commands shown to
everyone). Owner-only commands live in the Admin section, offered to owners
only, so every other page holds only what the reader can run. The whole table
as one embed was a wall of 45 commands; a page holds one section.
"""

import discord

from utils.commands.embed_style import add_field, box, shorten
from utils.infrastructure.logging.kaia_logger import log_error, log_info

COLOR = 0x5F5CAF
ADMIN = "🔧  Admin"
HOME = "home"

#: A section's one line on the landing page.
TAGLINES = {
    "🧠  Kaia": "where her answers came from, leaderboards",
    "🎵  Music & art": "she DJs in your voice channel, paints fractals",
    "🌙  Radio & sky": "shortwave, scanners, the ISS, tonight's sky",
    "📰  News & social": "today's headlines, her posts on the agent boards",
    "📚  Knowledge": "hand her a page or a video to read",
    "⚔️  Aethelgard": "the turn-based RPG and fishing",
    ADMIN: "her mind's internals, the index, the machine",
}

#: Short button labels (Discord truncates at 80, but a row of five wants ~14).
LABELS = {
    "🧠  Kaia": ("🧠", "Kaia"), "🎵  Music & art": ("🎵", "Music & art"),
    "🌙  Radio & sky": ("🌙", "Radio & sky"), "📰  News & social": ("📰", "News"),
    "📚  Knowledge": ("📚", "Knowledge"), "⚔️  Aethelgard": ("⚔️", "Aethelgard"),
    ADMIN: ("🔧", "Admin"),
}

FOOTER = "talk to her by @mention or reply — commands are for everything else"


def _reference_values():
    """(flag constructs, art palettes), from the modules that accept them.

    Copied by hand they drifted: the copy offered `paraternal_framing`, which
    `!flag` rejects.
    """
    from utils.commands.audit_handler import VALID_CONSTRUCTS
    from utils.core.kaia_art import PALETTES
    return tuple(sorted(VALID_CONSTRUCTS)), tuple(PALETTES)


def _args_of(cmd) -> str:
    """The argument part of a usage string, without repeating the command name."""
    usage = (cmd.usage or "").strip()
    if not usage:
        return ""
    head = f"!{cmd.name}"
    return usage[len(head):].strip() if usage.startswith(head) else usage


def _line(cmd) -> str:
    args = _args_of(cmd)
    head = f"**`!{cmd.name}`**" + (f" `{args}`" if args else "")
    return f"{head}\n {cmd.summary}"


def _commands(section: str):
    from utils.commands.registry import COMMANDS
    if section == ADMIN:
        return [c for c in COMMANDS if c.owner_only]
    return [c for c in COMMANDS if c.group == section and not c.owner_only]


def sections(is_owner: bool) -> list:
    from utils.commands.registry import GROUP_ORDER
    return [g for g in GROUP_ORDER if _commands(g)] + ([ADMIN] if is_owner else [])


def _fields(embed, title: str, lines: list) -> None:
    """Lines into as many fields as Discord's 1,024-character limit needs."""
    value = ""
    for line in lines:
        if value and len(value) + 1 + len(line) > 1024:
            add_field(embed, title, value)
            title, value = "​", ""
        value = f"{value}\n{line}" if value else line
    if value:
        add_field(embed, title, value)


def home_embed(is_owner: bool) -> discord.Embed:
    from utils.commands.registry import COMMANDS
    total = sum(1 for c in COMMANDS if is_owner or not c.owner_only)
    embed = box("Kaia — commands",
                f"{total} commands in {len(sections(is_owner))} sections. Press a section to open it, "
                "or type `!help <command>` for one command.", COLOR, footer=FOOTER)
    for s in sections(is_owner):
        names = " ".join(f"`!{c.name}`" for c in _commands(s)[:4])
        more = len(_commands(s)) - 4
        add_field(embed, s, f"{TAGLINES.get(s, '')}\n{names}" + (f" +{more}" if more > 0 else ""), inline=True)
    return embed


def section_embed(section: str, is_owner: bool) -> discord.Embed:
    if section == ADMIN and not is_owner:
        return box(ADMIN, "Admin commands are for the bot's owners.", COLOR, footer=FOOTER)
    cmds = _commands(section)
    embed = box(section, TAGLINES.get(section, ""), COLOR, footer=FOOTER)
    if section == "🌙  Radio & sky":
        # Split the way !nightshift does: on the air, then overhead.
        from utils.commands.nightshift import THEME
        fam = {k: v[2] for k, v in THEME.items()}
        for family, title in (("radio", "📻  On the air"), ("sky", "🛰️  Overhead"), (None, "🌙  The panel")):
            _fields(embed, title, [_line(c) for c in cmds if fam.get(c.name) == family])
    else:
        _fields(embed, "​", [_line(c) for c in cmds])
    constructs, palettes = _reference_values()
    if section == "🎵  Music & art":
        add_field(embed, "Art palettes", " ".join(f"`{p}`" for p in palettes) + "\n `!art --palette void`")
    if section == ADMIN:
        add_field(embed, "Flag constructs", " ".join(f"`{c}`" for c in constructs) + "\n `!flag hedge_density`")
    return embed


def command_embed(cmd, is_owner: bool) -> discord.Embed:
    group = ADMIN if cmd.owner_only else cmd.group
    embed = box(f"!{cmd.name}", cmd.summary, COLOR, footer=f"in {group.strip()} · {FOOTER}")
    add_field(embed, "Usage", f"`{shorten(cmd.usage, 1000)}`")
    if cmd.aliases:
        add_field(embed, "Also", " ".join(f"`!{a}`" for a in cmd.aliases))
    if cmd.owner_only and not is_owner:
        add_field(embed, "​", "Owners only.")
    return embed


def _find(word: str, is_owner: bool):
    """A section or a command named by `!help <word>`."""
    from utils.commands.registry import LOOKUP
    w = word.lower().lstrip("!")
    cmd = LOOKUP.get(f"!{w}")
    if cmd is not None:
        return "command", cmd
    for s in sections(is_owner):
        if w and (w in s.lower() or w == LABELS.get(s, ("", ""))[1].lower()):
            return "section", s
    return None, None


def _is_owner(ctx, user) -> bool:
    try:
        return bool(ctx.config.is_owner(user.name, getattr(user, "display_name", user.name), str(user.id)))
    except Exception:
        return False


def help_view(ctx, is_owner: bool, page: str = HOME) -> discord.ui.View:
    """A button per section and one home button. The page shown to whoever
    presses is decided by *their* ownership, not the invoker's."""
    view = discord.ui.View(timeout=None)
    pages = [HOME] + sections(is_owner)
    for i, key in enumerate(pages):
        emoji, label = ("🏠", "Home") if key == HOME else LABELS.get(key, ("", key.strip()))
        style = discord.ButtonStyle.primary if key == page else discord.ButtonStyle.secondary
        button = discord.ui.Button(label=label, emoji=emoji, style=style, row=i // 4)

        async def _pressed(interaction, _key=key):
            try:
                owner = _is_owner(ctx, interaction.user)
                embed = home_embed(owner) if _key == HOME else section_embed(_key, owner)
                if _key == ADMIN and not owner:
                    return await interaction.response.send_message(embed=embed, ephemeral=True)
                await interaction.response.edit_message(embed=embed, view=help_view(ctx, is_owner, _key))
            except Exception as e:
                log_error(f"[help] section {_key!r} failed: {e}")
        button.callback = _pressed
        view.add_item(button)
    if page == "🌙  Radio & sky":
        panel = discord.ui.Button(label="Open the night shift panel", emoji="🌙",
                                  style=discord.ButtonStyle.success, row=2)

        async def _panel(interaction):
            from utils.commands.nightshift import panel_embed, panel_view
            await interaction.response.send_message(embed=panel_embed(), view=panel_view(ctx))
        panel.callback = _panel
        view.add_item(panel)
    return view


async def handle_help_command(ctx, msg, send_kaia_response=None):
    is_owner = _is_owner(ctx, msg.author)
    parts = (msg.content or "").split(maxsplit=1)
    page = HOME
    if len(parts) > 1:
        kind, found = _find(parts[1].strip(), is_owner)
        if kind == "command":
            await msg.channel.send(embed=command_embed(found, is_owner))
            return
        if kind == "section":
            page = found
        else:
            await msg.channel.send(embed=box("Not a command", f"There's no `!{parts[1].strip().lstrip('!')}` — "
                                             "here's everything there is.", COLOR))
    embed = home_embed(is_owner) if page == HOME else section_embed(page, is_owner)
    await msg.channel.send(embed=embed, view=help_view(ctx, is_owner, page))
    log_info(f"Help displayed for {msg.author.name} (owner={is_owner}, page={page.strip()})")
