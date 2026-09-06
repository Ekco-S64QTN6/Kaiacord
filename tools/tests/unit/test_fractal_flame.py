"""Fractal flame renderer — tone mapping, quality gate and accumulator.

The renderer had no tests. The September 2026 pass found that the tone mapper
put a single-hit pixel at 65% brightness (five of ten sample seeds rendered
with a median brightness of 255, pure white) and that the quality gate scored
the tinted background rather than the fractal, so a flame putting every point
on 0.5% of pixels was reported as "100% coverage" and shipped.

Rendering is expensive, so the tests here work on synthetic histograms and
short probes rather than full generations.
"""
import numpy as np
import pytest

from utils.core.kaia_art import (
    FractalFlameRenderer,
    PALETTES,
    PRIMARY_VARIATIONS,
    ACCENT_VARIATIONS,
    VARIATIONS,
    _VARIATION_MAP,
)


@pytest.fixture
def renderer():
    return FractalFlameRenderer()


def _histogram(shape, alpha, color=0.5):
    """Build (r, g, b, alpha) accumulators from a synthetic density field.

    Only used where the spatial arrangement genuinely does not matter.
    """
    lut_rgb = np.array([0.4, 0.7, 0.9])
    rgb = alpha[..., None] * lut_rgb * color
    return rgb[..., 0], rgb[..., 1], rgb[..., 2], alpha


def real_histogram(renderer, seed, res=360, points=40_000, iterations=25):
    """Run a genuine (small) chaos game and return its accumulators.

    Tone mapping cannot be judged on random noise: a flame histogram is
    spatially structured — contiguous filaments over an empty field — and the
    density-estimation and percentile steps behave completely differently on
    per-pixel noise. These stay small enough to run in a unit test.
    """
    system = renderer._build_system(seed, None)
    saved = renderer.N_POINTS, renderer.N_ITERATIONS
    try:
        renderer.N_POINTS, renderer.N_ITERATIONS = points, iterations
        return renderer._chaos_game(
            system["rng"], system["compiled"], system["weights"],
            system["color_speed"], res, res, system["symmetry_k"],
            None, system["palette_fn"],
        )
    finally:
        renderer.N_POINTS, renderer.N_ITERATIONS = saved


# ── Tone mapping ─────────────────────────────────────────────────────

def test_single_hit_pixels_render_dark(renderer):
    """The core defect: `log1p(alpha * 500)` normalised by the max meant one
    hit was already 65% brightness, so everything above it clipped to white."""
    res = renderer.OUTPUT_RES
    alpha = np.zeros((res, res))
    alpha[:] = 1.0                       # a field of single hits
    alpha[res // 2, res // 2] = 10_000   # one genuinely dense pixel
    img, _ = renderer._render(*_histogram(alpha.shape, alpha), res, res)

    lum = np.asarray(img.convert("L"), dtype=float)
    faint = np.median(lum)
    assert faint < 90, f"single-hit pixels rendered at {faint:.0f}/255"


def test_dense_core_is_brighter_than_sparse_field(renderer):
    res = renderer.OUTPUT_RES
    alpha = np.ones((res, res))
    alpha[res // 3: 2 * res // 3, res // 3: 2 * res // 3] = 5_000
    img, _ = renderer._render(*_histogram(alpha.shape, alpha), res, res)
    lum = np.asarray(img.convert("L"), dtype=float)
    core = lum[res // 2 - 20: res // 2 + 20, res // 2 - 20: res // 2 + 20].mean()
    edge = lum[:20, :20].mean()
    assert core > edge + 40


def test_highlights_do_not_clip_to_white(renderer):
    """The old final step divided by the 99th percentile of the whole frame,
    background included, driving everything above it to pure white."""
    rng = np.random.default_rng(3)
    res = renderer.OUTPUT_RES
    alpha = rng.gamma(0.4, 400.0, size=(res, res))
    img, _ = renderer._render(*_histogram(alpha.shape, alpha), res, res)
    arr = np.asarray(img.convert("RGB"), dtype=float)
    clipped = (arr.min(axis=-1) > 250).mean()
    assert clipped < 0.02, f"{clipped:.1%} of pixels are pure white"


@pytest.mark.parametrize("seed", [900, 903, 907])
def test_real_flames_are_well_exposed(renderer, seed):
    """Peak density across ten sample seeds ranged from 289 to 1,446,289 hits
    — a factor of 5,000 — so a fixed `contrast = 500` multiplier could not
    serve both ends. Five of those ten rendered with a median brightness of
    255 (pure white); none may now."""
    r, g, b, a = real_histogram(renderer, seed)
    img, stats = renderer._render(r, g, b, a, a.shape[1], a.shape[0])

    arr = np.asarray(img.convert("RGB"), dtype=float)
    lum = arr.max(axis=-1)
    assert (arr.min(axis=-1) > 250).mean() < 0.03, "blown highlights"
    assert np.median(lum) < 140, "no dark ground for the flame to glow against"
    assert np.percentile(lum, 99.5) > 60, "nothing bright enough to see"


@pytest.mark.parametrize("scale", [1, 250])
def test_exposure_survives_a_large_density_rescale(renderer, scale):
    """The same flame accumulated with far more samples must still render."""
    r, g, b, a = real_histogram(renderer, 900)
    img, _ = renderer._render(r * scale, g * scale, b * scale, a * scale,
                              a.shape[1], a.shape[0])
    arr = np.asarray(img.convert("RGB"), dtype=float)
    assert (arr.min(axis=-1) > 250).mean() < 0.03
    assert np.median(arr.max(axis=-1)) < 140


def test_empty_histogram_returns_a_black_image_not_a_crash(renderer):
    res = renderer.OUTPUT_RES
    alpha = np.zeros((res, res))
    img, stats = renderer._render(*_histogram(alpha.shape, alpha), res, res)
    assert img.size == (res, res)
    assert stats["occupancy"] == 0.0


# ── Quality gate ─────────────────────────────────────────────────────

def test_gate_rejects_a_collapsed_attractor(renderer):
    """Every point on a thin curve. The old gate called this 100% coverage
    because it measured the tinted background."""
    res = 256
    alpha = np.zeros((res, res))
    alpha[128, :] = 5_000            # 0.4% of pixels
    stats = renderer._histogram_stats(alpha)
    assert stats["occupancy"] < renderer.MIN_OCCUPANCY


def test_gate_accepts_a_structured_flame(renderer):
    rng = np.random.default_rng(5)
    alpha = rng.gamma(0.4, 200.0, size=(256, 256))
    alpha[alpha < 1] = 0
    stats = renderer._histogram_stats(alpha)
    assert stats["occupancy"] >= renderer.MIN_OCCUPANCY
    assert stats["density_contrast"] >= renderer.MIN_DENSITY_CONTRAST


def test_gate_measures_the_histogram_not_the_image(renderer):
    """A bright background must not be able to satisfy the gate."""
    res = 256
    alpha = np.zeros((res, res))
    alpha[10, 10] = 1e6
    assert renderer._histogram_stats(alpha)["occupancy"] < 0.001


# ── Accumulator ──────────────────────────────────────────────────────

def test_accumulator_matches_a_naive_scatter():
    """Points are batched across symmetry copies into one bincount call; the
    histogram must stay identical to a point-by-point scatter."""
    W = H = 48
    total = W * H
    rng = np.random.default_rng(7)
    n = 2000
    x = rng.uniform(-1.2, 1.2, n)
    y = rng.uniform(-1.2, 1.2, n)
    c = rng.random(n)
    lut = rng.random((256, 3))
    palette = lambda t: lut[np.clip((t * 255).astype(int), 0, 255)]

    acc = [np.zeros(total) for _ in range(4)]
    FractalFlameRenderer._accumulate_points(
        x, y, c, -1.0, -1.0, W / 2.0, H / 2.0, W, H, total, *acc, palette)

    ref = [np.zeros(total) for _ in range(4)]
    for xi, yi, ci in zip(x, y, c):
        px, py = int((xi + 1.0) * (W / 2.0)), int((yi + 1.0) * (H / 2.0))
        if 0 <= px < W and 0 <= py < H:
            idx = py * W + px
            col = palette(np.array([ci]))[0]
            ref[3][idx] += 1
            for ch in range(3):
                ref[ch][idx] += col[ch]

    assert np.array_equal(acc[3], ref[3])
    assert all(np.allclose(a, b) for a, b in zip(acc[:3], ref[:3]))


def test_accumulator_ignores_points_outside_the_viewport():
    W = H = 16
    total = W * H
    acc = [np.zeros(total) for _ in range(4)]
    far = np.array([50.0, -50.0])
    FractalFlameRenderer._accumulate_points(
        far, far, np.array([0.5, 0.5]), -1.0, -1.0, W / 2.0, H / 2.0,
        W, H, total, *acc, lambda t: np.zeros((len(t), 3)))
    assert acc[3].sum() == 0


# ── Variations ───────────────────────────────────────────────────────

def test_blur_is_excluded_from_primary_variations():
    """`blur` discards its input, so as a dominant variation it paints a flat
    haze — the visible out-of-focus discs in older renders."""
    assert "blur" in VARIATIONS
    assert "blur" not in PRIMARY_VARIATIONS
    assert "blur" in ACCENT_VARIATIONS


def test_dense_variation_set_excludes_blur():
    """The density guarantee must add structure, not uniform noise."""
    assert "blur" not in FractalFlameRenderer._DENSE_VARIATIONS
    assert FractalFlameRenderer._DENSE_VARIATIONS <= set(PRIMARY_VARIATIONS)


def test_every_variation_name_maps_to_a_function():
    assert set(VARIATIONS) == set(_VARIATION_MAP)


@pytest.mark.parametrize("name", VARIATIONS)
def test_variation_returns_finite_coordinates(name):
    """A variation returning NaN poisons the whole point set."""
    rng = np.random.default_rng(0)
    x = rng.uniform(-3, 3, 500)
    y = rng.uniform(-3, 3, 500)
    vx, vy = _VARIATION_MAP[name](x, y, rng)
    assert np.isfinite(vx).all() and np.isfinite(vy).all()


def test_transforms_carry_normalised_variation_weights(renderer):
    """flam3 blends variations as a weighted sum; an unweighted mean gives a
    shape with the character of neither input."""
    rng = np.random.default_rng(4)
    transforms, weights, color_speed = renderer._random_transforms(rng, 4)
    assert np.isclose(weights.sum(), 1.0)
    for _affine, var_names, _color, _post, var_weights in transforms:
        assert len(var_weights) == len(var_names)
        assert np.isclose(np.sum(var_weights), 1.0, atol=1e-6)
        assert (np.asarray(var_weights) >= 0).all()


def test_post_affine_reaches_the_chaos_game(renderer):
    """It was generated, recorded in the params dict, and then dropped: the
    compiled tuple hardcoded None in its place."""
    rng = np.random.default_rng(2)
    system = renderer._build_system(seed=2, palette_name="void")
    posts_declared = [t[3] is not None for t in system["transforms"]]
    posts_compiled = [t[3] is not None for t in system["compiled"]]
    assert posts_declared == posts_compiled


# ── End to end ───────────────────────────────────────────────────────

def test_seeded_generation_is_reproducible(renderer):
    """Retry seeds derive from the caller's seed, so `!art --seed N` gives the
    same image even when the first parameters are rejected."""
    a, pa = renderer.generate(seed=306)
    b, pb = renderer.generate(seed=306)
    assert np.array_equal(np.asarray(a), np.asarray(b))
    assert pa["seed"] == pb["seed"]


@pytest.mark.slow
def test_generated_image_is_high_resolution_and_well_exposed(renderer):
    img, params = renderer.generate(seed=900)
    assert img.size == (renderer.OUTPUT_RES, renderer.OUTPUT_RES)
    assert renderer.OUTPUT_RES >= 1080

    arr = np.asarray(img.convert("RGB"), dtype=float)
    assert (arr.min(axis=-1) > 250).mean() < 0.02, "blown highlights"
    assert np.median(arr.max(axis=-1)) < 128, "image is not predominantly dark"
    assert params["occupancy"] >= renderer.MIN_OCCUPANCY


def test_palettes_are_all_usable():
    for name, fn in PALETTES.items():
        rgb = fn(np.linspace(0, 1, 64))
        assert rgb.shape == (64, 3), name
        assert np.isfinite(rgb).all() and (0 <= rgb).all() and (rgb <= 1).all(), name
