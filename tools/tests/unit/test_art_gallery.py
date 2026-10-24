"""tools/development/art_gallery.py: fixed cases, files written, sheets built."""
import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image

from utils.core.kaia_art import PALETTES

_PATH = Path(__file__).resolve().parents[3] / "tools" / "development" / "art_gallery.py"


@pytest.fixture(scope="module")
def gallery():
    """The script is not a package module; load it by path, at test time."""
    spec = importlib.util.spec_from_file_location("art_gallery", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StubRenderer:
    """Stands in for FractalFlameRenderer: a flat image per seed, no chaos game."""

    def __init__(self):
        self.calls = []

    def generate(self, seed=None, palette_name=None, intent=None):
        self.calls.append((seed, palette_name, intent))
        shade = seed % 256
        image = Image.new("RGB", (64, 64), (shade, 0, 255 - shade))
        return image, {"type": "flame", "seed": seed, "palette": palette_name,
                       "n_transforms": 3, "symmetry_k": 4,
                       "occupancy": 0.6, "density_contrast": 0.5}


def test_cases_are_unique_and_force_a_known_palette(gallery):
    names = [c[0] for c in gallery.CASES]
    assert len(names) == len(set(names))
    # A forced palette is what makes a case reproducible: an unforced one
    # follows Kaia's mood.
    assert all(c[3] in PALETTES for c in gallery.CASES)
    assert all(isinstance(c[2], int) for c in gallery.CASES)


def test_run_writes_each_case_index_and_sheet(gallery, tmp_path):
    renderer = StubRenderer()
    cases = gallery.CASES[:3]
    index = gallery.run(tmp_path, cases, renderer, fast=True)

    assert index["gallery_version"] == gallery.GALLERY_VERSION
    assert index["mode"] == "fast"
    assert index["cases"] == [c[0] for c in cases]
    # The palette is always passed through, never left to the mood bias.
    assert [(s, p) for s, p, _ in renderer.calls] == [(c[2], c[3]) for c in cases]
    for name, prompt, seed, _palette in cases:
        params = json.loads((tmp_path / f"{name}.json").read_text())
        assert (params["case"], params["prompt"], params["requested_seed"]) == (name, prompt, seed)
        assert "wall_time_s" in params and "intent" in params
        assert (tmp_path / f"{name}.png").exists()
    sheet = Image.open(tmp_path / "sheet.png")
    assert sheet.width == 4 * gallery.TILE


def test_against_builds_a_before_after_sheet(gallery, tmp_path):
    before, after = tmp_path / "before", tmp_path / "after"
    cases = gallery.CASES[:2]
    gallery.run(before, cases, StubRenderer(), fast=True)
    gallery.run(after, cases, StubRenderer(), fast=True, against=before)

    compare = Image.open(after / "compare.png")
    # Two cases, each a before and an after tile: one row of four.
    assert compare.width == 4 * gallery.TILE
    assert compare.height == 28 + gallery.TILE + gallery.LABEL_H


def test_labels_are_ascii_for_the_default_font(gallery):
    params = {"case": "x", "requested_seed": 1, "seed": 2, "palette": "ember",
              "n_transforms": 3, "symmetry_k": 4, "intent": {"shapes": ["spiral"]},
              "occupancy": 0.5, "density_contrast": 0.4, "wall_time_s": 1.0}
    lines = gallery._label(params)
    assert all(line.isascii() for line in lines)
    assert "re-rolled" in lines[0]
