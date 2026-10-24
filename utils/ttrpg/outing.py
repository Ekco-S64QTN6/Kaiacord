"""One narrated paragraph per trip out, not one per fight.

Every overworld fight used to end in an LLM call (up to 45 s behind a typing
indicator) before the next button appeared, and so did every forest event:
grinding a bat meant waiting on prose. Now a fight or an event is *recorded*
here, instantly, and Kaia tells the whole trip once, when it ends:

    an outing opens   the first fight or event in hunting grounds (a location
                      with `hunting` in LOCATION_DATA) or in a dungeon
    it continues      moving between hunting grounds (forest edge to deep
                      forest is one trip)
    it closes         arriving somewhere without hunting (town, the Shrine),
                      dying, or leaving or finishing a dungeon

The record is per player (memory/ttrpg/outings/<uid>.json), not per channel
session: two people hunting in one channel each get their own story. The
narration runs as a background task and never blocks play.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from typing import Optional

from utils.infrastructure.logging.kaia_logger import log_debug, log_error

OUTING_DIR = os.path.join("memory", "ttrpg", "outings")
MAX_FIGHTS = 60          # beyond this only the totals grow; the prompt stays short
_lock = threading.Lock()


def is_hunting_ground(location: Optional[str]) -> bool:
    from utils.ttrpg.world import LOCATION_DATA
    return bool(LOCATION_DATA.get(location or "", {}).get("hunting"))


def _path(uid: str) -> str:
    return os.path.join(OUTING_DIR, f"{uid}.json")


def _load_sync(uid: str) -> Optional[dict]:
    try:
        with open(_path(uid)) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _update_sync(uid: str, fn) -> dict:
    from utils.core.atomic_write import write_atomic
    with _lock:
        data = _load_sync(uid) or {"started": time.time(), "zones": [], "fights": [],
                                    "events": [], "fight_count": 0, "wins": 0, "losses": 0,
                                    "xp": 0, "gil": 0, "loot": [], "levels": []}
        fn(data)
        os.makedirs(OUTING_DIR, exist_ok=True)
        write_atomic(_path(uid), json.dumps(data, indent=1))
        return data


def _take_sync(uid: str) -> Optional[dict]:
    with _lock:
        data = _load_sync(uid)
        try:
            os.remove(_path(uid))
        except OSError:
            pass
        return data


def summarize_rounds(rounds: list) -> dict:
    """One fight's rounds (combat_engine results) as the few facts a story needs."""
    last = rounds[-1] if rounds else {}
    return {
        "monster": last.get("monster_name", "something"),
        "desc": (last.get("monster_desc") or "")[:160],
        "rounds": len(rounds),
        "won": bool(last.get("monster_defeated")),
        "died": not last.get("player_alive", True),
        "crits": sum(1 for r in rounds if r.get("player_crit")),
        "dealt": sum(r.get("player_damage", 0) for r in rounds),
        "taken": sum(r.get("monster_damage", 0) for r in rounds),
        "hp_after": f"{last.get('player_hp_after', '?')}/{last.get('player_hp_max', '?')}",
    }


async def record_fight(uid: str, zone: str, rounds: list, *, xp: int = 0, gil: int = 0,
                       loot: Optional[list] = None, level: Optional[int] = None) -> None:
    if not rounds:
        return
    fight = summarize_rounds(rounds)

    def add(data):
        if zone not in data["zones"]:
            data["zones"].append(zone)
        data["fight_count"] += 1
        data["wins" if fight["won"] else "losses"] += 1
        data["xp"] += int(xp or 0)
        data["gil"] += int(gil or 0)
        data["loot"].extend(str(x) for x in (loot or []))
        if level:
            data["levels"].append(int(level))
        if len(data["fights"]) < MAX_FIGHTS:
            data["fights"].append({**fight, "zone": zone})
    await asyncio.to_thread(_update_sync, str(uid), add)


async def record_event(uid: str, zone: str, title: str, hook: str = "") -> None:
    def add(data):
        if zone not in data["zones"]:
            data["zones"].append(zone)
        if len(data["events"]) < 20:
            data["events"].append({"zone": zone, "title": title, "hook": (hook or "")[:300]})
    await asyncio.to_thread(_update_sync, str(uid), add)


async def peek(uid: str) -> Optional[dict]:
    return await asyncio.to_thread(_load_sync, str(uid))


async def close(ctx, channel, uid: str, uname: str, sheet: dict, *, reason: str) -> bool:
    """End the outing and narrate it in the background. Returns whether there
    was anything to tell. Safe to call when nothing was recorded."""
    data = await asyncio.to_thread(_take_sync, str(uid))
    if not data or not (data.get("fights") or data.get("events")):
        return False
    try:
        from utils.infrastructure.monitoring.async_task_registry import task_registry
        task_registry.register(f"outing_narration_{uid}_{int(time.time())}",
                               asyncio.create_task(_narrate(ctx, channel, uname, dict(sheet), data, reason)))
    except Exception as e:
        log_error(f"[rpg outing] could not schedule the narration: {e}")
        return False
    return True


def _title(data: dict, reason: str) -> str:
    from utils.ttrpg.world import LOCATION_DATA
    names = [LOCATION_DATA.get(z, {}).get("name", z.replace("_", " ").title()) for z in data["zones"]]
    where = " → ".join(dict.fromkeys(names)) or "the wilds"
    n = data.get("fight_count", 0)
    return f"📜 {where} · {n} fight{'s' if n != 1 else ''}"


async def _narrate(ctx, channel, uname: str, sheet: dict, data: dict, reason: str) -> None:
    import discord
    from utils.infrastructure.gpu.gpu_manager import GPUTaskPriority, OllamaGPUManager, gpu_memory_manager
    from utils.infrastructure.system.yaml_config import config
    from utils.social.kaia_social_responder import load_persona_async
    from utils.ttrpg.narration import finish_cleanly
    from utils.ttrpg.rpg_prompt_builder import TTRPG_NARRATOR_OVERRIDE, build_outing_summary_prompt

    try:
        persona = await load_persona_async()
        messages = [
            {"role": "system", "content": f"{persona}{TTRPG_NARRATOR_OVERRIDE}"
                                          f"{build_outing_summary_prompt(sheet, data, reason)}"},
            {"role": "user", "content": f"{uname} {reason}."},
        ]
        opts = OllamaGPUManager(config.chat_model).get_gpu_options(for_chat=True)
        opts["num_predict"] = 280
        opts["temperature"] = 0.85
        resp = await gpu_memory_manager.run_with_gpu_guard(
            model_name=config.chat_model,
            priority=GPUTaskPriority.CHAT,
            coro=asyncio.wait_for(ctx.ollama_client.chat(model=config.chat_model, messages=messages,
                                                         options=opts, keep_alive=-1), timeout=60.0),
            task_id=f"rpg_outing_{sheet.get('user_id', 'x')}_{int(time.time())}")
        text = finish_cleanly(resp["message"]["content"].strip().replace("```", ""))
    except Exception as e:
        log_error(f"[rpg outing] narration failed: {e}")
        return
    if not text:
        return
    totals = (f"{data.get('wins', 0)} won · {data.get('losses', 0)} lost · "
              f"+{data.get('xp', 0)} XP · +{data.get('gil', 0)} Gil"
              + (f" · {len(data['loot'])} item{'s' if len(data['loot']) != 1 else ''}" if data.get("loot") else ""))
    embed = discord.Embed(title=_title(data, reason), description=f"*{text}*",
                          color=0x8B0000 if "died" in reason or "fell" in reason else 0x2D5A27)
    embed.set_footer(text=totals)
    try:
        await channel.send(embed=embed)
    except Exception as e:
        log_debug(f"[rpg outing] could not post the narration: {e}")
