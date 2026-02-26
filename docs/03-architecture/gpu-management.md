# VRAM Management System - RTX 3060 12GB

## Hardware Specs
- **GPU**: RTX 3060 12GB VRAM
- **CPU**: Ryzen 5 9600X  
- **RAM**: 32GB system RAM

## Model Specification

| Model | Purpose | Runs On | VRAM Impact |
|:------|:--------|:--------|:------------|
| **gemma3:12b** | Chat / Generation | GPU | ~8.0 GB |
| **gemma2:2b** | Intent Classification | CPU (`num_gpu: 0`) | 0 GB |
| **nomic-embed-text-cpu** | RAG Embeddings | CPU (`num_gpu: 0`) | 0 GB |

## VRAM Allocation Strategy

Kaia is optimized for continuous presence on a single 12GB GPU. Unlike previous versions that swapped models in and out, the current architecture keeps the chat model permanently loaded and offloads all auxiliary inference to CPU.

### 1. Residency Policy
- **Chat Model** (`gemma3:12b`): Stays loaded in VRAM permanently. Never unloaded.
- **Classification Model** (`gemma2:2b`): Runs entirely on CPU via `ThreadPoolExecutor`. Zero VRAM usage.
- **Embedding Model** (`nomic-embed-text-cpu`): Runs on CPU via `ollama_additional_kwargs: {"num_gpu": 0}`. Zero VRAM usage.

### 2. Context Window Optimization
- **Default Window**: 8192 tokens (config-driven via `config.max_context_tokens`).
- **VRAM Impact**: Approximately 0.6GB of KV cache on top of the model weights.
- **Budget**: 8GB (gemma3:12b) + 0.6GB (KV cache) + 0.5GB (system overhead) = ~9.1GB total.
- **Headroom**: ~2GB remains for OS, display buffers, and transient allocations.

### 3. GPU Semaphore Guard
The system uses a global `asyncio.Semaphore(1)` to prevent concurrent GPU access:
- All GPU-bound operations (chat, dream generation) acquire the semaphore before calling Ollama.
- A `ContextVar` tracks re-entrancy to prevent deadlocks from nested GPU calls.
- The guard is managed through `GPUMemoryManager.run_with_gpu_guard()`.

### 4. Boot Sequence (Phase 1/2/3)
On startup, `on_ready()` runs a sequenced boot:
- **Phase 1**: `gemma3:12b` loaded exclusively via direct `ollama.generate()` under `_gpu_startup_lock`. Timeout: `model_load_seconds` (default 240s). A 5s recovery delay after Ollama cleanup ensures the daemon is ready.
- **Phase 1.5**: `ModelWarmPool` and `IntentParser` (gemma2:2b, CPU-only) initialized AFTER GPU is claimed.
- **Phase 2**: Bot marked ready to serve messages.
- **Phase 3**: RAG init, classifier warm, knowledge refresh — all background, non-blocking.

## Adaptive Performance Monitoring

Kaia monitors response times and memory pressure through the `PerformanceMonitor`.

### Performance Indicators
| Metric | Healthy Range | Action on Degradation |
|:---|:---|:---|
| **Chat Latency** | < 10.0s | Check for background model updates or GPU temperature. |
| **RAG Retrieval** | < 2.0s | Verify vector index integrity or disk I/O speed. |
| **Memory Pressure** | < 11.5GB | If VRAM exceeded, the system will trigger a graceful model reload. |

## Graceful Shutdown & VRAM Teardown

If the application is stopped (either via `Ctrl+C` or the dashboard `[Q]uit` key), it triggers a specialized multi-tier teardown to ensure Ollama completely releases the 12GB VRAM lock:
1. **Asynchronous Teardown**: `dashboard_manager.py` utilizes `asyncio.shield` to forcibly finalize HTTP unloading requests during OS interrupt signals, before the event loop drops.
2. **Synchronous Fallback**: For hard-kills, `kill_orphaned_runners()` in `clear_gpu_memory.py` is called. It bypasses `asyncio` entirely, issuing blocking `urllib` POST requests with `keep_alive: 0` to immediately flush the Master Ollama daemon, followed by actively terminating `ollama runner` processes if they refuse to close.

## Troubleshooting VRAM Issues

### CUDA Out of Memory (OOM) (`cudaMalloc failed`)
If you encounter OOM errors (e.g., during model pre-warming or generation):
1. **Video Games / Background Apps**: `gemma3:12b` combined with a 8K token context window consumes ~9.1GB to 10GB of VRAM. This provides high stability even if other apps are running.
   - *Fix*: If you still hit VRAM issues, open `config/kaia.yaml` and reduce `max_context_tokens` to `4096` to lower the KV cache size footprint and free up space.
2. **Restart Kaia**: `python Kaiacord.py`
3. **Clear GPU Cache**: Run `python utils/infrastructure/gpu/clear_gpu_memory.py` manually.

## Summary
✅ **Chat model always resident** for low latency.
✅ **Classification & embeddings on CPU** — zero GPU contention.
✅ **8K Context window** config-driven, optimized for 12GB hardware stability.
✅ **Semaphore guard** prevents concurrent GPU access.
✅ Sequenced Phase 1/2/3 boot prevents VRAM contention at startup.
