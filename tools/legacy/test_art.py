"""Standalone test for the fractal flame renderer."""
import sys, types

mock_logger = types.ModuleType("utils.infrastructure.logging.kaia_logger")
mock_logger.log_info = lambda msg: print(f"INFO: {msg}")
mock_logger.log_debug = lambda msg: None
mock_logger.log_warning = lambda msg: print(f"WARN: {msg}")
mock_logger.log_error = lambda msg: print(f"ERROR: {msg}")

utils_mod = types.ModuleType("utils")
utils_mod.__path__ = ["utils"]
infra_mod = types.ModuleType("utils.infrastructure")
infra_mod.__path__ = ["utils/infrastructure"]
log_mod = types.ModuleType("utils.infrastructure.logging")
log_mod.__path__ = ["utils/infrastructure/logging"]
log_mod.kaia_logger = mock_logger

sys.modules["utils"] = utils_mod
sys.modules["utils.infrastructure"] = infra_mod
sys.modules["utils.infrastructure.logging"] = log_mod
sys.modules["utils.infrastructure.logging.kaia_logger"] = mock_logger

sys.path.insert(0, ".")
from utils.core.kaia_art import FractalFlameRenderer
import numpy as np

renderer = FractalFlameRenderer()

for seed in [42, 12345, 999, 7777, 314159]:
    print(f"\n--- Seed {seed} ---")
    img, params = renderer.generate(seed=seed)
    arr = np.array(img)
    mean_b = arr.mean()
    max_b = arr.max()
    nonzero = (arr > 10).sum() / arr.size * 100
    print(f"  Palette: {params['palette']} | k={params['symmetry_k']} | xforms={params['n_transforms']}")
    print(f"  Mean: {mean_b:.1f}/255 | Max: {max_b} | Non-black: {nonzero:.1f}% | Time: {params['render_time_s']}s")
    status = "✓" if mean_b > 15 else "⚠️ DARK"
    print(f"  {status}")
    img.save(f"/home/ekco/github/Kaiacord/test_flame_{seed}.png")

print("\nDone.")
