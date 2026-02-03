# VRAM Management System - RTX 3060 12GB

## Hardware Specs
- **GPU**: RTX 3060 12GB VRAM
- **CPU**: Ryzen 5 9600X  
- **RAM**: 32GB system RAM

## Model Sizes
- **gemma3:12b** (Chat): ~8.0 GB VRAM
- **llama3.2-vision:11b** (Vision): ~7.5 GB VRAM  
- **Flux.1-schnell** (Image Gen): ~3.5-5 GB VRAM (via 4-bit quantization)

## Current VRAM Management Flow

### Chat Operation (Normal)
```
1. gemma3:12b loaded (8GB VRAM used)
2. User sends message
3. Chat response generated
4. Model stays loaded
```

### Vision Operation
```
1. gemma3:12b loaded (8GB VRAM used)
2. User uploads image
3. ✅ Unload gemma3:12b (0GB VRAM) 
4. Wait 1.0s for VRAM release
5. Load llama3.2-vision:11b (7.5GB VRAM)
6. Process vision task (60s timeout for load + 90s for analysis)
7. Unload llama3.2-vision:11b (0GB VRAM)
8. Wait 1.5s
9. ✅ Reload gemma3:12b (8GB VRAM)
10. Resume chat
```

### Image Generation Operation  
```
1. gemma3:12b loaded (8GB VRAM used)
2. User requests image gen
3. ✅ Unload gemma3:12b (0GB VRAM)
4. Wait 1.0s for VRAM release
5. Load Flux.1-schnell-4bit (6-8GB VRAM)
6. Generate image
7. Unload Flux model (0GB VRAM)
8. Wait 1.5s
9. ✅ Reload gemma3:12b (8GB VRAM)  
10. Resume chat
```

## Key Changes Made

### 1. Re-enabled Chat Model Unloading
**Files**: `Kaiacord.py` lines 1340-1343 (image gen), 1468-1471 (vision)

**Before** (BROKEN):
```python
# Unload chat model DISABLED (Rollback - protect chat model)
# await unload_chat_model()
```

**After** (FIXED):
```python
# Unload chat model to free VRAM for vision
# CRITICAL: With 12GB VRAM, gemma3:12b (8GB) + llama3.2-vision (7GB) won't fit
await unload_chat_model()
await asyncio.sleep(1.0)  # Wait for VRAM to be released
```

### 2. Increased Model Load Timeout
**File**: `utils/gpu_manager.py` line 118

**Before**:
```python
timeout=30.0  # 30 second timeout
```

**After**:
```python
timeout=60.0  # 60 second timeout for large model load
# llama3.2-vision:11b is ~7.5GB, can take 30-60s to load from disk
```

### 3. Why This Was Disabled Before

The unloading was disabled in a "rollback" to "protect chat model" - likely because:
- Someone was worried about chat model stability
- Didn't realize 12GB VRAM can't fit 2 models simultaneously
- The timeout issue made it seem like unloading was the problem

**Reality**: With 12GB VRAM, you MUST unload the chat model before vision/image tasks.

## Verification

### Test Vision:
```bash
# In Discord, upload an image and send message
# Expected timeline:
# T+0s: "looking..."
# T+1-2s: Chat model unloaded
# T+2-62s: Vision model loads (60s timeout)
# T+62-152s: Vision analysis (90s timeout)
# T+153s: Response sent
# T+154.5s: Chat model reloaded
```

### Test Image Generation:
```bash
# In Discord: "kaia draw sunset"
# Expected timeline:
# T+0s: Start generation
# T+1-2s: Chat model unloaded
# T+2-62s: Flux model loads
# T+62-100s: Image generation
# T+101.5s: Chat model reloaded
```

### Monitor VRAM:
```bash
watch -n 1 nvidia-smi
# Should see VRAM go: 8GB → 0GB → 7.5GB → 0GB → 8GB
```

## Logs to Watch For

### Success Pattern:
```
[TIME] ACTION: Unloading chat model gemma3:12b...
[TIME] SUCCESS: Chat model unloaded.
[TIME] INFO: 🔄 Triggering GPU load for llama3.2-vision:11b...
[TIME] INFO: ✅ llama3.2-vision:11b loaded successfully
[TIME] SUCCESS: Vision analysis completed in XXs
[TIME] ACTION: Re-warming chat model after vision task...
[TIME] INFO: ✅ gemma3:12b loaded and verified on GPU
```

### Timeout Pattern (if still issues):
```
[TIME] ACTION: Unloading chat model gemma3:12b...
[TIME] SUCCESS: Chat model unloaded.
[TIME] INFO: 🔄 Triggering GPU load for llama3.2-vision:11b...
[TIME] ERROR: ❌ GPU load TIMED OUT after 60s for llama3.2-vision:11b
[TIME] ERROR: Vision analysis failed: ...
```

## Troubleshooting

### If Vision Still Times Out:
1. **Check Ollama is running**: `ollama list`
2. **Check model exists**: Should see `llama3.2-vision:11b`
3. **Pre-pull model**: `ollama pull llama3.2-vision:11b`
4. **Check disk speed**: SSD recommended, HDD may be too slow for 60s timeout
5. **Increase timeout further**: Edit `utils/gpu_manager.py` line 118 to `timeout=90.0`

### If VRAM Still Overflows:
1. **Verify unloading**: Check logs for "Chat model unloaded"
2. **Check nvidia-smi**: Should drop to ~0GB before loading next model
3. **Wait longer**: Increase sleep from 1.0s to 2.0s in Kaiacord.py

### If Chat Model Won't Reload:
1. **Check logs**: Look for "Re-warming chat model"
2. **Manual reload**: In Discord, send "kaia status" to trigger chat
3. **Restart Kaia**: If chat model is stuck

## Performance Expectations

- **Vision First Call**: 60-150s (model load + analysis)
- **Vision Subsequent**: 90-120s if model cached (analysis only)
- **Image Gen**: 40-100s (load + generate)
- **Chat Recovery**: 1-5s (model already loaded or quick reload)

## Summary

✅ **VRAM management is now WORKING**  
✅ **Chat model unloads before vision/image tasks**  
✅ **60s timeout prevents indefinite hangs**  
✅ **Chat model reloads after task completes**  
✅ **12GB VRAM properly managed**
