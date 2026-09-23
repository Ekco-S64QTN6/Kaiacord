"""
!art — Kaia makes a fractal and posts it.

    !art                         whatever she feels like making
    !art <words>                 a piece from a prompt: "!art a lighthouse at the end of the world"
    !art  + an attached image    painted in that picture's colours
    !art mandelbrot | <weirdly.net link>
    !art --seed N --palette NAME reproduce or force a render

She decides the piece before it is drawn (`kaia_art_intent.decide`), titles it,
says what she sees in the result, and remembers having made it.
"""
import asyncio
import io
import json
import time
import uuid
from pathlib import Path

import discord

from utils.commands.embed_style import COLOR_INFO, box, clean, notice
from utils.core.kaia_art import FractalFlameRenderer, parse_mandelbrot_url
from utils.infrastructure.logging.kaia_logger import log_debug, log_error, log_info, log_warning

ART_DIR = Path("memory/art")
COLOR_ART = 0xA78BFA

_last_art_time: dict[int, float] = {}
_COOLDOWN_S = 30
_IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def parse_args(content: str) -> dict:
    """Split `!art ...` into flags, a link, a type and the free-text prompt."""
    args = content.strip().split()[1:]
    out = {"type": "flame", "seed": None, "palette": None, "viewport": None,
           "bad_url": False, "bad_seed": False, "prompt": ""}
    words = []
    i = 0
    while i < len(args):
        raw, arg = args[i], args[i].lower()
        if arg.startswith(("http://", "https://")):
            out["viewport"] = parse_mandelbrot_url(raw)
            if out["viewport"]:
                out["type"] = "mandelbrot"
            else:
                out["bad_url"] = True
        elif arg in ("mandelbrot", "flame") and not words:
            out["type"] = arg
        elif arg in ("--seed", "-s") and i + 1 < len(args):
            i += 1
            try:
                out["seed"] = int(args[i])
            except ValueError:
                out["bad_seed"] = True
        elif arg in ("--palette", "-p") and i + 1 < len(args):
            i += 1
            out["palette"] = args[i].lower()
        else:
            words.append(raw)
        i += 1
    out["prompt"] = " ".join(words)[:300]
    return out


def _title_for(intent, params) -> str:
    if intent is not None and intent.title:
        return intent.title
    if intent is not None and intent.prompt:
        return clean(intent.prompt.lower(), 60)
    if params.get("type") == "mandelbrot":
        return str(params.get("location", "the mandelbrot set"))
    return f"untitled, {intent.feeling}" if intent is not None and intent.feeling else "untitled"


def _footer_for(params) -> str:
    if params.get("type") == "mandelbrot":
        return (f"{params.get('location', '?')} · {params.get('zoom', '?')}x · "
                f"{params.get('max_iter', '?')} iterations · {params.get('palette', '?')} · "
                f"{params.get('render_time_s', '?')}s")
    return (f"{params.get('palette', '?')} · {params.get('symmetry_k', '?')}-fold · "
            f"seed {params.get('seed', '?')} · {params.get('render_time_s', '?')}s")


def _comment_prompt(params, intent, viewport) -> str:
    if params.get("type") == "mandelbrot":
        return (f"you just rendered the mandelbrot set at {params.get('location', 'a location')}, "
                f"magnification {params.get('zoom', 'unknown')}, palette {params.get('palette', 'unknown')}. "
                f"{'the coordinates came from a link someone shared with you. ' if viewport else ''}"
                "describe what you see in it in one or two sentences. be specific and a little strange.")
    shapes = set()
    for t in params.get("transforms", []):
        shapes.update(t.get("variations", []))
    why = ""
    if intent is not None:
        if intent.prompt:
            why += f'someone asked for "{intent.prompt}". '
        if intent.title:
            why += f'you titled it "{intent.title}". '
        if intent.feeling:
            why += f"you made it feeling {intent.feeling}. "
        if intent.lut is not None:
            why += "it is painted in the colours of a picture they sent. "
    return (f"you just made a fractal flame. {why}"
            f"it has {params.get('symmetry_k', '?')}-fold symmetry, shapes: {', '.join(sorted(shapes)) or 'unknown'}, "
            f"palette: {params.get('palette', 'unknown')}. "
            "in one or two sentences, say what you see in it or what you were reaching for. "
            "be specific and a little strange; don't explain the maths.")


async def _comment(ctx, prompt: str) -> str:
    try:
        from utils.infrastructure.gpu.gpu_manager import GPUTaskPriority, chat_options, gpu_memory_manager
        response = await gpu_memory_manager.run_with_gpu_guard(
            model_name=ctx.config.chat_model,
            priority=GPUTaskPriority.CHAT,
            coro=asyncio.wait_for(
                ctx.ollama_client.chat(
                    model=ctx.config.chat_model,
                    messages=[{"role": "system", "content": "you are kaia. lowercase only. one or two sentences max. no asterisks."},
                              {"role": "user", "content": prompt}],
                    options=chat_options(num_predict=90),
                    keep_alive=-1),
                timeout=15.0),
            task_id=f"art_comment_{uuid.uuid4().hex[:8]}")
        return response["message"]["content"].strip().replace("*", "")
    except Exception as e:
        log_warning(f"[art] comment generation failed (non-fatal): {e}")
        return ""


async def _image_palette(msg):
    """The attached picture's colours as a palette, or None."""
    for att in getattr(msg, "attachments", None) or []:
        name = (getattr(att, "filename", "") or "").lower()
        if name.endswith(_IMAGE_TYPES) and getattr(att, "size", 0) <= 12 * 1024 * 1024:
            try:
                from utils.core.kaia_art_intent import palette_from_image
                data = await att.read()
                return await asyncio.to_thread(palette_from_image, data)
            except Exception as e:
                log_warning(f"[art] couldn't read the attached image: {e}")
    return None


def _save(image, params, intent) -> None:
    """Keep the piece and what went into it. Blocking."""
    from utils.core.atomic_write import write_atomic
    ART_DIR.mkdir(parents=True, exist_ok=True)
    file_id = uuid.uuid4().hex[:12]
    image.save(str(ART_DIR / f"{file_id}.png"), format="PNG")
    write_atomic(ART_DIR / f"{file_id}.json", json.dumps(params, indent=2, default=str))


async def handle_art_command(ctx, msg, send_kaia_response):
    """Handle !art — decide, render, title, comment, post, remember."""
    channel_id = msg.channel.id
    now = time.time()
    if now - _last_art_time.get(channel_id, 0) < _COOLDOWN_S:
        await msg.channel.send(embed=notice("still cooling down from the last one."))
        return
    _last_art_time[channel_id] = now

    opts = parse_args(msg.content)
    if opts["bad_seed"]:
        await msg.channel.send(embed=notice("seed needs to be a number.", error=True))
        return
    if opts["bad_url"] and not opts["viewport"]:
        await msg.channel.send(embed=notice(
            "i can read a weirdly.net mandelbrot link — the `?config=v1,x,y,...` kind. "
            "that one i couldn't parse, so i'm making my own."))

    placeholder = None
    try:
        placeholder = await msg.channel.send(embed=notice("thinking about what to make..."))
    except Exception:
        pass

    intent = None
    renderer = FractalFlameRenderer()
    try:
        if opts["type"] == "mandelbrot":
            kwargs = {"seed": opts["seed"], "palette_name": opts["palette"]}
            if opts["viewport"]:
                v = opts["viewport"]
                kwargs.update(center=v["center"], span=v["span"], max_iter=v["max_iter"],
                              location_name="shared coordinates")
            image, params = await asyncio.to_thread(renderer.generate_mandelbrot, **kwargs)
        else:
            from utils.core.kaia_art_intent import decide
            lut = await _image_palette(msg)
            intent = await decide(opts["prompt"], ctx=ctx, image_lut=lut)
            log_info(f"[art] intent ({intent.chosen_by}): title={intent.title!r} "
                     f"palette={intent.palette or ('image' if intent.lut is not None else '-')} "
                     f"symmetry={intent.symmetry} shapes={intent.shapes} complexity={intent.complexity}")
            if placeholder:
                try:
                    await placeholder.edit(embed=notice(
                        f"making *{clean(intent.title, 80)}*..." if intent.title else "drawing it..."))
                except Exception:
                    pass
            image, params = await asyncio.to_thread(
                renderer.generate, seed=opts["seed"], palette_name=opts["palette"], intent=intent)
    except Exception as e:
        log_error(f"[art] Render failed: {e}")
        await msg.channel.send(embed=notice("something went wrong rendering. try again?", error=True))
        if placeholder:
            try: await placeholder.delete()
            except Exception: pass
        return

    try:
        from utils.core.kaia_desires import desire_engine
        desire_engine.observe_creation()
    except Exception:
        pass

    try:
        await asyncio.to_thread(_save, image, params, intent)
    except Exception as e:
        log_warning(f"[art] Failed to save art to disk: {e}")

    comment = await _comment(ctx, _comment_prompt(params, intent, opts["viewport"]))
    title = _title_for(intent, params)

    try:
        buf = io.BytesIO()
        await asyncio.to_thread(image.save, buf, "PNG")
        buf.seek(0)
        embed = box(f"🎨  {clean(title, 200)}", clean(comment, 900) if comment else "",
                    COLOR_ART, footer=_footer_for(params))
        embed.set_image(url="attachment://kaia_art.png")
        await msg.channel.send(embed=embed, file=discord.File(buf, filename="kaia_art.png"))
    except discord.errors.DiscordServerError as e:
        log_warning(f"[art] Discord server error posting art: {e}")
        await msg.channel.send(embed=notice("discord choked on the upload. it's saved locally though.", error=True))
    except Exception as e:
        log_error(f"[art] Failed to post art to Discord: {e}")
        await msg.channel.send(embed=notice("couldn't post the image. something broke.", error=True))
    else:
        from utils.core.kaia_expression import remember
        asked = f' for "{intent.prompt}"' if intent is not None and intent.prompt else ""
        remember("art", f'[i made a piece called "{title}"{asked}. {comment}]'.strip(),
                 channel_id=channel_id, title=title,
                 detail={"seed": params.get("seed"), "palette": params.get("palette"),
                         "requested_by": getattr(msg.author, "display_name", "")})
        log_debug(f"[art] posted '{title}'")

    if placeholder:
        try:
            await placeholder.delete()
        except Exception:
            pass
