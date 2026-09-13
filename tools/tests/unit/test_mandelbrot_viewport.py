"""Mandelbrot viewports, including ones shared as a link.

Starkind posted a weirdly.net URL pointing at a location eleven orders of
magnitude deeper than anything `!art mandelbrot` could reach, and there was no
way to feed it to her but to read the numbers out by hand.
"""
import math
import numpy as np
import pytest

from utils.core.kaia_art import (
    FractalFlameRenderer, MANDELBROT_TARGETS, PALETTE_LUTS, parse_mandelbrot_url,
    _cyclic, _iterations_for_span, _lut_palette, _lut_palette_smooth, depth_of,
)

SHARED = ("http://weirdly.net/webtoys/mandelbrot/index.html?config=v1,"
          "-1.7689411331682035,-0.002827913661875118,1.482190207452281e-11,"
          "1.3655110275298383e-11,1024,541.2410775221192,0.63841,0,"
          "2.201273161068578,-1.97159,0,3.1043389972836914,-0.72159,0,"
          "-3.3907138805023216,-0.00159,0.23841,11000,01100,00110,1,1,0,0,0,"
          "1,-2,1,1,1,,4,1,0,1,0.8072286659724766")


def test_the_shared_link_parses_to_its_viewport():
    cfg = parse_mandelbrot_url(SHARED)
    assert cfg is not None
    assert cfg["center"] == pytest.approx((-1.7689411331682035, -0.002827913661875118))
    assert cfg["span"] == pytest.approx(1.482190207452281e-11)
    assert cfg["max_iter"] == 1024


@pytest.mark.parametrize("url", [
    "", None, "http://example.com/nothing",
    "?config=garbage,1,2",
    "?config=v1,0,0,0,0,100",              # zero span renders one point
    "?config=v1,50,50,0.1,0.1,100",        # nowhere near the set
    "?config=v1,-0.5,0,1e-30,1e-30,100",   # far below double precision
])
def test_a_bad_link_is_declined_not_raised(url):
    """A malformed link must fall back to a random location, never throw at
    whoever pasted it."""
    assert parse_mandelbrot_url(url) is None


# ── Iteration budget scales with depth ────────────────────────────────

def test_iterations_grow_with_zoom_depth():
    """Pinned at 256 for every view, detail that only resolves after several
    hundred iterations never appeared and a deep frame saturated flat."""
    shallow = _iterations_for_span(1e-2)
    deep = _iterations_for_span(1e-11)
    assert deep > shallow * 3
    assert _iterations_for_span(1e-11) <= 2600, "budget must stay bounded"


def test_an_explicit_iteration_count_is_honoured():
    assert _iterations_for_span(1e-11, 1024) == 1024


# ── The render is actually the Mandelbrot set ─────────────────────────

def test_the_interior_fraction_matches_the_known_area():
    """The set's area is ~1.5065, so over the 3x3 box around it the interior is
    ~16.7% of the frame. This is the cheapest end-to-end check that the
    iteration really is z -> z^2 + c and that interior detection is right."""
    _img, p = FractalFlameRenderer().generate_mandelbrot(
        seed=1, palette_name="ember", center=(-0.5, 0.0), span=1.5)
    assert p["interior_fraction"] == pytest.approx(1.5065 / 9.0, abs=0.01)


def test_a_point_deep_inside_the_cardioid_is_all_interior():
    _img, p = FractalFlameRenderer().generate_mandelbrot(
        seed=1, palette_name="ember", center=(0.0, 0.0), span=0.05)
    assert p["interior_fraction"] == 1.0


def test_the_interior_is_drawn_black_and_the_outside_is_not():
    """Non-escaping points kept M=0 and so did the fastest-escaping ones, so the
    body of the set was painted the same colour as the band beside it."""
    img, _p = FractalFlameRenderer().generate_mandelbrot(
        seed=1, palette_name="ember", center=(-0.5, 0.0), span=1.5)
    a = np.asarray(img)
    assert a[360, 360].sum() == 0, "the centre of the cardioid must be black"
    assert a[5, 5].sum() > 0, "the corner is outside the set and must be coloured"


def test_a_deep_view_uses_the_whole_palette():
    """Linear mapping over [0, max_iter] compressed a deep view into a few
    adjacent LUT entries; equalising by rank is what shows the layering."""
    img, _p = FractalFlameRenderer().generate_mandelbrot(
        seed=7, palette_name="nebula", center=(-1.7689411331682035, -0.002827913661875118),
        span=1.482190207452281e-11, max_iter=1024)
    a = np.asarray(img)
    # Was 230 distinct colours on this exact frame, the nearest-stop LUT's
    # ceiling. The point of comparison is the weirdly.net render, which
    # evaluates a continuous function per channel.
    assert len(np.unique(a.reshape(-1, 3), axis=0)) > 5000
    assert a.std() > 25


# ── What the shared toy does better, and we now do too ────────────────

def test_the_palette_interpolates_instead_of_snapping():
    """`(t * 255).astype(int)` caps any image at 256 colours however smooth the
    underlying field is, and bands every gradient."""
    t = np.linspace(0, 1, 4000)
    lut = PALETTE_LUTS["nebula"]
    count = lambda x: len(np.unique((np.clip(x, 0, 1) * 255).astype(np.uint8), axis=0))
    assert count(_lut_palette(t, lut)) <= 256
    assert count(_lut_palette_smooth(t, lut)) > 256


def test_interpolated_and_nearest_agree_at_the_stops():
    """Interpolation must not shift the palette, only fill between its entries."""
    t = np.arange(256) / 255.0
    lut = PALETTE_LUTS["ember"]
    assert np.allclose(_lut_palette(t, lut), _lut_palette_smooth(t, lut), atol=1e-9)


def test_colour_cycling_is_seamless():
    """A sawtooth jumps from the last colour back to the first at every period
    boundary. Mirroring lets any palette repeat without a seam — the
    `colour_period` term in the shared config."""
    t = np.linspace(0, 1, 20000)
    c = _cyclic(t, 5)
    assert 0.0 <= c.min() and c.max() <= 1.0
    assert np.abs(np.diff(c)).max() < 0.01, "a discontinuity means a visible seam"


def test_deeper_views_get_more_colour_cycles():
    """A deep view occupies a narrow band of escape times; repeating the ramp
    through it is what makes the layering legible."""
    _i, shallow = FractalFlameRenderer().generate_mandelbrot(
        seed=1, palette_name="ember", center=(-0.5, 0.0), span=1.5)
    _i, deep = FractalFlameRenderer().generate_mandelbrot(
        seed=1, palette_name="ember",
        center=(-1.7689411331682035, -0.002827913661875118),
        span=1.482190207452281e-11, max_iter=600)
    assert deep["colour_cycles"] > shallow["colour_cycles"] * 3


def test_the_frame_is_supersampled():
    """The boundary is detail all the way down; one sample per pixel turns every
    filament into a dotted line."""
    _img, p = FractalFlameRenderer().generate_mandelbrot(
        seed=1, palette_name="void", center=(-0.5, 0.0), span=1.5)
    assert p["supersample"] >= 2
    assert p["resolution"] == [720, 720], "supersampling is internal, not output size"


def test_depth_of_matches_the_span():
    assert depth_of(3.0) == pytest.approx(0.0, abs=1e-9)
    assert depth_of(1.482190207452281e-11) == pytest.approx(11.3, abs=0.1)


def test_deep_targets_are_reachable_and_jitter_stays_local():
    """Jitter was a fixed fraction of a shallow span; applied to a 1e-11 view an
    absolute offset would throw it clean out of the interesting region."""
    deep = [t for t in MANDELBROT_TARGETS if t[3] < 1e-6]
    assert deep, "the target list must include genuinely deep locations"
    r = FractalFlameRenderer()
    name, cx, cy, span = deep[0]
    _img, p = r.generate_mandelbrot(seed=3, palette_name="void",
                                    center=(cx, cy), span=span)
    assert abs(p["center"][0] - cx) < span
    assert p["zoom_exponent"] > 6
    assert p["zoom"].startswith("1e")
