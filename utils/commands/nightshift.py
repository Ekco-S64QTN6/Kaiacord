"""Kaia's night shift: the radio and sky commands, and the index that lists them.

Every box in the theme ends with one short pointer to `!nightshift`; the index
is the only place the whole set is listed. A list of siblings under every
answer read as clutter and buried the answer's own footer. THEME is the index's
one source, so a new command is added once.
"""
from __future__ import annotations

from utils.commands.embed_style import add_field, box

COLOR_NIGHT = 0x3B5B8B

#: key → (usage, one line, family)
THEME = {
    "skyking": ("!skyking [n | classic]", "latest military EAMs", "radio"),
    "numbers": ("!numbers [station] [hours]", "number stations on the air soon", "radio"),
    "radio": ("!radio [hfgcs | kHz | station | log | listen | off]", "what Kaia heard · listen live", "radio"),
    "buzzer": ("!buzzer", "UVB-76, The Buzzer, live", "radio"),
    "tacamo": ("!tacamo", "are the EAM relay planes up?", "radio"),
    "spaceweather": ("!spaceweather", "the sun, aurora, and whether HF is open", "sky"),
    "beacons": ("!beacons", "which continents Kaia can hear right now", "radio"),
    "iss": ("!iss", "the space station, its crew, the next pass", "sky"),
    "nasa": ("!nasa", "today's space picture · who the DSN is talking to", "sky"),
    "earth": ("!earth", "the whole Earth, from a million miles", "sky"),
    "rocks": ("!rocks", "asteroids passing close", "sky"),
    "launch": ("!launch", "the next rockets", "sky"),
    "quake": ("!quake", "the ground moving", "sky"),
    "sky": ("!sky", "tonight overhead", "sky"),
    "overnight": ("!overnight", "what the night shift saw, written up now", "radio"),
    "scanner": ("!scanner [history | off]", "the local scanner · listen live", "radio"),
}

#: Only commands that exist are advertised; each module adds itself on import.
LIVE: set[str] = set()


def register(*keys: str) -> None:
    LIVE.update(keys)


POINTER = "More in !nightshift"


def others(this: str = "", *_ignored: str, **_kw) -> str:
    """The footer line every box in the theme ends with."""
    return POINTER


def index_embed():
    embed = box("🌙  Kaia's night shift",
                "The strange end of the sky and the airwaves: what's transmitting, what's "
                "overhead, and what she heard while you were asleep.", COLOR_NIGHT,
                footer="feeds are volunteer-run and polled gently; some answers are a few hours old")
    for family, title in (("radio", "📻  On the air"), ("sky", "🛰️  Overhead")):
        lines = [f"`{THEME[k][0]}` — {THEME[k][1]}" for k in THEME if k in LIVE and THEME[k][2] == family]
        if lines:
            add_field(embed, title, "\n".join(lines))
    return embed


# ── The control panel ───────────────────────────────────────────────────────
# One box with a button for every feature, so nobody has to remember a
# command: each button runs the same handler the typed command does, with a
# message-shaped stand-in for the click.

#: (key, button label, row, the command text it stands for)
BUTTONS = [
    ("iss", "🛰️ ISS", 0, "!iss"), ("sky", "🌌 Tonight", 0, "!sky"),
    ("spaceweather", "☀️ Space weather", 0, "!spaceweather"), ("launch", "🚀 Launches", 0, "!launch"),
    ("rocks", "☄️ Asteroids", 0, "!rocks"),
    ("quake", "🌍 Quakes", 1, "!quake"), ("nasa", "🖼️ NASA", 1, "!nasa"), ("earth", "🌏 Earth", 1, "!earth"),
    ("skyking", "📻 EAMs", 1, "!skyking"), ("numbers", "🔢 Numbers", 1, "!numbers"),
    ("tacamo", "✈️ TACAMO", 2, "!tacamo"), ("beacons", "🗼 Beacons", 2, "!beacons"),
    ("radio", "📡 What she heard", 2, "!radio"), ("overnight", "🌙 Overnight log", 2, "!overnight"),
    ("scanner", "🎧 Local scanner", 3, "!scanner"), ("buzzer", "🐝 Buzzer live", 3, "!buzzer"),
    ("radio", "🛩️ HFGCS live", 3, "!radio hfgcs"), ("radio", "⏹ Off air", 3, "!radio off"),
]


def _handlers() -> dict:
    from utils.commands import radio_handler as r, scanner_handler as sc, sky_handler as sk
    return {"iss": sk.handle_iss_command, "sky": sk.handle_sky_command,
            "spaceweather": sk.handle_spaceweather_command, "launch": sk.handle_launch_command,
            "rocks": sk.handle_rocks_command, "quake": sk.handle_quake_command,
            "nasa": sk.handle_nasa_command, "earth": sk.handle_earth_command,
            "skyking": r.handle_skyking_command, "numbers": r.handle_numbers_command,
            "tacamo": r.handle_tacamo_command, "beacons": r.handle_beacons_command,
            "radio": r.handle_radio_command, "overnight": r.handle_overnight_command,
            "buzzer": r.handle_buzzer_command, "scanner": sc.handle_scanner_command}


class _Click:
    """A button press, shaped like the message a typed command arrives as."""

    def __init__(self, interaction, content: str):
        self.content = content
        self.author = interaction.user
        self.guild = interaction.guild
        self.channel = interaction.channel
        self.mentions = []


def panel_view(ctx):
    import discord
    from utils.infrastructure.logging.kaia_logger import log_error
    handlers = _handlers()
    view = discord.ui.View(timeout=None)
    for key, label, row, text in BUTTONS:
        if key not in LIVE and key != "scanner":
            continue
        style = (discord.ButtonStyle.danger if "Off" in label else
                 discord.ButtonStyle.success if row == 3 else discord.ButtonStyle.secondary)
        button = discord.ui.Button(label=label, style=style, row=row)

        async def _pressed(interaction, _key=key, _text=text):
            await interaction.response.defer()
            try:
                await handlers[_key](ctx, _Click(interaction, _text))
            except Exception as e:
                log_error(f"[nightshift] {_text} from the panel failed: {e}")
                await interaction.followup.send(f"{_text} didn't work — it's in the log.", ephemeral=True)
        button.callback = _pressed
        view.add_item(button)
    return view


def panel_embed():
    embed = box("🌙  Kaia's night shift",
                "The strange end of the sky and the airwaves. Press a button: the top rows show what's "
                "overhead and what's on the air; the bottom row puts Kaia in your voice channel playing "
                "a live receiver — the Buzzer, the military HFGCS net, or the local scanner.",
                COLOR_NIGHT, footer="join a voice channel before the live buttons · every button is also a "
                                    "!command — !nightshift list shows them")
    return embed


async def handle_nightshift_command(ctx, msg, send_kaia_response=None):
    parts = msg.content.strip().split()
    if len(parts) > 1 and parts[1].lower() in ("list", "commands", "help"):
        return await msg.channel.send(embed=index_embed())
    await msg.channel.send(embed=panel_embed(), view=panel_view(ctx))


register("skyking", "numbers", "radio")
