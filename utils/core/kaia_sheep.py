"""Electric Sheep for !art: real flock genomes rendered by flam3.

The old renderer (`kaia_art.FractalFlameRenderer`) drew 2-4 random affine
transforms with a hue-wheel palette, and it looked like it: the same few
shapes in three or four colours. Electric Sheep's look comes from two things
it did not have: genomes a crowd evolved over years, and flam3, the renderer
that was written for them. This module uses both.

    genomes   memory/art/flock/electricsheep.<gen>.<id>.flam3, fetched from the
              public sheep server by tools/maintenance/fetch_art_flock.py and
              topped up here. Git-ignored: the repo never redistributes them.
    renderer  flam3-render / flam3-genome / flam3-animate (GPL), run as
              separate programs, never linked or copied in. Built by the same
              tool into ~/.local/bin.

**Licence.** Algorithm-generated sheep are CC BY-NC 3.0
(https://electricsheep.org/license/): free for non-commercial use with the
credit "artwork by Scott Draves and the Electric Sheep", a link, and the
sheep's generation and serial number. Every piece posted carries `credit()`.

Kaia still chooses: the prompt's colour and complexity words steer which
sheep she picks, she sometimes breeds two sheep into one of her own
(flam3-genome cross), and an attached picture recolours the piece.
"""
from __future__ import annotations

import colorsys
import gzip
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from utils.infrastructure.logging.kaia_logger import log_debug, log_info, log_warning

FLOCK_DIR = Path("memory/art/flock")
INDEX = FLOCK_DIR / "index.json"
SERVER = "http://v2d7c.sheepserver.net"
GENERATION = 248
CREDIT = "artwork by Scott Draves and the Electric Sheep · electricsheep.org"


def _cfg(key: str, default):
    try:
        from utils.infrastructure.system.yaml_config import config
        return config.get(f"art.{key}", default)
    except Exception:
        return default


# ── flam3 ───────────────────────────────────────────────────────────

def flam3_bin(name: str) -> Optional[str]:
    """Path to a flam3 program: `art.flam3_dir`, then ~/.local/bin, then PATH."""
    for d in (_cfg("flam3_dir", None), str(Path.home() / ".local" / "bin")):
        if d and (p := Path(os.path.expanduser(d)) / name).is_file() and os.access(p, os.X_OK):
            return str(p)
    return shutil.which(name)


def _threads() -> str:
    # Leave a couple of cores for the bot and the model runner.
    return str(_cfg("render_threads", max(1, (os.cpu_count() or 4) - 2)))


def _run(name: str, env_extra: dict, timeout: float, stdin: Optional[str] = None) -> subprocess.CompletedProcess:
    exe = flam3_bin(name)
    if not exe:
        raise RuntimeError(f"{name} is not installed — run tools/maintenance/fetch_art_flock.py --build-flam3")
    env = dict(os.environ, **{k: str(v) for k, v in env_extra.items()})
    return subprocess.run([exe], env=env, input=stdin, capture_output=True, text=True,
                          timeout=timeout, check=False)


# ── genomes ─────────────────────────────────────────────────────────

_FLAME = re.compile(r"<flame\b.*?</flame>", re.S)


def split_flames(text: str) -> dict[str, str]:
    """name -> one <flame> element. A transition sheep's file is two flames
    (its two end points, themselves loop sheep) with no wrapping element, which
    is not well-formed XML; each half is a genome in its own right."""
    out = {}
    for m in _FLAME.finditer(text or ""):
        block = m.group(0)
        if "<xform" not in block:
            continue
        name = re.search(r'name="([^"]+)"', block)
        out.setdefault(name.group(1) if name else f"unnamed.{len(out)}", block)
    return out


def palette_of(genome: str) -> list[tuple[int, int, int]]:
    return [tuple(int(v) for v in m.groups())
            for m in re.finditer(r'<color index="\d+" rgb="(\d+) (\d+) (\d+)"', genome)]


def describe(genome: str) -> dict:
    """What the picker needs, read from the genome text alone: no render."""
    pal = palette_of(genome)
    hues, sats, vals = [], [], []
    for r, g, b in pal:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        hues.append(h); sats.append(s); vals.append(v)
    # Saturation-weighted circular mean hue: greys have no say in the colour.
    import math
    x = sum(s * math.cos(2 * math.pi * h) for h, s in zip(hues, sats))
    y = sum(s * math.sin(2 * math.pi * h) for h, s in zip(hues, sats))
    hue = (math.degrees(math.atan2(y, x)) % 360) if (x or y) else None
    return {
        "xforms": genome.count("<xform"),
        "hue": round(hue, 1) if hue is not None else None,
        "saturation": round(sum(sats) / len(sats), 3) if sats else 0.0,
        "value": round(sum(vals) / len(vals), 3) if vals else 0.0,
    }


def resize(genome: str, width: int, *, quality: Optional[float] = None,
           supersample: Optional[int] = None, temporal_samples: Optional[int] = None) -> str:
    """Set the output width, keeping aspect and framing (`scale` is pixels per
    unit, so it scales with the width), and optionally the render budget."""
    m = re.search(r'size="(\d+) (\d+)"', genome)
    if not m:
        return genome
    w0, h0 = int(m.group(1)), int(m.group(2))
    width = max(2, int(width) // 2 * 2)                   # both sides even, for H.264
    f = width / w0
    height = max(2, round(h0 * f) // 2 * 2)
    out = genome.replace(m.group(0), f'size="{width} {height}"', 1)
    out = re.sub(r' scale="([-\d.e+]+)"', lambda s: f' scale="{float(s.group(1)) * f:.6g}"', out, count=1)
    for attr, value in (("quality", quality), ("supersample", supersample),
                        ("temporal_samples", temporal_samples)):
        if value is not None:
            out = re.sub(rf' {attr}="[\d.]+"', f' {attr}="{value}"', out, count=1)
    return out


def recolor(genome: str, lut) -> str:
    """Repaint a sheep in a picture's colours, keeping its light and shade.

    `lut` is the 256x3 dark-to-light ramp `kaia_art_intent.palette_from_image`
    makes. A sheep's palette is not a ramp, so taking the new colours in index
    order would scramble its structure; instead each entry takes the ramp
    colour at its own brightness rank.
    """
    pal = palette_of(genome)
    if len(pal) < 2 or lut is None:
        return genome
    order = sorted(range(len(pal)), key=lambda i: 0.2126 * pal[i][0] + 0.7152 * pal[i][1] + 0.0722 * pal[i][2])
    rank = {i: r for r, i in enumerate(order)}
    n = len(lut)

    def repl(m):
        i = int(m.group(1))
        c = lut[min(n - 1, rank.get(i, 0) * n // len(pal))]
        r, g, b = (max(0, min(255, round(float(v) * 255))) for v in c)
        return f'<color index="{i}" rgb="{r} {g} {b}"'
    return re.sub(r'<color index="(\d+)" rgb="\d+ \d+ \d+"', repl, genome)


# ── the flock ───────────────────────────────────────────────────────

def load_index() -> dict:
    try:
        return json.loads(INDEX.read_text())
    except Exception:
        return {}


def save_index(index: dict) -> None:
    from utils.core.atomic_write import write_atomic
    FLOCK_DIR.mkdir(parents=True, exist_ok=True)
    write_atomic(INDEX, json.dumps(index, indent=1, sort_keys=True))


def _fetch(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "kaiacord-art/1 (+electricsheep.org reuse)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def add_genomes(text: str, index: dict) -> int:
    """File every genome in a downloaded sheep. Returns how many were new."""
    added = 0
    for name, block in split_flames(text).items():
        if not name.startswith("electricsheep.") or name in index:
            continue
        (FLOCK_DIR / f"{name}.flam3").write_text(block)
        index[name] = describe(block)
        added += 1
    return added


def fetch_flock(count: int, *, delay: float = 0.4, rng: Optional[random.Random] = None,
                log=print) -> int:
    """Download up to `count` new genomes: the live flock first, then sheep from
    generation 248's history (ids up to ~33,000 still served). Gentle on the
    server: one request at a time, with a pause."""
    rng = rng or random.Random()
    FLOCK_DIR.mkdir(parents=True, exist_ok=True)
    index = load_index()
    before = len(index)
    ids: list[int] = []
    try:
        listing = gzip.decompress(_fetch(f"{SERVER}/cgi/list?v=3.0.2")).decode("utf-8", "replace")
        ids = [int(i) for i in re.findall(r'<sheep id="(\d+)" type="0" state="done"', listing)]
    except Exception as e:
        log(f"live flock list unavailable ({e}); using history only")
    history = rng.sample(range(1, 33_000), k=min(32_999, max(0, count * 2)))
    for sid in ids + history:
        if len(index) - before >= count:
            break
        try:
            text = _fetch(f"{SERVER}/gen/{GENERATION}/{sid}/spex").decode("utf-8", "replace")
        except Exception as e:
            log(f"  {sid}: {e}")
            continue
        new = add_genomes(text, index)
        if new:
            log(f"  {sid}: +{new} (flock {len(index)})")
        time.sleep(delay)
    save_index(index)
    return len(index) - before


def flock() -> dict:
    """name -> description, for genomes actually on disk."""
    index = load_index()
    return {n: d for n, d in index.items() if (FLOCK_DIR / f"{n}.flam3").exists() and not d.get("rejected")}


def available() -> bool:
    return bool(flam3_bin("flam3-render") and flock())


# ── choosing ────────────────────────────────────────────────────────

#: Kaia's palette words (kaia_art_intent's menu) as a hue in degrees, so a
#: request for "ember" or "deep ocean" finds sheep of that colour.
PALETTE_HUES = {
    "electric": 285, "ember": 15, "acid": 90, "void": 300, "aurora": 150,
    "ghost": None, "deep_ocean": 210, "solar_flare": 32, "biolume": 172, "nebula": 275,
}


def _hue_distance(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def candidates(sheep: dict, intent=None) -> list[str]:
    """The sheep that fit what she chose; all of them when nothing was asked."""
    names = sorted(sheep)
    if intent is None:
        return names
    complexity = getattr(intent, "complexity", None)
    if complexity == "simple":
        names = [n for n in names if sheep[n]["xforms"] <= 4] or names
    elif complexity == "intricate":
        names = [n for n in names if sheep[n]["xforms"] >= 7] or names
    palette = getattr(intent, "palette", None)
    if palette == "ghost":                      # pastel: the least saturated third
        names = sorted(names, key=lambda n: sheep[n]["saturation"])[: max(8, len(names) // 3)]
    elif palette in PALETTE_HUES and PALETTE_HUES[palette] is not None:
        target = PALETTE_HUES[palette]
        coloured = [n for n in names if sheep[n]["hue"] is not None and sheep[n]["saturation"] > 0.25]
        names = sorted(coloured or names,
                       key=lambda n: _hue_distance(sheep[n]["hue"] or 0, target))[: max(8, len(names) // 6)]
    return names


@dataclass
class Piece:
    genome: str
    parents: list[str]
    bred: bool = False
    notes: dict = field(default_factory=dict)


def _preview_ok(genome: str, strict: bool = False) -> bool:
    """A 160 px, low-quality render: reject a piece that came out black or
    blown out. `strict` is for bred children, which can lose what made both
    parents good: they must also keep their colour and not wash out to a pale
    fog (the failure the first crosses showed)."""
    from PIL import Image
    small = resize(genome, 160, quality=25, supersample=1, temporal_samples=1)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "p.flam3"
        path.write_text(small)
        _run("flam3-render", {"in": path, "prefix": f"{tmp}/p_", "format": "png",
                              "nthreads": _threads(), "verbose": 0}, timeout=30)
        png = Path(tmp) / "p_00000.png"
        if not png.exists():
            return False
        im = Image.open(png).convert("RGB")
        hist = im.convert("L").histogram()
        total = sum(hist)
        lit = sum(hist[24:]) / total               # visibly drawn
        blown = sum(hist[250:]) / total
        if not (lit > 0.12 and blown < 0.5):
            return False
        if not strict:
            return True
        mean_luma = sum(i * n for i, n in enumerate(hist)) / total
        sat = im.convert("HSV").split()[1].histogram()
        mean_sat = sum(i * n for i, n in enumerate(sat)) / total
        return lit > 0.25 and blown < 0.2 and mean_luma < 150 and mean_sat > 60


def choose(rng: random.Random, intent=None, *, breed_chance: Optional[float] = None) -> Piece:
    """A sheep from the flock, or now and then a cross of two of them."""
    sheep = flock()
    if not sheep:
        raise RuntimeError("the flock is empty — run tools/maintenance/fetch_art_flock.py")
    pool = candidates(sheep, intent)
    first = rng.choice(pool)
    genome = (FLOCK_DIR / f"{first}.flam3").read_text()
    # Rare on purpose: a flock sheep is a design a crowd chose; a cross is a gamble.
    chance = float(_cfg("breed_chance", 0.15)) if breed_chance is None else breed_chance
    if len(sheep) > 1 and rng.random() < chance:
        second = rng.choice([n for n in pool if n != first] or [n for n in sheep if n != first])
        try:
            child = _cross(genome, (FLOCK_DIR / f"{second}.flam3").read_text(), rng)
            if child and _preview_ok(child, strict=True):
                return Piece(child, [first, second], bred=True)
            log_debug(f"[art] cross of {first} and {second} came out degenerate; using {first}")
        except Exception as e:
            log_warning(f"[art] breeding failed ({e}); using {first}")
    return Piece(genome, [first])


def _cross(a: str, b: str, rng: random.Random) -> Optional[str]:
    with tempfile.TemporaryDirectory() as tmp:
        pa, pb = Path(tmp) / "a.flam3", Path(tmp) / "b.flam3"
        pa.write_text(a); pb.write_text(b)
        r = _run("flam3-genome", {"cross0": pa, "cross1": pb,
                                  "method": rng.choice(["alternate", "interpolate", "union"]),
                                  "seed": rng.randrange(1 << 30), "isaac_seed": rng.randrange(1 << 30)},
                 timeout=30)
    flames = split_flames(r.stdout)
    return next(iter(flames.values()), None)


# ── rendering ───────────────────────────────────────────────────────

def render_still(genome: str, *, width: Optional[int] = None, quality: Optional[float] = None):
    """The piece as a PIL image and the render's params."""
    from PIL import Image
    # 1280 px at quality 1000: the filament detail holds, and a typical sheep
    # renders in 10-25 s on ten cores (1400/1500 took 14-46 s).
    width = int(width or _cfg("still_width", 1280))
    quality = float(quality or _cfg("still_quality", 1000))
    sized = resize(genome, width, quality=quality, temporal_samples=1)
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "piece.flam3"
        path.write_text(sized)
        r = _run("flam3-render", {"in": path, "prefix": f"{tmp}/out_", "format": "png",
                                  "nthreads": _threads(), "verbose": 0, "transparency": 0},
                 timeout=float(_cfg("still_timeout_s", 180)))
        png = Path(tmp) / "out_00000.png"
        if not png.exists():
            raise RuntimeError(f"flam3-render produced nothing: {r.stderr.strip()[-200:]}")
        image = Image.open(png).convert("RGB")
        image.load()
    return image, {"width": image.width, "height": image.height, "quality": quality,
                   "render_time_s": round(time.time() - t0, 1)}


def render_loop(genome: str, out_path: Path, *, width: Optional[int] = None,
                frames: Optional[int] = None, fps: int = 24, quality: Optional[float] = None) -> dict:
    """One full rotation of the sheep, the way the screensaver plays it, as an
    H.264 MP4 (Discord plays it inline). flam3-genome's `sequence` makes the
    loop; motion blur is off (`temporal_samples=1`): the rotation is slow
    enough not to need it and it multiplies the render time."""
    width = int(width or _cfg("loop_width", 640))
    frames = int(frames or _cfg("loop_frames", 96))
    quality = float(quality or _cfg("loop_quality", 120))
    sized = resize(genome, width, quality=quality, supersample=2, temporal_samples=1)
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        one = Path(tmp) / "one.flam3"
        one.write_text(sized)
        seq = _run("flam3-genome", {"sequence": one, "nframes": frames, "loops": 1}, timeout=60)
        if "<flame" not in seq.stdout:
            raise RuntimeError(f"flam3-genome made no sequence: {seq.stderr.strip()[-200:]}")
        seq_path = Path(tmp) / "seq.flam3"
        seq_path.write_text(re.sub(r'temporal_samples="[\d.]+"', 'temporal_samples="1"', seq.stdout))
        _run("flam3-animate", {"in": seq_path, "prefix": f"{tmp}/f", "format": "png",
                               "nthreads": _threads(), "begin": 0, "end": frames - 1, "verbose": 0},
             timeout=float(_cfg("loop_timeout_s", 420)))
        if not (Path(tmp) / "f00000.png").exists():
            raise RuntimeError("flam3-animate produced no frames")
        enc = subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps),
                              "-i", f"{tmp}/f%05d.png", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                              "-crf", "20", "-movflags", "+faststart", str(out_path)],
                             capture_output=True, text=True, timeout=120, check=False)
        if enc.returncode or not out_path.exists():
            raise RuntimeError(f"ffmpeg failed: {enc.stderr.strip()[-200:]}")
    return {"width": width, "frames": frames, "fps": fps, "quality": quality,
            "render_time_s": round(time.time() - t0, 1), "bytes": out_path.stat().st_size}


def credit(piece: Piece) -> str:
    names = " × ".join(piece.parents)
    how = "bred from " if piece.bred else ""
    return f"{how}{names} · {CREDIT}"


def make(intent=None, *, seed: Optional[int] = None, lut=None, loop: bool = False,
         out_path: Optional[Path] = None):
    """Choose, colour and render a piece. Blocking: run it in a thread.

    Returns (image or None, video path or None, params)."""
    rng = random.Random(seed)
    piece = choose(rng, intent)
    genome = recolor(piece.genome, lut) if lut is not None else piece.genome
    params = {"type": "sheep", "seed": seed, "sheep": piece.parents, "bred": piece.bred,
              "recoloured": lut is not None, "credit": credit(piece),
              **describe(genome)}
    if loop:
        out_path = out_path or Path(tempfile.mkstemp(suffix=".mp4")[1])
        params.update(render_loop(genome, out_path))
        # A still of the first frame, for her to look at and for the archive.
        image, _ = render_still(genome, width=900, quality=400)
        log_info(f"[art] sheep loop {params['sheep']} in {params['render_time_s']}s")
        return image, out_path, params
    image, info = render_still(genome)
    params.update(info)
    log_info(f"[art] sheep {params['sheep']}{' (bred)' if piece.bred else ''} in {params['render_time_s']}s")
    return image, None, params
