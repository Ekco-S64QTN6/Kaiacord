"""!scanner — the local RTL-SDR: what it has found, and live listening.

!scanner            the panel: what the scanner is, its status, a dropdown of
                    presets from the ledger, Listen / Off / History / Refresh
!scanner history    the latest catches
!scanner off        stop listening
"""
from __future__ import annotations

import time
from datetime import datetime

import discord

from utils.commands import nightshift
from utils.commands.embed_style import COLOR_ERROR, add_field, box, clean
from utils.infrastructure.logging.kaia_logger import log_action, log_error

COLOR_SCANNER = 0x2F7D6D
MHZ = 1_000_000
ABOUT = ("An RTL-SDR attached to the bot listens to the local airwaves — ham repeaters, "
         "walkie-talkies on FRS/GMRS/MURS, NOAA weather, business and marine radio. Every night from "
         "midnight to 6 it sweeps the bands, listens wherever something is transmitting, and writes "
         "down what it heard and when. Pick a frequency and I'll play it in your voice channel, or "
         "listen along and hear me scan.")


def _label(ch: dict) -> str:
    return ch.get("label") or f"{ch.get('service') or 'unknown'} · found {ch['freq_hz'] / MHZ:.4f}"


def panel_embed() -> discord.Embed:
    from utils.radio import ledger, rtl, scanner, live
    chans = ledger.channels()
    heard = [c for c in chans if c["hits"]]
    voice = [c for c in chans if c["voice"]]
    tonight = [e for e in ledger.recent(200) if time.time() - e["ts"] < 12 * 3600]
    status = ("scanning now, with listeners" if scanner.listening_along() else
              "scanning now" if scanner.running() else
              "listening live" if any(s.local for s in live.active()) else
              "scans nightly 00:00–06:00" if rtl.available() else "RTL-SDR not found")
    embed = box("📻  Local scanner", ABOUT, COLOR_SCANNER,
                footer="!scanner history · !scanner off · pick a preset, then ▶ Listen")
    add_field(embed, "Status", status, inline=True)
    add_field(embed, "Ledger", f"{len(chans)} channels · {len(heard)} heard · {len(voice)} with voice", inline=True)
    add_field(embed, "Last 12 hours", f"{len(tonight)} catches · "
              f"{sum(1 for e in tonight if e['kind'] == 'voice')} voice", inline=True)
    if voice:
        add_field(embed, "Voices heard on", "\n".join(
            f"`{c['freq_hz'] / MHZ:.4f}` {clean(_label(c), 60)} · {c['voice']}× · {ledger.active_hours(c)}"
            for c in sorted(voice, key=lambda c: -c["voice"])[:6]))
    return embed


def history_embed(limit: int = 12) -> discord.Embed:
    from utils.radio import ledger
    rows = ledger.recent(limit)
    lines = []
    for e in rows:
        when = datetime.fromtimestamp(e["ts"]).strftime("%a %H:%M")
        what = f" — \"{clean(e['transcript'], 110)}\"" if e.get("transcript") else ""
        lines.append(f"`{when}` **{e['kind']}** `{e['freq_hz'] / MHZ:.4f}` {clean(e.get('label') or e.get('service') or '', 40)}{what}")
    return box("📜  What the scanner caught", "\n".join(lines) or "Nothing yet — the first night's scan will fill this.",
               COLOR_SCANNER, footer="!scanner — the panel")


class HistoryView(discord.ui.View):
    """Recent catches that were recorded, and a button to play one in voice."""

    def __init__(self, catches: list[dict]):
        super().__init__(timeout=600)
        self.catches = {str(c["id"]): c for c in catches}
        self.choice = str(catches[0]["id"]) if catches else None
        if catches:
            options = [discord.SelectOption(
                label=(f"{datetime.fromtimestamp(c['ts']).strftime('%a %H:%M')} · {c['freq_hz'] / MHZ:.4f} · "
                       f"{c['kind']}")[:100],
                description=clean(c.get("transcript") or c.get("label") or c.get("service") or "", 95) or None,
                value=str(c["id"]), default=(i == 0)) for i, c in enumerate(catches[:25])]
            select = discord.ui.Select(placeholder="Pick a recording", options=options, row=0)

            async def _picked(interaction: discord.Interaction):
                self.choice = select.values[0]
                await interaction.response.defer()
            select.callback = _picked
            self.add_item(select)

    @discord.ui.button(label="▶ Play in voice", style=discord.ButtonStyle.success, row=1)
    async def play(self, interaction: discord.Interaction, _button):
        from utils.radio import live, scanner
        c = self.catches.get(self.choice or "")
        member = interaction.user
        if not c:
            return await interaction.response.send_message("Pick a recording first.", ephemeral=True)
        if not getattr(member, "voice", None) or not member.voice.channel:
            return await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
        await interaction.response.defer()
        label = f"{c['freq_hz'] / MHZ:.4f} MHz {c['kind']}"
        try:
            await live.play_clip(member.voice.channel, scanner._clips_dir() / c["clip"], label, member.display_name)
        except Exception as e:
            return await interaction.followup.send(embed=box("📼  Scanner", clean(str(e), 200), COLOR_ERROR))
        await interaction.followup.send(embed=box(
            "📼  Playing", f"{label}, {datetime.fromtimestamp(c['ts']).strftime('%a %H:%M')}, "
            f"in **{member.voice.channel.name}**." + (f"\n\n\"{clean(c['transcript'], 300)}\"" if c.get("transcript") else ""),
            COLOR_SCANNER))


def _recorded(limit: int = 25) -> list[dict]:
    from utils.radio import ledger, scanner
    folder = scanner._clips_dir()                  # the clip folder keeps the newest 300
    return [e for e in ledger.recent(200, kinds=("voice", "data"))
            if e.get("clip") and (folder / e["clip"]).is_file()][:limit]


class ScannerView(discord.ui.View):
    def __init__(self, presets: list[dict]):
        super().__init__(timeout=600)
        self.choice = presets[0]["freq_hz"] if presets else None
        self.labels = {c["freq_hz"]: _label(c) for c in presets}
        if presets:
            options = [discord.SelectOption(
                label=f"{c['freq_hz'] / MHZ:.4f} MHz · {_label(c)}"[:100],
                description=(f"{c.get('service') or ''} · heard {c['hits']}× · voice {c['voice']}×")[:100],
                value=str(c["freq_hz"]), default=(i == 0)) for i, c in enumerate(presets[:25])]
            select = discord.ui.Select(placeholder="Pick a frequency", options=options, row=0)

            async def _picked(interaction: discord.Interaction):
                self.choice = int(select.values[0])
                await interaction.response.defer()
            select.callback = _picked
            self.add_item(select)

    @discord.ui.button(label="▶ Listen", style=discord.ButtonStyle.success, row=1)
    async def listen(self, interaction: discord.Interaction, _button):
        from utils.radio import live
        member = interaction.user
        if not self.choice:
            return await interaction.response.send_message("Pick a frequency first.", ephemeral=True)
        if not getattr(member, "voice", None) or not member.voice.channel:
            return await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
        from utils.audio.strudel_session import get_session as music_session
        if music_session(interaction.guild.id):
            return await interaction.response.send_message("The music's playing — `!music off` first.", ephemeral=True)
        await interaction.response.defer()
        label = self.labels.get(self.choice, f"{self.choice / MHZ:.4f} MHz")
        try:
            await live.start_local(member.voice.channel, self.choice, label, member.display_name)
        except Exception as e:
            log_error(f"[scanner] listen failed: {e}")
            return await interaction.followup.send(embed=box("📻  Scanner", clean(str(e), 200), COLOR_ERROR))
        await interaction.followup.send(embed=box(
            f"📻  Live · {self.choice / MHZ:.4f} MHz", f"{clean(label, 80)} in **{member.voice.channel.name}**. "
            "The nightly scan pauses while you listen. ⏹ Off, or `!scanner off`.", COLOR_SCANNER))

    @discord.ui.button(label="🎧 Listen along", style=discord.ButtonStyle.primary, row=1)
    async def along(self, interaction: discord.Interaction, _button):
        """Hear the scan as it happens: a tick per hop, the channel when it holds,
        each catch posted here."""
        from utils.radio import rtl, scanner
        member = interaction.user
        if not getattr(member, "voice", None) or not member.voice.channel:
            return await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
        if not rtl.available():
            return await interaction.response.send_message("The RTL-SDR isn't connected.", ephemeral=True)
        await interaction.response.defer()
        try:
            await scanner.start_listen_along(member.voice.channel, interaction.channel, member.display_name)
        except Exception as e:
            log_error(f"[scanner] listen along failed: {e}")
            return await interaction.followup.send(embed=box("📻  Scanner", clean(str(e), 200), COLOR_ERROR))
        await interaction.followup.send(embed=box(
            "🎧  Listening along", f"I'm in **{member.voice.channel.name}** scanning the bands. You'll hear a "
            "soft tick each time I step, and the channel itself whenever something keys up — I'll post each "
            "catch here as I log it. ⏹ Off to stop.", COLOR_SCANNER))

    @discord.ui.button(label="⏹ Off", style=discord.ButtonStyle.danger, row=1)
    async def off(self, interaction: discord.Interaction, _button):
        from utils.radio import live, scanner
        stopped = await live.stop(interaction.guild.id)
        stopped = await scanner.stop_listen_along(interaction.guild.id) or stopped
        await interaction.response.send_message("off the air." if stopped else "nothing was playing.")

    @discord.ui.button(label="📜 History", style=discord.ButtonStyle.secondary, row=2)
    async def history(self, interaction: discord.Interaction, _button):
        catches = _recorded()
        await interaction.response.send_message(embed=history_embed(),
                                                **({"view": HistoryView(catches)} if catches else {}))

    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.secondary, row=2)
    async def refresh(self, interaction: discord.Interaction, _button):
        from utils.radio import ledger
        await interaction.response.edit_message(embed=panel_embed(), view=ScannerView(ledger.presets()))


async def handle_scanner_command(ctx, msg, send_kaia_response=None):
    from utils.radio import ledger, live, scanner
    parts = msg.content.strip().split()
    verb = parts[1].lower() if len(parts) > 1 else ""
    log_action(f"!scanner {verb} for {msg.author}")
    try:
        ledger.seed(scanner.seed_channels())
        if verb == "history":
            catches = _recorded()
            return await msg.channel.send(embed=history_embed(20),
                                          **({"view": HistoryView(catches)} if catches else {}))
        if verb == "off":
            stopped = msg.guild and (await live.stop(msg.guild.id) | await scanner.stop_listen_along(msg.guild.id))
            return await msg.channel.send(embed=box("📻  Scanner", "off the air." if stopped else "nothing was playing.",
                                                    COLOR_SCANNER))
        await msg.channel.send(embed=panel_embed(), view=ScannerView(ledger.presets()))
    except Exception as e:
        log_error(f"[scanner] !scanner failed: {e}")
        await msg.channel.send(embed=box("📻  Scanner", "Something went wrong with the scanner. It's in the log.",
                                         COLOR_ERROR))


nightshift.register("scanner")
