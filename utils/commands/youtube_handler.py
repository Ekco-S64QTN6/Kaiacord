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
import threading
import time
from pathlib import Path

from utils.infrastructure.logging.kaia_logger import log_action, log_error, log_warning
from utils.core.atomic_write import write_atomic
from utils.commands.embed_style import COLOR_INFO, add_field, box, clean, notice

INGRESS = Path("knowledge_base/_ingress")
TRANSCRIPTS = Path("knowledge_base/transcripts")


def _already_have(video_id: str):
    """The title of a filed or staged transcript of this video, or None."""
    for folder in (TRANSCRIPTS, INGRESS):
        for f in folder.glob("*.md") if folder.is_dir() else []:
            try:
                if video_id in f.read_text(encoding="utf-8", errors="ignore"):
                    return f.stem.removeprefix("Transcript - ")
            except OSError:
                continue
    return None

# The global command rate limiter is per user; this separate cap protects
# transcript fetches and local correction work across all channels/users.
MAX_CONCURRENT_TRANSCRIPTS = 2
_COOLDOWN_S = 20
_last_used: dict[int, float] = {}
_inflight_lock = threading.Lock()
_inflight_video_ids: set[str] = set()
_inflight_paths: set[Path] = set()


def _reserve_transcript(video_id: str) -> str:
    """Atomically reserve a global job slot and deduplicate an in-flight video."""
    with _inflight_lock:
        if video_id in _inflight_video_ids:
            return "duplicate"
        if len(_inflight_video_ids) >= MAX_CONCURRENT_TRANSCRIPTS:
            return "busy"
        _inflight_video_ids.add(video_id)
        return "reserved"


def _release_transcript(video_id: str) -> None:
    """Release a reservation after every worker and staging step has finished."""
    with _inflight_lock:
        _inflight_video_ids.discard(video_id)


def _reserve_ingress_path(title: str, safe_filename) -> Path:
    """Reserve a collision-free transcript filename across concurrent jobs."""
    with _inflight_lock:
        path = INGRESS / safe_filename(title)
        suffix = 2
        while path.exists() or path in _inflight_paths:
            path = path.with_name(f"{path.stem.rsplit(' (', 1)[0]} ({suffix}){path.suffix}")
            suffix += 1
        _inflight_paths.add(path)
        return path


def _release_ingress_path(path: Path) -> None:
    """Release a filename reservation once its staged document is committed."""
    with _inflight_lock:
        _inflight_paths.discard(path)


def _is_transcript_inflight(video_id: str) -> bool:
    with _inflight_lock:
        return video_id in _inflight_video_ids


async def _run_off_loop(func, /, *args):
    """Run blocking work off-loop, but retain ownership until its thread exits.

    Cancelling asyncio.to_thread() only cancels its awaiter. Shield the worker
    and drain it on cancellation so the caller's reservation cannot be released
    while its network/disk worker is still alive.
    """
    worker = asyncio.create_task(asyncio.to_thread(func, *args))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        try:
            worker.result()
        except Exception:
            pass
        raise


async def handle_youtube_command(ctx, msg, send_kaia_response):
    """Handle !youtube <url> with bot-wide concurrency and in-flight deduplication."""
    parts = msg.content.strip().split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await msg.channel.send(embed=notice(
            "usage: `!youtube <url>`\npulls the transcript and queues it for the knowledge base"))
        return

    now = time.time()
    channel_id = msg.channel.id
    if now - _last_used.get(channel_id, 0.0) < _COOLDOWN_S:
        await msg.channel.send(embed=notice("Give it a second — one transcript at a time here.", error=True))
        return

    url = parts[1].strip().split()[0]
    from tools.maintenance.youtube_to_kb_md import (
        YouTubeError, convert, extract_video_id, safe_filename,
    )

    # Validate before taking a global slot or starting any work.
    try:
        video_id = extract_video_id(url)
    except YouTubeError as e:
        await msg.channel.send(embed=notice(clean(str(e), 400), error=True))
        return

    reservation = _reserve_transcript(video_id)
    if reservation == "duplicate":
        await msg.channel.send(embed=notice(
            "that transcript is already being fetched.", error=True))
        return
    if reservation == "busy":
        await msg.channel.send(embed=notice(
            "already fetching a couple of transcripts. try again in a minute.", error=True))
        return

    _last_used[channel_id] = now
    try:
        await _stage_transcript(ctx, msg, video_id, convert, safe_filename)
    finally:
        # _stage_transcript drains blocking worker threads on cancellation.
        _release_transcript(video_id)


async def _stage_transcript(ctx, msg, video_id: str, convert, safe_filename):
    """Run one admitted transcript job through conversion, correction and staging."""
    from tools.maintenance.youtube_to_kb_md import YouTubeError
    have = await _run_off_loop(_already_have, video_id)
    if have:
        await msg.channel.send(embed=notice(
            f"I already have that one: **{clean(have, 150)}**.", title="🎬  YouTube"))
        return

    placeholder = None
    try:
        placeholder = await msg.channel.send(embed=notice("Pulling the transcript…", title="🎬  YouTube"))
    except Exception:
        pass

    try:
        # The converter injects a requests.Session with finite per-request
        # timeouts. Await the actual thread rather than timing out only its
        # asyncio wrapper and leaving the network worker behind.
        markdown, stats = await _run_off_loop(convert, video_id)
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

    reserved_path = None
    try:
        INGRESS.mkdir(parents=True, exist_ok=True)
        path = _reserve_ingress_path(stats["title"], safe_filename)
        reserved_path = path
        # preformatted: the converter already produced knowledge-base Markdown
        # with frontmatter, headings and timestamp anchors. Running the ingress
        # normaliser over it would reflow the paragraphs and destroy them. So
        # the sidecar lands first: the hourly processor must never find the
        # document without it. Both writes fsync; neither runs on the loop.
        await _run_off_loop(write_atomic, path.with_suffix(".meta.json"), json.dumps({
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
        await _run_off_loop(write_atomic, path, markdown)
    except Exception as e:
        log_error(f"[youtube] staging failed: {e}")
        await _fail(msg, placeholder, "got the transcript but couldn't stage it.")
        return
    finally:
        if reserved_path is not None:
            _release_ingress_path(reserved_path)

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
            await placeholder.edit(embed=notice(f"Checking names in the transcript ({chunks} part(s))…",
                                                title="🎬  YouTube"))
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

    glossary = await find_corrections(markdown, stats["title"], stats.get("channel", ""), ask,
                                      description=stats.get("description", ""))
    fixed, counts = await _run_off_loop(apply_corrections, markdown, glossary)
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
        await msg.channel.send(embed=notice(clean(text, 400), error=True))
    except Exception:
        log_warning(f"[youtube] could not report failure: {text}")
