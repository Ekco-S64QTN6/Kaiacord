"""
YouTube Transcript Command
==========================

!youtube <url> — pull a video's transcript and stage it for the knowledge base.

Open to everyone, and staged rather than filed directly, for the same reason
`!download` is: the document lands in `knowledge_base/_ingress/`, which the RAG
indexer skips, so nothing a user submits is retrievable until the hourly ingest
pass has processed it.

The conversion itself lives in `tools/maintenance/youtube_to_kb_md.py` so the
same code serves the command, the CLI and `kaia-tools.sh`.
"""
import asyncio
import json
import time
from pathlib import Path

from utils.infrastructure.logging.kaia_logger import log_action, log_error, log_warning

INGRESS = Path("knowledge_base/_ingress")

# Fetching a two-hour transcript is a few seconds of network; cap it so a
# hung request cannot occupy the worker thread indefinitely.
FETCH_TIMEOUT_S = 90

# Per-channel cooldown. A transcript is cheap for us and expensive for
# YouTube; this also stops one user filling the ingress queue.
_COOLDOWN_S = 20
_last_used: dict[int, float] = {}


async def handle_youtube_command(ctx, msg, send_kaia_response):
    """Handle !youtube <url>."""
    parts = msg.content.strip().split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await msg.channel.send(
            "```\nusage: !youtube <url>\n"
            "pulls the transcript and queues it for the knowledge base\n```"
        )
        return

    now = time.time()
    if now - _last_used.get(msg.channel.id, 0.0) < _COOLDOWN_S:
        await send_kaia_response(msg.channel, "give it a second.")
        return
    _last_used[msg.channel.id] = now

    url = parts[1].strip().split()[0]

    from tools.maintenance.youtube_to_kb_md import (
        YouTubeError, convert, extract_video_id, safe_filename,
    )

    # Validate before promising anything — a bad link should not cost a
    # placeholder message and a typing indicator.
    try:
        video_id = extract_video_id(url)
    except YouTubeError as e:
        await msg.channel.send(f"```\n{e}\n```")
        return

    placeholder = None
    try:
        placeholder = await msg.channel.send("pulling the transcript...")
    except Exception:
        pass

    try:
        # Network and text processing, off the event loop.
        markdown, stats = await asyncio.wait_for(
            asyncio.to_thread(convert, video_id), timeout=FETCH_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        await _fail(msg, placeholder, "that took too long. try again in a bit.")
        return
    except YouTubeError as e:
        await _fail(msg, placeholder, str(e))
        return
    except Exception as e:
        log_error(f"[youtube] {type(e).__name__}: {e}")
        await _fail(msg, placeholder, "something went wrong pulling that transcript.")
        return

    try:
        INGRESS.mkdir(parents=True, exist_ok=True)
        path = INGRESS / safe_filename(stats["title"])
        n = 2
        while path.exists():
            path = INGRESS / safe_filename(f"{stats['title']} ({n})")
            n += 1
        path.write_text(markdown, encoding="utf-8")

        # preformatted: the converter already produced knowledge-base Markdown
        # with frontmatter, headings and timestamp anchors. Running the ingress
        # normaliser over it would reflow the paragraphs and destroy them.
        path.with_suffix(".meta.json").write_text(json.dumps({
            "title": stats["title"],
            "author": stats.get("channel", ""),
            "source_url": stats["url"],
            "submitted_by": msg.author.display_name,
            "submitted_by_id": str(msg.author.id),
            "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "folder": "transcripts",
            "category": "Transcript",
            "document_type": "video_transcript",
            "content_type": "youtube",
            "preformatted": True,
        }, indent=2), encoding="utf-8")
    except Exception as e:
        log_error(f"[youtube] staging failed: {e}")
        await _fail(msg, placeholder, "got the transcript but couldn't stage it.")
        return

    if placeholder:
        try:
            await placeholder.delete()
        except Exception:
            pass

    total = int(stats["duration_seconds"])
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    length = f"{hours}h{minutes:02d}m" if hours else f"{minutes}m{seconds:02d}s"

    lines = [
        "staged for the knowledge base.",
        f"  {stats['title'][:70]}",
    ]
    if stats.get("channel"):
        lines.append(f"  channel: {stats['channel']}")
    lines += [
        f"  length: {length}   words: ~{stats['words']:,}",
        f"  destination: knowledge_base/transcripts",
        "",
        "it gets filed on the next ingest pass (hourly).",
    ]
    await msg.channel.send("```\n" + "\n".join(lines) + "\n```")
    log_action(
        f"Staged YouTube transcript {stats['url']} "
        f"({stats['words']} words) by {msg.author.display_name}"
    )


async def _fail(msg, placeholder, text: str):
    if placeholder:
        try:
            await placeholder.delete()
        except Exception:
            pass
    try:
        await msg.channel.send(f"```\n{text}\n```")
    except Exception:
        log_warning(f"[youtube] could not report failure: {text}")
