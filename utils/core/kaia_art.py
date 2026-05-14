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
# Each maps a float array [0,1] → RGB array (H, W, 3) float [0,1].

def _palette_electric(t):
    """Deep blue/purple → cyan/white (Electric Sheep vibe)."""
    r = np.clip(0.1 + 0.6 * t**2 + 0.3 * t**3, 0, 1)
    g = np.clip(0.05 + 0.4 * t + 0.5 * t**2.5, 0, 1)
    b = np.clip(0.3 + 0.7 * t**0.6, 0, 1)
    return np.stack([r, g, b], axis=-1)

def _palette_ember(t):
    """Black → orange → yellow/white."""
    r = np.clip(t**0.4, 0, 1)
    g = np.clip(t**1.5 * 0.85, 0, 1)
    b = np.clip(t**4.0 * 0.6, 0, 1)
    return np.stack([r, g, b], axis=-1)

def _palette_acid(t):
    """Green/lime → yellow."""
    r = np.clip(0.2 * t + 0.7 * t**2.5, 0, 1)
    g = np.clip(0.3 + 0.7 * t**0.5, 0, 1)
    b = np.clip(0.05 + 0.15 * t, 0, 1)
    return np.stack([r, g, b], axis=-1)

def _palette_void(t):
    """Red/magenta → purple → dark."""
    r = np.clip(0.6 * t**0.7 + 0.3 * np.sin(t * np.pi), 0, 1)
    g = np.clip(0.05 + 0.1 * t**2, 0, 1)
    b = np.clip(0.3 * t + 0.5 * t**1.8, 0, 1)
    return np.stack([r, g, b], axis=-1)

def _palette_aurora(t):
    """Green/teal → pink."""
    r = np.clip(0.1 + 0.7 * t**2, 0, 1)
    g = np.clip(0.4 * (1.0 - t**1.5) + 0.3 * t, 0, 1)
    b = np.clip(0.2 + 0.5 * t**0.8, 0, 1)
    return np.stack([r, g, b], axis=-1)

def _palette_ghost(t):
    """Single-hue white-blue, sparse and eerie."""
    r = np.clip(0.6 * t**1.5, 0, 1)
    g = np.clip(0.65 * t**1.2, 0, 1)
    b = np.clip(0.3 + 0.7 * t**0.7, 0, 1)
    return np.stack([r, g, b], axis=-1)

PALETTES = {
    'electric': _palette_electric,
    'ember':    _palette_ember,
    'acid':     _palette_acid,
    'void':     _palette_void,
    'aurora':   _palette_aurora,
    'ghost':    _palette_ghost,
}

# ── LUT Palettes (curated color tables for Electric Sheep richness) ─────────

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

_LUT_DEEP_OCEAN = _build_lut([
    (0.0,  0.00, 0.00, 0.05), (0.15, 0.02, 0.04, 0.25),
    (0.30, 0.10, 0.08, 0.55), (0.45, 0.05, 0.25, 0.75),
    (0.60, 0.03, 0.55, 0.85), (0.75, 0.30, 0.75, 0.92),
    (0.90, 0.80, 0.92, 0.98), (1.0,  1.00, 1.00, 1.00),
])
_LUT_SOLAR_FLARE = _build_lut([
    (0.0,  0.02, 0.00, 0.00), (0.15, 0.20, 0.02, 0.00),
    (0.30, 0.55, 0.08, 0.00), (0.45, 0.85, 0.20, 0.02),
    (0.60, 0.95, 0.50, 0.05), (0.75, 1.00, 0.80, 0.20),
    (0.90, 1.00, 0.95, 0.60), (1.0,  1.00, 1.00, 0.95),
])
_LUT_BIOLUME = _build_lut([
    (0.0,  0.00, 0.02, 0.05), (0.12, 0.00, 0.10, 0.15),
    (0.25, 0.00, 0.35, 0.20), (0.40, 0.05, 0.60, 0.30),
    (0.55, 0.20, 0.75, 0.50), (0.70, 0.50, 0.55, 0.70),
    (0.85, 0.80, 0.40, 0.85), (1.0,  0.95, 0.85, 1.00),
])
_LUT_NEBULA = _build_lut([
    (0.0,  0.02, 0.00, 0.05), (0.15, 0.15, 0.00, 0.25),
    (0.30, 0.35, 0.02, 0.50), (0.45, 0.55, 0.10, 0.65),
    (0.55, 0.40, 0.30, 0.80), (0.70, 0.25, 0.55, 0.90),
    (0.85, 0.60, 0.80, 0.95), (1.0,  0.95, 0.95, 1.00),
])

PALETTES['deep_ocean'] = lambda t: _lut_palette(t, _LUT_DEEP_OCEAN)
PALETTES['solar_flare'] = lambda t: _lut_palette(t, _LUT_SOLAR_FLARE)
PALETTES['biolume'] = lambda t: _lut_palette(t, _LUT_BIOLUME)
PALETTES['nebula'] = lambda t: _lut_palette(t, _LUT_NEBULA)


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
    N_POINTS = 500_000
    N_WARMUP = 20
    N_ITERATIONS = 80
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

        # Generate transforms (with optional post-transforms)
        n_transforms = int(rng.integers(2, 5))
        transforms, weights = self._random_transforms(rng, n_transforms)

        # Build variation function closures for each transform
        compiled_transforms = []
        for item in transforms:
            affine, var_names, color_i = item[0], item[1], item[2]
            post_affine = item[3] if len(item) > 3 else None
            var_fns = [_VARIATION_MAP[v] for v in var_names]
            compiled_transforms.append((affine, var_fns, color_i, post_affine))

        # Final transform (global camera — 30% chance)
        final_xform = None
        if rng.random() < 0.3:
            angle = float(rng.uniform(0, 2 * np.pi))
            scale = float(rng.uniform(0.8, 1.2))
            final_xform = (np.cos(angle) * scale, np.sin(angle) * scale)

        W = H = self.INTERNAL_RES

        # Chaos game
        histogram, color_acc = self._chaos_game(
            rng, compiled_transforms, weights, W, H, symmetry_k, final_xform
        )

        # Render
        img = self._render(histogram, color_acc, W, H, palette_fn)

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
            "weights": weights.tolist(),
            "palette": pal_name,
            "final_transform": {"cos": final_xform[0], "sin": final_xform[1]} if final_xform else None,
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
        """Generate n random affine transforms + variation assignments + optional post-transforms."""
        transforms = []
        weights = np.abs(rng.standard_normal(n_transforms))
        weights /= weights.sum()

        for _ in range(n_transforms):
            # Random affine matrix (keep determinant between 0.3 and 0.9 for convergence)
            for _attempt in range(100):
                a, b, c = rng.uniform(-1.5, 1.5, 3)
                d, e, f = rng.uniform(-1.5, 1.5, 3)
                det = a * e - b * d
                if 0.3 < abs(det) < 0.9:
                    break
            affine = np.array([a, b, c, d, e, f])

            # Pick 1-3 variations (weighted toward 2)
            n_vars = int(rng.choice([1, 2, 2, 3]))
            var_names = list(rng.choice(VARIATIONS, size=n_vars, replace=False))
            color_i = float(rng.uniform(0, 1))

            # Optional post-transform (40% chance) — subtle refinement after variation
            post_affine = None
            if rng.random() < 0.4:
                pa, pb, pc = rng.uniform(-0.5, 0.5, 3)
                pd, pe, pf = rng.uniform(-0.5, 0.5, 3)
                post_affine = np.array([pa, pb, pc, pd, pe, pf])

            transforms.append((affine, var_names, color_i, post_affine))

        return transforms, weights

    def _chaos_game(self, rng, transforms, weights, W, H, symmetry_k, final_xform=None):
        """Run the vectorized chaos game loop with multi-blend, post-transforms, and final transform."""
        N = self.N_POINTS
        x = rng.uniform(-1, 1, N)
        y = rng.uniform(-1, 1, N)
        c = rng.uniform(0, 1, N)  # color coordinate

        total_pixels = H * W
        hist_flat = np.zeros(total_pixels, dtype=np.float64)
        color_flat = np.zeros(total_pixels, dtype=np.float64)

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

            # Color blending (vectorized)
            c = (c + colors[choices]) * 0.5

            # Skip warmup iterations
            if iteration < self.N_WARMUP:
                continue

            # Apply final transform (global camera) if present
            if final_xform is not None:
                fc, fs = final_xform
                fx = fc * x - fs * y
                fy = fs * x + fc * y
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
                    p_lo_x, p_hi_x = np.percentile(all_x, [1, 99])
                    p_lo_y, p_hi_y = np.percentile(all_y, [1, 99])
                    pad_x = 0.15 * (p_hi_x - p_lo_x + 1e-10)
                    pad_y = 0.15 * (p_hi_y - p_lo_y + 1e-10)
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
                W, H, total_pixels, hist_flat, color_flat
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
                        W, H, total_pixels, hist_flat, color_flat
                    )

        histogram = hist_flat.reshape((H, W))
        color_acc = color_flat.reshape((H, W))
        return histogram, color_acc

    @staticmethod
    def _accumulate_points(x, y, c, xmin, ymin, x_scale, y_scale,
                           W, H, total_pixels, hist_flat, color_flat):
        """Accumulate points into histogram using fast np.bincount."""
        px = ((x - xmin) * x_scale).astype(np.intp)
        py = ((y - ymin) * y_scale).astype(np.intp)
        valid = (px >= 0) & (px < W) & (py >= 0) & (py < H)

        flat_idx = py[valid] * W + px[valid]
        hist_flat += np.bincount(flat_idx, minlength=total_pixels).astype(np.float64)
        color_flat += np.bincount(flat_idx, weights=c[valid], minlength=total_pixels)

    def _render(self, histogram, color_acc, W, H, palette_fn):
        """Adaptive density estimation, log-density tone mapping, colorize, gamma, supersample."""
        # Step 1: Log-density tone mapping
        log_hist = np.log1p(histogram)
        log_max = log_hist.max()
        if log_max == 0:
            # Empty histogram — generate a fallback
            log_warning("[art] Empty histogram — all points escaped. Producing noise fallback.")
            rng = np.random.default_rng()
            noise = rng.uniform(0, 1, (self.OUTPUT_RES, self.OUTPUT_RES, 3))
            return Image.fromarray((noise * 60).astype(np.uint8))

        alpha = log_hist / log_max

        # Step 2: Adaptive density estimation (multi-pass, spatially varying blur)
        # Low-density areas get more blur (reduce noise), high-density areas less (preserve detail)
        density_norm = alpha  # 0 = empty, 1 = max density
        sigma_levels = [0.5, 1.0, 1.8, 3.0]
        alpha_passes = [gaussian_filter(alpha, sigma=s) for s in sigma_levels]
        color_passes = [gaussian_filter(color_acc, sigma=s) for s in sigma_levels]

        # Sigma map: sparse regions → large sigma, dense regions → small sigma
        sigma_map = 3.0 - 2.5 * density_norm

        # Blend passes based on sigma_map (piecewise linear interpolation)
        alpha_smooth = np.zeros_like(alpha)
        color_smooth = np.zeros_like(color_acc)
        n_levels = len(sigma_levels)
        for i in range(n_levels - 1):
            lo, hi = sigma_levels[i], sigma_levels[i + 1]
            weight = np.clip((sigma_map - lo) / (hi - lo + 1e-10), 0, 1)
            blend = np.where((sigma_map >= lo) & (sigma_map < hi), 1.0, 0.0)
            if i == 0:
                blend = np.where(sigma_map < lo, 1.0, blend)
            if i == n_levels - 2:
                blend = np.where(sigma_map >= hi, 1.0, blend)
            alpha_smooth += blend * ((1 - weight) * alpha_passes[i] + weight * alpha_passes[i + 1])
            color_smooth += blend * ((1 - weight) * color_passes[i] + weight * color_passes[i + 1])

        # Step 3: Color coordinate (smoothed)
        color_coord = np.zeros((H, W), dtype=float)
        nonzero = histogram > 0
        color_coord[nonzero] = color_smooth[nonzero] / (log_hist[nonzero] + 1e-10)
        color_coord = np.clip(color_coord, 0, 1)

        # Step 4: Colorize with vibrancy-preserving blend (flam3-style)
        # Instead of rgb *= alpha (which kills saturation), blend between
        # full-palette color and alpha-dimmed color using a vibrancy factor.
        rgb = palette_fn(color_coord)  # shape (H, W, 3), full brightness
        vibrancy = 0.45  # 0 = pure alpha multiply, 1 = full palette color
        # Vibrancy blend: lerp between alpha-dimmed and alpha-pow-dimmed
        alpha_3d = alpha_smooth[..., np.newaxis]
        rgb = vibrancy * rgb * np.power(alpha_3d + 1e-10, 0.5) + \
              (1.0 - vibrancy) * rgb * alpha_3d

        # Step 5: Gamma correction (flam3 uses gamma=4.0, we use 3.2 for balance)
        gamma = 3.2
        rgb = np.power(np.clip(rgb, 0, 1), 1.0 / gamma)

        # Step 6: Brightness boost — lift midtones but preserve black background
        # Only boost pixels that have some structure; pure background stays black
        rgb = np.clip(rgb, 0, 1)
        brightness = rgb.max(axis=-1, keepdims=True)
        boost = np.where(brightness > 0.05, 1.0 + 0.5 * (1.0 - brightness), 1.0)
        rgb = np.clip(rgb * boost, 0, 1)

        # Step 7: Supersampling downsample
        img_high = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
        img_out = img_high.resize((self.OUTPUT_RES, self.OUTPUT_RES), Image.LANCZOS)
        return img_out
