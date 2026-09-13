"""
Kaia Art System — Fractal Flame Renderer
Pure NumPy/SciPy implementation. CPU-only (GPU reserved for Ollama).
Based on the Draves/Reckase algorithm (flam3.com/flame_draves.pdf).
"""
import math
import time
import zlib
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

from utils.infrastructure.logging.kaia_logger import log_info, log_debug, log_warning, log_error

# ── Variation Functions ────────────────────────────────────────────────────────
# All vectorized: take (x, y) arrays, return (x, y) arrays.
# 20 variations — subset of the flam3 spec, chosen for visual diversity.

VARIATIONS = [
    'linear', 'sinusoidal', 'spherical', 'swirl', 'horseshoe', 'polar',
    'spiral', 'hyperbolic', 'julia', 'disc', 'heart', 'diamond',
    'rings', 'waves', 'eyefish', 'bubble', 'curl', 'ngon', 'bent', 'blur',
]

# Variations that transform their input, and so carry structure. These are the
# only ones eligible to be a transform's dominant shape.
PRIMARY_VARIATIONS = [v for v in VARIATIONS if v != 'blur']

# Variations that DISCARD their input. `blur` maps every point to a uniform
# sample of the unit disc, so as a primary it contributes a flat haze — the
# visible soft discs in the background of some renders. In flam3 it is used at
# low weight as a glow accent, which is how it is restricted here.
ACCENT_VARIATIONS = {'blur'}

def _var_linear(x, y, *args):     return x, y
def _var_sinusoidal(x, y, *args): return np.sin(x), np.sin(y)

def _var_spherical(x, y, *args):
    r2 = x**2 + y**2 + 1e-10
    return x / r2, y / r2

def _var_swirl(x, y, *args):
    r2 = x**2 + y**2
    return x * np.sin(r2) - y * np.cos(r2), x * np.cos(r2) + y * np.sin(r2)

def _var_horseshoe(x, y, *args):
    r = np.sqrt(x**2 + y**2) + 1e-10
    return (x - y) * (x + y) / r, 2 * x * y / r

def _var_polar(x, y, *args):
    r = np.sqrt(x**2 + y**2) + 1e-10
    theta = np.arctan2(y, x)
    return theta / np.pi, r - 1

def _var_spiral(x, y, *args):
    r = np.sqrt(x**2 + y**2) + 1e-10
    theta = np.arctan2(y, x)
    return (np.cos(theta) + np.sin(r)) / r, (np.sin(theta) - np.cos(r)) / r

def _var_hyperbolic(x, y, *args):
    r = np.sqrt(x**2 + y**2) + 1e-10
    theta = np.arctan2(y, x)
    return np.sin(theta) / r, r * np.cos(theta)

def _var_julia(x, y, *args):
    """Classic Electric Sheep swirling organic tendrils."""
    r = np.sqrt(np.sqrt(x**2 + y**2) + 1e-10)
    theta = np.arctan2(y, x) * 0.5
    rng = args[0] if args else None
    if rng is None:
        rng = np.random.default_rng()
    sign = rng.choice([-1.0, 1.0], size=len(x))
    theta = theta + sign * np.pi * 0.5
    return r * np.cos(theta), r * np.sin(theta)

def _var_disc(x, y, *args):
    """Disc mapping — circular, mandala-like structures."""
    theta = np.arctan2(y, x) / np.pi
    r = np.pi * np.sqrt(x**2 + y**2)
    return theta * np.sin(r), theta * np.cos(r)

def _var_heart(x, y, *args):
    """Heart-shaped distortion."""
    r = np.sqrt(x**2 + y**2)
    theta = np.arctan2(y, x)
    return r * np.sin(theta * r), -r * np.cos(theta * r)

def _var_diamond(x, y, *args):
    """Diamond/gem-like faceted shapes."""
    r = np.sqrt(x**2 + y**2) + 1e-10
    theta = np.arctan2(y, x)
    return np.sin(theta) * np.cos(r), np.cos(theta) * np.sin(r)

def _var_rings(x, y, *args):
    """Concentric ring patterns — halos and circles."""
    r = np.sqrt(x**2 + y**2)
    theta = np.arctan2(y, x)
    c2 = 0.36
    rmod = np.fmod(r + c2, 2 * c2) - c2 + r * (1 - c2)
    return rmod * np.cos(theta), rmod * np.sin(theta)

def _var_waves(x, y, *args):
    """Sine wave distortion — flowing, fabric-like."""
    return x + 0.5 * np.sin(y * 3.0), y + 0.5 * np.sin(x * 3.0)

def _var_eyefish(x, y, *args):
    """Wide-angle fisheye — organic bulging look."""
    r = np.sqrt(x**2 + y**2) + 1e-10
    factor = 2.0 / (r + 1.0)
    return factor * x, factor * y

def _var_bubble(x, y, *args):
    """Spherical bubble distortion."""
    r2 = x**2 + y**2 + 1e-10
    factor = 4.0 / (r2 + 4.0)
    return factor * x, factor * y

def _var_curl(x, y, *args):
    """Smooth flowing curves like smoke."""
    c1, c2 = 0.5, 0.3
    t1 = 1 + c1 * x + c2 * (x**2 - y**2)
    t2 = c1 * y + 2 * c2 * x * y
    denom = t1**2 + t2**2 + 1e-10
    return (x * t1 + y * t2) / denom, (y * t1 - x * t2) / denom

def _var_ngon(x, y, *args):
    """Polygonal distortion — crystalline structures."""
    r = np.sqrt(x**2 + y**2) + 1e-10
    theta = np.arctan2(y, x)
    n = 5
    p = 2 * np.pi / n
    phi = theta - p * np.floor(theta / p)
    phi = np.where(phi > p / 2, phi - p, phi)
    factor = (np.cos(p / 2) / (np.cos(phi) + 1e-10)) / r
    return factor * x, factor * y

def _var_bent(x, y, *args):
    """Piecewise distortion — adds asymmetry."""
    return np.where(x >= 0, x, 2 * x), np.where(y >= 0, y, y / 2)

def _var_blur(x, y, *args):
    """True stochastic blur variation for soft glow backgrounds."""
    N = len(x)
    rng = args[0] if args else None
    if rng is None:
        rng = np.random.default_rng()
    r = rng.uniform(0, 1, N)
    theta = rng.uniform(0, 2 * np.pi, N)
    return r * np.cos(theta), r * np.sin(theta)

_VARIATION_MAP = {
    'linear': _var_linear, 'sinusoidal': _var_sinusoidal,
    'spherical': _var_spherical, 'swirl': _var_swirl,
    'horseshoe': _var_horseshoe, 'polar': _var_polar,
    'spiral': _var_spiral, 'hyperbolic': _var_hyperbolic,
    'julia': _var_julia, 'disc': _var_disc,
    'heart': _var_heart, 'diamond': _var_diamond,
    'rings': _var_rings, 'waves': _var_waves,
    'eyefish': _var_eyefish, 'bubble': _var_bubble,
    'curl': _var_curl, 'ngon': _var_ngon,
    'bent': _var_bent, 'blur': _var_blur,
}

# ── Palettes ──────────────────────────────────────────────────────────────────
# All palettes are 256-entry LUTs for rich, multi-hue color like Electric Sheep.
# Each palette traverses multiple hues rather than being monochrome.

def _build_lut(stops):
    """Build a 256-entry RGB LUT from (position, r, g, b) color stops."""
    lut = np.zeros((256, 3))
    for i in range(len(stops) - 1):
        p0, r0, g0, b0 = stops[i]
        p1, r1, g1, b1 = stops[i + 1]
        idx0 = int(p0 * 255)
        idx1 = min(int(p1 * 255), 255)
        for j in range(idx0, idx1 + 1):
            t = (j - idx0) / max(1, idx1 - idx0)
            lut[j] = [r0 + t * (r1 - r0), g0 + t * (g1 - g0), b0 + t * (b1 - b0)]
    return lut

def _lut_palette(t, lut):
    """Map float [0,1] array through a 256-entry LUT → (H, W, 3)."""
    indices = np.clip((t * 255).astype(int), 0, 255)
    return lut[indices]


def _lut_palette_smooth(t, lut):
    """As _lut_palette, but interpolating between entries instead of snapping.

    `(t * 255).astype(int)` takes the nearest stop, so an image can hold at most
    256 distinct colours no matter how smooth the underlying value field is — a
    720x720 deep zoom came out with 230 of them, and the banding is plainly
    visible. The toy Starkind linked evaluates a continuous function per channel
    instead, which is most of why its output looks better than ours.
    """
    x = np.clip(t, 0.0, 1.0) * 255.0
    i0 = np.floor(x).astype(np.int32)
    i1 = np.minimum(i0 + 1, 255)
    f = (x - i0)[..., np.newaxis]
    return lut[i0] * (1.0 - f) + lut[i1] * f


def _cyclic(t, cycles: float):
    """Repeat a [0,1] ramp `cycles` times, mirroring so it never seams.

    A sawtooth would jump from the last colour back to the first at every
    boundary. Mirroring (ping-pong) makes any palette cycle seamlessly, which is
    what lets a deep view band repeatedly — the `colour_period` term in the
    weirdly.net config — instead of spending its whole range on one traverse.
    """
    frac = np.modf(np.clip(t, 0.0, 1.0) * max(cycles, 1e-6))[0]
    return 1.0 - np.abs(2.0 * frac - 1.0)

# Electric Sheep-style multi-hue palettes — each traverses 3+ distinct hues
_LUT_ELECTRIC = _build_lut([
    (0.0,  0.02, 0.00, 0.10), (0.10, 0.10, 0.02, 0.35),
    (0.22, 0.30, 0.05, 0.65), (0.35, 0.15, 0.20, 0.85),
    (0.48, 0.05, 0.50, 0.90), (0.60, 0.10, 0.75, 0.80),
    (0.72, 0.40, 0.90, 0.60), (0.85, 0.80, 0.95, 0.40),
    (1.0,  1.00, 0.95, 0.70),
])
_LUT_EMBER = _build_lut([
    (0.0,  0.05, 0.00, 0.00), (0.12, 0.25, 0.02, 0.00),
    (0.25, 0.55, 0.05, 0.00), (0.38, 0.80, 0.15, 0.02),
    (0.50, 0.95, 0.35, 0.05), (0.62, 1.00, 0.55, 0.10),
    (0.75, 1.00, 0.75, 0.20), (0.88, 0.95, 0.85, 0.50),
    (1.0,  0.90, 0.80, 0.70),
])
_LUT_ACID = _build_lut([
    (0.0,  0.00, 0.05, 0.02), (0.12, 0.00, 0.20, 0.05),
    (0.25, 0.05, 0.45, 0.10), (0.38, 0.20, 0.70, 0.15),
    (0.50, 0.50, 0.85, 0.20), (0.62, 0.80, 0.90, 0.30),
    (0.75, 0.95, 0.80, 0.50), (0.88, 0.90, 0.60, 0.75),
    (1.0,  0.75, 0.45, 0.90),
])
_LUT_VOID = _build_lut([
    (0.0,  0.05, 0.00, 0.05), (0.12, 0.20, 0.00, 0.15),
    (0.25, 0.45, 0.02, 0.30), (0.38, 0.65, 0.05, 0.45),
    (0.50, 0.80, 0.10, 0.55), (0.62, 0.85, 0.25, 0.60),
    (0.75, 0.75, 0.45, 0.70), (0.88, 0.55, 0.60, 0.85),
    (1.0,  0.40, 0.70, 0.95),
])
_LUT_AURORA = _build_lut([
    (0.0,  0.00, 0.08, 0.05), (0.12, 0.00, 0.25, 0.15),
    (0.25, 0.05, 0.50, 0.25), (0.38, 0.15, 0.70, 0.35),
    (0.50, 0.35, 0.80, 0.45), (0.62, 0.60, 0.75, 0.55),
    (0.75, 0.80, 0.55, 0.65), (0.88, 0.90, 0.40, 0.80),
    (1.0,  0.85, 0.50, 0.95),
])
_LUT_GHOST = _build_lut([
    (0.0,  0.02, 0.02, 0.08), (0.12, 0.08, 0.08, 0.25),
    (0.25, 0.15, 0.15, 0.45), (0.38, 0.25, 0.25, 0.65),
    (0.50, 0.40, 0.35, 0.80), (0.62, 0.55, 0.50, 0.85),
    (0.75, 0.70, 0.65, 0.88), (0.88, 0.82, 0.78, 0.90),
    (1.0,  0.90, 0.88, 0.92),
])
_LUT_DEEP_OCEAN = _build_lut([
    (0.0,  0.00, 0.00, 0.08), (0.12, 0.02, 0.05, 0.25),
    (0.25, 0.05, 0.12, 0.50), (0.38, 0.03, 0.30, 0.70),
    (0.50, 0.05, 0.50, 0.82), (0.62, 0.20, 0.65, 0.88),
    (0.75, 0.45, 0.78, 0.90), (0.88, 0.70, 0.85, 0.88),
    (1.0,  0.85, 0.90, 0.85),
])
_LUT_SOLAR_FLARE = _build_lut([
    (0.0,  0.05, 0.00, 0.00), (0.10, 0.20, 0.02, 0.00),
    (0.22, 0.50, 0.08, 0.00), (0.35, 0.80, 0.18, 0.02),
    (0.48, 0.95, 0.40, 0.05), (0.60, 1.00, 0.60, 0.10),
    (0.72, 0.95, 0.75, 0.25), (0.85, 0.85, 0.80, 0.55),
    (1.0,  0.80, 0.70, 0.80),
])
_LUT_BIOLUME = _build_lut([
    (0.0,  0.00, 0.05, 0.08), (0.12, 0.00, 0.15, 0.18),
    (0.25, 0.02, 0.35, 0.25), (0.38, 0.08, 0.55, 0.35),
    (0.50, 0.25, 0.72, 0.50), (0.62, 0.50, 0.65, 0.65),
    (0.75, 0.72, 0.50, 0.78), (0.88, 0.88, 0.45, 0.88),
    (1.0,  0.92, 0.55, 0.95),
])
_LUT_NEBULA = _build_lut([
    (0.0,  0.03, 0.00, 0.08), (0.12, 0.12, 0.02, 0.25),
    (0.25, 0.30, 0.05, 0.50), (0.38, 0.50, 0.12, 0.65),
    (0.50, 0.42, 0.30, 0.78), (0.62, 0.30, 0.50, 0.85),
    (0.75, 0.25, 0.68, 0.88), (0.88, 0.55, 0.80, 0.90),
    (1.0,  0.80, 0.85, 0.88),
])

PALETTES = {
    'electric':    lambda t: _lut_palette(t, _LUT_ELECTRIC),
    'ember':       lambda t: _lut_palette(t, _LUT_EMBER),
    'acid':        lambda t: _lut_palette(t, _LUT_ACID),
    'void':        lambda t: _lut_palette(t, _LUT_VOID),
    'aurora':      lambda t: _lut_palette(t, _LUT_AURORA),
    'ghost':       lambda t: _lut_palette(t, _LUT_GHOST),
    'deep_ocean':  lambda t: _lut_palette(t, _LUT_DEEP_OCEAN),
    'solar_flare': lambda t: _lut_palette(t, _LUT_SOLAR_FLARE),
    'biolume':     lambda t: _lut_palette(t, _LUT_BIOLUME),
    'nebula':      lambda t: _lut_palette(t, _LUT_NEBULA),
}

# The same tables, unwrapped. The flame renderer wants the nearest-stop lookup
# it was tuned against; the mandelbrot path interpolates them instead.
PALETTE_LUTS = {
    'electric': _LUT_ELECTRIC, 'ember': _LUT_EMBER, 'acid': _LUT_ACID,
    'void': _LUT_VOID, 'aurora': _LUT_AURORA, 'ghost': _LUT_GHOST,
    'deep_ocean': _LUT_DEEP_OCEAN, 'solar_flare': _LUT_SOLAR_FLARE,
    'biolume': _LUT_BIOLUME, 'nebula': _LUT_NEBULA,
}


# ── Mandelbrot locations and the weirdly.net config format ────────────────────

# `span` is the half-width of the view in complex units, so a smaller number is
# a deeper zoom. The original six targets all sat between 0.003 and 0.02 — the
# familiar postcard views. Starkind shared a location eleven orders of magnitude
# deeper, which is where the set stops looking like a picture of itself and
# starts producing the layered, organic imagery he was asking about.
MANDELBROT_TARGETS = [
    # (name, center_x, center_y, span)
    ("classic spiral",   -0.7269,               0.1889,                 5e-3),
    ("seahorse valley",  -0.1592,               1.0317,                 1e-2),
    ("antenna tip",      -1.7686,               0.0042,                 5e-3),
    ("mini brot",        -0.5251,               0.5255,                 2e-2),
    ("spiral arm",       -0.745,                0.186,                  3e-3),
    ("double spiral",    -1.256,                0.382,                  8e-3),
    # Deep field. Double precision holds to roughly 1e-15 of absolute
    # coordinate, so a span of 1e-11 still resolves cleanly at this size.
    ("starkind's antenna", -1.7689411331682035, -0.002827913661875118,  1.48e-11),
    ("deep valley",      -0.7436438870371587,   0.1318259042243799,     2e-9),
    ("elephant hollow",   0.2929859127507,       0.6117848324958,       1e-8),
    ("triple spiral",    -0.088,                 0.654,                 5e-7),
]


def parse_mandelbrot_url(url: str) -> dict | None:
    """Pull a viewport out of a weirdly.net/webtoys/mandelbrot config URL.

    The format is a flat comma-separated list after `?config=`:

        v1, centre_x, centre_y, span_x, span_y, max_iter, ...colour terms...

    Everything past max_iter describes that toy's own colouring model and has no
    counterpart here, so it is read and discarded. Returns None for anything
    that is not recognisably this format — a bad URL should fall back to a random
    location, never raise at a person.
    """
    if not url or "config=" not in url:
        return None
    try:
        raw = url.split("config=", 1)[1].split("#")[0].split("&")[0]
        parts = raw.split(",")
        if len(parts) < 6 or not parts[0].startswith("v"):
            return None
        cx, cy, sx, sy = (float(parts[i]) for i in range(1, 5))
        max_iter = int(float(parts[5]))
    except (ValueError, IndexError):
        return None

    span = max(abs(sx), abs(sy))
    # Sanity: a span of zero renders one point, and anything wider than the set
    # is just the whole set. Neither is what the link meant.
    if not (1e-14 < span < 4.0):
        return None
    if not (-2.5 < cx < 1.5 and -2.0 < cy < 2.0):
        return None
    return {
        "center": (cx, cy),
        "span": span,
        "max_iter": int(np.clip(max_iter, 64, 8000)),
    }


def depth_of(span: float) -> float:
    """Zoom depth as a base-10 exponent: 0 at the full set, ~11 very deep."""
    return math.log10(3.0 / max(span, 1e-14))


def _iterations_for_span(span: float, requested: int | None = None) -> int:
    """Iteration budget for a zoom depth.

    A fixed 256 was the real limit on the old renderer: iteration count has to
    grow with depth or the detail that only appears after a few hundred
    iterations never resolves, and the frame saturates into one flat colour.
    """
    if requested:
        return int(np.clip(requested, 64, 4000))
    depth = depth_of(span)
    return int(np.clip(256 + 210 * depth, 256, 2600))


class FractalFlameRenderer:
    """
    Pure NumPy fractal flame renderer.
    Based on the Draves/Reckase algorithm (flam3.com/flame_draves.pdf).
    Designed for CPU execution alongside Ollama — no GPU dependencies.

    Usage:
        renderer = FractalFlameRenderer()
        image, params = renderer.generate(seed=42)
    """

    # 2x supersampled: the chaos game accumulates at INTERNAL_RES and the
    # histogram is box-filtered down to OUTPUT_RES before tone mapping.
    INTERNAL_RES = 2160
    OUTPUT_RES = 1080
    N_POINTS = 500_000
    N_WARMUP = 40
    N_ITERATIONS = 60
    DENSITY_SIGMA = 1.2

    # ── Tone mapping ────────────────────────────────────────────────
    # Log density is anchored on percentiles of the OCCUPIED pixels rather
    # than scaled by a fixed constant. The previous pipeline used
    # `log1p(alpha * 500)` normalised by the max, which put a single-hit
    # pixel at 65% brightness — measured across ten seeds, five rendered
    # with a median brightness of 255 (pure white).
    GAMMA = 2.2
    BLACK_POINT_PCT = 12.0   # log-density percentile mapped to black
    WHITE_POINT_PCT = 99.8   # log-density percentile mapped to white
    EXPOSURE = 1.20

    # Density estimation: blur strength at zero density, falling to zero at
    # full density. flam3 blurs sparse regions to hide sampling noise and
    # leaves dense regions sharp; the old code added an ungated
    # `narrow_blur * 0.2` to every pixel, softening every filament.
    # Measured across twelve seeds, 0.25 gave the best mean occupancy and is
    # half the smoothing of the value it replaced.
    DE_STRENGTH = 0.35
    DE_SIGMA = 2.5

    # Bloom weights, roughly half the previous values. At the old 0.45 total
    # the final image was ~31% blur by weight.
    BLOOM = ((2.0, 0.10), (9.0, 0.10), (28.0, 0.05))

    VIBRANCY = 0.95       # flam3 vibrancy: 1.0 = full color preservation
    HIGHLIGHT_POWER = 0.5 # flam3 highlight power: controls bright area handling

    # Parameters are screened by a cheap probe before anything is rendered,
    # so a generous probe budget costs a fraction of one full render.
    MAX_PROBES = 12
    PROBE_RES = 384
    PROBE_POINTS = 60_000
    PROBE_ITERATIONS = 25
    # Fraction of the histogram that must be occupied. The lower bound
    # rejects degenerate attractors that collapse onto a few thin curves
    # (one measured seed put every point on 0.5% of pixels and still passed
    # the old gate at "100% coverage", because that gate was measuring the
    # tinted background rather than the fractal).
    MIN_OCCUPANCY = 0.12
    # Contrast of the log-density field. A uniform fog has structure but no
    # composition; this rejects the flattest results.
    MIN_DENSITY_CONTRAST = 0.28

    def generate(self, seed=None, palette_name=None):
        """
        Generate a fractal flame image, screening parameters before rendering.

        A random flame system is frequently degenerate — it collapses onto a
        few thin curves, or fills the frame with featureless fog. Those are
        properties of the parameters, so they can be detected from a cheap
        low-resolution chaos game (~0.3s) instead of a full render (~8s).
        Only parameters that pass are rendered at full quality, which makes
        being picky affordable.

        Args:
            seed: Random seed for reproducibility. None = random.
            palette_name: Force a specific palette. None = random.

        Returns:
            (PIL.Image.Image, dict) — the rendered image and its parameter dict.
        """
        best_seed, best_score, best_stats = None, -1.0, None

        # Retry seeds are derived from the caller's seed, so `!art --seed 42`
        # reproduces the same image even when the first parameters are
        # rejected. Previously each retry drew from an unseeded RNG, which
        # made a seeded request reproducible only if it happened to pass the
        # gate on the first try.
        seed_rng = np.random.default_rng(seed)

        for attempt in range(self.MAX_PROBES):
            attempt_seed = seed if attempt == 0 else int(
                seed_rng.integers(0, 2 ** 63 - 1)
            )
            stats = self._probe(attempt_seed, palette_name)

            occupancy, contrast = stats["occupancy"], stats["density_contrast"]
            # Prefer a flame that fills a fair share of the frame and has
            # tonal range, without rewarding fog for being everywhere.
            score = min(occupancy / self.MIN_OCCUPANCY, 1.0) * contrast
            if score > best_score:
                best_seed, best_score, best_stats = attempt_seed, score, stats

            if occupancy >= self.MIN_OCCUPANCY and contrast >= self.MIN_DENSITY_CONTRAST:
                if attempt > 0:
                    log_info(f"[art] Parameters accepted after {attempt + 1} probes "
                             f"(occupancy={occupancy:.1%}, contrast={contrast:.2f})")
                return self._generate_single(attempt_seed, palette_name)

            log_debug(f"[art] Probe {attempt + 1}/{self.MAX_PROBES} rejected: "
                      f"occupancy={occupancy:.1%} (min {self.MIN_OCCUPANCY:.0%}), "
                      f"contrast={contrast:.2f} (min {self.MIN_DENSITY_CONTRAST:.2f})")

        log_warning(f"[art] No parameter set passed in {self.MAX_PROBES} probes — "
                    f"rendering the best of them (score={best_score:.2f}, "
                    f"occupancy={best_stats['occupancy']:.1%})")
        return self._generate_single(best_seed, palette_name)

    # Roadmap 57-4, visual self-expression: palette follows mood rather than
    # being drawn uniformly. Warm/high-valence states pull toward ember and
    # solar_flare, low-valence toward void and deep_ocean, high arousal toward
    # electric and acid. It is a bias, not a rule — the remaining palettes stay
    # reachable so output does not become monotonous.
    MOOD_PALETTES = {
        "bright": ("solar_flare", "ember", "aurora", "acid"),
        "dark": ("void", "deep_ocean", "ghost", "nebula"),
        "charged": ("electric", "acid", "solar_flare"),
        "calm": ("biolume", "aurora", "deep_ocean", "ghost"),
    }

    def _mood_palette(self, rng) -> str:
        """Pick a palette biased by Kaia's current emotional state.

        Stream-neutral by construction. The base draw is made from the seeded
        generator exactly as before, so the flame *geometry* for a given seed is
        unchanged; the mood substitution then runs on a separate generator
        derived from that draw. Consuming a different number of draws here
        would shift every downstream parameter and silently change what a seed
        renders.
        """
        all_names = list(PALETTES.keys())
        base = str(rng.choice(all_names))       # the one and only main-stream draw

        try:
            from utils.core.kaia_mood import emotional_arc
            valence = float(emotional_arc.valence)
            arousal = float(emotional_arc.arousal)
        except Exception:
            return base

        if arousal > 0.7:
            bucket = "charged"
        elif valence > 0.25:
            bucket = "bright"
        elif valence < -0.15:
            bucket = "dark"
        else:
            bucket = "calm"

        preferred = [p for p in self.MOOD_PALETTES[bucket] if p in PALETTES]
        if not preferred or base in preferred:
            return base

        # Separate generator: deterministic for a given (base draw, mood), and
        # it cannot perturb the main stream. crc32 rather than hash() — the
        # latter is salted per process, so the same seed would render a
        # different palette after every restart.
        side = np.random.default_rng(zlib.crc32(f"{base}:{bucket}".encode()))
        # 70/30 so her state shows without collapsing the range.
        return str(side.choice(preferred)) if side.random() < 0.7 else base

    def _build_system(self, seed, palette_name):
        """Draw a complete flame system from a seed.

        Split out so the probe and the full render can share one definition of
        "what this seed means" — the probe would be worthless if it screened
        different parameters than the render then used.
        """
        rng = np.random.default_rng(seed)
        actual_seed = seed if seed is not None else rng.bit_generator.seed_seq.entropy

        if palette_name and palette_name in PALETTES:
            pal_name = palette_name
        else:
            pal_name = self._mood_palette(rng)

        # Always use rotational symmetry — k=1 produces sparse, uninteresting flames
        symmetry_k = int(rng.choice([3, 4, 5, 5, 6]))
        n_transforms = int(rng.integers(2, 5))
        transforms, weights, color_speed = self._random_transforms(rng, n_transforms)

        # The post-affine is passed through: it was previously hardcoded to
        # None at this point, so the secondary affine that _random_transforms
        # generates for ~40% of transforms was computed, recorded in the params
        # dict, and then never applied to a single point.
        compiled = [
            (affine, [_VARIATION_MAP[v] for v in var_names], color_i, post_affine, var_weights)
            for affine, var_names, color_i, post_affine, var_weights in transforms
        ]
        return dict(rng=rng, actual_seed=actual_seed, pal_name=pal_name,
                    palette_fn=PALETTES[pal_name], symmetry_k=symmetry_k,
                    n_transforms=n_transforms, transforms=transforms,
                    compiled=compiled, weights=weights, color_speed=color_speed)

    def _probe(self, seed, palette_name):
        """Cheap low-resolution chaos game, for screening parameters only.

        Returns the same {occupancy, density_contrast} figures the full render
        reports, measured on a small histogram. Roughly 3% of the cost.
        """
        try:
            sysm = self._build_system(seed, palette_name)
            res = self.PROBE_RES
            saved_points, saved_iters = self.N_POINTS, self.N_ITERATIONS
            try:
                self.N_POINTS, self.N_ITERATIONS = self.PROBE_POINTS, self.PROBE_ITERATIONS
                _r, _g, _b, alpha = self._chaos_game(
                    sysm["rng"], sysm["compiled"], sysm["weights"], sysm["color_speed"],
                    res, res, sysm["symmetry_k"], None, sysm["palette_fn"],
                )
            finally:
                self.N_POINTS, self.N_ITERATIONS = saved_points, saved_iters
            return self._histogram_stats(alpha)
        except Exception as e:
            log_debug(f"[art] Probe failed ({e}); assuming parameters are usable.")
            return {"occupancy": 1.0, "density_contrast": 1.0}

    def _histogram_stats(self, alpha_acc):
        """Quality figures for a density histogram.

        Measured on the histogram rather than the finished image. The previous
        gate measured non-black pixels in the *tinted* output, so the ambient
        background counted as fractal: one flame that put every point on 0.5%
        of pixels was scored at "100% coverage" and shipped.
        """
        occupied = alpha_acc > 0
        n_occupied = int(occupied.sum())
        if n_occupied == 0:
            return {"occupancy": 0.0, "density_contrast": 0.0}
        logs = np.log1p(alpha_acc[occupied])
        black = np.percentile(logs, self.BLACK_POINT_PCT)
        white = np.percentile(logs, self.WHITE_POINT_PCT)
        return {"occupancy": n_occupied / alpha_acc.size,
                "density_contrast": float((white - black) / (white + 1e-12))}

    def _generate_single(self, seed=None, palette_name=None):
        """Render one flame at full quality from a seed."""
        t_start = time.time()
        sysm = self._build_system(seed, palette_name)
        rng = sysm["rng"]
        actual_seed = sysm["actual_seed"]
        pal_name = sysm["pal_name"]
        palette_fn = sysm["palette_fn"]
        symmetry_k = sysm["symmetry_k"]
        n_transforms = sysm["n_transforms"]
        transforms = sysm["transforms"]
        compiled_transforms = sysm["compiled"]
        weights = sysm["weights"]
        color_speed = sysm["color_speed"]

        W = H = self.INTERNAL_RES

        # Chaos game
        r_acc, g_acc, b_acc, a_acc = self._chaos_game(
            rng, compiled_transforms, weights, color_speed, W, H, symmetry_k, None, palette_fn
        )

        # Render
        img, render_stats = self._render(r_acc, g_acc, b_acc, a_acc, W, H)

        render_time = time.time() - t_start
        log_info(f"[art] Fractal flame rendered in {render_time:.1f}s "
                 f"(seed={actual_seed}, palette={pal_name}, k={symmetry_k})")

        # Build params dict
        params = {
            "type": "flame",
            "seed": int(actual_seed) if actual_seed is not None else None,
            "n_transforms": n_transforms,
            "symmetry_k": symmetry_k,
            "transforms": [
                {
                    "affine": item[0].tolist(),
                    "variations": list(item[1]),
                    "variation_weights": [round(float(w), 4) for w in item[4]],
                    "color": float(item[2]),
                    "post_affine": item[3].tolist() if item[3] is not None else None,
                }
                for item in transforms
            ],
            "color_speed": round(color_speed, 3),
            "palette": pal_name,
            "n_points": self.N_POINTS,
            "n_iterations": self.N_ITERATIONS,
            "density_sigma": self.DENSITY_SIGMA,
            "render_time_s": round(render_time, 2),
            "resolution": [self.OUTPUT_RES, self.OUTPUT_RES],
            # Quality figures measured on the histogram, for the retry gate.
            "occupancy": round(render_stats["occupancy"], 4),
            "density_contrast": round(render_stats["density_contrast"], 4),
        }

        return img, params

    def generate_mandelbrot(self, seed=None, palette_name=None, *,
                            center=None, span=None, max_iter=None,
                            location_name=None):
        """Render a Mandelbrot viewport.

        Called with no viewport it picks a location at random. `center`/`span`
        target one explicitly, which is how a shared weirdly.net link is
        honoured — see `parse_mandelbrot_url`.

        Three things were wrong with the previous version and all three showed
        in the image:

        * `max_iter` was pinned at 256 at every depth. Detail that only resolves
          after several hundred iterations never appeared, so a deep zoom came
          out as one flat colour.
        * Points that never escaped kept `M = 0`, and so did the points that
          escaped immediately — the interior of the set was drawn in the same
          colour as the outermost band, which muddied every edge in the frame.
        * Escape values were mapped linearly over `[0, max_iter]`. Deep views
          use a narrow band of that range, so the palette was compressed into a
          few adjacent LUT entries; equalising by rank is what makes the
          layering visible.
        """
        t_start = time.time()
        rng = np.random.default_rng(seed)
        actual_seed = seed if seed is not None else rng.bit_generator.seed_seq.entropy

        if center is not None and span is not None:
            cx, cy = float(center[0]), float(center[1])
            span = float(span)
            name = location_name or "shared coordinates"
        else:
            name, cx, cy, span = MANDELBROT_TARGETS[int(rng.integers(len(MANDELBROT_TARGETS)))]
            # Jitter proportionally, so a deep target stays deep. A fixed
            # absolute jitter would have thrown a 1e-11 view clean out of the
            # interesting region.
            cx += float(rng.uniform(-span * 0.25, span * 0.25))
            cy += float(rng.uniform(-span * 0.25, span * 0.25))

        iters = _iterations_for_span(span, max_iter)

        if palette_name and palette_name in PALETTES:
            pal_name = palette_name
        else:
            pal_name = rng.choice(list(PALETTES.keys()))
        palette_fn = PALETTES[pal_name]

        W = H = 720
        # Supersample. The boundary of the set is detail all the way down, so a
        # single sample per pixel aliases every filament into a dotted line.
        # 2x2 is the cheapest ratio that visibly fixes it.
        SS = 2
        WS, HS = W * SS, H * SS
        x = np.linspace(cx - span, cx + span, WS)
        y = np.linspace(cy - span * H / W, cy + span * H / W, HS)
        C = (x[np.newaxis, :] + 1j * y[:, np.newaxis]).ravel()

        # Iterate only the points still in play. The previous loop rebuilt a
        # boolean-masked copy of the full grid every pass and called np.abs —
        # a square root — over all 518,400 points each time, including the ones
        # that had already escaped hundreds of iterations earlier.
        smooth = np.zeros(C.size, dtype=np.float64)
        active = np.arange(C.size)
        Za = np.zeros(C.size, dtype=np.complex128)
        Ca = C

        for i in range(iters):
            Za = Za * Za + Ca
            mag2 = Za.real * Za.real + Za.imag * Za.imag
            escaped = mag2 > 4.0
            if escaped.any():
                # Smooth (continuous) escape time. log2|Z| is half of log2|Z|^2,
                # which avoids the square root entirely.
                with np.errstate(divide='ignore', invalid='ignore'):
                    nu = i + 1 - np.log2(np.maximum(0.5 * np.log2(mag2[escaped]), 1e-12))
                smooth[active[escaped]] = np.nan_to_num(nu, nan=float(i + 1))
                keep = ~escaped
                active = active[keep]
                Za = Za[keep]
                Ca = Ca[keep]
                if active.size == 0:
                    break

        interior = np.zeros(C.size, dtype=bool)
        interior[active] = True

        # Equalise by rank across the escaped points only, so the palette spans
        # whatever narrow band of escape times this particular view occupies.
        t = np.zeros(C.size, dtype=np.float64)
        outside = ~interior
        if outside.any():
            vals = smooth[outside]
            order = np.argsort(vals, kind="stable")
            ranks = np.empty(vals.size, dtype=np.float64)
            ranks[order] = np.linspace(0.0, 1.0, vals.size)
            # A little linear blend keeps some of the true gradient, which reads
            # as depth; pure equalisation alone can look posterised.
            lin = np.clip(vals / max(iters, 1), 0.0, 1.0)
            t[outside] = 0.78 * ranks + 0.22 * lin

        # Cycle the palette instead of spending its whole range on one traverse.
        # This is the `colour_period` term in the weirdly.net config: a deep view
        # occupies a narrow, dense band of escape times, and repeating the ramp
        # through it is what makes the layering legible at every scale. Deeper
        # views carry more structure, so they get more cycles.
        cycles = float(np.clip(1.0 + depth_of(span) / 2.0, 1.0, 7.0))
        t = _cyclic(t, cycles)

        lut = PALETTE_LUTS.get(pal_name)
        # Interpolated, not nearest-stop: the nearest-stop lookup caps an image
        # at 256 colours and bands every gradient.
        rgb = (_lut_palette_smooth(t.reshape(HS, WS), lut) if lut is not None
               else palette_fn(t.reshape(HS, WS)))
        # The set itself is black. It is the one region with no escape time, and
        # giving it its own value is what separates it from the fastest-escaping
        # band next to it.
        rgb = np.where(interior.reshape(HS, WS)[:, :, np.newaxis], 0.0, rgb)
        # Box-downsample the supersampled buffer.
        rgb = rgb.reshape(H, SS, W, SS, 3).mean(axis=(1, 3))
        img_array = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)

        render_time = time.time() - t_start
        depth = depth_of(span)
        log_info(f"[art] Mandelbrot '{name}' rendered in {render_time:.1f}s "
                 f"(span={span:.3e}, ~1e{depth:.1f} zoom, iters={iters}, "
                 f"interior={100.0 * interior.mean():.1f}%, palette={pal_name})")

        params = {
            "type": "mandelbrot",
            "seed": int(actual_seed) if actual_seed is not None else None,
            "location": name,
            "center": [cx, cy],
            "span": span,
            "zoom": f"1e{depth:.1f}",
            # Numeric alongside the display string: "1e11.3" is for the footer,
            # not for anything that needs to compare depths.
            "zoom_exponent": round(depth, 2),
            "max_iter": iters,
            "interior_fraction": round(float(interior.mean()), 4),
            "colour_cycles": round(cycles, 2),
            "supersample": SS,
            "palette": pal_name,
            "render_time_s": round(render_time, 2),
            "resolution": [W, H],
        }

        return Image.fromarray(img_array), params

    # ── Internal Methods ──────────────────────────────────────────────────────

    # Variations that produce dense, space-filling patterns
    # 'blur' deliberately excluded: it guarantees density by filling the
    # frame with uniform noise, which is density without structure.
    _DENSE_VARIATIONS = {'julia', 'swirl', 'waves', 'eyefish', 'curl', 'linear'}

    def _random_transforms(self, rng, n_transforms=3):
        """Generate variations matching true flam3 xml structure.
        
        Ensures at least one transform uses a 'dense' variation to prevent
        degenerate all-contracting combos that produce sparse black images.
        """
        transforms = []
        weights = np.abs(rng.standard_normal(n_transforms))
        weights /= weights.sum()

        base_colors = np.linspace(0.05, 0.95, n_transforms)
        jitter = rng.uniform(-0.08, 0.08, n_transforms)
        color_values = np.clip(base_colors + jitter, 0, 1)

        # Track which transform will get the forced dense variation
        dense_target = int(rng.integers(n_transforms))
        all_var_names = []

        for _idx in range(n_transforms):
            # Enforce strict contraction: scale must be < 1
            scale_x = float(rng.uniform(0.4, 0.9))
            scale_y = float(rng.uniform(0.4, 0.9))
            angle = float(rng.uniform(0, 2 * np.pi))
            
            cos_a = np.cos(angle)
            sin_a = np.sin(angle)
            
            a = scale_x * cos_a
            b = -scale_y * sin_a
            d = scale_x * sin_a
            e = scale_y * cos_a
            
            c = float(rng.uniform(-1.0, 1.0))
            f = float(rng.uniform(-1.0, 1.0))
            affine = np.array([a, b, c, d, e, f])

            # Pick 1-3 variations with per-variation weights.
            #
            # flam3 blends variations as a WEIGHTED sum. The previous code
            # summed them and divided by the count, so a two-variation
            # transform was always an even 50/50 average — which mushes two
            # distinct shapes into something with the character of neither.
            # That is the main reason some flames read as crisp and others as
            # formless fog. Weights are drawn so one variation usually
            # dominates and the others act as accents.
            n_vars = int(rng.choice([1, 2, 2, 3]))
            var_names = list(rng.choice(PRIMARY_VARIATIONS, size=n_vars, replace=False))
            # A Dirichlet with alpha < 1 concentrates mass on one component.
            var_weights = rng.dirichlet(np.full(n_vars, 0.6))
            # ACCENT_VARIATIONS are excluded from selection entirely. `blur`
            # is the only member, and even at a 12% weight it painted visible
            # out-of-focus discs across the frame — the literal blur in
            # "sometimes blurry". It stays defined so saved parameter dicts
            # from older renders still replay.
            all_var_names.append(var_names)
            
            color_i = float(color_values[_idx])

            # Optional post-transform: subtle secondary affine after variation
            post_affine = None
            if rng.random() < 0.4:
                ps = float(rng.uniform(0.6, 1.0))  # mild scale
                pa_angle = float(rng.uniform(0, 2 * np.pi))
                pa_cos = ps * np.cos(pa_angle)
                pa_sin = ps * np.sin(pa_angle)
                pc = float(rng.uniform(-0.3, 0.3))
                pf = float(rng.uniform(-0.3, 0.3))
                post_affine = np.array([pa_cos, -pa_sin, pc, pa_sin, pa_cos, pf])

            transforms.append((affine, var_names, color_i, post_affine, var_weights))

        # Guarantee at least one dense variation across all transforms
        has_dense = any(
            set(vn) & self._DENSE_VARIATIONS for vn in all_var_names
        )
        if not has_dense:
            # Inject a dense variation into the target transform
            dense_var = str(rng.choice(list(self._DENSE_VARIATIONS)))
            old_affine, old_vars, old_color, old_post, old_w = transforms[dense_target]
            new_vars = old_vars + [dense_var]
            # Give the injected variation a real share without erasing the
            # transform's existing character.
            new_w = np.append(old_w * 0.55, 0.45)
            transforms[dense_target] = (old_affine, new_vars, old_color, old_post, new_w)
            log_debug(f"[art] Injected dense variation '{dense_var}' into transform {dense_target}")

        return transforms, weights, rng.uniform(0.1, 0.4)

    def _chaos_game(self, rng, transforms, weights, color_speed, W, H, symmetry_k, final_xform=None, palette_fn=None):
        """Run the vectorized chaos game loop with multi-blend, post-transforms, and final transform."""
        N = self.N_POINTS
        x = rng.uniform(-1, 1, N)
        y = rng.uniform(-1, 1, N)
        c = rng.uniform(0, 1, N)  # color coordinate

        total_pixels = H * W
        r_flat = np.zeros(total_pixels, dtype=np.float64)
        g_flat = np.zeros(total_pixels, dtype=np.float64)
        b_flat = np.zeros(total_pixels, dtype=np.float64)
        a_flat = np.zeros(total_pixels, dtype=np.float64)

        n_transforms = len(transforms)

        # Precompute affine matrices as stacked arrays for vectorized lookup
        affines = np.array([t[0] for t in transforms])  # shape (n_transforms, 6)
        colors = np.array([t[2] for t in transforms])   # shape (n_transforms,)
        post_affines = [t[3] for t in transforms]  # list of arrays or None

        # 1. Warmup loop (without accumulation)
        for iteration in range(self.N_WARMUP):
            choices = rng.choice(n_transforms, size=N, p=weights)
            af = affines[choices]
            xa = af[:, 0] * x + af[:, 1] * y + af[:, 2]
            ya = af[:, 3] * x + af[:, 4] * y + af[:, 5]

            new_x = np.empty_like(xa)
            new_y = np.empty_like(ya)
            for i in range(n_transforms):
                mask = choices == i
                if not mask.any():
                    continue
                var_fns = transforms[i][1]
                var_ws = transforms[i][4]
                xi, yi = xa[mask], ya[mask]
                if len(var_fns) == 1:
                    vx, vy = var_fns[0](xi, yi, rng)
                else:
                    # Weighted sum, per flam3. An unweighted mean of two
                    # variations produces a shape with the character of
                    # neither; the weights let one dominate.
                    vx = np.zeros(xi.shape[0])
                    vy = np.zeros(xi.shape[0])
                    for vfn, vw in zip(var_fns, var_ws):
                        fx, fy = vfn(xi, yi, rng)
                        vx += vw * fx
                        vy += vw * fy
                pa = post_affines[i]
                if pa is not None:
                    vx, vy = pa[0] * vx + pa[1] * vy + pa[2], pa[3] * vx + pa[4] * vy + pa[5]
                new_x[mask] = vx
                new_y[mask] = vy

            x = new_x
            y = new_y

            np.clip(x, -1e4, 1e4, out=x)
            np.clip(y, -1e4, 1e4, out=y)
            bad = ~(np.isfinite(x) & np.isfinite(y))
            if bad.any():
                x[bad] = rng.uniform(-1, 1, bad.sum())
                y[bad] = rng.uniform(-1, 1, bad.sum())

        # 2. Viewport bounds fitting from warmed-up points
        if final_xform is not None:
            fc, fs = final_xform['affine']
            tx = fc * x - fs * y
            ty = fs * x + fc * y
            fx, fy = final_xform['var_fns'][0](tx, ty)
        else:
            fx, fy = x, y

        finite = np.isfinite(fx) & np.isfinite(fy)
        if not finite.any():
            xmin, xmax = -2.0, 2.0
            ymin, ymax = -2.0, 2.0
        else:
            p_lo_x, p_hi_x = np.percentile(fx[finite], [5, 95])
            p_lo_y, p_hi_y = np.percentile(fy[finite], [5, 95])
            pad_x = 0.05 * (p_hi_x - p_lo_x + 1e-10)
            pad_y = 0.05 * (p_hi_y - p_lo_y + 1e-10)
            cx_f = (p_lo_x + p_hi_x) / 2
            cy_f = (p_lo_y + p_hi_y) / 2
            half = max(p_hi_x - p_lo_x + 2 * pad_x, p_hi_y - p_lo_y + 2 * pad_y) / 2
            half = max(half, 0.1)
            xmin, xmax = cx_f - half, cx_f + half
            ymin, ymax = cy_f - half, cy_f + half

        x_scale = W / (xmax - xmin)
        y_scale = H / (ymax - ymin)

        # 3. Accumulation loop
        for iteration in range(self.N_ITERATIONS):
            choices = rng.choice(n_transforms, size=N, p=weights)
            af = affines[choices]
            xa = af[:, 0] * x + af[:, 1] * y + af[:, 2]
            ya = af[:, 3] * x + af[:, 4] * y + af[:, 5]

            new_x = np.empty_like(xa)
            new_y = np.empty_like(ya)
            for i in range(n_transforms):
                mask = choices == i
                if not mask.any():
                    continue
                var_fns = transforms[i][1]
                var_ws = transforms[i][4]
                xi, yi = xa[mask], ya[mask]
                if len(var_fns) == 1:
                    vx, vy = var_fns[0](xi, yi, rng)
                else:
                    # Weighted sum, per flam3. An unweighted mean of two
                    # variations produces a shape with the character of
                    # neither; the weights let one dominate.
                    vx = np.zeros(xi.shape[0])
                    vy = np.zeros(xi.shape[0])
                    for vfn, vw in zip(var_fns, var_ws):
                        fx, fy = vfn(xi, yi, rng)
                        vx += vw * fx
                        vy += vw * fy
                pa = post_affines[i]
                if pa is not None:
                    vx, vy = pa[0] * vx + pa[1] * vy + pa[2], pa[3] * vx + pa[4] * vy + pa[5]
                new_x[mask] = vx
                new_y[mask] = vy

            x = new_x
            y = new_y

            np.clip(x, -1e4, 1e4, out=x)
            np.clip(y, -1e4, 1e4, out=y)
            bad = ~(np.isfinite(x) & np.isfinite(y))
            if bad.any():
                x[bad] = rng.uniform(-1, 1, bad.sum())
                y[bad] = rng.uniform(-1, 1, bad.sum())

            c = c * (1.0 - color_speed) + colors[choices] * color_speed

            if final_xform is not None:
                fc, fs = final_xform['affine']
                tx = fc * x - fs * y
                ty = fs * x + fc * y
                fx, fy = final_xform['var_fns'][0](tx, ty)
            else:
                fx, fy = x, y

            # Accumulate the point set and all its rotational copies in a
            # single call. Each bincount allocates and adds a full
            # `total_pixels` array, so that fixed cost was previously paid
            # symmetry_k times per iteration; batching pays it once and
            # amortises the palette lookup over every copy. The resulting
            # histogram is bit-identical.
            if symmetry_k > 1:
                angles = (2 * np.pi / symmetry_k) * np.arange(symmetry_k)
                cos_a = np.cos(angles)[:, None]
                sin_a = np.sin(angles)[:, None]
                xs = (fx * cos_a - fy * sin_a).ravel()
                ys = (fx * sin_a + fy * cos_a).ravel()
                cs = np.tile(c, symmetry_k)
            else:
                xs, ys, cs = fx, fy, c

            self._accumulate_points(
                xs, ys, cs, xmin, ymin, x_scale, y_scale,
                W, H, total_pixels, r_flat, g_flat, b_flat, a_flat, palette_fn
            )

        r_acc = r_flat.reshape((H, W))
        g_acc = g_flat.reshape((H, W))
        b_acc = b_flat.reshape((H, W))
        a_acc = a_flat.reshape((H, W))
        return r_acc, g_acc, b_acc, a_acc

    @staticmethod
    def _accumulate_points(x, y, c, xmin, ymin, x_scale, y_scale,
                           W, H, total_pixels, r_flat, g_flat, b_flat, a_flat, palette_fn):
        """Accumulate points into the histogram using np.bincount."""
        px = ((x - xmin) * x_scale).astype(np.intp)
        py = ((y - ymin) * y_scale).astype(np.intp)
        valid = (px >= 0) & (px < W) & (py >= 0) & (py < H)
        if not valid.any():
            return

        # Fold the row offset in before masking so only one array is indexed.
        np.multiply(py, W, out=py)
        np.add(py, px, out=py)
        flat_idx = py[valid]

        rgb = palette_fn(c[valid])

        np.add(a_flat, np.bincount(flat_idx, minlength=total_pixels), out=a_flat,
               casting="unsafe")
        r_flat += np.bincount(flat_idx, weights=rgb[:, 0], minlength=total_pixels)
        g_flat += np.bincount(flat_idx, weights=rgb[:, 1], minlength=total_pixels)
        b_flat += np.bincount(flat_idx, weights=rgb[:, 2], minlength=total_pixels)

    def _render(self, r_acc, g_acc, b_acc, alpha_acc, W, H):
        """Tone-map an accumulated histogram into a finished image.

        Returns (PIL.Image, stats) where stats carries the quality figures the
        retry gate needs — they are properties of the histogram, not of the
        tinted output, so the gate cannot be fooled by a bright background.
        """
        # ── Step 0: Supersample down to the output resolution ─────────────────
        if W == self.INTERNAL_RES and H == self.INTERNAL_RES and W == 2 * self.OUTPUT_RES:
            r_acc = (r_acc[0::2, 0::2] + r_acc[1::2, 0::2] + r_acc[0::2, 1::2] + r_acc[1::2, 1::2]) / 4.0
            g_acc = (g_acc[0::2, 0::2] + g_acc[1::2, 0::2] + g_acc[0::2, 1::2] + g_acc[1::2, 1::2]) / 4.0
            b_acc = (b_acc[0::2, 0::2] + b_acc[1::2, 0::2] + b_acc[0::2, 1::2] + b_acc[1::2, 1::2]) / 4.0
            alpha_acc = (alpha_acc[0::2, 0::2] + alpha_acc[1::2, 0::2]
                         + alpha_acc[0::2, 1::2] + alpha_acc[1::2, 1::2]) / 4.0
            W = H = self.OUTPUT_RES

        occupied = alpha_acc > 0
        n_occupied = int(occupied.sum())
        stats = self._histogram_stats(alpha_acc)

        if n_occupied == 0:
            log_warning("[art] Empty histogram — all points escaped.")
            return Image.new("RGB", (W, H), (0, 0, 0)), stats

        # ── Step 1: Percentile-anchored log density ───────────────────────────
        # log1p on the raw counts, then a black and white point taken from the
        # distribution of occupied pixels. This is scale-free: it behaves the
        # same for a histogram peaking at 289 and one peaking at 1.4 million,
        # both of which occur in practice.
        log_density = np.log1p(alpha_acc)
        occupied_logs = log_density[occupied]
        black = np.percentile(occupied_logs, self.BLACK_POINT_PCT)
        white = np.percentile(occupied_logs, self.WHITE_POINT_PCT)
        span = white - black

        density_norm = np.clip((log_density - black) / (span + 1e-12), 0.0, 1.0)
        alpha_gamma = density_norm ** (1.0 / self.GAMMA)

        # Mean colour per pixel, scaled by the gamma-compressed density.
        rgb_acc = np.stack([r_acc, g_acc, b_acc], axis=-1)
        rgb_average = np.zeros_like(rgb_acc)
        rgb_average[occupied] = rgb_acc[occupied] / alpha_acc[occupied][..., np.newaxis]
        rgb_mapped = rgb_average * alpha_gamma[..., np.newaxis]

        # ── Step 2: Density-gated estimation ──────────────────────────────────
        # Blur weight falls off as the square of density, so the sparse outer
        # filaments are smoothed and the bright core keeps its detail. This is
        # a crossfade, not an addition: blurred content replaces sharp content
        # rather than being layered on top of it.
        sparse = ((1.0 - density_norm) ** 2)[..., np.newaxis] * self.DE_STRENGTH
        blurred = gaussian_filter(rgb_mapped, sigma=self.DE_SIGMA, axes=(0, 1))
        rgb_de = rgb_mapped * (1.0 - sparse) + blurred * sparse

        # ── Step 3: Auto-exposure with a soft shoulder ────────────────────────
        # The old final step divided by the 99th percentile of the *whole*
        # frame, background included, which drove everything above that value
        # to pure white.
        v_hi = np.percentile(rgb_de[occupied], 99.7)
        exposed = rgb_de / (v_hi + 1e-12) * self.EXPOSURE
        # Reinhard shoulder: linear near zero, rolling off towards 1.0.
        exposed = np.clip(exposed / (1.0 + exposed) * 2.0, 0.0, 1.0)

        # ── Step 4: Vibrancy blend ────────────────────────────────────────────
        gray = np.mean(exposed, axis=-1, keepdims=True)
        rgb_vib = np.clip(self.VIBRANCY * exposed + (1.0 - self.VIBRANCY) * gray, 0.0, 1.0)

        # ── Step 5: Multi-scale bloom ─────────────────────────────────────────
        bloomed = rgb_vib.copy()
        for sigma, weight in self.BLOOM:
            bloomed += gaussian_filter(rgb_vib, sigma=sigma, axes=(0, 1)) * weight
        rgb_bloomed = np.clip(bloomed, 0.0, 1.0)

        # ── Step 6: Near-black vignetted ground ───────────────────────────────
        # Tinted at ~3% of the mean flame colour so the frame reads as a dark
        # room rather than a coloured card. The previous 6% tint plus the
        # divide-by-percentile above is what produced flat cyan backgrounds.
        mean_color = rgb_bloomed[occupied].mean(axis=0)
        bg = np.maximum(mean_color * 0.035, np.array([0.008, 0.006, 0.014]))

        Y, X = np.ogrid[:H, :W]
        dist = np.sqrt((X - W / 2.0) ** 2 + (Y - H / 2.0) ** 2)
        vignette = 1.0 - np.clip(dist / np.sqrt(2.0 * (W / 2.0) ** 2), 0, 1) * 0.55
        blend = np.clip(density_norm * 3.0, 0, 1)[..., np.newaxis]
        rgb_final = rgb_bloomed * blend + (bg * vignette[..., np.newaxis]) * (1.0 - blend)

        return Image.fromarray((np.clip(rgb_final, 0, 1) * 255).astype(np.uint8)), stats
