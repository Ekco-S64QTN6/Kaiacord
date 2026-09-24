"""
YouTube Transcript Command
==========================

!youtube <url> — pull a video's transcript and stage it for the knowledge base.

Open to everyone, and staged rather than filed directly, for the same reason
`!download` is: the document lands in `knowledge_base/_ingress/`, which the RAG
indexer skips, so nothing a user submits is retrievable until it has been
cleaned and filed — which the command starts straight away.

The conversion itself lives in `tools/maintenance/youtube_to_kb_md.py` so the
same code serves the command, the CLI and `kaia-tools.sh`. Misheard names are
corrected before staging by `tools/maintenance/transcript_names.py`, which also
runs on its own over transcripts already in the corpus.
"""
import asyncio
import json
import time
from pathlib import Path

from utils.infrastructure.logging.kaia_logger import log_action, log_error, log_warning
from utils.core.atomic_write import write_atomic
from utils.commands.embed_style import COLOR_INFO, add_field, box, clean, notice

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
        await msg.channel.send(embed=notice(
            "usage: `!youtube <url>`\npulls the transcript and queues it for the knowledge base"))
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
        await msg.channel.send(embed=notice(clean(str(e), 400), error=True))
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

    # Auto-captions mishear names ("house ATT treaties" for House Atreides), and
    # names are what retrieval keys on. Best effort: a failure here stages the
    # transcript as fetched.
    corrections, counts = {}, {}
    try:
        corrections, counts, markdown = await _correct_names(ctx, markdown, stats, placeholder)
    except Exception as e:
        log_warning(f"[youtube] name correction skipped: {type(e).__name__}: {e}")

    try:
        INGRESS.mkdir(parents=True, exist_ok=True)
        path = INGRESS / safe_filename(stats["title"])
        n = 2
        while path.exists():
            path = INGRESS / safe_filename(f"{stats['title']} ({n})")
            n += 1
        write_atomic(path, markdown)
        # preformatted: the converter already produced knowledge-base Markdown
        # with frontmatter, headings and timestamp anchors. Running the ingress
        # normaliser over it would reflow the paragraphs and destroy them.
        write_atomic(path.with_suffix(".meta.json"), json.dumps({
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
            # What was changed from the captions, so a bad correction can be
            # found and reversed.
            "name_corrections": {h: corrections[h] for h in counts},
        }, indent=2))
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

    embed = box(f"🎬  {clean(stats['title'], 200)}", "staged for the knowledge base.",
                COLOR_INFO, footer="filing it…")
    if stats.get("channel"):
        add_field(embed, "Channel", clean(stats["channel"], 100), inline=True)
    add_field(embed, "Length", length, inline=True)
    add_field(embed, "Words", f"~{stats['words']:,}", inline=True)
    if counts:
        from tools.maintenance.transcript_names import describe
        add_field(embed, "Fixed misheard names", clean(describe(counts, corrections, limit=4), 900))
    reply = await msg.channel.send(embed=embed)
    from utils.core import ingress
    ingress.start_filing(path, reply)
    log_action(
        f"Staged YouTube transcript {stats['url']} "
        f"({stats['words']} words) by {msg.author.display_name}"
    )


async def _correct_names(ctx, markdown: str, stats: dict, placeholder):
    """Fix misheard names through the local model. Returns (glossary, counts, text)."""
    import uuid
    from tools.maintenance.transcript_names import (
        apply_corrections, find_corrections, prose_chunks,
    )
    from utils.infrastructure.gpu.gpu_manager import (
        GPUTaskPriority, chat_options, gpu_memory_manager,
    )

    model = ctx.config.chat_model
    chunks = len(prose_chunks(markdown))
    if placeholder:
        try:
            await placeholder.edit(content=f"checking names in the transcript ({chunks} part(s))...")
        except Exception:
            pass

    async def ask(prompt: str) -> str:
        resp = await gpu_memory_manager.run_with_gpu_guard(
            model_name=model,
            priority=GPUTaskPriority.BACKGROUND,
            coro=asyncio.wait_for(
                ctx.ollama_client.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    options=chat_options(temperature=0.1, num_predict=600),
                    format="json",
                    keep_alive=-1,
                ),
                timeout=120,
            ),
            task_id=f"yt_names_{uuid.uuid4().hex[:8]}",
        )
        return resp["message"]["content"]

    glossary = await find_corrections(markdown, stats["title"], stats.get("channel", ""), ask)
    fixed, counts = apply_corrections(markdown, glossary)
    if counts:
        log_action(f"[youtube] corrected {len(counts)} misheard name(s) in "
                   f"'{stats['title'][:60]}' ({sum(counts.values())} replacements)")
    return glossary, counts, fixed


async def _fail(msg, placeholder, text: str):
    if placeholder:
        try:
            await placeholder.delete()
        except Exception:
            pass
    try:
        await msg.channel.send(embed=notice(text, error=True))
    except Exception:
        log_warning(f"[youtube] could not report failure: {text}")
