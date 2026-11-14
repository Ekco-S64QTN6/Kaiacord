"""World-information commands for Aethelgard.

The command/view interfaces stay stable in rpg_core_handler.py; this module
owns the seasonal calendar, deterministic weather, and tavern-rumor responses.
"""
import asyncio
import uuid as _uuid

import discord

from utils.infrastructure.logging.kaia_logger import log_error
from utils.infrastructure.system.yaml_config import config
from utils.social.kaia_social_responder import load_persona_async
from utils.ttrpg.character_manager import load
from utils.ttrpg.narration import finish_cleanly
from utils.ttrpg.rpg_views import _make_status_view


async def _handle_rumor(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.rpg_prompt_builder import build_rumor_prompt
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    
    sheet = await load(uid)
    if sheet and sheet.get("location") != "stone_hearth":
        return await msg.channel.send(embed=discord.Embed(description="You must be at the Stone Hearth to hear rumors. (`!rpg go stone_hearth`)", color=0xcc4444))
        
    prompt = build_rumor_prompt()
    persona = await load_persona_async()
    messages = [
        {"role": "system", "content": f"{persona}\n\n{prompt}"},
        {"role": "user", "content": "I sit at the bar. What are people talking about?"}
    ]
    
    gpu_manager = OllamaGPUManager(config.chat_model)
    opts = gpu_manager.get_gpu_options(for_chat=True)
    opts["num_predict"] = 100
    opts["temperature"] = 0.95
    
    async with msg.channel.typing():
        try:
            resp = await gpu_memory_manager.run_with_gpu_guard(
                model_name=config.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(
                    ctx.ollama_client.chat(model=config.chat_model, messages=messages, options=opts, keep_alive=-1),
                    timeout=30.0
                ),
                task_id=f"rpg_rumor_{_uuid.uuid4().hex[:8]}"
            )
            rumor = finish_cleanly(resp["message"]["content"].strip().replace("```", ""))
            if not rumor:
                rumor = "The tavern is quiet tonight. Nobody has anything to say."
            embed = discord.Embed(
                title="🗣️ Rumor Heard",
                description=f"*{rumor}*",
                color=0x888888
            )
            view = _make_status_view(ctx, msg, uid, uname, is_owner)
            await msg.channel.send(embed=embed, view=view)
        except Exception as e:
            # The typing indicator ran for up to 30 s; say something instead of nothing.
            log_error(f"[rpg rumor] {e}")
            await msg.channel.send(embed=discord.Embed(
                description="*The tavern is too loud to hear anything. Try again in a moment.*", color=0x888888))


async def _handle_calendar(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.calendar import get_today_summary, SPECIAL_DAYS
    from datetime import date

    summary = get_today_summary()
    season = summary["season"]
    special = summary["special_day"]

    # Build upcoming events (next 14 days)
    today = date.today()
    upcoming = []
    for i in range(1, 15):
        from datetime import timedelta
        check = today + timedelta(days=i)
        day_data = SPECIAL_DAYS.get((check.month, check.day))
        if day_data:
            upcoming.append(f"**{check.strftime('%b %d')}** — {day_data['name']}")

    color_map = {
        "spring": 0x88cc88,
        "summer": 0xf5c842,
        "autumn": 0xd4703c,
        "winter": 0x88aacc,
    }

    embed = discord.Embed(
        title=f"{summary['season_emoji']} {summary['season_name']} — {summary['date']}",
        description=f"*{summary['season_flavor']}*",
        color=color_map[season]
    )

    if special:
        embed.add_field(
            name=f"✨ {special['name']}",
            value=f"{special['desc']}\n\n**Today's effect:** {special.get('buff_desc', 'None')}",
            inline=False
        )
    else:
        embed.add_field(
            name="Today",
            value="An ordinary day. The Whisperwood does not care about ordinary days.",
            inline=False
        )

    if upcoming:
        embed.add_field(
            name="Upcoming",
            value="\n".join(upcoming[:5]),
            inline=False
        )

    embed.set_footer(text="!rpg calendar — updated daily at dawn")
    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=embed, view=view)


async def _handle_weather(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg weather — check today's deterministic weather conditions."""
    from utils.ttrpg.calendar import get_weather, get_today_summary

    weather = get_weather()
    summary = get_today_summary()

    color_map = {
        "clear":        0xf5c842,
        "overcast":     0x9aabb5,
        "rain":         0x5b8fa8,
        "storm":        0x4a4a7a,
        "fog":          0xb0b8bb,
        "hot":          0xe8742a,
        "drought_wind": 0xd4a030,
        "snow":         0xc8ddf0,
        "blizzard":     0x8aaac8,
        "frost":        0x88ccee,
        "wind":         0xa0b8c0,
    }

    desc_lines = [f"*{weather['desc']}*"]

    effect = weather.get("effect")
    if effect:
        desc_lines.append(f"\n⚠️ **Today:** {effect['desc']}")

    embed = discord.Embed(
        title=f"{weather['emoji']} {weather['name']} — {summary['date']}",
        description="\n".join(desc_lines),
        color=color_map.get(weather["key"], 0x888888)
    )
    embed.set_footer(text=f"{summary['season_name']} · Weather changes at dawn")
    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=embed, view=view)
