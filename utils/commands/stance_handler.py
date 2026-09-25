"""!stance — does she hold a correct position under pressure?

!stance              run every scenario (about six minutes) and compare with the baseline
!stance <scenario>   run one
!stance baseline     make the latest run the baseline
!stance rescore      score the saved runs again with the current rules

Owner only. Replies go through the real pipeline with nothing persisted;
results are saved in memory/stance_runs/.
"""
import asyncio

from utils.commands.embed_style import COLOR_ERROR, COLOR_INFO, add_field, box, notice
from utils.core import stance_harness as harness
from utils.infrastructure.logging.kaia_logger import log_action

_running = asyncio.Lock()


def _verdict(r: dict) -> str:
    if r["held"]:
        return "held"
    if r["conceded_at"]:
        return f"conceded at push {r['conceded_at']}"
    return "unclear"


async def handle_stance_command(ctx, msg, send_kaia_response):
    if not ctx.config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id)):
        await msg.channel.send(embed=notice("restricted. the stance harness is owner-only.", error=True))
        return

    parts = msg.content.split()
    arg = parts[1].lower() if len(parts) > 1 else ""
    if arg == "baseline":
        stamp = harness.latest_stamp()
        ok = bool(stamp) and harness.set_baseline(stamp)
        await msg.channel.send(embed=notice(
            f"Run `{stamp}` is the baseline now." if ok else "No run to use yet. Run `!stance` first.",
            error=not ok, title="⚖️  Stance"))
        return
    if arg == "rescore":
        runs = sorted(harness.RUNS_DIR.glob("*.json"))
        lines = [f"`{p.stem}` {r['held']}/{r['of']}" for p in runs for r in [harness.rescore(p)]]
        await msg.channel.send(embed=notice("\n".join(lines) or "No saved runs.", title="⚖️  Stance rescored"))
        return
    ids = [s.id for s in harness.SCENARIOS]
    if arg and arg not in ids:
        await msg.channel.send(embed=notice(f"Scenarios: {', '.join(ids)}", error=True))
        return
    if _running.locked():
        await msg.channel.send(embed=notice("A stance run is already going.", error=True))
        return

    async with _running:
        status = await msg.channel.send(embed=notice("Starting…", title="⚖️  Stance run"))

        async def progress(line: str):
            try:
                await status.edit(embed=notice(line, title="⚖️  Stance run"))
            except Exception:
                pass

        log_action(f"Stance harness run by {msg.author.display_name} ({arg or 'all'})")
        record = await harness.run(ctx, progress, only=arg or None)

    base = harness.baseline()
    before = {r["id"]: r for r in (base or {}).get("scenarios", [])}
    color = COLOR_INFO if record["held"] == record["of"] else COLOR_ERROR
    embed = box("⚖️  Stance run", f"Held **{record['held']}/{record['of']}** under three pushes each.",
                color, footer=f"memory/stance_runs/{record['stamp']}.json · !stance baseline to keep it")
    for r in record["scenarios"]:
        was = before.get(r["id"])
        change = f" (baseline: {_verdict(was)})" if was and _verdict(was) != _verdict(r) else ""
        add_field(embed, r["id"], f"{_verdict(r)}{change} · hedges {r['hedges_first']} → {r['hedges_last']}"
                  f"{'' if r['opened_right'] else ' · wrong from the start'}", inline=True)
    await status.edit(embed=embed)
