# VRAM Management System - RTX 3060 12GB

## Hardware Specs
- **GPU**: RTX 3060 12GB VRAM
- **CPU**: Ryzen 5 9600X  
- **RAM**: 32GB system RAM

## Model Specification
- **gemma3:12b** (Chat): ~8.0 GB VRAM
- **nomic-embed-text** (RAG): ~0.5 GB VRAM

## VRAM Allocation Strategy

Kaia is optimized for continuous presence. Unlike previous versions that swapped models for vision and image generation, the current architecture focuses on maintaining high-performance chat availability with a massive context window.

### 1. Residency Policy
- **Chat Model**: Stays loaded in VRAM permanently.
- **Embedding Model**: Loaded on-demand for RAG retrieval but generally stays resident if memory permits.

### 2. Context Window Optimization
- **Default Window**: 28,000 tokens.
- **VRAM Impact**: This consumes approximately 2.3GB of KV cache on top of the model weights.
- **Budget**: 8GB (gemma3) + 2.3GB (Context) + 0.5GB (System/Embed) = ~10.8GB Total.
- **Headroom**: ~1.2GB remains for OS and display buffers.

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
✅ **28k Context window** fully utilized on 12GB hardware.
✅ **Modular unloading** of non-essential models prevents fragmentation.
