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

A closed trip is moved to `untold/` and stays there, with its paragraph once
written, until the post to #aethelgard (`discord.rpg_channel`) succeeds: a
failed generation or post is retried at the next boot (`tell_untold`), never
dropped. #aethelgard so every player can follow what the others did that day;
the channel the trip was played in is the fallback.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from typing import Optional

from utils.infrastructure.logging.kaia_logger import log_debug, log_error, log_info, log_warning
from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

OUTING_DIR = telemetry_path(os.path.join("memory", "ttrpg", "outings"))
UNTOLD_DIR = os.path.join(OUTING_DIR, "untold")
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


def _take_sync(uid: str, tale: dict) -> Optional[str]:
    """Close the open record into `untold/` with what telling it needs; the
    path of the untold trip, or None when there was nothing to tell."""
    from utils.core.atomic_write import write_atomic
    with _lock:
        data = _load_sync(uid)
        try:
            os.remove(_path(uid))
        except OSError:
            pass
        if not data or not (data.get("fights") or data.get("events") or data.get("notes")):
            return None
        data.update(tale)
        os.makedirs(UNTOLD_DIR, exist_ok=True)
        path = os.path.join(UNTOLD_DIR, f"{uid}_{int(tale['ended'] * 1000)}.json")
        write_atomic(path, json.dumps(data, indent=1))
        return path


def _untold_sync() -> list:
    try:
        names = sorted(n for n in os.listdir(UNTOLD_DIR) if n.endswith(".json"))
    except OSError:
        return []
    return [os.path.join(UNTOLD_DIR, n) for n in names]


def _write_sync(path: str, data: dict) -> None:
    from utils.core.atomic_write import write_atomic
    write_atomic(path, json.dumps(data, indent=1))


def _remove_sync(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def summarize_rounds(rounds: list) -> dict:
    """One fight's rounds (combat_engine results) as the few facts a story needs."""
    last = rounds[-1] if rounds else {}
    return {
        "monster": last.get("monster_name", "something"),
        "tier": last.get("monster_tier"),
        "desc": (last.get("monster_desc") or "")[:400],
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


#: What else a trip can hold, besides fights and events.
NOTE_KINDS = ("quest", "quest_done", "fled", "used")


def _note_sync(uid: str, kind: str, text: str, start: bool) -> None:
    def add(data):
        notes = data.setdefault("notes", {}).setdefault(kind, [])
        if len(notes) < 20:
            notes.append(str(text))
    if start:
        _update_sync(uid, add)
        return
    from utils.core.atomic_write import write_atomic
    with _lock:
        data = _load_sync(uid)
        if data is None:
            return
        add(data)
        write_atomic(_path(uid), json.dumps(data, indent=1))


async def note(uid: str, kind: str, text: str, *, start: bool = False) -> None:
    """Something else that happened on the trip: a quest moved on or finished,
    a fight fled, a potion drunk. `start` lets it open a trip (a fight's quest
    progress is noted before the fight is recorded); otherwise it only joins
    one under way, so a potion drunk in town is not a trip."""
    if kind in NOTE_KINDS:
        await asyncio.to_thread(_note_sync, str(uid), kind, text, start)


async def peek(uid: str) -> Optional[dict]:
    return await asyncio.to_thread(_load_sync, str(uid))


# The sheet fields the paragraph is written from, kept with the untold trip.
_SHEET_KEYS = ("user_id", "character_name", "class", "advanced_class", "level", "hp")

_telling: set = set()      # untold trips being told now, so a boot replay never doubles one


async def close(ctx, channel, uid: str, uname: str, sheet: dict, *, reason: str) -> bool:
    """End the outing and narrate it in the background. Returns whether there
    was anything to tell. Safe to call when nothing was recorded."""
    hunts = None
    try:
        from utils.ttrpg.progression import get_max_hunts
        hunts = [int(sheet.get("hunts_today", 0)), int(get_max_hunts(sheet))]
    except Exception:
        pass
    tale = {"uid": str(uid), "uname": uname, "reason": reason, "ended": time.time(), "hunts": hunts,
            "channel_id": getattr(channel, "id", None),
            "sheet": {k: sheet.get(k) for k in _SHEET_KEYS if k in (sheet or {})}}
    path = await asyncio.to_thread(_take_sync, str(uid), tale)
    if not path:
        return False
    try:
        from utils.infrastructure.monitoring.async_task_registry import task_registry
        task_registry.register(f"outing_narration_{uid}_{int(time.time())}",
                               asyncio.create_task(tell(ctx, path, channel=channel)))
    except Exception as e:
        log_error(f"[rpg outing] could not schedule the narration (kept for the next boot): {e}")
        return False
    return True


async def tell_untold(ctx) -> int:
    """Tell every trip still waiting, oldest first, one at a time: what a crash,
    a failed generation or a failed post left behind. Returns how many posted."""
    told = 0
    for path in await asyncio.to_thread(_untold_sync):
        told += await tell(ctx, path)
    if told:
        log_info(f"[rpg outing] told {told} trip(s) left untold")
    return told


def _rpg_channel(ctx, fallback_id=None):
    from utils.infrastructure.system.yaml_config import config
    import discord
    bot = getattr(ctx, "bot", None)
    if bot is None:
        return None
    name = str(config.get("discord.rpg_channel", "aethelgard")).lower()
    return (discord.utils.get(bot.get_all_channels(), name=name)
            or (bot.get_channel(int(fallback_id)) if fallback_id else None))


async def tell(ctx, path: str, *, channel=None) -> bool:
    """Write (once) and post one untold trip; it leaves `untold/` only when posted.
    `channel` is used only where #aethelgard cannot be found."""
    if path in _telling:
        return False
    _telling.add(path)
    try:
        data = await asyncio.to_thread(_load_path_sync, path)
        if not data:
            return False
        if not data.get("text"):
            text = await _narrate(ctx, data)
            if not text:
                return False                       # kept: tried again at the next boot
            data["text"] = text
            await asyncio.to_thread(_write_sync, path, data)
        target = _rpg_channel(ctx, data.get("channel_id")) or channel
        if target is None:
            log_warning(f"[rpg outing] no channel for {data.get('uname')}'s trip; kept for the next boot")
            return False
        try:
            sent = await target.send(embed=_embed(data))
        except Exception as e:
            log_warning(f"[rpg outing] could not post {data.get('uname')}'s trip (kept for the next boot): {e}")
            return False
        await asyncio.to_thread(_remove_sync, path)
        log_info(f"[rpg outing] told {data.get('uname')}'s trip ({data.get('fight_count', 0)} fights) "
                 f"in #{getattr(target, 'name', '?')} (message {getattr(sent, 'id', '?')})")
        return True
    finally:
        _telling.discard(path)


def _load_path_sync(path: str) -> Optional[dict]:
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _title(data: dict, reason: str) -> str:
    from utils.ttrpg.world import LOCATION_DATA
    names = [LOCATION_DATA.get(z, {}).get("name", z.replace("_", " ").title()) for z in data["zones"]]
    return " → ".join(dict.fromkeys(names)) or "the wilds"


def _count(names) -> list:
    """[(name, times)] in first-seen order."""
    seen: dict = {}
    for n in names:
        seen[n] = seen.get(n, 0) + 1
    return list(seen.items())


def _embed(data: dict):
    """The trip in the RPG's box, the way the character sheet is drawn. A field
    appears only for what happened: no quest line on a trip without one."""
    import discord
    from utils.ttrpg.narration import fit_embed_description
    from utils.ttrpg.rpg_ui import CLASS_ICONS, TIER_ICONS, colored_bar, hp_label
    reason, sheet = data.get("reason", ""), data.get("sheet") or {}
    fights, notes = data.get("fights", []), data.get("notes", {})
    who = sheet.get("character_name") or data.get("uname") or "someone"
    died = "knocked out" in reason or "fell" in reason
    levels = data.get("levels", [])
    color = 0x8B0000 if died else 0xFFD700 if levels else 0x2D5A27
    embed = discord.Embed(
        title=f"{CLASS_ICONS.get(sheet.get('class'), '⚔️')}  {who.upper()} · {_title(data, reason)}",
        description=f"*{fit_embed_description(data['text'])}*", color=color)

    if fights:
        crits = sum(f.get("crits", 0) for f in fights)
        clean = sum(1 for f in fights if f.get("won") and not f.get("taken"))
        line = f"{data.get('wins', 0)} won" + (f" · {data['losses']} lost" if data.get("losses") else "")
        extra = " · ".join(x for x in (f"💥 {crits} crit{'s' if crits != 1 else ''}" if crits else "",
                                        f"🛡️ {clean} untouched" if clean else "") if x)
        embed.add_field(name="⚔️ Fights", value=line + (f"\n{extra}" if extra else ""), inline=True)
    earned = [x for x in (f"+{data['xp']} XP" if data.get("xp") else "",
                          f"+{data['gil']} Gil" if data.get("gil") else "") if x]
    if earned:
        embed.add_field(name="✨ Earned", value="\n".join(earned), inline=True)
    if levels:
        embed.add_field(name="🎉 Level up", value=f"Lv.{max(levels)}", inline=True)
    hp = sheet.get("hp") or {}
    if hp.get("max"):
        embed.add_field(name="❤️ HP home",
                        value=f"```ansi\n{colored_bar(hp.get('current', 0), hp['max'], 14)}\n``` "
                              f"{hp_label(hp.get('current', 0), hp['max'])}", inline=False)
    if fights:
        tiers = {f["monster"]: f.get("tier") for f in fights}
        met = [f"{TIER_ICONS.get(tiers.get(n) or '', '')} {n}{f' ×{k}' if k > 1 else ''}".strip()
               for n, k in sorted(_count(f["monster"] for f in fights), key=lambda kv: -kv[1])]
        embed.add_field(name="🐾 Met", value=" · ".join(met)[:1024], inline=False)
    if data.get("loot"):
        loot = [f"{n}{f' ×{k}' if k > 1 else ''}" for n, k in _count(data["loot"])]
        embed.add_field(name="🎒 Loot", value=", ".join(loot)[:1024], inline=False)
    quests = [f"✅ {q}" for q in dict.fromkeys(notes.get("quest_done", []))]
    quests += [f"📜 {q}" for q in dict.fromkeys(notes.get("quest", [])) if q not in notes.get("quest_done", [])]
    if quests:
        embed.add_field(name="📜 Quests", value="\n".join(quests)[:1024], inline=False)
    along = [f"🌲 {e['title']}" for e in data.get("events", [])]
    along += [f"🏃 fled a {n}{f' ×{k}' if k > 1 else ''}" for n, k in _count(notes.get("fled", []))]
    along += [f"🧪 {n}{f' ×{k}' if k > 1 else ''}" for n, k in _count(notes.get("used", []))]
    if along:
        embed.add_field(name="🗺️ Along the way", value="\n".join(along)[:1024], inline=False)

    foot = [f"{sheet.get('advanced_class') or sheet.get('class') or 'Adventurer'} Lv.{sheet.get('level', '?')}"]
    if data.get("hunts"):
        foot.append(f"🎯 {data['hunts'][0]}/{data['hunts'][1]} hunts today")
    minutes = int((data.get("ended", 0) - data.get("started", 0)) // 60) if data.get("started") else 0
    if minutes >= 1:
        foot.append(f"out {minutes} min" if minutes < 120 else f"out {minutes // 60} h")
    embed.set_footer(text=" · ".join(foot))
    return embed


async def _narrate(ctx, data: dict) -> str:
    """The paragraph for one trip, or "" when it could not be written."""
    from utils.infrastructure.gpu.gpu_manager import GPUTaskPriority, chat_options, gpu_memory_manager
    from utils.infrastructure.system.yaml_config import config
    from utils.social.kaia_social_responder import load_persona_async
    from utils.ttrpg.narration import finish_cleanly
    from utils.ttrpg.rpg_prompt_builder import TTRPG_NARRATOR_OVERRIDE, build_outing_summary_prompt

    sheet, reason, uname = data.get("sheet") or {}, data.get("reason", "came back"), data.get("uname", "someone")
    try:
        persona = await load_persona_async()
        messages = [
            {"role": "system", "content": f"{persona}{TTRPG_NARRATOR_OVERRIDE}"
                                          f"{build_outing_summary_prompt(sheet, data, reason)}"},
            {"role": "user", "content": f"{uname} {reason}."},
        ]
        opts = chat_options(num_predict=280, temperature=0.85)
        resp = await gpu_memory_manager.run_with_gpu_guard(
            model_name=config.chat_model,
            coro=lambda: asyncio.wait_for(ctx.ollama_client.chat(model=config.chat_model, messages=messages,
                                                                 options=opts, keep_alive=-1), timeout=60.0),
            task_id=f"rpg_outing_{data.get('uid', 'x')}_{int(time.time())}",
            priority=GPUTaskPriority.CHAT)
        text = finish_cleanly(resp["message"]["content"].strip().replace("```", ""))
    except Exception as e:
        log_error(f"[rpg outing] narration failed (kept for the next boot): {e}")
        return ""
    if not text:
        log_warning(f"[rpg outing] the model wrote nothing for {uname}'s trip; kept for the next boot")
    return text
