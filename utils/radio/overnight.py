"""The overnight log: a morning post in Kaia's voice about what her night shift saw.

Python gathers the facts — what she recorded and copied, what eam.watch
logged, whether a TACAMO plane showed itself, the sun, the closest rock, the
biggest quake, what the beacons said. One model call then writes them up,
told to use those facts and nothing else. It goes out through
`unprompted.speak` as source `overnight`, so the shared daily limit, the gap
and the posting hours apply, and it is cross-posted only if
`unprompted.bluesky.overnight` is literally true.

A night with fewer than two facts produces no log.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from utils.infrastructure.logging.kaia_logger import log_debug, log_warning
from utils.radio.fetch import read_cache, write_cache

STATE = "overnight_state"
WINDOW_H = 12
MIN_FACTS = 2


def _since() -> datetime:
    last = float(read_cache(STATE).get("last_posted") or 0)
    floor = time.time() - WINDOW_H * 3600
    return datetime.fromtimestamp(max(last, floor), timezone.utc)


async def gather(since: Optional[datetime] = None) -> list[str]:
    """The night's facts, each one short sentence, all computed here."""
    from utils.radio import adsb, beacons, eam_watch, log as radio_log
    from utils.sky import feeds
    since = since or _since()
    facts: list[str] = []

    entries = [e for e in radio_log.entries() if datetime.fromisoformat(e["started"]) >= since]
    eams = [e for e in entries if e.get("kind") == "hfgcs" and (e.get("parsed") or {}).get("message")]
    if eams:
        clean = [e for e in eams if (e["parsed"].get("uncertain") or 0) == 0]
        calls = sorted({e["parsed"].get("callsign") for e in eams if e["parsed"].get("callsign")})
        facts.append(f"you recorded {len(eams)} EAM(s) on the HFGCS net yourself"
                     + (f", from {', '.join(calls)}" if calls else "")
                     + f"; {len(clean)} copied with no uncertain characters")
        checked = [e["check"]["accuracy"] for e in eams if e.get("check")]
        if checked:
            facts.append(f"checked against the human logs you were {sum(checked) / len(checked):.0%} right on average")
    numbers = [e for e in entries if e.get("kind") == "numbers"]
    for e in numbers[:3]:
        facts.append(f"you recorded {e['station']} on {e['khz']:g} kHz at "
                     f"{datetime.fromisoformat(e['started']):%H:%M} UTC")

    msgs = [m for m in eam_watch.messages(read_cache(eam_watch.MESSAGES_CACHE))
            if m.time and m.time >= since and m.type == eam_watch.EAM_TYPE]
    if msgs:
        senders = sorted({m.sender for m in msgs})
        facts.append(f"eam.watch listeners logged {len(msgs)} EAM(s) overnight, from {', '.join(senders[:4])}")

    for kind, v in adsb.last_seen().items():
        if v.get("at", 0) >= since.timestamp():
            facts.append(f"an {adsb.TYPES.get(kind, kind)} was broadcasting on ADS-B"
                         + (f" at {v['altitude_ft']:,} ft" if v.get("altitude_ft") else ""))

    try:
        w = await feeds.space_weather()
        facts.append(f"the planetary K index is {w['kp']:.1f} ({feeds.kp_words(w['kp'])}), "
                     f"solar flux {w.get('solar_flux') or '?'}")
        flare = w.get("flare") or {}
        if flare.get("max_class", "").startswith(("M", "X")):
            facts.append(f"the sun put out a {flare['max_class']} flare")
    except Exception as e:
        log_debug(f"[overnight] space weather unavailable: {e}")
    try:
        rocks = [r for r in await feeds.close_approaches(days=2) if r["ld"] < 5]
        if rocks:
            r = rocks[0]
            when = datetime.strptime(r["when"], "%Y-%b-%d %H:%M").replace(tzinfo=timezone.utc)
            verb = "will pass" if when > datetime.now(timezone.utc) else "passed"
            facts.append(f"asteroid {r['name']} {verb} Earth at {r['ld']:.1f} lunar distances "
                         f"({when:%d %b %H:%M} UTC)")
    except Exception as e:
        log_debug(f"[overnight] close approaches unavailable: {e}")
    try:
        quakes = [q for q in await feeds.quakes() if q["when"] >= since]
        if quakes and (quakes[0]["mag"] or 0) >= 6:
            q = quakes[0]
            facts.append(f"a magnitude {q['mag']:.1f} earthquake hit {q['place']}")
    except Exception as e:
        log_debug(f"[overnight] quakes unavailable: {e}")

    b = beacons.recent()
    if b and datetime.fromisoformat(b["at"]) >= since:
        heard = [c for c, _, db in b["beacons"] if db >= beacons.HEARD_DB]
        facts.append(f"on the beacon chain at {b['khz'] / 1000:.3f} MHz you heard {len(heard)} of 18"
                     + (f" ({', '.join(heard[:5])})" if heard else ""))
    return facts


PROMPT = (
    "You are Kaia. Write your overnight log for the server: lowercase, dry, observant, in your "
    "own voice, 40 to 110 words, one or two short paragraphs.\n"
    "Rules:\n"
    "- Every sentence comes from one of the facts listed below. Nothing else happened.\n"
    "- Do not mention weather, clouds, what you heard or saw, or anything not listed.\n"
    "- Keep each fact's tense: 'will pass' stays in the future.\n"
    "- EAMs are encrypted: never say what one means.\n"
    "- You may add one short reaction of your own at the end — a feeling, not a fact.\n"
    "- No headers, no lists, no sign-off.\n\nTHE NIGHT'S FACTS:\n"
)

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def invented_numbers(text: str, facts: list[str]) -> set[str]:
    """Numbers in the write-up that no fact contains: the check that it made nothing up."""
    def norm(n: str) -> str:            # "1,234" is 1234 and "08" is 8
        n = n.replace(",", "")
        return n.lstrip("0") or "0" if "." not in n else n
    have = {norm(n) for n in _NUMBER.findall(" ".join(facts))}
    return {n for n in _NUMBER.findall(text) if norm(n) not in have}


async def write(ctx, facts: list[str]) -> str:
    import asyncio
    import uuid
    from utils.core.response_filter import BotSpeakFilter
    from utils.infrastructure.gpu.gpu_manager import GPUTaskPriority, chat_options, gpu_memory_manager
    from utils.infrastructure.system.yaml_config import config
    from utils.ttrpg.narration import finish_cleanly

    prompt = PROMPT + "\n".join(f"- {f}" for f in facts)

    async def _chat():
        return await ctx.ollama_client.chat(model=config.chat_model,
                                            messages=[{"role": "user", "content": prompt}],
                                            options=chat_options(num_predict=220, temperature=0.4),
                                            keep_alive=-1)
    for attempt in range(2):
        resp = await gpu_memory_manager.run_with_gpu_guard(
            model_name=config.chat_model, priority=GPUTaskPriority.BACKGROUND,
            coro=asyncio.wait_for(_chat(), timeout=90.0), task_id=f"overnight_{uuid.uuid4().hex[:8]}")
        text = BotSpeakFilter.harden(finish_cleanly(resp["message"]["content"].strip().replace("`", "")))
        extra = invented_numbers(text, facts)
        if not extra:
            return text
        log_warning(f"[overnight] draft {attempt + 1} had numbers no fact contains ({sorted(extra)[:4]}); retrying")
    return ""


async def post(ctx, channel, manual: bool = False) -> Optional[str]:
    """Gather, write, speak. Returns what was posted, or None and why is logged."""
    from utils.core import unprompted
    facts = await gather()
    if len(facts) < MIN_FACTS:
        log_debug(f"[overnight] only {len(facts)} fact(s) tonight; no log")
        return None
    if not manual:
        ok, why = unprompted.gate(getattr(ctx, "bot_state", None), "overnight")
        if not ok:
            log_debug(f"[overnight] held: {why}")
            return None
    text = await write(ctx, facts)
    if not text:
        log_warning("[overnight] the model returned nothing usable")
        return None
    spoken = await unprompted.speak(ctx, channel, "overnight", text, manual=manual)
    if spoken.posted:
        write_cache(STATE, {"last_posted": time.time(), "facts": facts})
        return text
    return None


def due(now: Optional[datetime] = None, hhmm: str = "08:30") -> bool:
    """Once a day, from `hhmm` local for two hours, until one is posted."""
    now = now or datetime.now()
    h, m = (int(x) for x in hhmm.split(":"))
    start = now.replace(hour=h, minute=m, second=0, microsecond=0)
    last = float(read_cache(STATE).get("last_posted") or 0)
    posted_today = datetime.fromtimestamp(last).date() == now.date() if last else False
    return start <= now < start + timedelta(hours=2) and not posted_today
