#!/usr/bin/env python3
"""A fixed, versioned gallery of `!art` renders, for before/after comparisons.

    venv/bin/python3 tools/development/art_gallery.py --out /tmp/art-before
    # ... change the renderer ...
    venv/bin/python3 tools/development/art_gallery.py --out /tmp/art-after \\
        --against /tmp/art-before

Each case is a prompt, a seed and a palette. The intent comes from
`kaia_art_intent.from_words` (vocabulary only, no model), and the palette is
always forced, which also bypasses the mood bias in `_mood_palette()`: an
unforced palette follows Kaia's emotional state, and the same seed would
render differently from one day to the next. Same case, same code, same
image.

Writes `<case>.png` and `<case>.json` (the render's own params: transforms,
symmetry, occupancy, density contrast, render time, plus the prompt and
intent), `index.json` (gallery version, mode, git commit), and `sheet.png`, a
labelled contact sheet. With `--against DIR` it also writes `compare.png`,
each case before and after with the change in occupancy, contrast and time.

`--fast` renders at a quarter of the resolution and a fifth of the points to
check that a change does what was meant. It is labelled on the sheet and in
`index.json`; compare like with like. The metrics are guardrails, not a
verdict: look at the pictures (issue #48).

Issue #48, step 1.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

#: Bump when a case is added, removed or changed, so two galleries are only
#: compared when they rendered the same cases.
GALLERY_VERSION = 1

#: name, prompt, seed, palette. The prompts cover the vocabulary `from_words`
#: understands (shapes, symmetry, complexity) and the range of palettes;
#: the empty prompt is the seed alone.
CASES = [
    ("seed_only_ember", "", 42, "ember"),
    ("seed_only_void", "", 7, "void"),
    ("spiral_electric", "a slow electric spiral", 1001, "electric"),
    ("swirl_aurora", "swirling aurora ribbons", 2024, "aurora"),
    ("heart_solar", "a heart of solar fire", 314, "solar_flare"),
    ("rings_ocean", "rings in the deep ocean", 8080, "deep_ocean"),
    ("julia_nebula", "julia nebula, intricate", 1337, "nebula"),
    ("simple_ghost", "a simple ghost", 55, "ghost"),
    ("sixfold_biolume", "six-fold bioluminescent bloom", 606, "biolume"),
    ("waves_acid", "acid waves, balanced", 99, "acid"),
    ("eyefish_ember", "an eyefish ember, intricate", 4242, "ember"),
    ("disc_void", "a quiet disc in the void", 123, "void"),
]

TILE = 300
LABEL_H = 62


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def make_renderer(fast: bool):
    from utils.core.kaia_art import FractalFlameRenderer
    r = FractalFlameRenderer()
    if fast:
        # Instance attributes shadow the class constants for this run only.
        r.INTERNAL_RES, r.OUTPUT_RES = 540, 270
        r.N_POINTS, r.N_ITERATIONS = 100_000, 30
    return r


def render_case(renderer, case) -> tuple:
    from utils.core.kaia_art_intent import from_words
    name, prompt, seed, palette = case
    intent = from_words(prompt)
    t0 = time.time()
    image, params = renderer.generate(seed=seed, palette_name=palette, intent=intent)
    params = dict(params)
    params.update(case=name, prompt=prompt, requested_seed=seed,
                  wall_time_s=round(time.time() - t0, 2), intent=intent.to_dict())
    return image, params


def _label(p: dict) -> list[str]:
    return [
        # PIL's default font is ASCII-only. A re-rolled seed (the first one
        # failed the quality gate) is marked; the seed used is in the JSON.
        f"{p.get('case')}  seed {p.get('requested_seed')}"
        + (" (re-rolled)" if p.get('seed') != p.get('requested_seed') else ""),
        f"{p.get('palette')} | {p.get('n_transforms')} xf | sym {p.get('symmetry_k')}"
        + (f" | {', '.join(p['intent']['shapes'])}" if p.get('intent', {}).get('shapes') else ""),
        f"occ {p.get('occupancy', 0):.0%} | contrast {p.get('density_contrast', 0):.2f}"
        f" | {p.get('wall_time_s', 0):.1f}s",
    ]


def _tile(image, lines, size=TILE):
    from PIL import Image, ImageDraw
    tile = Image.new("RGB", (size, size + LABEL_H), (12, 12, 14))
    tile.paste(image.convert("RGB").resize((size, size), Image.LANCZOS), (0, 0))
    draw = ImageDraw.Draw(tile)
    for i, line in enumerate(lines):
        draw.text((6, size + 4 + i * 19), line, fill=(225, 225, 225))
    return tile


def contact_sheet(entries, title: str, cols: int = 4):
    """entries: [(image, label_lines)]."""
    from PIL import Image, ImageDraw
    rows = max(1, (len(entries) + cols - 1) // cols)
    th = TILE + LABEL_H
    sheet = Image.new("RGB", (cols * TILE, 28 + rows * th), (0, 0, 0))
    ImageDraw.Draw(sheet).text((8, 8), title, fill=(255, 255, 255))
    for i, (image, lines) in enumerate(entries):
        sheet.paste(_tile(image, lines), ((i % cols) * TILE, 28 + (i // cols) * th))
    return sheet


def compare_sheet(before_dir: Path, after_dir: Path, names):
    """Each case as a before/after pair, with the metric deltas."""
    from PIL import Image
    entries = []
    for name in names:
        b_png, a_png = before_dir / f"{name}.png", after_dir / f"{name}.png"
        if not (b_png.exists() and a_png.exists()):
            continue
        b = json.loads((before_dir / f"{name}.json").read_text())
        a = json.loads((after_dir / f"{name}.json").read_text())
        delta = (f"change: occ {a.get('occupancy', 0) - b.get('occupancy', 0):+.0%}, "
                 f"contrast {a.get('density_contrast', 0) - b.get('density_contrast', 0):+.2f}, "
                 f"{a.get('wall_time_s', 0) - b.get('wall_time_s', 0):+.1f}s")
        entries.append((Image.open(b_png), [f"{name}  BEFORE"] + _label(b)[1:]))
        entries.append((Image.open(a_png), [f"{name}  AFTER"] + [_label(a)[1], delta]))
    return contact_sheet(entries, f"before: {before_dir}   after: {after_dir}", cols=4)


def run(out: Path, cases, renderer, *, fast: bool, against: Path | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    entries, rendered = [], []
    for case in cases:
        image, params = render_case(renderer, case)
        image.save(out / f"{case[0]}.png")
        (out / f"{case[0]}.json").write_text(json.dumps(params, indent=2, default=str))
        entries.append((image, _label(params)))
        rendered.append(case[0])
        print(f"  {case[0]:<18} occ {params.get('occupancy', 0):.0%}  "
              f"contrast {params.get('density_contrast', 0):.2f}  {params['wall_time_s']:.1f}s",
              flush=True)
    index = {"gallery_version": GALLERY_VERSION, "mode": "fast" if fast else "full",
             "commit": _git_commit(), "cases": rendered}
    (out / "index.json").write_text(json.dumps(index, indent=2))
    contact_sheet(entries, f"!art gallery v{GALLERY_VERSION} | {index['mode']} | {index['commit']}"
                  ).save(out / "sheet.png")
    if against is not None:
        other = json.loads((against / "index.json").read_text())
        if (other.get("gallery_version"), other.get("mode")) != (GALLERY_VERSION, index["mode"]):
            print(f"warning: comparing v{other.get('gallery_version')}/{other.get('mode')} "
                  f"against v{GALLERY_VERSION}/{index['mode']}", file=sys.stderr)
        compare_sheet(against, out, rendered).save(out / "compare.png")
    return index


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True, help="directory to write the gallery to")
    ap.add_argument("--against", type=Path, help="an earlier gallery to compare with")
    ap.add_argument("--fast", action="store_true", help="quarter resolution, for quick checks")
    ap.add_argument("--only", help="comma-separated case names")
    ap.add_argument("--list", action="store_true", help="print the cases and exit")
    args = ap.parse_args()

    if args.list:
        for name, prompt, seed, palette in CASES:
            print(f"{name:<18} seed {seed:<5} {palette:<12} {prompt!r}")
        return 0
    cases = CASES
    if args.only:
        want = {n.strip() for n in args.only.split(",")}
        cases = [c for c in CASES if c[0] in want]
        missing = want - {c[0] for c in cases}
        if missing:
            print(f"unknown case(s): {', '.join(sorted(missing))}", file=sys.stderr)
            return 2
    run(args.out, cases, make_renderer(args.fast), fast=args.fast, against=args.against)
    print(f"-> {args.out / 'sheet.png'}" + (f", {args.out / 'compare.png'}" if args.against else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
