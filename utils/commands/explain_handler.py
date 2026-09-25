"""
Knowledge Source Provenance Display
====================================

!explain          — the sources behind the latest retrieval in this channel.
!explain N        — source N from that list: what it is and the passages used.
!explain back [N] — the sources behind an earlier retrieval (1 = the one before).
"""

import time

import discord

from utils.commands.embed_style import (
    COLOR_ERROR, COLOR_SOURCES, box, clean, describe_source, shorten)
from utils.infrastructure.logging.kaia_logger import log_info

#: Sources shown per retrieval. The trace keeps eight.
SHOWN = 8


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.45:
        return "moderate"
    return "low"


def _ago(ts: float) -> str:
    minutes = int((time.time() - ts) // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    return f"{minutes // 60} h {minutes % 60} min ago"


def _grouped(rows):
    """One entry per source, in first-seen order: [(row, passage_count)]."""
    order, counts = [], {}
    for row in rows:
        key = row.get("source", "")
        if key not in counts:
            order.append(row)
            counts[key] = 0
        counts[key] += 1
    return [(row, counts[row.get("source", "")]) for row in order]


_STRENGTH = {"high": "strong match", "moderate": "partial match", "low": "weak match"}


def render_sources(title: str, query: str, confidence: float, total: int,
                   rows, footer: str, when: str = "") -> discord.Embed:
    """The provenance box: the question, then one line per source it drew on.

    Names only. Scores, retrieval methods and excerpts were all shown and none
    of them told a reader anything; the excerpt of a document mostly repeated
    its title.
    """
    lines = []
    # What they typed: the recorded query carries any fetched page after it.
    from utils.core.sanitizer import user_authored_text
    question = clean(user_authored_text(query), 200) if query else ""
    if question:
        lines.append(f"> {question}")
    status = [when] if when else []
    status.append(_STRENGTH[_confidence_label(confidence)])
    lines.append(" · ".join(status))
    lines.append("")
    for i, (row, passages) in enumerate(_grouped(rows[:SHOWN]), 1):
        extra = f" · {passages} passages" if passages > 1 else ""
        flags = row.get("flags") or []
        flag = f" · ⚑ {', '.join(flags)}" if flags else ""
        lines.append(f"**{i}.** {describe_source(row.get('source', ''))}{extra}{flag}")
    return box(title, "\n".join(lines), COLOR_SOURCES, footer)


def render_source_detail(n: int, row: dict, past: dict) -> discord.Embed:
    """One source from a retrieval: what it is, and the passages that were used."""
    source = row.get("source", "")
    passages = [r for r in past.get("nodes", []) if r.get("source", "") == source]
    lines = [f"`{clean(source, 180)}`", ""]
    for i, r in enumerate(passages[:4], 1):
        head = clean(r.get("head", ""), 300)
        if head:
            lines.append(f"**{i}.** {head}")
    flags = row.get("flags") or []
    if flags:
        lines.append(f"\n⚑ flagged: {', '.join(flags)}")
    return box(f"📚  Source {n} · {describe_source(source)}", "\n".join(lines), COLOR_SOURCES,
               "!explain for the whole list")


async def handle_explain_command(ctx, msg, send_kaia_response):
    """Handle the !explain command — display provenance of a RAG retrieval.

    Open to everyone, and scoped to the channel it is typed in: the box quotes
    the question, so it shows only what was asked there.
    """
    rag = ctx.rag
    if not rag:
        await msg.channel.send(embed=box(
            "📚  Sources", "Retrieval is unavailable right now.", COLOR_ERROR))
        return

    raw = getattr(msg, "content", "")
    parts = raw.split() if isinstance(raw, str) else []
    args = parts[1:]
    back = 0
    if args and args[0].lower() == "back":
        back = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
        args = []
    pick = int(args[0]) if args and args[0].isdigit() else 0

    # Always the trace: it carries the question and the time. The live cache
    # carried neither, so after a reply that searched nothing, `!explain`
    # showed the retrieval before it as if it were that reply's sources.
    from utils.infrastructure.monitoring.retrieval_trace import recent
    history = recent(back + 1, channel_id=msg.channel.id)
    if not history:
        await msg.channel.send(embed=box(
            "📚  Sources", "Nothing retrieved in this channel since the last restart. Ask me something first.",
            COLOR_SOURCES))
        return
    if len(history) <= back:
        await msg.channel.send(embed=box(
            "📚  Sources", f"Only {len(history)} retrieval(s) in this channel since the last restart.",
            COLOR_ERROR))
        return

    past = history[back]
    grouped = _grouped(past.get("nodes", [])[:SHOWN])
    if pick:
        if pick > len(grouped):
            await msg.channel.send(embed=box(
                "📚  Sources", f"That list has {len(grouped)} source(s).", COLOR_ERROR))
            return
        await msg.channel.send(embed=render_source_detail(pick, grouped[pick - 1][0], past))
        return

    title = "📚  Sources" if not back else f"📚  Sources · {back} back"
    footer = "!explain 2 opens source 2 · !explain back for the one before"
    embed = render_sources(title, past.get("query", ""), past.get("confidence", 0.0),
                           past.get("n", 0), past.get("nodes", []), footer,
                           when=_ago(past["ts"]))
    try:
        await msg.channel.send(embed=embed)
    except discord.HTTPException as e:
        log_info(f"Embed send failed ({e.status}/{e.code}), falling back to plain text.")
        lines = [f"{i}. {describe_source(r['source'])}" for i, (r, _) in
                 enumerate(_grouped(past.get("nodes", [])), 1)]
        await msg.channel.send(shorten("Sources:\n" + "\n".join(lines), 1900))
    log_info(f"Provenance display shown for {msg.author.name}")
