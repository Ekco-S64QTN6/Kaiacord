Here's the full plan. A few key design calls worth noting:
CPU-only renderer. The RTX 3060 is already fully loaded by Ollama. Any CUDA renderer would race for VRAM and crash generation. Pure NumPy in asyncio.to_thread() keeps the GPU free — renders a 720px image in 3–8 seconds, which is fine for Discord.
Real fractal flames, not just Mandelbrot. The Mandelbrot is a fallback (!art mandelbrot). The default is proper fractal flames — chaos game algorithm, log-density rendering, structural coloring, 6 named palettes. This is what Electric Sheep actually uses and it produces genuinely strange, luminous images.
Kaia comments on her own work. After rendering, a short Ollama call (max 80 tokens) generates a 1–2 sentence in-character reaction using the flame's parameter set as context. No image vision — just the variation names and palette. Fast and keeps her voice on it.
3 files total: utils/core/kaia_art.py, utils/commands/art_handler.py, and one line in registry.py. No new dependencies — Pillow and NumPy are already in the venv.
The plan has complete pseudocode for every method Opus will need — the vectorized chaos game loop, all 8 variation functions, log-density tone mapping, palette implementations, and the Discord file send pattern.

# Kaia Art System — Implementation Plan
**Target:** Claude Opus  
**Project:** Kaiacord (Discord bot, Python async, RTX 3060 / gemma3:12b via Ollama)  
**Feature:** `!art` command → Kaia generates a fractal flame image and posts it to Discord with a brief in-character comment

---

## Design Decisions (Read Before Coding)

### Why pure NumPy, not CUDA
The RTX 3060 (12GB) is fully reserved by Ollama running gemma3:12b. Any CUDA render kernel would race with the LLM for VRAM and cause generation failures or OOM crashes. The fractal renderer **must run on CPU**, wrapped in `asyncio.to_thread()` so it doesn't block the event loop. NumPy vectorized fractal flames on CPU render a 720×720 image in ~3–8 seconds, which is perfectly acceptable for a Discord command.

Do **not** use `cuburn`, PyCUDA, Numba CUDA, or any GPU-backed renderer. Pure NumPy only.

### Why fractal flames (not just Mandelbrot)
Mandelbrot/Julia sets look like "programmer art." Fractal flames look like Electric Sheep — luminous, organic, colored filaments. They're genuinely beautiful and distinctive. The algorithm is more complex but completely self-contained in NumPy. We implement a subset: 6–8 variation functions, log-density rendering, structural coloring, and gamma correction. That's enough to produce stunning images.

### Kaia names and comments on her own art
After rendering, Kaia makes a short Ollama call (`gemma3:12b`, max 80 tokens) to generate a 1–2 sentence comment on the image — what she "sees" in it, what it reminds her of. This goes in the Discord message alongside the image. The comment uses the flame parameters as seed context for the prompt, not vision (no base64 image passed — too slow). This keeps it fast and characterful.

### Art persistence
Each image is saved to `memory/art/` with a UUID filename and a JSON sidecar storing the parameters. This enables future features like `!art --reseed <id>` to regenerate from the same parameters.

---

## New Files to Create

### 1. `utils/core/kaia_art.py`
The fractal flame renderer. Entirely self-contained. No imports from the rest of the codebase except `kaia_logger`.

**Class: `FractalFlameRenderer`**

```python
class FractalFlameRenderer:
    """
    Pure NumPy fractal flame renderer.
    Based on the Draves/Reckase algorithm (flam3.com/flame_draves.pdf).
    Designed for CPU execution alongside Ollama — no GPU dependencies.
    """

    # Variation function IDs (subset of the 48 in the spec)
    VARIATIONS = ['linear', 'sinusoidal', 'spherical', 'swirl', 
                  'horseshoe', 'polar', 'spiral', 'hyperbolic']
```

**Method: `generate(seed=None) -> tuple[PIL.Image.Image, dict]`**

Returns `(image, params)` where `params` is a JSON-serializable dict of all the random seeds used (for reproducibility). Runs synchronously — caller wraps in `asyncio.to_thread()`.

**Implementation details for Opus:**

The chaos game loop must be vectorized with NumPy batch processing. Do NOT use a Python `for` loop over individual points — it will take minutes. Use this pattern:

```python
# Batch N points simultaneously
N_POINTS = 500_000
N_WARMUP = 20

x = np.random.uniform(-1, 1, N_POINTS)
y = np.random.uniform(-1, 1, N_POINTS)
c = np.random.uniform(0, 1, N_POINTS)  # color coordinate

for iteration in range(N_WARMUP + N_ITERATIONS):
    # Choose transform for each point (vectorized)
    choices = rng.choice(len(transforms), size=N_POINTS, p=weights)
    
    # Apply each transform to its subset of points
    for i, (affine, variation_fn, color_i) in enumerate(transforms):
        mask = (choices == i)
        if not mask.any():
            continue
        xi, yi = x[mask], y[mask]
        # 1. Affine transform: (a*x + b*y + c, d*x + e*y + f)
        xa = affine[0]*xi + affine[1]*yi + affine[2]
        ya = affine[3]*xi + affine[4]*yi + affine[5]
        # 2. Variation function
        x[mask], y[mask] = variation_fn(xa, ya)
        # 3. Color blending
        c[mask] = (c[mask] + color_i) * 0.5
    
    # Skip warmup iterations (don't plot)
    if iteration < N_WARMUP:
        continue
    
    # Accumulate to histogram
    # (coordinate → pixel index mapping)
    px = ((x - xmin) / (xmax - xmin) * W).astype(int)
    py = ((y - ymin) / (ymax - ymin) * H).astype(int)
    valid = (px >= 0) & (px < W) & (py >= 0) & (py < H)
    
    np.add.at(histogram, (py[valid], px[valid]), 1)
    np.add.at(color_acc, (py[valid], px[valid], 0), c[valid])  # R channel via color map
```

**Log-density rendering + density estimation filtering + rotational symmetry (all three required for Electric Sheep quality):**

```python
# ── STEP 1: Chaos game accumulation (done in the loop above) ──────────────────
# histogram shape: (H, W)        — hit count per pixel
# color_acc shape: (H, W)        — color coordinate sum per pixel

# ── STEP 2: Log-density tone mapping ─────────────────────────────────────────
log_hist = np.log1p(histogram)
log_max = log_hist.max()
if log_max == 0:
    raise ValueError("Empty histogram — all points escaped bounds, try a different seed")
alpha = log_hist / log_max

# ── STEP 3: Density estimation filtering (THE single biggest quality upgrade) ─
# Blur both the log-histogram and color accumulator with a small Gaussian.
# This smooths the wispy filament regions from grainy speckle into silky strands.
# sigma=1.2 is a good default — larger = smoother but loses fine structure.
from scipy.ndimage import gaussian_filter
alpha_smooth    = gaussian_filter(alpha,    sigma=1.2)
color_acc_smooth = gaussian_filter(color_acc, sigma=1.2)

# Use the smoothed versions for final coloring
color_coord = np.zeros((H, W), dtype=float)
nonzero = histogram > 0
color_coord[nonzero] = color_acc_smooth[nonzero] / (log_hist[nonzero] + 1e-10)
color_coord = np.clip(color_coord, 0, 1)

# ── STEP 4: Colorize ──────────────────────────────────────────────────────────
rgb = palette(color_coord)          # shape (H, W, 3), float [0,1]
rgb *= alpha_smooth[..., np.newaxis]  # modulate brightness by smoothed density

# ── STEP 5: Gamma correction ──────────────────────────────────────────────────
gamma = 2.2
rgb = np.power(np.clip(rgb, 0, 1), 1.0 / gamma)

# ── STEP 6: Supersampling downsample (see resolution section below) ───────────
img_high = Image.fromarray((rgb * 255).astype(np.uint8))
img_out = img_high.resize((720, 720), Image.LANCZOS)
return img_out
```

**scipy.ndimage is the only new dependency this introduces.** It's almost certainly already installed (LlamaIndex pulls it in), but verify with `pip show scipy`. If missing: `pip install scipy --break-system-packages`.

**Rotational symmetry (k-fold) — adds the mandala/designed quality to flames:**

Add this inside the chaos game accumulation loop, immediately after computing valid pixel indices, before the `np.add.at` calls:

```python
# K-fold rotational symmetry
# After computing x[valid], y[valid] pixel coords, also plot k-1 rotated copies.
# k=1 means no symmetry (plain flame). k=3,4,5,6 produces structured beauty.
# k is chosen randomly at the start of generate(): k = rng.choice([1, 1, 3, 4, 5, 6])
# (weighted toward 1 so ~40% of flames are asymmetric, 60% have symmetry)

if symmetry_k > 1:
    angle_step = (2 * np.pi) / symmetry_k
    # xf, yf are the float coords (pre-pixel-index)
    for s in range(1, symmetry_k):
        angle = angle_step * s
        cos_a, sin_a = np.cos(angle), np.sin(angle)
        # Rotate the float coordinates
        xr = xf[valid] * cos_a - yf[valid] * sin_a
        yr = xf[valid] * sin_a + yf[valid] * cos_a
        # Map to pixel indices
        pxr = ((xr - xmin) / (xmax - xmin) * W).astype(int)
        pyr = ((yr - ymin) / (ymax - ymin) * H).astype(int)
        valid_r = (pxr >= 0) & (pxr < W) & (pyr >= 0) & (pyr < H)
        np.add.at(histogram,  (pyr[valid_r], pxr[valid_r]), 1)
        np.add.at(color_acc,  (pyr[valid_r], pxr[valid_r]), c[valid][valid_r])
```

Store `symmetry_k` in the params dict so `--seed` reproduces the same symmetry. The rotation happens in **float-space before pixel mapping** — do not rotate pixel indices, you'll get distorted results.

**Updated params dict** (add symmetry_k field):
```python
{
    "seed": int,
    "n_transforms": int,
    "symmetry_k": int,          # ← NEW: 1 = none, 3/4/5/6 = rotational
    "transforms": [{"affine": [6 floats], "variations": [str], "color": float}],
    "weights": [float],
    "palette": str,
    "n_points": int,
    "n_iterations": int,
    "density_sigma": float,     # ← NEW: gaussian blur sigma used
    "render_time_s": float,
    "resolution": [720, 720]    # output resolution (internal render is 1440×1440)
}
```

**Palettes:** Implement 6 named palettes as functions mapping `[0,1] → RGB`:
- `'electric'` — deep blue/purple to cyan/white (default, Electric Sheep vibe)
- `'ember'` — black to orange to yellow/white
- `'acid'` — green/lime through yellow 
- `'void'` — red/magenta through purple to black
- `'aurora'` — green/teal through pink
- `'ghost'` — single-hue white-blue, sparse and eerie

Palette selection is part of the random seed — pick one randomly each render.

**Transform parameter generation:**

```python
def _random_transforms(rng, n_transforms=3):
    """Generate n random affine transforms + variation assignments."""
    transforms = []
    weights = np.abs(rng.standard_normal(n_transforms))
    weights /= weights.sum()
    
    for i in range(n_transforms):
        # Random affine matrix (keep determinant between 0.3 and 0.9 for convergence)
        while True:
            a, b, c = rng.uniform(-1.5, 1.5, 3)
            d, e, f = rng.uniform(-1.5, 1.5, 3)
            det = a * e - b * d
            if 0.3 < abs(det) < 0.9:
                break
        affine = np.array([a, b, c, d, e, f])
        
        # Pick 1-2 variations (weighted sum)
        var_names = rng.choice(VARIATIONS, size=rng.integers(1, 3), replace=False)
        color_i = rng.uniform(0, 1)
        transforms.append((affine, var_names, float(color_i)))
    
    return transforms, weights
```

**Variation functions to implement** (all vectorized, take xa, ya arrays, return x, y arrays):

```python
def _var_linear(x, y):     return x, y
def _var_sinusoidal(x, y): return np.sin(x), np.sin(y)
def _var_spherical(x, y):
    r2 = x**2 + y**2 + 1e-10
    return x/r2, y/r2
def _var_swirl(x, y):
    r2 = x**2 + y**2
    return x*np.sin(r2) - y*np.cos(r2), x*np.cos(r2) + y*np.sin(r2)
def _var_horseshoe(x, y):
    r = np.sqrt(x**2 + y**2) + 1e-10
    return (x-y)*(x+y)/r, 2*x*y/r
def _var_polar(x, y):
    r = np.sqrt(x**2 + y**2) + 1e-10
    theta = np.arctan2(y, x)
    return theta/np.pi, r-1
def _var_spiral(x, y):
    r = np.sqrt(x**2 + y**2) + 1e-10
    theta = np.arctan2(y, x)
    return (np.cos(theta) + np.sin(r))/r, (np.sin(theta) - np.cos(r))/r
def _var_hyperbolic(x, y):
    r = np.sqrt(x**2 + y**2) + 1e-10
    theta = np.arctan2(y, x)
    return np.sin(theta)/r, r*np.cos(theta)
```

**Output resolution:** Render internally at **1440×1440**, then downsample to **720×720** for output. This is supersampling — it dramatically reduces aliasing on sharp filaments and thin tendrils, making them look smooth instead of jagged. The downsample uses PIL's `LANCZOS` filter:

```python
# After building the final rgb array at 1440×1440:
img_high = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
img_out = img_high.resize((720, 720), Image.LANCZOS)
return img_out, params
```

All histogram and coordinate math uses `W = H = 1440` internally. The output saved to disk and posted to Discord is the downsampled 720×720.

**Render parameters dict** (returned alongside image, saved to JSON sidecar):
```python
{
    "seed": int,
    "n_transforms": int,
    "transforms": [{"affine": [6 floats], "variations": [str], "color": float}],
    "weights": [float],
    "palette": str,
    "n_points": int,
    "n_iterations": int,
    "render_time_s": float,
    "resolution": [720, 720]
}
```

---

### 2. `utils/commands/art_handler.py`
The Discord command handler.

```python
async def handle_art_command(ctx, msg, send_kaia_response):
    """Handle !art command — generate fractal flame and post to Discord."""
```

**Full command syntax:**
- `!art` — random flame with random palette
- `!art flame` — explicit fractal flame (same as default)
- `!art mandelbrot` — Mandelbrot set (simpler fallback, implement in kaia_art.py)
- `!art --seed <int>` — reproduce a specific seed
- `!art --palette <name>` — force a specific palette

**Flow:**
1. Parse args from `msg.content`
2. Send a "generating..." message (this takes 3–8 seconds, user needs feedback): `await msg.channel.send("generating...")`
3. Build `FractalFlameRenderer` instance
4. Call `image, params = await asyncio.to_thread(renderer.generate, seed=seed)` — this runs the NumPy renderer on a thread pool, non-blocking
5. Save image to `memory/art/<uuid>.png` and params to `memory/art/<uuid>.json`
6. Generate Kaia's comment via Ollama (short call, ~2s): call `ctx.ollama_client.chat()` directly with the params as context, max 80 tokens, system prompt is brief "you are kaia, describe what you see in abstract terms"
7. Save image to `io.BytesIO()` buffer
8. Post to Discord: `await msg.channel.send(content=f"```\n{comment}\n```", file=discord.File(buf, filename="kaia_art.png"))`
9. Delete the "generating..." message

**GPU guard:** The Ollama comment call must go through the existing GPU semaphore. Look at how `message_processor.py` calls `self.ollama_client.chat()` and replicate the pattern — specifically the `_call_ollama_with_retries` pattern or the direct `ctx.ollama_client.chat()` with the GPU manager options. The fractal render itself is pure CPU and needs no GPU guard.

**Error handling:**
- If render throws (rare but possible with bad random params — NaN/inf in arrays): catch, log, send "something went wrong rendering, try again"
- If Ollama comment call fails: still post the image, just without the comment text
- If Discord file upload fails (503 etc, as seen in logs): catch `discord.errors.DiscordServerError`, log warning, don't crash

**The Ollama comment prompt:**
```python
comment_prompt = (
    f"you just generated a fractal flame image. "
    f"it used {params['n_transforms']} transforms, "
    f"variations: {', '.join(set(v for t in params['transforms'] for v in t['variations']))}, "
    f"palette: {params['palette']}. "
    f"describe what you see in it in one or two sentences. "
    f"be specific and a little strange. no 'it is a fractal' — you know what it is. "
    f"speak as kaia. lowercase only. no asterisks."
)
```

---

### 3. Registry wiring — `utils/commands/registry.py`

Add to `dispatch_command()`, before the general message handler fallthrough. Place it with the other `!` commands:

```python
from utils.commands.art_handler import handle_art_command

# In dispatch_command():
if content.startswith("!art"):
    await handle_art_command(ctx, msg, send_kaia_response)
    return True
```

---

## Dependencies to Add

**`requirements.txt` / install:**
```
Pillow>=10.0.0    # PIL — image creation (likely already installed)
numpy>=1.24.0     # numpy — likely already installed
scipy>=1.10.0     # gaussian_filter for density estimation — likely already installed via LlamaIndex
```

Verify with `pip show Pillow numpy scipy`. If scipy is missing: `pip install scipy --break-system-packages`. No GPU packages needed.

**Do NOT add:** `cuburn`, `pycuda`, `numba`, `torch`, `tensorflow`, `taichi`, or any GPU fractal library.

---

## Directory to Create

```
memory/art/           # fractal image outputs + JSON sidecars
```

Create it in `art_handler.py` on first use:
```python
ART_DIR = Path("memory/art")
ART_DIR.mkdir(parents=True, exist_ok=True)
```

---

## Optional Mandelbrot Implementation (Simpler Fallback)

If `!art mandelbrot` or `!art julia` is invoked, use a simpler renderer in `kaia_art.py`:

```python
def generate_mandelbrot(self, seed=None) -> tuple[Image.Image, dict]:
    rng = np.random.default_rng(seed)
    
    # Random zoom into interesting region
    zoom_targets = [
        (-0.7269, 0.1889, 0.005),   # classic spiral
        (-0.1592, 1.0317, 0.01),    # seahorse valley
        (-1.7686, 0.0042, 0.005),   # antenna tip
        (-0.5251, 0.5255, 0.02),    # mini brot
    ]
    cx, cy, zoom = zoom_targets[rng.integers(len(zoom_targets))]
    jitter = rng.uniform(-zoom*0.3, zoom*0.3, 2)
    cx += jitter[0]; cy += jitter[1]
    
    W, H = 720, 720
    max_iter = 256
    x = np.linspace(cx - zoom, cx + zoom, W)
    y = np.linspace(cy - zoom*H/W, cy + zoom*H/W, H)
    C = x[np.newaxis, :] + 1j * y[:, np.newaxis]
    
    Z = np.zeros_like(C)
    M = np.zeros(C.shape, dtype=float)
    escaped = np.zeros(C.shape, dtype=bool)
    
    for i in range(max_iter):
        mask = ~escaped
        Z[mask] = Z[mask]**2 + C[mask]
        newly_escaped = mask & (np.abs(Z) > 2)
        M[newly_escaped] = i + 1 - np.log2(np.log2(np.abs(Z[newly_escaped]) + 1e-10))
        escaped |= newly_escaped
    
    # Smooth coloring + palette
    M_norm = M / max_iter
    palette_name = rng.choice(list(self.PALETTES.keys()))
    rgb = self.PALETTES[palette_name](M_norm)
    img_array = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(img_array), {"type": "mandelbrot", "seed": seed, ...}
```

---

## Integration with Existing Systems

### GPU semaphore
The Ollama comment call in `art_handler.py` must use the GPU manager. The correct pattern (from how the codebase works):

```python
from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
gpu_mgr = OllamaGPUManager()
options = gpu_mgr.get_gpu_options(for_chat=True)
response = await ctx.ollama_client.chat(
    model=ctx.config.chat_model,
    messages=[
        {"role": "system", "content": "you are kaia. lowercase only."},
        {"role": "user", "content": comment_prompt}
    ],
    options=options
)
comment = response['message']['content'].strip()
```

Wrap this in a try/except. If it fails, `comment = ""` and post the image without text.

### Watchdog suppression
The render loop takes 3–8 seconds synchronously (in a thread). The loop watchdog monitors the asyncio event loop, not threads, so this is fine — no suppression needed.

### Rate limiting
Add a simple cooldown: store `last_art_time` in `bot_state` (or module-level dict keyed by channel). Minimum 30 seconds between `!art` calls per channel. Return `"generating takes a moment, wait 30s"` if called too fast.

```python
_last_art_time: dict[int, float] = {}  # channel_id -> timestamp, module-level

async def handle_art_command(ctx, msg, send_kaia_response):
    channel_id = msg.channel.id
    now = time.time()
    if now - _last_art_time.get(channel_id, 0) < 30:
        await send_kaia_response(msg.channel, "still cooling down from the last one.")
        return
    _last_art_time[channel_id] = now
    ...
```

---

## File Structure Summary

```
utils/
  commands/
    art_handler.py          ← NEW: !art command handler
  core/
    kaia_art.py             ← NEW: FractalFlameRenderer + MandelbrotRenderer
utils/commands/registry.py  ← EDIT: add !art dispatch
memory/
  art/                      ← NEW DIR: auto-created on first run
    <uuid>.png
    <uuid>.json
```

---

## Testing

After implementation, test with:
1. `!art` — should produce a flame in ~6–12s with Kaia's comment. Run 5–6 times — roughly half should have rotational symmetry (k=3/4/5/6), the rest asymmetric
2. `!art mandelbrot` — Mandelbrot zoom, should be ~2s
3. `!art --seed 42` — run twice, images must be pixel-identical (deterministic)
4. `!art --palette ember` — forced palette, verify warm orange/yellow tones
5. Rapid fire `!art` twice — second should hit cooldown message

Check logs for:
- No `CUDA`/`GPU` errors (renderer is CPU-only)
- `[art]` render time logged (should be <15s for default config)
- The Ollama comment call completing in <5s
- Discord image post succeeding (503s are Discord-side transient, not our bug — the handler catches them)

---

## Approximate Render Times (CPU, RTX 3060 system / i7 equivalent)

| Config | Internal res | Output res | Time |
|--------|-------------|------------|------|
| 500k points, 50 iter, no symmetry | 1440×1440 | 720×720 | ~6–9s |
| 500k points, 50 iter, k=5 symmetry | 1440×1440 | 720×720 | ~8–12s |
| 1M points, 100 iter | 1440×1440 | 720×720 | ~14–20s |
| Mandelbrot 720×720, 256 iter | 720×720 | 720×720 | ~1–2s |

**Default config:** 500k points, 50 iterations, 1440→720 supersampling, density sigma=1.2, random symmetry k. This renders in ~6–12s depending on symmetry. That's acceptable for a Discord command with a "generating..." placeholder message.

If render times prove too slow in practice, reduce to 300k points — quality drop is minor, speed improves significantly.
