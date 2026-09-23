"""
Knowledge Source Provenance Display
====================================

!explain     — the sources behind the latest retrieval.
!explain N   — the sources behind the Nth-most-recent one.

Both render the same box: the question, how confident retrieval was, and each
source by name with a short cleaned excerpt. Both used to build raw code blocks
around the query and the node text, and a query that carried its own ``` fence
ended the block early and spilled the rest as escape codes.
"""

import time

import discord

from utils.commands.embed_style import (
    COLOR_ERROR, COLOR_SOURCES, add_field, box, clean, describe_source, shorten)
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
    question = clean(query, 200) if query else ""
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


async def handle_explain_command(ctx, msg, send_kaia_response):
    """Handle the !explain command — display provenance of a RAG retrieval.

    Open to everyone. It reports which knowledge-base nodes informed an answer
    and how they scored; it exposes no privileged state and changes nothing.
    """
    rag = ctx.rag
    if not rag:
        await msg.channel.send(embed=box(
            "📚  Sources", "Retrieval is unavailable right now.", COLOR_ERROR))
        return

    raw = getattr(msg, "content", "")
    parts = raw.split() if isinstance(raw, str) else []
    nth = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1

    # Always the trace: it carries the question and the time. The live cache
    # carried neither, so after a reply that searched nothing, `!explain`
    # showed the retrieval before it as if it were that reply's sources.
    from utils.infrastructure.monitoring.retrieval_trace import recent
    history = recent(nth)
    if not history:
        await msg.channel.send(embed=box(
            "📚  Sources", "Nothing retrieved since the last restart. Ask me something first.",
            COLOR_SOURCES))
        return
    if len(history) < nth:
        await msg.channel.send(embed=box(
            "📚  Sources",
            f"Only {len(history)} retrieval(s) since the last restart — "
            f"try `!explain {len(history)}`.", COLOR_ERROR))
        return

    past = history[nth - 1]
    title = "📚  Sources" if nth == 1 else f"📚  Sources · #{nth}"
    footer = f"!explain {nth + 1} for the one before"
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
