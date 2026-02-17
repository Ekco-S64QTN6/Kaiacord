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
| **nomic-embed-text** | RAG Embeddings | CPU (`num_gpu: 0`) | 0 GB |

## VRAM Allocation Strategy

Kaia is optimized for continuous presence on a single 12GB GPU. Unlike previous versions that swapped models in and out, the current architecture keeps the chat model permanently loaded and offloads all auxiliary inference to CPU.

### 1. Residency Policy
- **Chat Model** (`gemma3:12b`): Stays loaded in VRAM permanently. Never unloaded.
- **Classification Model** (`gemma2:2b`): Runs entirely on CPU via `ThreadPoolExecutor`. Zero VRAM usage.
- **Embedding Model** (`nomic-embed-text`): Runs on CPU via `ollama_additional_kwargs: {"num_gpu": 0}`. Zero VRAM usage.

### 2. Context Window Optimization
- **Default Window**: 20,000 tokens (config-driven via `config.max_context_tokens`).
- **VRAM Impact**: Approximately 1.5GB of KV cache on top of the model weights.
- **Budget**: 8GB (gemma3:12b) + 1.5GB (KV cache) + 0.5GB (system overhead) = ~10GB total.
- **Headroom**: ~2GB remains for OS, display buffers, and transient allocations.

### 3. GPU Semaphore Guard
The system uses a global `asyncio.Semaphore(1)` to prevent concurrent GPU access:
- All GPU-bound operations (chat, dream generation) acquire the semaphore before calling Ollama.
- A `ContextVar` tracks re-entrancy to prevent deadlocks from nested GPU calls.
- The guard is managed through `GPUMemoryManager.run_with_gpu_guard()`.

### 4. Pre-Warm Timeout
- On startup, `ModelWarmPool.pre_warm()` is wrapped in a 300s `asyncio.wait_for`.
- If the model takes >5 minutes to load, it's treated as a CRITICAL FAILURE with full traceback logging.
- This prevents indefinite startup hangs.

## Adaptive Performance Monitoring

Kaia monitors response times and memory pressure through the `PerformanceMonitor`.

### Performance Indicators
| Metric | Healthy Range | Action on Degradation |
|:---|:---|:---|
| **Chat Latency** | < 10.0s | Check for background model updates or GPU temperature. |
| **RAG Retrieval** | < 2.0s | Verify vector index integrity or disk I/O speed. |
| **Memory Pressure** | < 11.5GB | If VRAM exceeded, the system will trigger a graceful model reload. |

## Troubleshooting VRAM Issues

### CUDA Out of Memory (OOM)
If you encounter OOM errors (typically after long uptime or OS updates):
1. **Restart Kaia**: `python Kaiacord.py`
2. **Clear GPU Cache**: Run `python tools/diagnostics/clear_gpu_memory.py`
3. **Check Background Processes**: Ensure no other AI tools (like ComfyUI or SD) are hogging VRAM.

## Summary
✅ **Chat model always resident** for low latency.
✅ **Classification & embeddings on CPU** — zero GPU contention.
✅ **20K Context window** config-driven, optimized for 12GB hardware.
✅ **Semaphore guard** prevents concurrent GPU access.
✅ **5-minute pre-warm timeout** ensures boot reliability.
