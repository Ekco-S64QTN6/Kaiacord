"""!dream [list|generate|stats] — owner only.

list      the most recent dream reflections
generate  run a dream cycle now, in the background, and say when it's done
stats     how many reflections, by kind
"""
import asyncio

from utils.commands.embed_style import add_field, box, clean, notice
from utils.infrastructure.logging.kaia_logger import log_error

COLOR_DREAM = 0x4F46E5
_generating = asyncio.Lock()


async def handle_dreams_command(ctx, msg, load_persona_async):
    """Handle !dream (owner only)."""
    if not ctx.config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id)):
        await msg.channel.send(embed=notice("you aren't my architect. restricted.", error=True))
        return
    engine = getattr(ctx, "dream_engine", None)
    if engine is None:
        await msg.channel.send(embed=notice("The dream engine isn't running yet.", error=True))
        return

    parts = msg.content.strip().split()
    sub = parts[1].lower() if len(parts) > 1 else "list"

    if sub in ("list", "stats"):
        stats = await asyncio.to_thread(engine.get_dreams_from_files)
        if not stats["total"]:
            await msg.channel.send(embed=notice("No dreams yet. `!dream generate` runs a cycle.", title="💤  Dreams"))
            return
        if sub == "list":
            embed = box("💤  Recent dreams", "Reflections from her offline dream cycles.", COLOR_DREAM,
                        footer=f"{stats['total']} dream records")
            for i, d in enumerate(stats["recent"], 1):
                source = " ".join(d.get("source", "unknown").replace(".md", "").replace("_", " ")
                                  .replace("-", " ").split())
                add_field(embed, f"{i}. {clean(source, 80)} ({d.get('category', 'unknown')})",
                          clean(d.get("reflection", ""), 180))
        else:
            embed = box("📊  Dream stats", f"**{stats['total']}** reflections.", COLOR_DREAM)
            add_field(embed, "By kind", "\n".join(
                f"• **{name.title()}**: {count}" for name, count in stats.get("categories", {}).items()) or "None")
        await msg.channel.send(embed=embed)
        return

    if sub == "generate":
        if _generating.locked():
            await msg.channel.send(embed=notice("A dream cycle is already running.", error=True))
            return
        await msg.channel.send(embed=notice(
            "Human brains must dream to reorganize, to get rid, periodically, of knots and snarls. "
            "Perhaps so must this robot, and for the same reason.\n\n"
            "Starting a dream cycle. I'll say here when it's done.", title="💤  Dreaming"))

        async def _run():
            async with _generating:
                try:
                    before = (await asyncio.to_thread(engine.get_dreams_from_files))["total"]
                    await engine.nightly_dream_processing(await load_persona_async())
                    after = (await asyncio.to_thread(engine.get_dreams_from_files))["total"]
                    await msg.channel.send(embed=notice(
                        f"Dream cycle finished: {max(0, after - before)} new reflection(s).", title="💤  Awake"))
                except Exception as e:
                    log_error(f"!dream generate failed: {e}")
                    await msg.channel.send(embed=notice("The dream cycle failed; the log has the reason.", error=True))

        from utils.infrastructure.monitoring.async_task_registry import task_registry
        task_registry.register("dream_generate", asyncio.create_task(_run()))
        return

    await msg.channel.send(embed=notice("Usage: `!dream [list|generate|stats]`", error=True))
