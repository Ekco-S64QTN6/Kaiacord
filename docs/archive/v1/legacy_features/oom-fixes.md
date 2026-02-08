# CUDA Out of Memory - Fixes Applied

## Problem
CUDA OOM errors during FLUX.1-schnell image generation due to memory fragmentation:
- PyTorch reserves memory but doesn't allocate it efficiently
- Error occurs during `FluxTransformer2DModel` warmup (trying to allocate 5.54 GiB)
- GPU has 11.62 GiB total, but fragmentation prevents large allocations

## Fixes Applied (2026-01-18)

### 1. More Aggressive Memory Cleanup
**File**: `kaia_image.py` lines 151-164

Added before transformer loading:
```python
# Additional aggressive cleanup to prevent fragmentation
torch.cuda.synchronize()  # Wait for all CUDA operations to complete
torch.cuda.reset_peak_memory_stats()  # Reset memory stats

# Force another cache clear after sync
torch.cuda.empty_cache()

# Log memory status
logger.info(f"GPU memory allocated: {torch.cuda.memory_allocated() / 1024**3:.2f} GiB")
logger.info(f"GPU memory reserved: {torch.cuda.memory_reserved() / 1024**3:.2f} GiB")
```

### 2. Reduced Memory Limit (More Headroom)
**File**: `kaia_image.py` line 18

Changed from **0.86** (10 GB) to **0.80** (9.3 GB):
```python
torch.cuda.set_per_process_memory_fraction(0.80)  # Leave more headroom
```

This gives PyTorch's allocator more room to work with and reduces fragmentation.

### 3. Pre-Flight Memory Check
**File**: `kaia_image.py` lines 165-169

Added safety check before loading transformer:
```python
free_memory = (torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated()) / 1024**3
logger.info(f"Free GPU memory: {free_memory:.2f} GiB")
if free_memory < 6.0:
    raise RuntimeError(f"Insufficient GPU memory...")
```

This fails fast with a clear error message instead of waiting for PyTorch to crash.

### 4. Better OOM Error Handling
**File**: `kaia_image.py` lines 220-227

Now catches `torch.cuda.OutOfMemoryError` specifically and provides recovery steps:
```python
except torch.cuda.OutOfMemoryError as oom_err:
    logger.error("RECOVERY STEPS:")
    logger.error("1. Run: python clear_gpu_memory.py")
    logger.error("2. If that doesn't help, restart the bot to fully clear VRAM")
    logger.error("3. Ensure Ollama models are unloaded...")
```

### 5. GPU Memory Utility Script
**File**: `clear_gpu_memory.py` (NEW)

Can be run standalone to aggressively clear GPU memory without restarting:
```bash
python clear_gpu_memory.py
```

This script:
- Runs GC 5 times
- Empties CUDA cache multiple times
- Synchronizes CUDA operations
- Resets memory stats
- Shows current GPU memory usage

### 6. Environment Variable Timing
**File**: `kaia_image.py` lines 1-10

Moved `PYTORCH_ALLOC_CONF` to the very top of the file, before any other imports. This ensures PyTorch's CUDA allocator reads the settings during initialization.

### 7. Explicit Device Management
**File**: `kaia_image.py` lines 211-226

Added `device_map={"": 0}` to the transformer loading and `pipe_gen.to("cuda")` to the pipeline. This prevents `accelerate` from offloading weights to CPU when VRAM is tight, which was causing "Input type mismatch" errors.

## Final Results
- **Ollama Unloading**: Successfully unloads all models (including embedding models) before generation.
- **Memory Usage**: Transformer now loads correctly on GPU (using ~8.2GB VRAM).
- **Success**: Image generation now completes in ~15 seconds after model loading.

## How to Use
1. Start the bot: `./venv/bin/python Kaiacord.py`
2. If OOM occurs, run: `./venv/bin/python clear_gpu_memory.py`
