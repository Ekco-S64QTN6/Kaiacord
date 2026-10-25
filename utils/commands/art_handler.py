"""
!art — Kaia makes a fractal and posts it.

    !art                         whatever she feels like making
    !art <words>                 a piece from a prompt: "!art a lighthouse at the end of the world"
    !art  + an attached image    painted in that picture's colours
    !art loop [<words>]          the piece as a rotating loop, the way Electric Sheep plays
    !art mandelbrot | <weirdly.net link>
    !art --seed N --palette NAME reproduce or force a render

    !art breed [a] [b] [words]   a child of two sheep (hers or the flock's); named or her pick
    !art mutate [a] [words]      a mutation of one sheep
    !art morph [a] [b]           one sheep turning into another, the screensaver's transition
    !art sheep <a> [loop]        one sheep by name: kaia.3 / k3, a flock number (541), or `last`
    !art flock                   her own sheep, the most loved, and how to vote
    !art help                    all of this, in the channel

Every child she breeds or mutates joins her own flock (`kaia_flock`). 👍 / 👎
on a posted piece is a vote for the sheep in it, the way Electric Sheep's
viewers steer the flock: liked sheep are picked and bred more, and a sheep
voted down to `kaia_flock.CULL_AT` is never used again.

Flames are Electric Sheep genomes rendered by flam3 (`kaia_sheep`); the
prompt's colour and complexity words pick the sheep, and she sometimes breeds
two into one of her own. Without flam3 or a flock it falls back to the old
NumPy renderer (`kaia_art.FractalFlameRenderer`). Every sheep is credited:
CC BY-NC, https://electricsheep.org/license/.

She decides the piece before it is drawn (`kaia_art_intent.decide`), titles it,
says what she sees in the result, and remembers having made it.
"""
import asyncio
import base64
import io
import json
import re
import time
import uuid
from pathlib import Path
from typing import Optional

import discord

from utils.commands.embed_style import add_field, box, clean, notice
from utils.core.kaia_art import FractalFlameRenderer, parse_mandelbrot_url
from utils.infrastructure.logging.kaia_logger import log_debug, log_error, log_info, log_warning

ART_DIR = Path("memory/art")
COLOR_ART = 0xA78BFA

_last_art_time: dict[int, float] = {}
_COOLDOWN_S = 30
_IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".gif")


#: The first word that makes `!art` something other than her pick.
ACTIONS = {"breed": "breed", "cross": "breed", "mutate": "mutate", "morph": "morph",
           "transition": "morph", "sheep": "sheep", "flock": "flock", "help": "help"}
#: How a sheep is named after an action: kaia.3 / k3, a flock number, a full name, or `last`.
SHEEP_TOKEN = re.compile(r"^(kaia\.\d+|k\d+|\d{1,5}|electricsheep\.\d+\.\d+|last)$", re.I)


def parse_args(content: str) -> dict:
    """Split `!art ...` into an action, sheep named for it, flags, a link, a
    type and the free-text prompt."""
    args = content.strip().split()[1:]
    out = {"type": "flame", "seed": None, "palette": None, "viewport": None,
           "bad_url": False, "bad_seed": False, "prompt": "", "loop": False,
           "action": "pick", "names": []}
    words = []
    i = 0
    if args and args[0].lower() in ("loop", "animate", "animated", "video", "--loop") \
            and len(args) > 1 and args[1].lower() in ACTIONS:
        out["loop"] = True
        i = 1
    if i < len(args) and args[i].lower() in ACTIONS:
        out["action"] = ACTIONS[args[i].lower()]
        i += 1
        while i < len(args) and (SHEEP_TOKEN.match(args[i]) or args[i].lower() in ("loop", "--loop")):
            if SHEEP_TOKEN.match(args[i]):
                out["names"].append(args[i])
            else:
                out["loop"] = True
            i += 1
    while i < len(args):
        raw, arg = args[i], args[i].lower()
        if arg.startswith(("http://", "https://")):
            out["viewport"] = parse_mandelbrot_url(raw)
            if out["viewport"]:
                out["type"] = "mandelbrot"
            else:
                out["bad_url"] = True
        elif arg in ("mandelbrot", "flame") and not words and out["action"] == "pick":
            out["type"] = arg
        elif arg in ("loop", "animate", "animated", "video", "--loop") and not words:
            out["loop"] = True
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
    if params.get("type") == "sheep":
        # The licence asks for the credit, a link and the sheep's number.
        return f"{params.get('credit', '')} · {params.get('render_time_s', '?')}s"
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
    if params.get("type") == "sheep":
        why = ""
        if intent is not None:
            if intent.prompt:
                why += f'someone asked for "{intent.prompt}". '
            elif getattr(intent, "about", ""):
                why += f"you made it about {intent.about}. "
            if intent.title:
                why += f'you titled it "{intent.title}". '
            if intent.lut is not None:
                why += "you repainted it in the colours of a picture they sent. "
        bred = _how_made(params)
        moving = ("it is a loop that turns slowly. " if params.get("frames") and params.get("action") != "morph"
                  else "")
        return (f"you just made this — the picture is attached; look at it. {bred}{moving}{why}"
                "in one or two sentences, say what you actually see in it and what it has to do with "
                "what you made it about. be specific and a little strange; don't explain the maths.")
    shapes = set()
    for t in params.get("transforms", []):
        shapes.update(t.get("variations", []))
    why = ""
    if intent is not None:
        if intent.prompt:
            why += f'someone asked for "{intent.prompt}". '
        elif getattr(intent, "about", ""):
            why += f"you made it about {intent.about}. "
        if intent.title:
            why += f'you titled it "{intent.title}". '
        if intent.feeling:
            why += f"you made it feeling {intent.feeling}. "
        if intent.lut is not None:
            why += "it is painted in the colours of a picture they sent. "
    before = ""
    try:
        from utils.core.kaia_art_intent import recent_art
        said = [r["summary"].strip("[]") for r in recent_art(3) if r.get("summary")]
        if said:
            before = ("how you described your last pieces, so this one isn't another of them: "
                      + " / ".join(f'"{x[:160]}"' for x in said) + ". ")
    except Exception:
        pass
    return (f"you just made this fractal flame — the picture is attached; look at it. {why}"
            f"it has {params.get('symmetry_k', '?')}-fold symmetry, palette: {params.get('palette', 'unknown')}. "
            f"{before}"
            "in one or two sentences, say what you actually see in it and what it has to do with what you made "
            "it about. be specific and a little strange; don't explain the maths.")


def _how_made(params) -> str:
    """What she did to make a sheep piece, for her comment."""
    name, parents = params.get("name", ""), params.get("sheep", [])
    action = params.get("action")
    if action == "morph":
        a, b = (parents + ["one sheep", "another"])[:2]
        return (f"it is a transition, {a} turning into {b} — the way the electric sheep screensaver "
                "moves from one sheep to the next; the picture is the moment halfway. ")
    if params.get("method") == "mutated":
        return f"you mutated {parents[0]} into a new sheep of your own, {name}. "
    if params.get("bred"):
        return f"you bred it yourself from {' and '.join(parents)}; it is {name} in your own flock now. "
    if name.startswith("kaia."):
        return f"it is {name}, one of the sheep you bred. "
    return "you picked it from the electric sheep flock. "


def _vision_b64(image) -> Optional[str]:
    """The rendered piece as base64 PNG at the vision encoder's size (896 px):
    the commentary asked her what she saw in a picture she was never shown."""
    try:
        im = image.convert("RGB")
        im.thumbnail((896, 896))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        log_warning(f"[art] couldn't prepare the piece for her to look at: {e}")
        return None


async def _comment(ctx, prompt: str, image=None) -> str:
    try:
        from utils.infrastructure.gpu.gpu_manager import GPUTaskPriority, chat_options, gpu_memory_manager
        user = {"role": "user", "content": prompt}
        if image is not None:
            b64 = await asyncio.to_thread(_vision_b64, image)
            if b64:
                user["images"] = [b64]
        response = await gpu_memory_manager.run_with_gpu_guard(
            model_name=ctx.config.chat_model,
            priority=GPUTaskPriority.CHAT,
            coro=asyncio.wait_for(
                ctx.ollama_client.chat(
                    model=ctx.config.chat_model,
                    messages=[{"role": "system", "content": "you are kaia. lowercase only. one or two sentences max. no asterisks."},
                              user],
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


def _save(image, params, intent, video: Optional[Path] = None) -> None:
    """Keep the piece and what went into it. Blocking."""
    import shutil
    from utils.core.atomic_write import write_atomic
    ART_DIR.mkdir(parents=True, exist_ok=True)
    file_id = uuid.uuid4().hex[:12]
    image.save(str(ART_DIR / f"{file_id}.png"), format="PNG")
    if video is not None and video.exists():
        shutil.copyfile(video, ART_DIR / f"{file_id}.mp4")
    write_atomic(ART_DIR / f"{file_id}.json", json.dumps(params, indent=2, default=str))


#: One flam3 render at a time: it uses every core but two, and a second
#: render alongside would only make both slower.
_render_lock = asyncio.Lock()


async def _open_voting(posted, channel_id: int, names: list) -> None:
    """Remember which sheep the post shows and put the vote buttons under it."""
    from utils.core import kaia_flock
    try:
        await asyncio.to_thread(kaia_flock.record_post, posted.id, channel_id, names)
        for emoji in (kaia_flock.UP, kaia_flock.DOWN):
            await posted.add_reaction(emoji)
    except Exception as e:
        log_warning(f"[art] couldn't open voting on {names}: {e}")


def _sheep_ready() -> bool:
    try:
        from utils.core import kaia_sheep
        return kaia_sheep.available()
    except Exception as e:
        log_warning(f"[art] electric sheep unavailable: {e}")
        return False


#: !help's "Music & art" section and `!art help` both show these.
ART_HELP = (
    "`!art` her choice · `!art a cold storm over the sea` from your words\n"
    "`!art loop deep ocean` a 4-second loop (about 30 s to make)\n"
    "attach a picture to paint it in that picture's colours · `!art mandelbrot`")
FLOCK_HELP = (
    "Electric Sheep evolves by votes, and so does hers. Every sheep she breeds or mutates is kept "
    "as her own — `kaia.1`, `kaia.2`… — with its parents and the Electric Sheep it descends from.\n"
    "`!art breed` two of her choosing · `!art breed 541 k3` two you name\n"
    "`!art mutate last` a mutation of the last piece here\n"
    "`!art morph k2 k5` one sheep turning into another, the screensaver's transition\n"
    "`!art sheep k3 loop` any sheep by name · `!art flock` hers and the most loved\n"
    "name a sheep as `kaia.3` / `k3`, a flock number (`541`), or `last`\n"
    "👍 / 👎 under any piece is a vote: loved sheep are picked and bred more; "
    "one voted down to −2 leaves the flock for good")


def help_embed() -> discord.Embed:
    from utils.core.kaia_art import PALETTES
    embed = box("🎨  !art", "Kaia makes Electric Sheep — real flock genomes, rendered by flam3.",
                COLOR_ART, footer="artwork by Scott Draves and the Electric Sheep · electricsheep.org")
    add_field(embed, "Art", ART_HELP + "\ncolour words pick the sheep: " + " ".join(f"`{p}`" for p in PALETTES))
    add_field(embed, "Kaia's flock", FLOCK_HELP)
    return embed


def flock_embed() -> discord.Embed:
    """Her own sheep, the most loved, and how to breed and vote."""
    from utils.core import kaia_flock, kaia_sheep
    mine, theirs, table = kaia_flock.hers(), kaia_sheep.flock(), kaia_flock.scores()
    culled = sum(1 for n in table if kaia_flock.culled(n, table))
    embed = box("🐑  kaia's flock",
                f"{len(mine)} of her own · {len(theirs)} electric sheep · {culled} voted out",
                COLOR_ART, footer=kaia_sheep.CREDIT)

    def line(n):
        e = mine.get(n)
        how = f" · {e.get('method', 'bred')} from {' × '.join(e.get('parents', []))}" if e else ""
        votes = table.get(n, 0)
        return f"`{n}`{f' {votes:+d}' if votes else ''}{how}"
    loved = [n for n, v in sorted(table.items(), key=lambda kv: -kv[1]) if v > 0][:6]
    if loved:
        add_field(embed, "Most loved", "\n".join(line(n) for n in loved))
    newest = sorted(mine, key=lambda n: -mine[n].get("born", 0))[:6]
    if newest:
        add_field(embed, "Newest of hers", "\n".join(f"{line(n)} · gen {mine[n].get('depth', 1)}" for n in newest))
    add_field(embed, "Breeding", (
        "`!art breed` two of her choosing · `!art breed 541 k3` two you name\n"
        "`!art mutate last` change the last one · `!art morph k2 k5` one into another\n"
        "`!art sheep k3 loop` one sheep, moving · 👍 / 👎 on any piece is a vote"))
    return embed


def install_vote_listener(bot) -> None:
    """👍 / 👎 on a posted sheep is a vote for it (`kaia_flock.vote`)."""
    from utils.core import kaia_flock

    async def on_vote(payload, add: bool):
        try:
            if bot.user is not None and payload.user_id == bot.user.id:
                return
            emoji = str(payload.emoji)
            if emoji not in (kaia_flock.UP, kaia_flock.DOWN):
                return
            counted = await asyncio.to_thread(kaia_flock.vote, payload.message_id, payload.user_id, emoji, add)
            for name, score in counted:
                log_info(f"[art] vote {emoji}{'' if add else ' taken back'} on {name}: now {score:+d}"
                         + (" — voted out of the flock" if score <= kaia_flock.CULL_AT else ""))
        except Exception as e:
            log_warning(f"[art] couldn't count a vote: {e}")

    async def on_raw_reaction_add(payload):
        await on_vote(payload, True)

    async def on_raw_reaction_remove(payload):
        await on_vote(payload, False)
    bot.add_listener(on_raw_reaction_add, "on_raw_reaction_add")
    bot.add_listener(on_raw_reaction_remove, "on_raw_reaction_remove")


_PLACEHOLDER = {
    "breed": "breeding {names}...", "mutate": "mutating {names}...",
    "morph": "turning {names} — about a minute...", "sheep": "drawing {names}...",
}


async def handle_art_command(ctx, msg, send_kaia_response):
    """Handle !art — decide, render, title, comment, post, remember."""
    channel_id = msg.channel.id
    opts = parse_args(msg.content)
    # Reading the help or the flock renders nothing, so it neither waits for
    # the cooldown nor starts it.
    if opts["action"] == "help":
        await msg.channel.send(embed=help_embed())
        return
    if opts["action"] == "flock":
        await msg.channel.send(embed=await asyncio.to_thread(flock_embed))
        return
    now = time.time()
    if now - _last_art_time.get(channel_id, 0) < _COOLDOWN_S:
        await msg.channel.send(embed=notice("still cooling down from the last one."))
        return
    _last_art_time[channel_id] = now
    names: list = []
    if opts["action"] != "pick":
        if not _sheep_ready():
            await msg.channel.send(embed=notice("breeding needs flam3 and the sheep flock.", error=True))
            return
        from utils.core import kaia_flock
        for token in opts["names"]:
            name = await asyncio.to_thread(kaia_flock.resolve, token, channel_id)
            if not name:
                await msg.channel.send(embed=notice(
                    f"i don't know a sheep called `{clean(token, 40)}` — `!art flock` lists mine.", error=True))
                return
            names.append(name)
        if opts["action"] == "sheep" and not names:
            await msg.channel.send(embed=notice("which sheep? `!art sheep k3`, `!art sheep 541` or `!art sheep last`."))
            return
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
    video = None
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
            intent = await decide(opts["prompt"], ctx=ctx, image_lut=lut, channel_id=channel_id)
            log_info(f"[art] intent ({intent.chosen_by}): title={intent.title!r} "
                     f"palette={intent.palette or ('image' if intent.lut is not None else '-')} "
                     f"symmetry={intent.symmetry} shapes={intent.shapes} complexity={intent.complexity}")
            if placeholder:
                text = (_PLACEHOLDER[opts["action"]].format(names=" × ".join(names) or "two of the flock")
                        if opts["action"] in _PLACEHOLDER
                        else f"making *{clean(intent.title, 80)}*..." if intent.title else "drawing it...")
                try:
                    await placeholder.edit(embed=notice(text))
                except Exception:
                    pass
            if _sheep_ready():
                from utils.core import kaia_sheep
                if opts["palette"]:
                    intent.palette = opts["palette"]
                if opts["loop"] and placeholder:
                    try:
                        await placeholder.edit(embed=notice(
                            f"rendering *{clean(intent.title, 80) or 'it'}* as a loop — about a minute..."))
                    except Exception:
                        pass
                async with _render_lock:
                    image, video, params = await asyncio.to_thread(
                        kaia_sheep.make, intent, seed=opts["seed"], lut=intent.lut, loop=opts["loop"],
                        action=opts["action"], names=names)
            else:
                if opts["loop"]:
                    await msg.channel.send(embed=notice(
                        "loops need flam3 and the sheep flock — making a still instead."))
                image, params = await asyncio.to_thread(
                    renderer.generate, seed=opts["seed"], palette_name=opts["palette"], intent=intent)
    except Exception as e:
        log_error(f"[art] Render failed: {e}")
        why = (f"{e}. try other sheep?" if opts["action"] in ("breed", "mutate") and "survived" in str(e)
               else "something went wrong rendering. try again?")
        await msg.channel.send(embed=notice(why, error=True))
        if placeholder:
            try: await placeholder.delete()
            except Exception: pass
        return

    try:
        await asyncio.to_thread(_save, image, params, intent, video)
    except Exception as e:
        log_warning(f"[art] Failed to save art to disk: {e}")

    comment = await _comment(ctx, _comment_prompt(params, intent, opts["viewport"]), image)
    title = _title_for(intent, params)

    try:
        embed = box(f"🎨  {clean(title, 200)}", clean(comment, 900) if comment else "",
                    COLOR_ART, footer=_footer_for(params))
        if video is not None:
            # An embed cannot hold a video; the MP4 goes alongside and plays inline.
            posted = await msg.channel.send(embed=embed, file=discord.File(str(video), filename="kaia_art.mp4"))
        else:
            buf = io.BytesIO()
            await asyncio.to_thread(image.save, buf, "PNG")
            buf.seek(0)
            embed.set_image(url="attachment://kaia_art.png")
            posted = await msg.channel.send(embed=embed, file=discord.File(buf, filename="kaia_art.png"))
    except discord.errors.DiscordServerError as e:
        log_warning(f"[art] Discord server error posting art: {e}")
        await msg.channel.send(embed=notice("discord choked on the upload. it's saved locally though.", error=True))
    except Exception as e:
        log_error(f"[art] Failed to post art to Discord: {e}")
        await msg.channel.send(embed=notice("couldn't post the image. something broke.", error=True))
    else:
        if params.get("type") == "sheep" and params.get("shown"):
            await _open_voting(posted, channel_id, params["shown"])
        from utils.core.kaia_expression import remember
        asked = f' for "{intent.prompt}"' if intent is not None and intent.prompt else ""
        remember("art", f'[i made a piece called "{title}"{asked}. {comment}]'.strip(),
                 channel_id=channel_id, title=title,
                 detail={"seed": params.get("seed"), "palette": params.get("palette"),
                         "sheep": params.get("shown"),
                         "requested_by": getattr(msg.author, "display_name", "")})
        log_debug(f"[art] posted '{title}'")

    if placeholder:
        try:
            await placeholder.delete()
        except Exception:
            pass
    if video is not None:
        try:
            video.unlink()
        except OSError:
            pass
