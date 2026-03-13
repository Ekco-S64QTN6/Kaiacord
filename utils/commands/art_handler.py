"""
Kaia Art Command Handler
Handles !art command — generates fractal flames and posts them to Discord.
"""
import asyncio
import io
import json
import time
import uuid
import re
from pathlib import Path

import discord

from utils.infrastructure.logging.kaia_logger import log_info, log_debug, log_warning, log_error
from utils.core.kaia_art import FractalFlameRenderer

ART_DIR = Path("memory/art")

# Rate limiting: channel_id → timestamp
_last_art_time: dict[int, float] = {}
_COOLDOWN_S = 30


async def handle_art_command(ctx, msg, send_kaia_response):
    """Handle !art command — generate fractal flame and post to Discord."""
    channel_id = msg.channel.id

    # ── Rate limiting ─────────────────────────────────────────────────────────
    now = time.time()
    if now - _last_art_time.get(channel_id, 0) < _COOLDOWN_S:
        await send_kaia_response(msg.channel, "still cooling down from the last one.")
        return
    _last_art_time[channel_id] = now

    # ── Parse arguments ───────────────────────────────────────────────────────
    content = msg.content.strip()
    args = content.split()

    art_type = "flame"      # default
    seed = None
    palette_name = None

    i = 1  # skip "!art"
    while i < len(args):
        arg = args[i].lower()

        if arg == "mandelbrot":
            art_type = "mandelbrot"
        elif arg == "flame":
            art_type = "flame"
        elif arg in ("--seed", "-s") and i + 1 < len(args):
            i += 1
            try:
                seed = int(args[i])
            except ValueError:
                await send_kaia_response(msg.channel, "seed needs to be a number.")
                return
        elif arg in ("--palette", "-p") and i + 1 < len(args):
            i += 1
            palette_name = args[i].lower()

        i += 1

    # ── Send placeholder ──────────────────────────────────────────────────────
    placeholder = None
    try:
        placeholder = await msg.channel.send("generating...")
    except Exception:
        pass

    # ── Render ────────────────────────────────────────────────────────────────
    renderer = FractalFlameRenderer()
    try:
        if art_type == "mandelbrot":
            image, params = await asyncio.to_thread(
                renderer.generate_mandelbrot, seed=seed, palette_name=palette_name
            )
        else:
            image, params = await asyncio.to_thread(
                renderer.generate, seed=seed, palette_name=palette_name
            )
    except Exception as e:
        log_error(f"[art] Render failed: {e}")
        await send_kaia_response(msg.channel, "something went wrong rendering. try again?")
        if placeholder:
            try: await placeholder.delete()
            except Exception: pass
        return

    # ── Save to disk ──────────────────────────────────────────────────────────
    ART_DIR.mkdir(parents=True, exist_ok=True)
    file_id = uuid.uuid4().hex[:12]
    img_path = ART_DIR / f"{file_id}.png"
    json_path = ART_DIR / f"{file_id}.json"

    try:
        image.save(str(img_path), format="PNG")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(params, f, indent=2)
        log_debug(f"[art] Saved to {img_path}")
    except Exception as e:
        log_warning(f"[art] Failed to save art to disk: {e}")

    # ── Generate Kaia's comment via Ollama ────────────────────────────────────
    comment = ""
    try:
        variations_used = set()
        for t in params.get("transforms", []):
            for v in t.get("variations", []):
                variations_used.add(v)

        comment_prompt = (
            f"you just generated a fractal flame image. "
            f"it used {params.get('n_transforms', '?')} transforms, "
            f"variations: {', '.join(variations_used) if variations_used else 'unknown'}, "
            f"palette: {params.get('palette', 'unknown')}. "
            f"describe what you see in it in one or two sentences. "
            f"be specific and a little strange. no 'it is a fractal' — you know what it is. "
            f"speak as kaia. lowercase only. no asterisks."
        )

        if params.get("type") == "mandelbrot":
            comment_prompt = (
                f"you just generated a mandelbrot zoom image. "
                f"palette: {params.get('palette', 'unknown')}, "
                f"zoom depth: {params.get('zoom', 'unknown')}. "
                f"describe what you see in it in one or two sentences. "
                f"be specific and a little strange. "
                f"speak as kaia. lowercase only. no asterisks."
            )

        from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
        gpu_mgr = OllamaGPUManager(ctx.config.chat_model)
        options = gpu_mgr.get_gpu_options(for_chat=True)

        response = await asyncio.wait_for(
            ctx.ollama_client.chat(
                model=ctx.config.chat_model,
                messages=[
                    {"role": "system", "content": "you are kaia. lowercase only. one or two sentences max."},
                    {"role": "user", "content": comment_prompt}
                ],
                options={**options, "num_predict": 80}
            ),
            timeout=15.0
        )
        comment = response['message']['content'].strip()
        # Strip any asterisks that leaked through
        comment = comment.replace("*", "")
        log_debug(f"[art] Kaia comment: {comment}")

    except Exception as e:
        log_warning(f"[art] Ollama comment generation failed (non-fatal): {e}")
        comment = ""

    # ── Post to Discord ───────────────────────────────────────────────────────
    try:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)

        msg_text = ""
        if comment:
            msg_text = comment

        seed_display = params.get("seed", "?")
        footer = f"`seed: {seed_display} | palette: {params.get('palette', '?')} | {params.get('render_time_s', '?')}s`"

        full_text = f"{msg_text}\n{footer}" if msg_text else footer

        await msg.channel.send(
            content=full_text,
            file=discord.File(buf, filename="kaia_art.png")
        )
    except discord.errors.DiscordServerError as e:
        log_warning(f"[art] Discord server error posting art: {e}")
        await send_kaia_response(msg.channel, "discord choked on the upload. the image was saved locally though.")
    except Exception as e:
        log_error(f"[art] Failed to post art to Discord: {e}")
        await send_kaia_response(msg.channel, "couldn't post the image. something broke.")

    # ── Cleanup placeholder ───────────────────────────────────────────────────
    if placeholder:
        try:
            await placeholder.delete()
        except Exception:
            pass
