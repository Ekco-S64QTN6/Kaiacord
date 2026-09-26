"""The overnight log: a morning post in Kaia's voice about what her night shift saw.

Python gathers the facts — what she recorded and copied, what eam.watch
logged, whether a TACAMO plane showed itself, the sun, the closest rock, the
biggest quake, what the beacons said, what the local scanner caught. They are
shown as a box, one field per section; one model call writes her account of
the night on top, told to use those facts and nothing else. It goes out through
`unprompted.speak` as source `overnight`, so the shared daily limit, the gap
and the posting hours apply, and it is cross-posted only if
`unprompted.bluesky.overnight` is literally true.

A night with fewer than two facts produces no log.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
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


@dataclass
class Fact:
    """One thing the night shift saw: a section of the box, the line shown in it,
    and the plain sentence the model is given."""
    section: str
    line: str
    text: str


#: The box's fields, in order, with the emoji each one wears.
SECTIONS = {
    "air": "📻  On the air",
    "local": "📡  Local scanner",
    "beacons": "🗼  Beacon chain",
    "sun": "☀️  Space weather",
    "earth": "🌍  Near Earth",
}


def kp_icon(kp: float) -> str:
    return "🔴" if kp >= 7 else "🟠" if kp >= 5 else "🟡" if kp >= 4 else "🟢"


async def gather(since: Optional[datetime] = None) -> list[Fact]:
    """The night's facts, all computed here."""
    from utils.radio import adsb, beacons, eam_watch, ledger, log as radio_log
    from utils.sky import feeds
    since = since or _since()
    facts: list[Fact] = []

    entries = [e for e in radio_log.entries() if datetime.fromisoformat(e["started"]) >= since]
    eams = [e for e in entries if e.get("kind") == "hfgcs" and (e.get("parsed") or {}).get("message")]
    if eams:
        clean = [e for e in eams if (e["parsed"].get("uncertain") or 0) == 0]
        calls = sorted({e["parsed"].get("callsign") for e in eams if e["parsed"].get("callsign")})
        checked = [e["check"]["accuracy"] for e in eams if e.get("check")]
        line = (f"📟 **{len(eams)} EAM{'s' if len(eams) != 1 else ''}** copied on HFGCS"
                + (f" · {', '.join(calls)}" if calls else "") + f" · {len(clean)} clean")
        if checked:
            line += f" · {sum(checked) / len(checked):.0%} vs the human logs"
        facts.append(Fact("air", line,
                          f"you recorded {len(eams)} EAM(s) on the HFGCS net yourself"
                          + (f", from {', '.join(calls)}" if calls else "")
                          + f"; {len(clean)} copied with no uncertain characters"
                          + (f"; checked against the human logs you were {sum(checked) / len(checked):.0%} right"
                             if checked else "")))
    numbers = sorted((e for e in entries if e.get("kind") == "numbers"), key=lambda e: e["started"])
    for e in numbers[-3:]:
        at = datetime.fromisoformat(e["started"])
        facts.append(Fact("air", f"🔢 **{e['station']}** · {e['khz']:g} kHz {str(e.get('mode') or '').upper()}"
                                 f" · recorded {at:%H:%M}Z".replace("  ", " "),
                          f"you recorded {e['station']} on {e['khz']:g} kHz at {at:%H:%M} UTC"))

    msgs = [m for m in eam_watch.messages(read_cache(eam_watch.MESSAGES_CACHE))
            if m.time and m.time >= since and m.type == eam_watch.EAM_TYPE]
    if msgs:
        senders = sorted({m.sender for m in msgs})
        facts.append(Fact("air", f"👂 eam.watch listeners logged **{len(msgs)}** · {', '.join(senders[:4])}",
                          f"eam.watch listeners logged {len(msgs)} EAM(s) overnight, from {', '.join(senders[:4])}"))

    for kind, v in adsb.last_seen().items():
        if v.get("at", 0) >= since.timestamp():
            name = adsb.TYPES.get(kind, kind)
            alt = f" at {v['altitude_ft']:,} ft" if v.get("altitude_ft") else ""
            facts.append(Fact("air", f"✈️ **{name}** on ADS-B{alt}",
                              f"an {name} was broadcasting on ADS-B{alt}"))

    try:
        caught = [e for e in ledger.recent(500) if e["ts"] >= since.timestamp()]
        if caught:
            kinds = {k: sum(1 for e in caught if e["kind"] == k) for k in ("voice", "data", "carrier")}
            busiest = max({e["freq_hz"] for e in caught}, key=lambda f: sum(1 for e in caught if e["freq_hz"] == f))
            n = sum(1 for e in caught if e["freq_hz"] == busiest)
            names = {"voice": "voice", "data": "data", "carrier": "carriers" if kinds["carrier"] != 1 else "carrier"}
            parts = [f"{icon} {kinds[k]} {names[k]}" for k, icon in (("voice", "🗣️"), ("data", "📶"), ("carrier", "〰️"))
                     if kinds[k]]
            facts.append(Fact("local", f"**{len(caught)}** catches · " + " · ".join(parts)
                                       + f"\nbusiest: {busiest / 1e6:.4f} MHz ({n}×)",
                              f"the local scanner caught {len(caught)} transmissions "
                              f"({', '.join(f'{kinds[k]} {k}' for k in kinds if kinds[k])}); "
                              f"the busiest channel was {busiest / 1e6:.4f} MHz"))
    except Exception as e:
        log_debug(f"[overnight] ledger unavailable: {e}")

    b = beacons.recent()
    if b and datetime.fromisoformat(b["at"]) >= since:
        heard = [c for c, _, db in b["beacons"] if db >= beacons.HEARD_DB]
        facts.append(Fact("beacons", f"**{len(heard)} of 18** heard on {b['khz'] / 1000:.3f} MHz"
                                     + (f" · {', '.join(heard[:5])}" if heard else ""),
                          f"on the beacon chain at {b['khz'] / 1000:.3f} MHz you heard {len(heard)} of 18"
                          + (f" ({', '.join(heard[:5])})" if heard else "")))

    try:
        w = await feeds.space_weather()
        kp, flux = w["kp"], w.get("solar_flux") or "?"
        facts.append(Fact("sun", f"{kp_icon(kp)} Kp **{kp:.1f}** · {feeds.kp_words(kp)}\n🌞 Solar flux **{flux}**",
                          f"the planetary K index is {kp:.1f} ({feeds.kp_words(kp)}), solar flux {flux}"))
        flare = w.get("flare") or {}
        if flare.get("max_class", "").startswith(("M", "X")):
            facts.append(Fact("sun", f"💥 **{flare['max_class']}** flare",
                              f"the sun put out a {flare['max_class']} flare"))
    except Exception as e:
        log_debug(f"[overnight] space weather unavailable: {e}")
    try:
        rocks = [r for r in await feeds.close_approaches(days=2) if r["ld"] < 5]
        if rocks:
            r = rocks[0]
            when = datetime.strptime(r["when"], "%Y-%b-%d %H:%M").replace(tzinfo=timezone.utc)
            verb = "will pass" if when > datetime.now(timezone.utc) else "passed"
            facts.append(Fact("earth", f"☄️ **{r['name']}** {verb} at {r['ld']:.1f} lunar distances · {when:%d %b %H:%M}Z",
                              f"asteroid {r['name']} {verb} Earth at {r['ld']:.1f} lunar distances "
                              f"({when:%d %b %H:%M} UTC)"))
    except Exception as e:
        log_debug(f"[overnight] close approaches unavailable: {e}")
    try:
        quakes = [q for q in await feeds.quakes() if q["when"] >= since]
        if quakes and (quakes[0]["mag"] or 0) >= 6:
            q = quakes[0]
            facts.append(Fact("earth", f"🫨 **M{q['mag']:.1f}** earthquake · {q['place']}",
                              f"a magnitude {q['mag']:.1f} earthquake hit {q['place']}"))
    except Exception as e:
        log_debug(f"[overnight] quakes unavailable: {e}")
    return facts


def embed(facts: list[Fact], note: str = "", when: Optional[datetime] = None):
    """The box: her note on top, then one field per section that has anything in it."""
    from utils.commands.embed_style import add_field, box, clean_block
    from utils.commands.nightshift import COLOR_NIGHT, others
    when = when or datetime.now()
    e = box(f"🌙  Overnight log · {when:%a %d %b}", clean_block(note, 1500) if note else "",
            COLOR_NIGHT, footer=others("overnight"))
    for key, title in SECTIONS.items():
        lines = [f.line for f in facts if f.section == key]
        if lines:
            add_field(e, title, "\n".join(lines), inline=key in ("beacons", "sun"))
    return e


PROMPT = (
    "You are Kaia, writing up your night shift for the server. The raw readings are shown "
    "underneath in a table, so this is the story of the night, not the list: lowercase, dry, "
    "observant, in your own voice, one or two short paragraphs, 60 to 130 words.\n"
    "Rules:\n"
    "- Tell it the way you'd tell a friend over coffee: what the night felt like, what stood "
    "out, what was dull, what you're curious about. Don't march through the facts one by one, "
    "and don't open every sentence with 'i recorded' or 'i heard'.\n"
    "- Everything that happened comes from the facts below. Nothing else happened; you may "
    "leave facts out.\n"
    "- Do not mention weather, clouds, or anything not listed.\n"
    "- Keep each fact's tense: 'will pass' stays in the future.\n"
    "- EAMs and number-station groups are encrypted: never say what one means.\n"
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


async def write(ctx, facts: list[Fact]) -> str:
    """Her note for the top of the box, or '' if every draft invented a number."""
    import asyncio
    import uuid
    from utils.core.response_filter import BotSpeakFilter
    from utils.infrastructure.gpu.gpu_manager import GPUTaskPriority, chat_options, gpu_memory_manager
    from utils.infrastructure.system.yaml_config import config
    from utils.ttrpg.narration import finish_cleanly

    texts = [f.text for f in facts]
    prompt = PROMPT + "\n".join(f"- {t}" for t in texts)

    async def _chat():
        return await ctx.ollama_client.chat(model=config.chat_model,
                                            messages=[{"role": "user", "content": prompt}],
                                            options=chat_options(num_predict=280, temperature=0.4),
                                            keep_alive=-1)
    for attempt in range(2):
        resp = await gpu_memory_manager.run_with_gpu_guard(
            model_name=config.chat_model, priority=GPUTaskPriority.BACKGROUND,
            coro=asyncio.wait_for(_chat(), timeout=90.0), task_id=f"overnight_{uuid.uuid4().hex[:8]}")
        text = BotSpeakFilter.harden(finish_cleanly(resp["message"]["content"].strip().replace("`", "")))
        extra = invented_numbers(text, texts)
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
        ok, why = unprompted.gate(getattr(ctx, "bot_state", None), "overnight", waiting_ok=True)
        if not ok:
            log_debug(f"[overnight] held: {why}")
            return None
    note = await write(ctx, facts)
    if not note:
        log_warning("[overnight] no usable note; posting the readings alone")
    text = "\n".join([note] * bool(note) + [f.text for f in facts])
    spoken = await unprompted.speak(ctx, channel, "overnight", text, manual=manual, embed=embed(facts, note))
    if spoken.posted or spoken.queued:           # queued: it goes out in turn
        write_cache(STATE, {"last_posted": time.time(), "facts": [f.text for f in facts]})
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
