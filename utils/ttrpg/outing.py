"""Accumulate hunts per player and publish one digest per in-game day.

Individual outings close when a player returns from hunting, dies, or leaves a
dungeon, but closing an outing only merges it into that player's daily record.
At midnight the dawn task rolls up any still-open outing and posts one combined
report to #aethelgard. Failed posts remain in `untold/` and are retried at boot.
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
DAILY_DIR = os.path.join(OUTING_DIR, "daily")
MAX_FIGHTS = 60          # beyond this only the totals grow; the prompt stays short
_lock = threading.Lock()


def is_hunting_ground(location: Optional[str]) -> bool:
    from utils.ttrpg.world import LOCATION_DATA
    return bool(LOCATION_DATA.get(location or "", {}).get("hunting"))


def _path(uid: str) -> str:
    return os.path.join(OUTING_DIR, f"{uid}.json")


def _local_day(timestamp: Optional[float] = None) -> str:
    return (time.strftime("%Y-%m-%d", time.localtime(timestamp))
            if timestamp is not None else time.strftime("%Y-%m-%d"))


def _daily_path(uid: str, day: str) -> str:
    return os.path.join(DAILY_DIR, f"{day}_{uid}.json")


def _has_activity(data: dict) -> bool:
    return bool(data.get("fights") or data.get("events") or data.get("notes"))


def _merge_daily_sync(trip: dict) -> None:
    """Idempotently merge a closed outing into its player's daily digest.

    The outing ID guards against re-merging if the process dies between writing
    the daily file and removing the open outing file.
    """
    from utils.core.atomic_write import write_atomic

    uid = str(trip.get("uid", ""))
    day = trip.get("day") or _local_day(trip.get("started"))
    os.makedirs(DAILY_DIR, exist_ok=True)
    path = _daily_path(uid, day)
    current = _load_path_sync(path)
    if current is None:
        current = {
            "uid": uid, "day": day, "zones": [], "fights": [], "events": [],
            "fight_count": 0, "wins": 0, "losses": 0, "xp": 0, "gil": 0,
            "loot": [], "levels": [], "notes": {}, "trips": 0, "trip_ids": [],
            "started": trip.get("started", time.time()), "ended": trip.get("ended", time.time()),
            "duration_seconds": 0, "had_knockout": False,
        }

    trip_id = str(trip.get("outing_id") or f"{uid}:{trip.get('started', 0)}")
    if trip_id in current.setdefault("trip_ids", []):
        return

    current["trip_ids"].append(trip_id)
    current["trips"] = int(current.get("trips", 0)) + 1
    current["started"] = min(float(current.get("started", trip.get("started", time.time()))),
                             float(trip.get("started", time.time())))
    current["ended"] = max(float(current.get("ended", trip.get("ended", time.time()))),
                           float(trip.get("ended", time.time())))
    current["duration_seconds"] = float(current.get("duration_seconds", 0)) + max(
        0, float(trip.get("ended", time.time())) - float(trip.get("started", time.time())))
    for zone in trip.get("zones", []):
        if zone not in current["zones"]:
            current["zones"].append(zone)
    for fight in trip.get("fights", []):
        if len(current["fights"]) < MAX_FIGHTS:
            current["fights"].append(fight)
    for event in trip.get("events", []):
        if len(current["events"]) < 20:
            current["events"].append(event)
    for key in ("fight_count", "wins", "losses", "xp", "gil"):
        current[key] = int(current.get(key, 0)) + int(trip.get(key, 0) or 0)
    current["loot"].extend(str(x) for x in trip.get("loot", []))
    current["levels"].extend(trip.get("levels", []))
    for kind, items in (trip.get("notes") or {}).items():
        bucket = current.setdefault("notes", {}).setdefault(kind, [])
        bucket.extend(str(x) for x in items[:max(0, 20 - len(bucket))])

    trip_reason = str(trip.get("reason", ""))
    knocked_out = ("knocked out" in trip_reason.lower() or "fell in " in trip_reason.lower()
                   or any(f.get("died") for f in trip.get("fights", [])))
    current["had_knockout"] = bool(current.get("had_knockout")) or knocked_out
    if knocked_out:
        current["reason"] = "was knocked out during the day's hunts and woke at the Shrine"
    elif current["had_knockout"]:
        current["reason"] = "finished the day's hunts after recovering from a knockout"
    else:
        current["reason"] = "finished the day's hunts"

    # Keep the latest sheet/channel snapshot, especially the hunt count just
    # before reset, while retaining the start and totals from earlier outings.
    current["uid"] = uid
    current["uname"] = trip.get("uname", current.get("uname", uid))
    current["channel_id"] = trip.get("channel_id", current.get("channel_id"))
    current["sheet"] = trip.get("sheet", current.get("sheet", {}))
    current["hunts"] = trip.get("hunts", current.get("hunts"))
    current["daily_summary"] = True
    write_atomic(path, json.dumps(current, indent=1))


def _load_sync(uid: str) -> Optional[dict]:
    try:
        with open(_path(uid)) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _update_sync(uid: str, fn) -> dict:
    from utils.core.atomic_write import write_atomic
    with _lock:
        data = _load_sync(uid) or {"uid": str(uid), "outing_id": f"{uid}_{time.time_ns()}",
                                    "day": _local_day(), "started": time.time(), "zones": [],
                                    "fights": [], "events": [], "fight_count": 0, "wins": 0,
                                    "losses": 0, "xp": 0, "gil": 0, "loot": [], "levels": []}
        data.setdefault("uid", str(uid))
        data.setdefault("outing_id", f"{uid}_{time.time_ns()}")
        data.setdefault("day", _local_day(data.get("started")))
        fn(data)
        os.makedirs(OUTING_DIR, exist_ok=True)
        write_atomic(_path(uid), json.dumps(data, indent=1))
        return data


def _take_sync(uid: str, tale: dict) -> bool:
    """Close the open outing into the durable per-player daily accumulator."""
    from utils.core.atomic_write import write_atomic
    with _lock:
        data = _load_sync(uid)
        if not data:
            return False
        if not _has_activity(data):
            try:
                os.remove(_path(uid))
            except OSError:
                pass
            return False
        data.update(tale)
        data.setdefault("day", _local_day(data.get("started")))
        # Write the daily aggregate before dropping the open outing. The outing
        # ID makes this safe if a crash happens between these two operations.
        _merge_daily_sync(data)
        try:
            os.remove(_path(uid))
        except OSError:
            pass
        return True


def _take_open_outings_sync(through_day: str) -> int:
    """Move any outing left open at dawn into the correct day's accumulator."""
    from utils.ttrpg.character_manager import _load_sync as load_sheet_sync
    moved = 0
    with _lock:
        try:
            names = [n for n in os.listdir(OUTING_DIR) if n.endswith(".json")
                     and os.path.isfile(os.path.join(OUTING_DIR, n))]
        except OSError:
            return 0
        for name in names:
            uid = name[:-5]
            data = _load_sync(uid)
            if not data:
                continue
            day = data.get("day") or _local_day(data.get("started"))
            if day > through_day:
                continue
            try:
                sheet = load_sheet_sync(uid) or {}
            except Exception:
                sheet = {}
            try:
                from utils.ttrpg.progression import get_max_hunts
                hunts = [int(sheet.get("hunts_today", 0)), int(get_max_hunts(sheet))]
            except Exception:
                hunts = None
            tale = {
                "uid": uid,
                "uname": sheet.get("character_name", uid),
                "reason": "finished the day's hunts",
                "ended": time.time(),
                "hunts": hunts,
                "channel_id": None,
                "sheet": {k: sheet.get(k) for k in _SHEET_KEYS if k in sheet},
                "day": day,
            }
            data.update(tale)
            if _has_activity(data):
                _merge_daily_sync(data)
                moved += 1
            try:
                os.remove(_path(uid))
            except OSError:
                pass
    return moved


def _finalize_daily_sync(through_day: str) -> list:
    """Move completed daily aggregates to untold storage before attempting posts."""
    from utils.core.atomic_write import write_atomic
    ready = []
    os.makedirs(UNTOLD_DIR, exist_ok=True)
    try:
        names = sorted(n for n in os.listdir(DAILY_DIR) if n.endswith(".json"))
    except OSError:
        return ready
    with _lock:
        for name in names:
            day = name[:10]
            if len(day) != 10 or day > through_day:
                continue
            src = os.path.join(DAILY_DIR, name)
            data = _load_path_sync(src)
            if not data:
                continue
            uid = str(data.get("uid") or name[11:-5])
            target = os.path.join(UNTOLD_DIR, f"daily_{day}_{uid}.json")
            data["daily_summary"] = True
            # Keep the file pending if the same day's report is already waiting;
            # never replace a generated paragraph that failed to post.
            if not os.path.exists(target):
                write_atomic(target, json.dumps(data, indent=1))
            try:
                os.remove(src)
            except OSError:
                pass
            ready.append(target)
    return ready


async def flush_daily(ctx, day: Optional[str] = None) -> int:
    """Publish at most one combined summary per player/day, oldest day first.

    Called by the midnight task before it resets hunts, so the footer retains
    the completed day's hunt count. An explicit `day` is useful in tests.
    """
    if day is None:
        from datetime import date, timedelta
        day = (date.today() - timedelta(days=1)).isoformat()
    await asyncio.to_thread(_take_open_outings_sync, day)
    paths = await asyncio.to_thread(_finalize_daily_sync, day)
    posted = 0
    for path in paths:
        posted += bool(await tell(ctx, path))
    if posted:
        log_info(f"[rpg outing] posted {posted} daily hunt digest(s) through {day}")
    return int(posted)


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
    """Close one outing into the daily accumulator; do not post until dawn."""
    hunts = None
    try:
        from utils.ttrpg.progression import get_max_hunts
        hunts = [int(sheet.get("hunts_today", 0)), int(get_max_hunts(sheet))]
    except Exception:
        pass
    tale = {"uid": str(uid), "uname": uname, "reason": reason, "ended": time.time(), "hunts": hunts,
            "channel_id": getattr(channel, "id", None),
            "sheet": {k: sheet.get(k) for k in _SHEET_KEYS if k in (sheet or {})}}
    return bool(await asyncio.to_thread(_take_sync, str(uid), tale))


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
    if data.get("daily_summary") and data.get("trips", 1) > 1:
        foot.append(f"{data['trips']} trips")
    elapsed = data.get("duration_seconds")
    if elapsed is None:
        elapsed = data.get("ended", 0) - data.get("started", 0)
    minutes = int(max(0, elapsed) // 60) if data.get("started") else 0
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
