"""
Kaia Art System — Fractal Flame Renderer
Pure NumPy/SciPy implementation. CPU-only (GPU reserved for Ollama).
Based on the Draves/Reckase algorithm (flam3.com/flame_draves.pdf).
"""
import time
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

def _var_linear(x, y):     return x, y
def _var_sinusoidal(x, y): return np.sin(x), np.sin(y)

def _var_spherical(x, y):
    r2 = x**2 + y**2 + 1e-10
    return x / r2, y / r2

def _var_swirl(x, y):
    r2 = x**2 + y**2
    return x * np.sin(r2) - y * np.cos(r2), x * np.cos(r2) + y * np.sin(r2)

def _var_horseshoe(x, y):
    r = np.sqrt(x**2 + y**2) + 1e-10
    return (x - y) * (x + y) / r, 2 * x * y / r

def _var_polar(x, y):
    r = np.sqrt(x**2 + y**2) + 1e-10
    theta = np.arctan2(y, x)
    return theta / np.pi, r - 1

def _var_spiral(x, y):
    r = np.sqrt(x**2 + y**2) + 1e-10
    theta = np.arctan2(y, x)
    return (np.cos(theta) + np.sin(r)) / r, (np.sin(theta) - np.cos(r)) / r

def _var_hyperbolic(x, y):
    r = np.sqrt(x**2 + y**2) + 1e-10
    theta = np.arctan2(y, x)
    return np.sin(theta) / r, r * np.cos(theta)

def _var_julia(x, y):
    """Classic Electric Sheep swirling organic tendrils."""
    r = np.sqrt(np.sqrt(x**2 + y**2) + 1e-10)
    theta = np.arctan2(y, x) * 0.5
    sign = np.where((x * 1000).astype(np.intp) % 2 == 0, 1.0, -1.0)
    theta = theta + sign * np.pi * 0.5
    return r * np.cos(theta), r * np.sin(theta)

def _var_disc(x, y):
    """Disc mapping — circular, mandala-like structures."""
    theta = np.arctan2(y, x) / np.pi
    r = np.pi * np.sqrt(x**2 + y**2)
    return theta * np.sin(r), theta * np.cos(r)

def _var_heart(x, y):
    """Heart-shaped distortion."""
    r = np.sqrt(x**2 + y**2)
    theta = np.arctan2(y, x)
    return r * np.sin(theta * r), -r * np.cos(theta * r)

def _var_diamond(x, y):
    """Diamond/gem-like faceted shapes."""
    r = np.sqrt(x**2 + y**2) + 1e-10
    theta = np.arctan2(y, x)
    return np.sin(theta) * np.cos(r), np.cos(theta) * np.sin(r)

def _var_rings(x, y):
    """Concentric ring patterns — halos and circles."""
    r = np.sqrt(x**2 + y**2)
    theta = np.arctan2(y, x)
    c2 = 0.36
    rmod = np.fmod(r + c2, 2 * c2) - c2 + r * (1 - c2)
    return rmod * np.cos(theta), rmod * np.sin(theta)

def _var_waves(x, y):
    """Sine wave distortion — flowing, fabric-like."""
    return x + 0.5 * np.sin(y * 3.0), y + 0.5 * np.sin(x * 3.0)

def _var_eyefish(x, y):
    """Wide-angle fisheye — organic bulging look."""
    r = np.sqrt(x**2 + y**2) + 1e-10
    factor = 2.0 / (r + 1.0)
    return factor * x, factor * y

def _var_bubble(x, y):
    """Spherical bubble distortion."""
    r2 = x**2 + y**2 + 1e-10
    factor = 4.0 / (r2 + 4.0)
    return factor * x, factor * y

def _var_curl(x, y):
    """Smooth flowing curves like smoke."""
    c1, c2 = 0.5, 0.3
    t1 = 1 + c1 * x + c2 * (x**2 - y**2)
    t2 = c1 * y + 2 * c2 * x * y
    denom = t1**2 + t2**2 + 1e-10
    return (x * t1 + y * t2) / denom, (y * t1 - x * t2) / denom

def _var_ngon(x, y):
    """Polygonal distortion — crystalline structures."""
    r = np.sqrt(x**2 + y**2) + 1e-10
    theta = np.arctan2(y, x)
    n = 5
    p = 2 * np.pi / n
    phi = theta - p * np.floor(theta / p)
    phi = np.where(phi > p / 2, phi - p, phi)
    factor = (np.cos(p / 2) / (np.cos(phi) + 1e-10)) / r
    return factor * x, factor * y

def _var_bent(x, y):
    """Piecewise distortion — adds asymmetry."""
    return np.where(x >= 0, x, 2 * x), np.where(y >= 0, y, y / 2)

def _var_blur(x, y):
    """Soft glow fill variation."""
    r = np.sqrt(np.abs(x * y) + 1e-10)
    theta = np.arctan2(y, x) * 2
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


class FractalFlameRenderer:
    """
    Pure NumPy fractal flame renderer.
    Based on the Draves/Reckase algorithm (flam3.com/flame_draves.pdf).
    Designed for CPU execution alongside Ollama — no GPU dependencies.

    Usage:
        renderer = FractalFlameRenderer()
        image, params = renderer.generate(seed=42)
    """

    INTERNAL_RES = 1440
    OUTPUT_RES = 720
    N_POINTS = 1_000_000
    N_WARMUP = 20
    N_ITERATIONS = 200
    DENSITY_SIGMA = 1.2
    GAMMA = 2.2

    def generate(self, seed=None, palette_name=None):
        """
        Generate a fractal flame image.

        Args:
            seed: Random seed for reproducibility. None = random.
            palette_name: Force a specific palette. None = random.

        Returns:
            (PIL.Image.Image, dict) — the rendered image and its parameter dict.
        """
        return self._generate_single(seed, palette_name)

    def _generate_single(self, seed=None, palette_name=None):
        """Internal generation logic for a single attempt."""
        t_start = time.time()
        rng = np.random.default_rng(seed)
        actual_seed = seed if seed is not None else rng.bit_generator.seed_seq.entropy

        # Choose palette
        if palette_name and palette_name in PALETTES:
            pal_name = palette_name
        else:
            pal_name = rng.choice(list(PALETTES.keys()))
        palette_fn = PALETTES[pal_name]

        # Choose symmetry
        symmetry_k = int(rng.choice([1, 1, 3, 4, 5, 6]))

        # Generate transforms
        n_transforms = int(rng.integers(2, 5))
        transforms, weights, color_speed = self._random_transforms(rng, n_transforms)

        # Build variation function closures for each transform
        compiled_transforms = []
        for item in transforms:
            affine, var_names, color_i = item[0], item[1], item[2]
            var_fns = [_VARIATION_MAP[v] for v in var_names]
            compiled_transforms.append((affine, var_fns, color_i, None))

        W = H = self.INTERNAL_RES

        # Chaos game
        r_acc, g_acc, b_acc, a_acc = self._chaos_game(
            rng, compiled_transforms, weights, color_speed, W, H, symmetry_k, None, palette_fn
        )

        # Render
        img = self._render(r_acc, g_acc, b_acc, a_acc, W, H)

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
                    "color": float(item[2]),
                    "post_affine": item[3].tolist() if len(item) > 3 and item[3] is not None else None,
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
        }

        return img, params

    def generate_mandelbrot(self, seed=None, palette_name=None):
        """
        Generate a Mandelbrot zoom image (simpler fallback).

        Returns:
            (PIL.Image.Image, dict) — the rendered image and its parameter dict.
        """
        t_start = time.time()
        rng = np.random.default_rng(seed)
        actual_seed = seed if seed is not None else rng.bit_generator.seed_seq.entropy

        zoom_targets = [
            (-0.7269, 0.1889, 0.005),    # classic spiral
            (-0.1592, 1.0317, 0.01),      # seahorse valley
            (-1.7686, 0.0042, 0.005),     # antenna tip
            (-0.5251, 0.5255, 0.02),      # mini brot
            (-0.745,  0.186,  0.003),     # spiral arm
            (-1.256,  0.382,  0.008),     # double spiral
        ]
        idx = int(rng.integers(len(zoom_targets)))
        cx, cy, zoom = zoom_targets[idx]
        jitter = rng.uniform(-zoom * 0.3, zoom * 0.3, 2)
        cx += jitter[0]
        cy += jitter[1]

        if palette_name and palette_name in PALETTES:
            pal_name = palette_name
        else:
            pal_name = rng.choice(list(PALETTES.keys()))
        palette_fn = PALETTES[pal_name]

        W = H = 720
        max_iter = 256
        x = np.linspace(cx - zoom, cx + zoom, W)
        y = np.linspace(cy - zoom * H / W, cy + zoom * H / W, H)
        C = x[np.newaxis, :] + 1j * y[:, np.newaxis]

        Z = np.zeros_like(C)
        M = np.zeros(C.shape, dtype=float)
        escaped = np.zeros(C.shape, dtype=bool)

        for i in range(max_iter):
            mask = ~escaped
            Z[mask] = Z[mask] ** 2 + C[mask]
            newly_escaped = mask & (np.abs(Z) > 2)
            M[newly_escaped] = i + 1 - np.log2(np.log2(np.abs(Z[newly_escaped]) + 1e-10))
            escaped |= newly_escaped

        M_norm = M / max_iter
        rgb = palette_fn(M_norm)
        img_array = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)

        render_time = time.time() - t_start
        log_info(f"[art] Mandelbrot rendered in {render_time:.1f}s (seed={actual_seed}, palette={pal_name})")

        params = {
            "type": "mandelbrot",
            "seed": int(actual_seed) if actual_seed is not None else None,
            "center": [cx, cy],
            "zoom": zoom,
            "max_iter": max_iter,
            "palette": pal_name,
            "render_time_s": round(render_time, 2),
            "resolution": [W, H],
        }

        return Image.fromarray(img_array), params

    # ── Internal Methods ──────────────────────────────────────────────────────

    def _random_transforms(self, rng, n_transforms=3):
        """Generate variations matching true flam3 xml structure."""
        transforms = []
        weights = np.abs(rng.standard_normal(n_transforms))
        weights /= weights.sum()

        base_colors = np.linspace(0.05, 0.95, n_transforms)
        jitter = rng.uniform(-0.08, 0.08, n_transforms)
        color_values = np.clip(base_colors + jitter, 0, 1)

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

            # Pick 1-3 variations
            n_vars = int(rng.choice([1, 2, 2, 3]))
            var_names = list(rng.choice(VARIATIONS, size=n_vars, replace=False))
            
            color_i = float(color_values[_idx])

            transforms.append((affine, var_names, color_i, None))

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

        # Initial bounds — will be fitted adaptively after warmup
        xmin, xmax = -2.0, 2.0
        ymin, ymax = -2.0, 2.0
        x_scale = W / (xmax - xmin)
        y_scale = H / (ymax - ymin)
        bounds_fitted = False
        bounds_sample_x = []
        bounds_sample_y = []

        n_transforms = len(transforms)

        # Precompute affine matrices as stacked arrays for vectorized lookup
        affines = np.array([t[0] for t in transforms])  # shape (n_transforms, 6)
        colors = np.array([t[2] for t in transforms])   # shape (n_transforms,)
        post_affines = [t[3] for t in transforms]  # list of arrays or None

        for iteration in range(self.N_WARMUP + self.N_ITERATIONS):
            # Choose transform for each point (single rng call)
            choices = rng.choice(n_transforms, size=N, p=weights)

            # Vectorized affine: lookup the 6 coefficients for each point's chosen transform
            af = affines[choices]  # shape (N, 6)
            xa = af[:, 0] * x + af[:, 1] * y + af[:, 2]
            ya = af[:, 3] * x + af[:, 4] * y + af[:, 5]

            # Apply variations per-transform with true multi-blend
            new_x = np.empty_like(xa)
            new_y = np.empty_like(ya)
            for i in range(n_transforms):
                mask = choices == i
                if not mask.any():
                    continue
                var_fns = transforms[i][1]  # list of variation functions
                xi, yi = xa[mask], ya[mask]
                if len(var_fns) == 1:
                    vx, vy = var_fns[0](xi, yi)
                else:
                    # Equal-weight blend of all variations for this transform
                    vx = np.zeros(mask.sum())
                    vy = np.zeros(mask.sum())
                    for vfn in var_fns:
                        fx, fy = vfn(xi, yi)
                        vx += fx
                        vy += fy
                    vx /= len(var_fns)
                    vy /= len(var_fns)
                # Apply post-transform if present
                pa = post_affines[i]
                if pa is not None:
                    px = pa[0] * vx + pa[1] * vy + pa[2]
                    py = pa[3] * vx + pa[4] * vy + pa[5]
                    vx, vy = px, py
                new_x[mask] = vx
                new_y[mask] = vy

            x = new_x
            y = new_y

            # Clamp runaway coordinates (prevent variation escape)
            np.clip(x, -1e4, 1e4, out=x)
            np.clip(y, -1e4, 1e4, out=y)
            # Replace any NaN/inf with random re-seed
            bad = ~(np.isfinite(x) & np.isfinite(y))
            if bad.any():
                x[bad] = rng.uniform(-1, 1, bad.sum())
                y[bad] = rng.uniform(-1, 1, bad.sum())

            # Color blending (vectorized) with configurable speed for rich gradients
            c = c * (1.0 - color_speed) + colors[choices] * color_speed

            # Skip warmup iterations
            if iteration < self.N_WARMUP:
                continue

            # Apply final transform (global camera) if present
            if final_xform is not None:
                fc, fs = final_xform['affine']
                tx = fc * x - fs * y
                ty = fs * x + fc * y
                fx, fy = final_xform['var_fns'][0](tx, ty)
            else:
                fx, fy = x, y

            # Adaptive bounds fitting — collect samples across first 5 post-warmup iterations
            if not bounds_fitted:
                # Subsample to keep memory reasonable
                finite = np.isfinite(fx) & np.isfinite(fy)
                sample_idx = finite & (np.arange(N) % 10 == 0)  # every 10th point
                bounds_sample_x.append(fx[sample_idx].copy())
                bounds_sample_y.append(fy[sample_idx].copy())
                if len(bounds_sample_x) >= 5:
                    bounds_fitted = True
                    all_x = np.concatenate(bounds_sample_x)
                    all_y = np.concatenate(bounds_sample_y)
                    p_lo_x, p_hi_x = np.percentile(all_x, [2, 98])
                    p_lo_y, p_hi_y = np.percentile(all_y, [2, 98])
                    pad_x = 0.1 * (p_hi_x - p_lo_x + 1e-10)
                    pad_y = 0.1 * (p_hi_y - p_lo_y + 1e-10)
                    cx_f = (p_lo_x + p_hi_x) / 2
                    cy_f = (p_lo_y + p_hi_y) / 2
                    half = max(p_hi_x - p_lo_x + 2 * pad_x, p_hi_y - p_lo_y + 2 * pad_y) / 2
                    half = max(half, 0.5)  # minimum viewport size
                    xmin, xmax = cx_f - half, cx_f + half
                    ymin, ymax = cy_f - half, cy_f + half
                    x_scale = W / (xmax - xmin)
                    y_scale = H / (ymax - ymin)
                    del bounds_sample_x, bounds_sample_y  # free memory

            # Accumulate via bincount
            self._accumulate_points(
                fx, fy, c, xmin, ymin, x_scale, y_scale,
                W, H, total_pixels, r_flat, g_flat, b_flat, a_flat, palette_fn
            )

            # K-fold rotational symmetry
            if symmetry_k > 1:
                angle_step = (2 * np.pi) / symmetry_k
                for s in range(1, symmetry_k):
                    angle = angle_step * s
                    cos_a, sin_a = np.cos(angle), np.sin(angle)
                    xr = fx * cos_a - fy * sin_a
                    yr = fx * sin_a + fy * cos_a
                    self._accumulate_points(
                        xr, yr, c, xmin, ymin, x_scale, y_scale,
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
        """Accumulate points into histogram using fast np.bincount."""
        px = ((x - xmin) * x_scale).astype(np.intp)
        py = ((y - ymin) * y_scale).astype(np.intp)
        valid = (px >= 0) & (px < W) & (py >= 0) & (py < H)

        flat_idx = py[valid] * W + px[valid]
        c_valid = c[valid]
        
        # Look up RGB colors from palette for valid points
        rgb = palette_fn(c_valid)
        
        a_flat += np.bincount(flat_idx, minlength=total_pixels).astype(np.float64)
        r_flat += np.bincount(flat_idx, weights=rgb[:, 0], minlength=total_pixels)
        g_flat += np.bincount(flat_idx, weights=rgb[:, 1], minlength=total_pixels)
        b_flat += np.bincount(flat_idx, weights=rgb[:, 2], minlength=total_pixels)

    def _render(self, r_acc, g_acc, b_acc, alpha_acc, W, H):
        """Render RGBA buffers to image: flam3 log-density, DE, gamma."""
        if alpha_acc.max() == 0:
            log_warning("[art] Empty histogram — all points escaped. Producing noise fallback.")
            rng = np.random.default_rng()
            noise = rng.uniform(0, 1, (self.OUTPUT_RES, self.OUTPUT_RES, 3))
            return Image.fromarray((noise * 60).astype(np.uint8))

        # Stack RGB buffers
        rgb_acc = np.stack([r_acc, g_acc, b_acc], axis=-1)

        # Step 1: True Flam3 Tone Mapping (No KDE Blur!)
        log_alpha = np.log1p(alpha_acc)
        scale = log_alpha / (alpha_acc + 1e-10)
        rgb_mapped = rgb_acc * scale[..., np.newaxis]
        
        # Step 2: Brightness scaling
        rgb_mapped_nonzero = rgb_mapped[alpha_acc > 0]
        if len(rgb_mapped_nonzero) > 100:
            v_max = np.percentile(rgb_mapped_nonzero, 99.9)
        else:
            v_max = rgb_mapped.max()
            
        rgb_normalized = rgb_mapped / (v_max + 1e-10)

        # Step 3: Gamma correction (flam3 standard = 2.2)
        gamma = self.GAMMA
        rgb_gamma = np.power(np.clip(rgb_normalized, 0, 1), 1.0 / gamma)

        # Step 4: Subtle Bloom pass (Electric Sheep glow)
        bloom = gaussian_filter(rgb_gamma, sigma=3.0, axes=(0, 1))
        rgb_bloomed = np.clip(rgb_gamma + bloom * 0.15, 0, 1)

        # Step 5: Supersampling downsample
        img_high = Image.fromarray((rgb_bloomed * 255).astype(np.uint8))
        img_out = img_high.resize((self.OUTPUT_RES, self.OUTPUT_RES), Image.LANCZOS)
        return img_out
