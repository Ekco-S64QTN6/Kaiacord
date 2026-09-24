# VRAM Management System - RTX 3060 12GB

## Hardware Specs
- **GPU**: RTX 3060 12GB VRAM
- **CPU**: Ryzen 5 9600X  
- **RAM**: 32GB system RAM

## Model Specification

| Model | Purpose | Runs On | VRAM Impact |
|:------|:--------|:--------|:------------|
| **gemma3:12b** | Chat / Generation | GPU | ~7.0 GB |
| **nomic-embed-text-cpu** | RAG Embeddings | CPU (`num_gpu: 0`) | 0 GB |

Two models, and only two. A `gemma2:2b` intent classifier was listed here until
September 2026; it ran on every ambiguous message and its verdict was never read,
so the model, its dispatch and its warm-up were removed. Intent is regex only.

## VRAM Allocation Strategy

Kaia is optimized for continuous presence on a single 12GB GPU. Unlike previous versions that swapped models in and out, the current architecture keeps the chat model permanently loaded and offloads all auxiliary inference to CPU.

### 1. Residency Policy
- **Chat Model** (`gemma3:12b`): Stays loaded in VRAM permanently — *provided every request asks
  for the same runner*. Ollama keeps one runner per model and reloads it whenever a request's
  `num_ctx`, `num_gpu`, `num_thread` or `main_gpu` differ from the loaded one, so a single call
  that builds its own options evicts the chat runner and the next chat turn pays a full reload.
  Build options with `gpu_manager.chat_options(**overrides)` and override sampling
  (`temperature`, `num_predict`) only. Until September 2026 the inner monologue sent no
  `num_ctx`, and its journal entries show gemma3 reloading at 4,096 context every 15 minutes.
  `journalctl -u ollama | grep "n_ctx  "` lists every load with its context size.
- **Embedding Model** (`nomic-embed-text-cpu`): Runs on CPU via `ollama_additional_kwargs: {"num_gpu": 0}`. Zero VRAM usage.

### 2. Context Window Optimization
- **Default Window**: 16,384 tokens (`performance.max_context_tokens`).
  The per-turn budget subtracts `system_reserve_tokens` and `max_response_tokens` before
  splitting the remainder between RAG and history, so anything added to the system prompt
  comes directly out of retrieval headroom.
- **VRAM Impact**, measured from Ollama's own load lines and `nvidia-smi` — gemma3 keeps a
  full-length KV cache for its global layers and a 1,536-cell one for its sliding-window
  layers, and loads its vision encoder beside the text model:

  | `max_context_tokens` | Weights | KV cache (f16) | Vision encoder + buffers | `llama-server` total |
  |:--|:--|:--|:--|:--|
  | 16,384 | 6.8 GiB | 1.5 GiB | ~1.2 GiB | ~9.5 GiB |
  | 24,576 | 6.8 GiB | 2.0 GiB | ~1.2 GiB | 9.9 GiB (10,188 MiB measured) |

  All 49 layers stay on the GPU at either size. The desktop, a browser and Discord take
  roughly another 1.2 GiB of the 12, so at 24,576 the card sits within a few hundred MiB of
  full. The KV cache is the one large piece that can shrink without losing context:
  `OLLAMA_KV_CACHE_TYPE=q8_0` (with `OLLAMA_FLASH_ATTENTION=1`) in Ollama's service
  environment halves it, about 1 GiB back at 24,576.
- **The bot process itself must hold no GPU memory.** `clear_gpu_memory()` called
  `torch.cuda.synchronize()` and `empty_cache()` in a process that never uses CUDA, which
  *created* a 104 MiB context on every boot. It now returns unless this process has
  initialised CUDA. `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` should show
  only `llama-server` for the bot's side. Ollama's scheduler *predicts* far more (16 GiB
  at 24,576) and logs "predicted to exceed available memory, evicting" — that is its
  estimate, not the allocation, and what it evicts is the CPU embedding runner.

### 3. GPU Semaphore Guard
The system uses a global `asyncio.Semaphore(1)` to prevent concurrent GPU access:
- All GPU-bound operations (chat, dream generation, dream consolidation, forum drafting,
  metadata enrichment) acquire the semaphore before calling Ollama.
- Every call carries a `GPUTaskPriority`, but it is only logged: the semaphore is first come,
  first served, so live chat does not jump ahead of queued `BACKGROUND` work. The number waiting
  (`gpu_queue_depth()`) is the queue size in `!sysmon` and on the dashboard.

**The semaphore does not span processes.** `gpu_semaphore = asyncio.Semaphore(1)` is a
module-level object, so a standalone tool — `consolidate_dreams.py`, `enrich_metadata.py`,
`synthesize_technical_knowledge.py`, the news refresh subprocess — gets its *own* semaphore that
coordinates with nothing the bot is doing. Calling `run_with_gpu_guard` there serialises the tool
against itself and nothing more.

What actually keeps them from colliding is the Ollama daemon: both processes talk to one server,
which queues work per model rather than running it concurrently. So the failure mode is **latency,
not VRAM thrash or corruption** — a message arriving mid-batch waits for the in-flight generation
to finish, which for a 400-token metadata call is several seconds.

Practical consequence: a long batch is safe to run while she is up, but it will make her slower to
answer for as long as it runs. Stop it if someone is actually talking to her. Every batch tool in
this repository is resumable and idempotent for that reason.
- A `ContextVar` tracks re-entrancy to prevent deadlocks from nested GPU calls.
- The guard is managed through `GPUMemoryManager.run_with_gpu_guard()`.

### 4. Boot Sequence (Phase 1/2/3)
On startup, `on_ready()` runs a sequenced boot:
- **Phase 1**: `gemma3:12b` loaded exclusively via direct `ollama.generate()` under `_gpu_startup_lock`. Timeout: `model_load_seconds` (default 240s). A 5s recovery delay after Ollama cleanup ensures the daemon is ready.
- **Phase 1.5**: `ModelWarmPool` and `IntentParser` (regex, no model) initialized AFTER GPU is claimed.
- **Phase 2**: Bot marked ready to serve messages.
- **Phase 3**: RAG init and knowledge refresh — background, non-blocking. There is no
  classifier to warm.

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
1. **Video Games / Background Apps**: `gemma3:12b` combined with a 8K token context window consumes ~8GB of VRAM. This provides high stability even if other apps are running.
   - *Fix*: If you still hit VRAM issues, open `config/kaia.yaml` and reduce `max_context_tokens` to `4096` to lower the KV cache size footprint and free up space.
2. **Restart Kaia**: `python Kaiacord.py`
3. **Clear GPU Cache**: Run `python utils/infrastructure/gpu/clear_gpu_memory.py` manually.

## Summary
✅ **Chat model always resident** for low latency.
✅ **Classification & embeddings on CPU** — zero GPU contention.
✅ **8K Context window** config-driven, optimized for 12GB hardware stability.
✅ **Semaphore guard** prevents concurrent GPU access.
✅ Sequenced Phase 1/2/3 boot prevents VRAM contention at startup.
