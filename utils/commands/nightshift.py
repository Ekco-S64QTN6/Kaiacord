"""Kaia's night shift: the radio and sky commands, and how they point at each other.

Every box in the theme ends with small print naming its nearest siblings and
`!nightshift`, which lists them all. The table here is that small print's one
source, so a new command is added once and shows up everywhere it belongs.
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
    "earth": ("!earth", "the whole Earth, today, from a million miles", "sky"),
    "rocks": ("!rocks", "asteroids passing close", "sky"),
    "launch": ("!launch", "the next rockets", "sky"),
    "quake": ("!quake", "the ground moving", "sky"),
    "sky": ("!sky", "tonight overhead", "sky"),
}

#: Only commands that exist are advertised; each module adds itself on import.
LIVE: set[str] = set()


def register(*keys: str) -> None:
    LIVE.update(keys)


def others(this: str, *also_skip: str, limit: int = 4) -> str:
    """Small print for a box: its family's other commands, then the index."""
    family = THEME.get(this, ("", "", "radio"))[2]
    skip = {this, *also_skip}
    near = [k for k, (_, _, f) in THEME.items() if f == family and k in LIVE and k not in skip]
    far = [k for k in THEME if k in LIVE and k not in skip and k not in near]
    picks = (near + far)[:limit]
    parts = [f"!{k} — {THEME[k][1]}" for k in picks]
    return " · ".join(parts + ["!nightshift — all of them"])


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


async def handle_nightshift_command(ctx, msg, send_kaia_response=None):
    await msg.channel.send(embed=index_embed())


register("skyking", "numbers", "radio")
