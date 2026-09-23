"""
Knowledge Source Provenance Display
====================================

!explain     — the sources behind the last reply.
!explain N   — the sources behind the Nth-most-recent retrieval.

Both render the same box: the question, how confident retrieval was, and each
source by name with a short cleaned excerpt. Both used to build raw code blocks
around the query and the node text, and a query that carried its own ``` fence
ended the block early and spilled the rest as escape codes.
"""

import os
import time
from datetime import datetime

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


def _from_live(results):
    """The live cache's result dicts, in the trace's shape."""
    from utils.infrastructure.monitoring.retrieval_trace import _head, _source_of
    rows = []
    for r in results[:SHOWN]:
        meta = r.get("metadata", {}) or {}
        rows.append({
            "score": float(r.get("score", 0.0) or 0.0),
            "source": _source_of(meta),
            "method": meta.get("retrieval_method", ""),
            "flags": meta.get("audit_flags", []) or [],
            "head": _head(r.get("content", "")),
        })
    return rows


def render_sources(title: str, query: str, confidence: float, total: int,
                   rows, footer: str) -> discord.Embed:
    """The provenance box. `rows` are trace-shaped node dicts."""
    question = clean(query, 300) if query else ""
    description = (f"> {question}\n" if question else "") + (
        f"Confidence **{confidence:.2f}** ({_confidence_label(confidence)}) · "
        f"top {min(len(rows), SHOWN)} of {total} sources")
    embed = box(title, description, COLOR_SOURCES, footer)
    for i, row in enumerate(rows[:SHOWN], 1):
        method = (row.get("method") or "").lower()
        name = f"{i}. {describe_source(row.get('source', ''))}"
        meta = f"score {row.get('score', 0.0):.2f}" + (f" · {method}" if method else "")
        flags = row.get("flags") or []
        if flags:
            meta += " · ⚑ " + ", ".join(flags)
        excerpt = clean(row.get("head", ""), 150)
        add_field(embed, name, f"*{meta}*\n{excerpt}" if excerpt else f"*{meta}*")
    return embed


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
    nth = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

    if nth:
        from utils.infrastructure.monitoring.retrieval_trace import recent
        history = recent(nth)
        if len(history) < nth:
            await msg.channel.send(embed=box(
                "📚  Sources",
                f"Only {len(history)} retrieval(s) since the last restart — "
                f"try `!explain {max(1, len(history))}`.", COLOR_ERROR))
            return
        past = history[nth - 1]
        embed = render_sources(
            f"📚  Sources · retrieval #{nth}",
            past.get("query", ""), past.get("confidence", 0.0), past.get("n", 0),
            past.get("nodes", []),
            f"{datetime.fromtimestamp(past['ts']):%H:%M:%S} · !explain for the latest reply")
        await msg.channel.send(embed=embed)
        return

    results = getattr(rag, "_last_retrieval_results", []) or []
    if not results:
        await msg.channel.send(embed=box(
            "📚  Sources", "Nothing retrieved yet. Ask me something first.", COLOR_SOURCES))
        return

    confidence = float(getattr(rag, "_last_retrieval_confidence", 0.0) or 0.0)
    self_model = os.path.join("memory", "kaia_self_model.md")
    if os.path.exists(self_model):
        age = (time.time() - os.path.getmtime(self_model)) / 86400
        sm_status = f"self-model {age:.0f}d old"
    else:
        sm_status = "no self-model"

    from utils.infrastructure.monitoring.retrieval_trace import recent
    last = recent(1)
    query = last[0].get("query", "") if last else ""

    embed = render_sources("📚  Sources · last reply", query, confidence,
                           len(results), _from_live(results),
                           f"{sm_status} · !explain 2 for the one before")
    try:
        await msg.channel.send(embed=embed)
    except discord.HTTPException as e:
        log_info(f"Embed send failed ({e.status}/{e.code}), falling back to plain text.")
        lines = [f"{i}. {describe_source(r['source'])} ({r['score']:.2f})"
                 for i, r in enumerate(_from_live(results), 1)]
        await msg.channel.send(shorten("Sources for the last reply:\n" + "\n".join(lines), 1900))
    log_info(f"Provenance display shown for {msg.author.name}")
