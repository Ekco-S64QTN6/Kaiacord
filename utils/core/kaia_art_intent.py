"""What Kaia decides to make before a fractal is drawn.

`!art` used to roll every parameter at random and ask her to caption the
result afterwards — she described art she had no part in. Here she chooses
first: given someone's words, her mood, or a picture, she picks a palette, a
symmetry, the shapes that should lead, how intricate it is, and a title. The
renderer (`kaia_art.FractalFlameRenderer`) then draws the geometry from a seed
under those choices.

Three sources of intent, all reduced to the same `ArtIntent`:

* **her choice** — one short model call that picks from the renderer's own
  menus and returns JSON. Python validates every field and drops anything not
  on a menu; the model never sets a number the renderer computes.
* **words** — a lexicon, so a prompt still steers the piece if the model is
  busy or answers badly.
* **mood** — valence, arousal and social energy mapped onto the same menus,
  for `!art` with nothing else said.

An attached image contributes its colours as a palette of its own.
"""
from __future__ import annotations

import io
import json
import re
from typing import Optional

import numpy as np

from utils.core.kaia_art import (
    COMPLEXITY_TRANSFORMS, PALETTES, PRIMARY_VARIATIONS, SYMMETRIES, ArtIntent,
    _build_lut)

# What each shape looks like, in words she can choose from.
SHAPE_NOTES = {
    "swirl": "a vortex", "spiral": "spiral arms", "julia": "split, mirrored lobes",
    "heart": "heart-shaped folds", "rings": "concentric rings", "waves": "rippling bands",
    "bubble": "soft spheres", "eyefish": "a lens bulge", "curl": "curling tendrils",
    "ngon": "polygonal petals", "disc": "a bright disc", "diamond": "crystal facets",
    "horseshoe": "horseshoe arcs", "polar": "radial streaks", "hyperbolic": "stretched horns",
    "spherical": "an inverted sphere", "sinusoidal": "a woven lattice", "bent": "broken planes",
    "linear": "straight filaments",
}
PALETTE_NOTES = {
    "electric": "violet into neon blue", "ember": "coal red into gold",
    "acid": "toxic green and magenta", "void": "black and deep indigo",
    "aurora": "green and teal lights", "ghost": "pale grey and silver",
    "deep_ocean": "navy into sea green", "solar_flare": "orange and white heat",
    "biolume": "dark water with cyan glow", "nebula": "purple dust and pink",
}

# ── words ────────────────────────────────────────────────────────────────

_PALETTE_WORDS = {
    "ember": "fire flame flames burning burn ember embers coal warm warmth autumn rust blood",
    "solar_flare": "sun sunny sunlight solar gold golden noon summer bright joy joyful",
    "deep_ocean": "ocean sea deep underwater tide tides abyss water drowning",
    "void": "void dark darkness night black empty nothing shadow shadows death grief",
    "ghost": "ghost ghostly pale mist fog snow winter silver memory memories faded",
    "biolume": "glow glowing bioluminescent forest moss jellyfish fungus firefly fireflies",
    "aurora": "aurora northern arctic ice sky dawn calm",
    "electric": "neon electric cyber city lightning circuit signal static",
    "acid": "acid toxic poison rave chaos glitch",
    "nebula": "space nebula cosmic stars star galaxy universe dream dreams dreaming",
}
_SHAPE_WORDS = {
    "spiral": "spiral galaxy shell nautilus", "swirl": "swirl vortex storm whirlpool",
    "heart": "heart love lover loving tender", "rings": "ring rings orbit halo ripple echo",
    "waves": "wave waves sea ocean tide water music", "bubble": "bubble bubbles foam soft",
    "eyefish": "eye eyes lens watching", "curl": "wind smoke hair curl tendril vine",
    "ngon": "flower petal petals star crystal snowflake", "disc": "moon sun disc planet",
    "diamond": "diamond crystal gem shard", "julia": "mirror twin reflection",
    "polar": "radiant burst explosion", "hyperbolic": "horn horns thorn thorns",
    "spherical": "sphere inside inverted hollow", "bent": "broken shattered fracture",
}
_SYMMETRY_WORDS = {
    6: "flower snowflake mandala hexagon honeycomb", 5: "star starfish petal",
    4: "cross compass square window", 3: "triangle trinity triad",
    2: "mirror twin pair butterfly", 8: "octagon wheel",
}
_COMPLEXITY_WORDS = {
    "simple": "simple quiet minimal calm still lonely alone single",
    "intricate": "intricate complex chaos chaotic busy wild storm tangled overwhelming",
}


def _index(table):
    out = {}
    for key, words in table.items():
        for w in words.split():
            out.setdefault(w, key)
    return out


_BY_WORD = {
    "palette": _index(_PALETTE_WORDS), "shape": _index(_SHAPE_WORDS),
    "symmetry": _index(_SYMMETRY_WORDS), "complexity": _index(_COMPLEXITY_WORDS),
}


def from_words(text: str) -> ArtIntent:
    """An intent from someone's prompt, by vocabulary. Empty if nothing matched."""
    words = re.findall(r"[a-z]+", (text or "").lower())
    intent = ArtIntent(prompt=(text or "").strip(), chosen_by="words")
    shapes = []
    for w in words:
        if intent.palette is None and w in _BY_WORD["palette"]:
            intent.palette = _BY_WORD["palette"][w]
        if w in _BY_WORD["shape"] and _BY_WORD["shape"][w] not in shapes:
            shapes.append(_BY_WORD["shape"][w])
        if intent.symmetry is None and w in _BY_WORD["symmetry"]:
            intent.symmetry = _BY_WORD["symmetry"][w]
        if intent.complexity is None and w in _BY_WORD["complexity"]:
            intent.complexity = _BY_WORD["complexity"][w]
    intent.shapes = shapes[:3]
    return intent


# ── mood ─────────────────────────────────────────────────────────────────

def mood() -> dict:
    """Her current state, or a neutral one if the mood system is unavailable."""
    try:
        from utils.core.kaia_mood import emotional_arc
        return {"valence": float(emotional_arc.valence),
                "arousal": float(emotional_arc.arousal),
                "energy": float(emotional_arc.social_energy)}
    except Exception:
        return {"valence": 0.0, "arousal": 0.5, "energy": 0.5}


def feeling_word(m: dict) -> str:
    """One plain word for a mood, used in titles, notes and the prompt."""
    v, a, e = m["valence"], m["arousal"], m["energy"]
    if a > 0.7:
        return "restless" if v < 0 else "wired"
    if e < 0.3:
        return "tired" if v >= 0 else "hollow"
    if v > 0.3:
        return "bright"
    if v < -0.2:
        return "heavy"
    return "calm" if a < 0.4 else "curious"


_MOOD_INTENT = {
    "wired": dict(palette="electric", symmetry=5, shapes=["swirl", "curl"], complexity="intricate"),
    "restless": dict(palette="acid", symmetry=3, shapes=["bent", "polar"], complexity="intricate"),
    "tired": dict(palette="ghost", symmetry=6, shapes=["bubble", "waves"], complexity="simple"),
    "hollow": dict(palette="void", symmetry=4, shapes=["spherical", "rings"], complexity="simple"),
    "bright": dict(palette="solar_flare", symmetry=6, shapes=["heart", "ngon"], complexity="balanced"),
    "heavy": dict(palette="deep_ocean", symmetry=4, shapes=["hyperbolic", "spherical"], complexity="balanced"),
    "calm": dict(palette="aurora", symmetry=6, shapes=["waves", "rings"], complexity="simple"),
    "curious": dict(palette="nebula", symmetry=5, shapes=["spiral", "julia"], complexity="balanced"),
}


def from_mood(m: Optional[dict] = None) -> ArtIntent:
    m = m or mood()
    word = feeling_word(m)
    return ArtIntent(feeling=word, chosen_by="mood", **_MOOD_INTENT[word])


# ── an image's colours ───────────────────────────────────────────────────

def palette_from_image(data: bytes, n_colors: int = 6) -> Optional[np.ndarray]:
    """A 256-entry colour ramp from a picture's dominant colours, dark to light.

    Blocking (PIL decode); call it in a thread.
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((160, 160))
        quant = img.quantize(colors=n_colors, method=Image.Quantize.MEDIANCUT)
        pal = quant.getpalette()[: n_colors * 3]
        counts = sorted(quant.getcolors() or [], reverse=True)
    except Exception:
        return None
    colours = []
    for _count, idx in counts:
        r, g, b = pal[idx * 3: idx * 3 + 3]
        colours.append((r / 255.0, g / 255.0, b / 255.0))
    if len(colours) < 2:
        return None
    # Dark to light, so low density reads as shadow and the dense core as
    # highlight, as in the built-in palettes. A near-black floor keeps the
    # background dark even when the picture has no dark tones.
    colours.sort(key=lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])
    # The picture's hues, but its brightness spread from shadow to highlight:
    # most photos and screenshots sit in the middle of the range, and taken
    # literally they render as murk with no bright core.
    import colorsys
    colours = [colorsys.hsv_to_rgb(h, s, 0.3 + 0.62 * i / (len(colours) - 1))
               for i, (h, s, _v) in enumerate(colorsys.rgb_to_hsv(*c) for c in colours)]
    darkest = tuple(max(0.0, x * 0.15) for x in colours[0])
    stops = [(0.0, *darkest)] + [
        (0.15 + 0.85 * i / (len(colours) - 1), *c) for i, c in enumerate(colours)]
    return _build_lut(stops)


# ── her own choice ───────────────────────────────────────────────────────

def _menu_prompt(prompt: str, m: dict, image: bool) -> str:
    import random
    # Shuffled per call: with a fixed order the first entry of each menu was
    # chosen far more often than anything the prompt asked for.
    shape_items, palette_items = list(SHAPE_NOTES.items()), list(PALETTE_NOTES.items())
    random.shuffle(shape_items)
    random.shuffle(palette_items)
    shapes = ", ".join(f"{k} ({v})" for k, v in shape_items)
    palettes = ", ".join(f"{k} ({v})" for k, v in palette_items)
    asked = (f'someone asked you for a piece: "{prompt}".' if prompt
             else "nobody asked for anything in particular; make what you feel like making.")
    img = " they attached a picture, and its colours will be your palette." if image else ""
    return (
        f"you are about to make a fractal flame. {asked}{img}\n"
        f"right now you feel {feeling_word(m)}. let the subject lead and your mood colour it; "
        f"don't just pick the options that match your mood.\n\n"
        f"choose from these menus only:\n"
        f"palette: {palettes}\n"
        f"shapes (pick 1 to 3): {shapes}\n"
        f"symmetry: one of {', '.join(map(str, SYMMETRIES))} (how many times it repeats around the centre)\n"
        f"complexity: simple, balanced or intricate\n\n"
        'answer with json only: {"title": "...", "palette": "...", "shapes": ["..."], '
        '"symmetry": 5, "complexity": "...", "feeling": "one or two words"}\n'
        "the title is yours: short, lowercase, not a description of the menu choices."
    )


def parse_choice(text: str) -> Optional[ArtIntent]:
    """Her JSON answer as an intent, keeping only values that are on a menu."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    shapes = [s for s in (data.get("shapes") or []) if isinstance(s, str) and s in PRIMARY_VARIATIONS]
    symmetry = data.get("symmetry")
    try:
        symmetry = int(symmetry)
    except (TypeError, ValueError):
        symmetry = None
    title = re.sub(r"[`*_#\n]", "", str(data.get("title") or "")).strip().lower()[:80]
    intent = ArtIntent(
        title=title,
        feeling=re.sub(r"[`*_#\n]", "", str(data.get("feeling") or "")).strip().lower()[:40],
        palette=data.get("palette") if data.get("palette") in PALETTES else None,
        symmetry=symmetry if symmetry in SYMMETRIES else None,
        shapes=shapes[:3],
        complexity=data.get("complexity") if data.get("complexity") in COMPLEXITY_TRANSFORMS else None,
        chosen_by="kaia",
    )
    if not (intent.palette or intent.shapes or intent.symmetry or intent.complexity):
        return None
    return intent


def merge(primary: Optional[ArtIntent], fallback: ArtIntent) -> ArtIntent:
    """Fields from `primary` where it chose, `fallback` elsewhere."""
    if primary is None:
        return fallback
    for name in ("title", "feeling", "palette", "symmetry", "complexity"):
        if not getattr(primary, name) and getattr(fallback, name):
            setattr(primary, name, getattr(fallback, name))
    if not primary.shapes:
        primary.shapes = list(fallback.shapes)
    primary.prompt = primary.prompt or fallback.prompt
    primary.lut = primary.lut if primary.lut is not None else fallback.lut
    return primary


async def decide(prompt: str, *, ctx=None, image_lut=None) -> ArtIntent:
    """Everything that goes into a piece before it is drawn.

    Her choice when the model answers well; the lexicon for anything she left
    open, and her mood for anything the words did not say either.
    """
    m = mood()
    base = merge(from_words(prompt), from_mood(m)) if prompt else from_mood(m)
    base.prompt = prompt or ""

    choice = None
    if ctx is not None and getattr(ctx, "ollama_client", None) is not None:
        choice = await _ask(ctx, prompt, m, image_lut is not None)
    intent = merge(choice, base)
    intent.prompt = prompt or ""
    if image_lut is not None:
        intent.lut = image_lut
        intent.palette = None
        intent.chosen_by = intent.chosen_by if choice else "image"
    return intent


async def _ask(ctx, prompt: str, m: dict, image: bool) -> Optional[ArtIntent]:
    import asyncio
    import uuid
    try:
        from utils.infrastructure.gpu.gpu_manager import GPUTaskPriority, chat_options, gpu_memory_manager
        response = await gpu_memory_manager.run_with_gpu_guard(
            model_name=ctx.config.chat_model,
            priority=GPUTaskPriority.CHAT,
            coro=asyncio.wait_for(
                ctx.ollama_client.chat(
                    model=ctx.config.chat_model,
                    messages=[
                        {"role": "system", "content": "you are kaia, choosing how to make a piece of art. json only."},
                        {"role": "user", "content": _menu_prompt(prompt, m, image)},
                    ],
                    options=chat_options(num_predict=160, temperature=0.9),
                    keep_alive=-1,
                ),
                timeout=20.0),
            task_id=f"art_intent_{uuid.uuid4().hex[:8]}",
        )
        return parse_choice(response["message"]["content"])
    except Exception:
        return None
