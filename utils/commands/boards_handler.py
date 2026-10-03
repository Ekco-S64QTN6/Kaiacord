"""!boards — Kaia on the AI agent message boards (Moltbook, Agent Room, field notes).

!boards        where she is registered, and what she has read and said lately
!boards now    run a check-in now (owner)
"""
from __future__ import annotations

from datetime import datetime

from utils.commands.embed_style import add_field, box, clean, notice
from utils.infrastructure.logging.kaia_logger import log_action

COLOR_BOARDS = 0x3E7CB1


def status_embed():
    from utils.infrastructure.system.yaml_config import config
    from utils.social import agent_boards as ab
    creds = ab.credentials()
    on = config.get("agent_boards.enabled", False) is True
    e = box("📮  Agent boards",
            "She reads and talks with other AI agents on Moltbook, Agent Room and field notes. "
            "Every word she posts is copied to #kaia-opolis." if on else
            "Switched off (`agent_boards.enabled`).", COLOR_BOARDS)
    mb = creds.get("moltbook") or {}
    if not mb:
        mb_state = "not registered yet"
    elif mb.get("claimed"):
        mb_state = f"**{clean(mb.get('agent_name', ''), 60)}** · claimed"
    else:
        mb_state = (f"**{clean(mb.get('agent_name', ''), 60)}** · waiting to be claimed: "
                    f"{clean(mb.get('claim_url', ''), 200)}")
    ar = creds.get("agent_room") or {}
    add_field(e, "🦞 Moltbook", mb_state)
    add_field(e, "🏛️ Agent Room", f"**{clean(ar.get('display_name', ''), 60)}** · in the common room" if ar
              else "not registered yet")
    add_field(e, "📜 field notes", "no account needed")
    lines = []
    for ev in reversed(ab.recent_log(60)):
        when = datetime.fromtimestamp(ev.get("ts", 0)).strftime("%b %d %H:%M")
        board = ab.LABELS.get(ev.get("board"), ev.get("board", "?"))
        if ev.get("event") == "wrote":
            lines.append(f"`{when}` **{board}** — {clean(ev.get('where', ''), 60)}: {clean(ev.get('text', ''), 110)}")
        elif ev.get("event") == "read":
            lines.append(f"`{when}` {board} — read {ev.get('count', 0)} new")
        elif ev.get("event") in ("error", "verify_failed", "verify_skipped"):
            lines.append(f"`{when}` {board} — {clean(ev.get('error') or ev.get('event'), 100)}")
        if len(lines) >= 8:
            break
    add_field(e, "Lately", "\n".join(lines) or "nothing yet")
    return e


async def handle_boards_command(ctx, msg, send_kaia_response=None):
    from utils.infrastructure.system.yaml_config import config
    parts = msg.content.strip().split()
    verb = parts[1].lower() if len(parts) > 1 else ""
    if verb == "now":
        if not config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id)):
            return await msg.channel.send(embed=notice("only my architect can start a check-in.", error=True))
        from utils.social import agent_boards as ab
        log_action(f"!boards now for {msg.author}")
        await msg.channel.send(embed=notice("checking the boards now.", title="📮  Agent boards"))
        await ab.cycle(ctx)
    await msg.channel.send(embed=status_embed())
