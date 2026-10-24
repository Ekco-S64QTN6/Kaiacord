"""!art's Electric Sheep path: genome handling offline; one real render if flam3 is here."""
import json
import random
from types import SimpleNamespace

import numpy as np
import pytest

from utils.core import kaia_sheep as ks


def _genome(name, rgb_fn, xforms=3, size=(800, 592), scale=500.0):
    colors = "\n".join(f'   <color index="{i}" rgb="{" ".join(str(v) for v in rgb_fn(i))}"/>'
                       for i in range(256))
    xf = "\n".join('   <xform weight="0.5" color="0" linear="1" coefs="0.5 0 0 0.5 0 0"/>'
                   for _ in range(xforms))
    return (f'<flame name="{name}" size="{size[0]} {size[1]}" center="0 0" scale="{scale}" '
            f'rotate="0" supersample="4" quality="2000" temporal_samples="1000">\n{xf}\n{colors}\n</flame>')


RED = lambda i: (i, 0, 0)                          # a dark-to-light red ramp
BLUE = lambda i: (0, 0, i)
GREY = lambda i: (i, i, i)


def test_a_transition_file_splits_into_its_two_end_points():
    a, b = _genome("electricsheep.248.1", RED), _genome("electricsheep.248.2", BLUE)
    text = a + "\n" + b + '\n<flame name="electricsheep.248.3"></flame>'   # no xforms: not a genome
    flames = ks.split_flames(text)
    assert list(flames) == ["electricsheep.248.1", "electricsheep.248.2"]


def test_resize_keeps_aspect_and_framing_and_sets_budget():
    g = _genome("s", RED, size=(800, 592), scale=500.0)
    out = ks.resize(g, 1600, quality=300, supersample=2, temporal_samples=1)
    assert 'size="1600 1184"' in out
    assert 'scale="1000"' in out                    # pixels per unit doubles with the width
    assert 'quality="300"' in out and 'supersample="2"' in out and 'temporal_samples="1"' in out
    assert 'size="640 474"' in ks.resize(g, 641)     # both sides even, for H.264


def test_recolor_keeps_the_sheeps_light_and_shade():
    g = _genome("s", lambda i: (255 - i, 0, 0))     # bright at index 0, dark at 255
    lut = np.stack([np.zeros(256), np.linspace(0, 1, 256), np.zeros(256)], axis=1)  # dark→light green
    out = ks.palette_of(ks.recolor(g, lut))
    assert all(r == 0 and b == 0 for r, _g, b in out)            # all green now
    assert out[0][1] > out[255][1]                               # index 0 is still the brightest


def test_describe_reads_colour_and_complexity_from_the_genome():
    red = ks.describe(_genome("r", RED, xforms=8))
    assert red["xforms"] == 8
    assert red["hue"] is not None and min(red["hue"], 360 - red["hue"]) < 5
    assert ks.describe(_genome("g", GREY))["saturation"] == 0.0


def test_candidates_follow_the_prompts_colour_and_complexity():
    sheep = {}
    for i in range(30):
        fn = RED if i % 2 else BLUE
        sheep[f"electricsheep.248.{i}"] = ks.describe(_genome(str(i), fn, xforms=3 if i < 15 else 9))
    ember = ks.candidates(sheep, SimpleNamespace(palette="ember", complexity=None))
    assert ember and all(sheep[n]["hue"] < 30 or sheep[n]["hue"] > 330 for n in ember)
    ocean = ks.candidates(sheep, SimpleNamespace(palette="deep_ocean", complexity=None))
    assert all(200 < sheep[n]["hue"] < 260 for n in ocean)
    simple = ks.candidates(sheep, SimpleNamespace(palette=None, complexity="simple"))
    assert simple and all(sheep[n]["xforms"] <= 4 for n in simple)
    assert ks.candidates(sheep, None) == sorted(sheep)


def test_choose_picks_from_the_flock_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(ks, "FLOCK_DIR", tmp_path)
    monkeypatch.setattr(ks, "INDEX", tmp_path / "index.json")
    index = {}
    for i in range(3):
        ks.FLOCK_DIR.mkdir(exist_ok=True)
        ks.add_genomes(_genome(f"electricsheep.248.{i}", RED), index)
    index["electricsheep.248.2"]["rejected"] = True              # gated out
    ks.save_index(index)
    picked = {ks.choose(random.Random(s), None, breed_chance=0).parents[0] for s in range(40)}
    assert picked == {"electricsheep.248.0", "electricsheep.248.1"}
    assert json.loads((tmp_path / "index.json").read_text())


def test_credit_names_every_parent_and_the_licence_text():
    piece = ks.Piece("<flame/>", ["electricsheep.248.1", "electricsheep.248.2"], bred=True)
    c = ks.credit(piece)
    assert "electricsheep.248.1 × electricsheep.248.2" in c and c.startswith("bred from")
    assert "Scott Draves and the Electric Sheep" in c and "electricsheep.org" in c


def test_art_command_parses_loop_and_credits_sheep_in_the_footer():
    from utils.commands import art_handler
    opts = art_handler.parse_args("!art loop a slow red bloom")
    assert opts["loop"] is True and opts["prompt"] == "a slow red bloom"
    assert art_handler.parse_args("!art a loop of string")["loop"] is False   # only as the first word
    footer = art_handler._footer_for({"type": "sheep", "credit": "x · " + ks.CREDIT,
                                      "render_time_s": 12.3})
    assert ks.CREDIT in footer and "12.3s" in footer


@pytest.mark.skipif(not ks.flam3_bin("flam3-render"), reason="flam3 is not installed here")
def test_a_real_flam3_render_draws_something():
    genome = (
        '<flame name="t" size="200 200" center="0 0" scale="60" rotate="0" supersample="1" '
        'quality="40" brightness="4" gamma="4" background="0 0 0">'
        '<xform weight="0.5" color="0" spherical="1" coefs="0.6 0 0 0.6 0.3 0"/>'
        '<xform weight="0.5" color="1" swirl="1" coefs="0.6 0.2 -0.2 0.6 -0.3 0.1"/>'
        + "".join(f'<color index="{i}" rgb="{i} {255 - i} 200"/>' for i in range(256))
        + "</flame>")
    image, info = ks.render_still(genome, width=200, quality=40)
    assert image.size == (200, 200)
    assert max(image.convert("L").getextrema()) > 40               # not a black frame
    assert info["render_time_s"] >= 0
