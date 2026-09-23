"""The box every ! command answers in.

`!help` set the look: a Discord embed with a short title, a plain description,
named fields and a quiet footer. Commands that hand-built code blocks instead
broke on the first piece of text that carried its own fence — `!explain 1` on a
query with a pasted ```ansi block rendered the rest of the reply as raw escape
codes. Anything quoted from a user or a document goes through `clean` before it
reaches an embed.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Optional

import discord

# Discord's own limits for an embed.
TITLE_LIMIT = 256
DESCRIPTION_LIMIT = 4096
FIELD_NAME_LIMIT = 256
FIELD_VALUE_LIMIT = 1024
MAX_FIELDS = 25

COLOR_INFO = 0x5F5CAF      # !help
COLOR_SOURCES = 0x10B981   # !explain
COLOR_NEWS = 0xE0A96D      # !news
COLOR_ERROR = 0xCC4444

_ANSI = re.compile(r"(?:\x1b)?\[[0-9;]{1,12}m")
_FENCE = re.compile(r"```[a-zA-Z0-9_+-]*")
_FRONTMATTER = re.compile(
    r"---\s+(?:title|summary|keywords|document_type|category|source_type):.*?\s---(?:\s|$)", re.S)
_LOG_STAMP = re.compile(r"\[(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}(?::\d{2})?\]\s*")


def clean(text: str, limit: int = 160) -> str:
    """One readable line from arbitrary text: no fences, escapes or frontmatter.

    Frontmatter is dropped whether it arrives as a block or flattened onto one
    line ("--- summary: "" keywords: [] ---"), because a retrieval head is
    usually the first 160 characters of a file, and for most files that is
    nothing but metadata.
    """
    text = str(text or "")
    text = _ANSI.sub("", text)
    text = _FENCE.sub("", text).replace("`", "'")
    text = _FRONTMATTER.sub(" ", " ".join(text.split()) + " ")
    text = re.sub(r"(^|\s)#{1,6}\s+", r"\1", text)
    text = _LOG_STAMP.sub("", text)
    text = discord.utils.escape_markdown(" ".join(text.split()), as_needed=True)
    return shorten(text, limit)


def shorten(text: str, limit: int) -> str:
    """Cut at a word boundary with an ellipsis, never mid-word."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:—-")
    return (cut or text[: limit - 1]) + "…"


def box(title: str, description: str = "", color: int = COLOR_INFO,
        footer: Optional[str] = None) -> discord.Embed:
    """An embed in the house style, with every part held inside Discord's limits."""
    embed = discord.Embed(title=shorten(title, TITLE_LIMIT),
                          description=shorten(description, DESCRIPTION_LIMIT) or None,
                          color=color)
    if footer:
        embed.set_footer(text=shorten(footer, 2048))
    return embed


def add_field(embed: discord.Embed, name: str, value: str, inline: bool = False) -> bool:
    """Add a field if there is room. Returns False once the embed is full."""
    if len(embed.fields) >= MAX_FIELDS:
        return False
    embed.add_field(name=shorten(name, FIELD_NAME_LIMIT) or "​",
                    value=shorten(value, FIELD_VALUE_LIMIT) or "​", inline=inline)
    return True


# ── Naming a knowledge-base source ─────────────────────────────────────────

_DATE8 = re.compile(r"(20\d{2})(\d{2})(\d{2})")
_MONTH6 = re.compile(r"(20\d{2})(\d{2})_archive")


def _date_of(name: str) -> str:
    m = _DATE8.search(name)
    if m:
        try:
            d = datetime(int(m[1]), int(m[2]), int(m[3]))
            return f"{d:%b} {d.day}"
        except ValueError:
            pass
    m = _MONTH6.search(name)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), 1).strftime("%b %Y")
        except ValueError:
            pass
    return ""


def describe_source(source: str) -> str:
    """"user_logs/Tenno_Henka_9197…/interactions_202608_archive.md" → "💬 Tenno Henka · chat · Aug 2026".

    `source` is a path relative to knowledge_base, as the retrieval trace
    records it, or an absolute path.
    """
    path = str(source or "").replace("\\", "/")
    if "knowledge_base/" in path:
        path = path.split("knowledge_base/", 1)[1]
    parts = [p for p in path.split("/") if p]
    if not parts:
        return "❔ unknown source"
    name = parts[-1]
    stem = os.path.splitext(name)[0]
    top = parts[0]
    when = _date_of(name)

    def _with(label: str) -> str:
        return f"{label} · {when}" if when else label

    if top == "user_logs" and len(parts) >= 3:
        folder = parts[1]
        forum = folder.startswith("forum_")
        person = folder[len("forum_"):] if forum else folder
        person = person.rsplit("_", 1)[0].replace("_", " ") if "_" in person else person
        where = " (forum)" if forum else ""
        if name == "user_profile.md":
            return f"👤 {person}{where} · profile"
        return _with(f"💬 {person}{where} · chat")
    if top == "news":
        if stem.startswith("tech_digest"):
            return _with("💻 Tech digest")
        return _with("📰 News brief")
    if top == "kaia_dreams":
        return _with("🌙 Dream")
    if top == "books":
        title = stem[len("Book - "):] if stem.startswith("Book - ") else stem
        return f"📖 {shorten(title, 70)}"
    icons = {"wiki": "📚", "troubleshooting": "🛠️", "transcripts": "🎬",
             "documents": "📄", "runtime": "🗂️"}
    # "<Topic> - <Title>" and "Project 1999 Wiki - <Page>": the title is the name.
    title = stem.split(" - ", 1)[1] if " - " in stem else stem
    return f"{icons.get(top, '📄')} {shorten(title.replace('_', ' '), 70)}"


def notice(text: str, error: bool = False, title: str = "") -> discord.Embed:
    """A one-message box: a status line, a refusal, a usage hint.

    The text is ours, not quoted content, so it is not passed through `clean`
    and keeps its inline code; anything interpolated into it from outside
    (an exception, a URL) should be `clean`-ed by the caller.
    """
    return box(title, text, COLOR_ERROR if error else COLOR_INFO)


def clean_block(text: str, limit: int = 3500) -> str:
    """Like `clean`, but keeps line breaks — for a draft or a post shown whole."""
    text = _ANSI.sub("", str(text or ""))
    text = _FENCE.sub("", text).replace("`", "'")
    text = discord.utils.escape_markdown(text, as_needed=True)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
