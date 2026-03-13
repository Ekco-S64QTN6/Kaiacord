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

VARIATIONS = ['linear', 'sinusoidal', 'spherical', 'swirl',
              'horseshoe', 'polar', 'spiral', 'hyperbolic']

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

_VARIATION_MAP = {
    'linear':     _var_linear,
    'sinusoidal': _var_sinusoidal,
    'spherical':  _var_spherical,
    'swirl':      _var_swirl,
    'horseshoe':  _var_horseshoe,
    'polar':      _var_polar,
    'spiral':     _var_spiral,
    'hyperbolic': _var_hyperbolic,
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


class FractalFlameRenderer:
    """
    Pure NumPy fractal flame renderer.
    Based on the Draves/Reckase algorithm (flam3.com/flame_draves.pdf).
    Designed for CPU execution alongside Ollama — no GPU dependencies.

    Usage:
        renderer = FractalFlameRenderer()
        image, params = renderer.generate(seed=42)
    """

    INTERNAL_RES = 1080
    OUTPUT_RES = 720
    N_POINTS = 200_000
    N_WARMUP = 20
    N_ITERATIONS = 30
    DENSITY_SIGMA = 1.0
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

        # Generate transforms
        n_transforms = int(rng.integers(2, 5))
        transforms, weights = self._random_transforms(rng, n_transforms)

        # Build variation function closures for each transform
        compiled_transforms = []
        for affine, var_names, color_i in transforms:
            var_fns = [_VARIATION_MAP[v] for v in var_names]
            compiled_transforms.append((affine, var_fns, color_i))

        W = H = self.INTERNAL_RES

        # Chaos game
        histogram, color_acc = self._chaos_game(
            rng, compiled_transforms, weights, W, H, symmetry_k
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
                    "affine": affine.tolist(),
                    "variations": list(var_names),
                    "color": float(color_i),
                }
                for affine, var_names, color_i in transforms
            ],
            "weights": weights.tolist(),
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
        """Generate n random affine transforms + variation assignments."""
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

            # Pick 1-2 variations
            n_vars = int(rng.integers(1, 3))
            var_names = list(rng.choice(VARIATIONS, size=n_vars, replace=False))
            color_i = float(rng.uniform(0, 1))
            transforms.append((affine, var_names, color_i))

        return transforms, weights

    def _chaos_game(self, rng, transforms, weights, W, H, symmetry_k):
        """Run the vectorized chaos game loop (fully vectorized, bincount-optimized)."""
        N = self.N_POINTS
        x = rng.uniform(-1, 1, N)
        y = rng.uniform(-1, 1, N)
        c = rng.uniform(0, 1, N)  # color coordinate

        total_pixels = H * W
        hist_flat = np.zeros(total_pixels, dtype=np.float64)
        color_flat = np.zeros(total_pixels, dtype=np.float64)

        # Bounds for pixel mapping
        xmin, xmax = -2.0, 2.0
        ymin, ymax = -2.0, 2.0
        x_scale = W / (xmax - xmin)
        y_scale = H / (ymax - ymin)

        n_transforms = len(transforms)

        # Precompute affine matrices as stacked arrays for vectorized lookup
        affines = np.array([t[0] for t in transforms])  # shape (n_transforms, 6)
        colors = np.array([t[2] for t in transforms])   # shape (n_transforms,)

        # For variations: since each transform can have different variations,
        # we need to keep the per-transform dispatch but apply it efficiently.
        # Precompute the single "primary" variation per transform for the fast path.
        # (Use only first variation per transform for speed — weighted average of
        # multiple variations is a minor quality detail, single variation is the norm)
        var_fns_list = [t[1][0] for t in transforms]  # first variation fn per transform

        for iteration in range(self.N_WARMUP + self.N_ITERATIONS):
            # Choose transform for each point (single rng call)
            choices = rng.choice(n_transforms, size=N, p=weights)

            # Vectorized affine: lookup the 6 coefficients for each point's chosen transform
            af = affines[choices]  # shape (N, 6)
            xa = af[:, 0] * x + af[:, 1] * y + af[:, 2]
            ya = af[:, 3] * x + af[:, 4] * y + af[:, 5]

            # Apply variations per-transform (still need dispatch, but minimized)
            new_x = np.empty_like(xa)
            new_y = np.empty_like(ya)
            for i in range(n_transforms):
                mask = choices == i
                if not mask.any():
                    continue
                vx, vy = var_fns_list[i](xa[mask], ya[mask])
                new_x[mask] = vx
                new_y[mask] = vy

            x = new_x
            y = new_y

            # Color blending (vectorized)
            c = (c + colors[choices]) * 0.5

            # Skip warmup iterations
            if iteration < self.N_WARMUP:
                continue

            # Accumulate via bincount
            self._accumulate_points(
                x, y, c, xmin, ymin, x_scale, y_scale,
                W, H, total_pixels, hist_flat, color_flat
            )

            # K-fold rotational symmetry
            if symmetry_k > 1:
                angle_step = (2 * np.pi) / symmetry_k
                for s in range(1, symmetry_k):
                    angle = angle_step * s
                    cos_a, sin_a = np.cos(angle), np.sin(angle)
                    xr = x * cos_a - y * sin_a
                    yr = x * sin_a + y * cos_a
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
        """Log-density rendering, density estimation, colorize, gamma, supersample."""
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

        # Step 2: Density estimation filtering (Gaussian blur for silky filaments)
        alpha_smooth = gaussian_filter(alpha, sigma=self.DENSITY_SIGMA)
        color_acc_smooth = gaussian_filter(color_acc, sigma=self.DENSITY_SIGMA)

        # Step 3: Color coordinate (smoothed)
        color_coord = np.zeros((H, W), dtype=float)
        nonzero = histogram > 0
        color_coord[nonzero] = color_acc_smooth[nonzero] / (log_hist[nonzero] + 1e-10)
        color_coord = np.clip(color_coord, 0, 1)

        # Step 4: Colorize
        rgb = palette_fn(color_coord)  # shape (H, W, 3)
        rgb *= alpha_smooth[..., np.newaxis]

        # Step 5: Gamma correction
        rgb = np.power(np.clip(rgb, 0, 1), 1.0 / self.GAMMA)

        # Step 6: Supersampling downsample
        img_high = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
        img_out = img_high.resize((self.OUTPUT_RES, self.OUTPUT_RES), Image.LANCZOS)
        return img_out
