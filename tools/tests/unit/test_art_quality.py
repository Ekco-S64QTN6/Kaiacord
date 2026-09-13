"""
Regression tests for the fractal flame quality gate.

The renderer screens parameters with a cheap low-resolution probe before
committing to an ~8 second render. The gate is the only thing standing between
a degenerate attractor and a mostly-black image, and it had been set far too
low: seeds probing at 0.129 and 0.134 occupancy passed and rendered 92% black.
"""

import numpy as np
import pytest

from utils.core.kaia_art import FractalFlameRenderer


def test_the_occupancy_gate_is_set_from_the_measured_relationship():
    """Black fraction in the finished image tracks (1 - probe occupancy)
    almost exactly:

        occupancy 0.94 0.87 0.79 0.64 0.60 0.44 0.40 0.33 0.20 0.13
        black %     15   21   27   45   47   66   68   76   91   93

    At the old 0.12 the gate admitted images that were over 90% black.
    """
    assert FractalFlameRenderer.MIN_OCCUPANCY >= 0.5, (
        "gate too low: at this threshold a passing seed can still render "
        "mostly black")


def test_the_probe_budget_survives_a_strict_gate():
    """Measured over 120 seeds, 35.8% clear occupancy 0.55. The budget has to
    be large enough that failing every probe is negligible, since the fallback
    renders the best of a bad set."""
    r = FractalFlameRenderer
    pass_rate = 0.358
    p_all_fail = (1.0 - pass_rate) ** r.MAX_PROBES
    assert p_all_fail < 1e-3, (
        f"{r.MAX_PROBES} probes leaves a {p_all_fail:.2%} chance of falling "
        f"back to a bad render")


def test_a_failed_probe_is_treated_as_unusable():
    """It used to return {occupancy: 1.0, contrast: 1.0} on exception, which
    is backwards — a probe that threw then outscored every real candidate and
    was accepted immediately."""
    r = FractalFlameRenderer()
    stats = r._probe("not-a-valid-seed-object", None)
    assert stats["occupancy"] == 0.0 and stats["density_contrast"] == 0.0


def test_histogram_stats_handle_an_empty_histogram():
    r = FractalFlameRenderer()
    stats = r._histogram_stats(np.zeros((32, 32), dtype=np.float32))
    assert stats["occupancy"] == 0.0 and stats["density_contrast"] == 0.0


@pytest.mark.parametrize("seed", [5, 6, 9, 11])
def test_seeds_that_used_to_render_almost_black_now_do_not(seed):
    """These four measured 91%, 93%, 92% and 76% black under the old gate."""
    img, _ = FractalFlameRenderer().generate(seed=seed)
    lum = np.asarray(img.convert("RGB")).astype(np.float32).max(axis=2)
    black = float((lum < 8).mean())
    assert black < 0.60, f"seed {seed} is {black:.1%} black"
    assert lum.mean() > 30, f"seed {seed} mean brightness {lum.mean():.1f}"


def test_a_render_is_not_blown_out_either():
    """The gate must not be satisfied by fog. An earlier tone-mapping bug put
    five of ten seeds at a median brightness of pure white."""
    img, _ = FractalFlameRenderer().generate(seed=1)
    lum = np.asarray(img.convert("RGB")).astype(np.float32).max(axis=2)
    assert np.percentile(lum, 50) < 250, "median pixel is essentially white"
