# Migration Guide: Kaia v1.0 → v2.0

## Overview

This guide helps you migrate from Kaia v1.0 (monolithic) to v2.0 (modular architecture).

**Good news**: v2.0 is 100% backward compatible. Your bot will continue to work without any changes.

**Better news**: Adopting the new architecture gives you better stability, maintainability, and future-proofing.

---

## What's Changed?

### 1. Code Organization

**Before (v1.0)**:
- Single `Kaiacord.py` file (2390 lines)
- All logic mixed together

**After (v2.0)**:
- `Kaiacord.py` (2260 lines → target <1000)
- `bot/managers/`: Config, state, rate limiting (**✅ DONE**)
- `bot/handlers/`: Message, command, event handling (⏳ Phase 2)
- `bot/services/`: RAG, vision, image wrappers (⏳ Phase 2)
- `utils/gpu_memory_manager.py`: Unified GPU management (**✅ DONE**)

### 2. Import Paths

**Old** (still works):
```python
from Kaiacord import config, bot_state, rate_limiter
```

**New** (recommended):
```python
from bot.managers.config import config
from bot.managers.state import bot_state
from bot.managers.rate_limiter import RateLimiter
```

### 3. Exception Handling

**Old**:
```python
try:
    await generate_image(prompt)
except Exception as e:
    print(f"Error: {e}")
```

**New**:
```python
from bot.exceptions import VRAMInsufficientError, get_user_friendly_message

try:
    await generate_image(prompt)
except VRAMInsufficientError as e:
    user_msg = get_user_friendly_message(e)
    await channel.send(user_msg)
```

### 4. GPU Memory Management

**Old**:
- Manual VRAM checks
- Direct torch.cuda calls
- No priority system

**New**:
```python
from utils.gpu_memory_manager import gpu_memory_manager, GPUTaskPriority

# Request VRAM with priority
if await gpu_memory_manager.request_vram(
    task_id="my_task",
    vram_gb=8.0,
    priority=GPUTaskPriority.IMAGE_GEN,
    model_name="FLUX"
):
    # Proceed with task
    ...
    
    # Release when done
    await gpu_memory_manager.release_vram("my_task")
```

### 5. Configuration

**Old**:
- Hardcoded values in `Config` class
- Environment variables only

**New**:
- `config/default_config.yaml` (defaults) (**✅ DONE**)
- `config/kaia.yaml` (user overrides) (⏳ Phase 3)
- Environment variables (highest priority)

---

## Migration Steps

### Step 1: Update Your Installation

```bash
cd /path/to/Kaiacord
git pull origin main
pip install -r requirements.txt
```

### Step 2: No Code Changes Required!

Your existing code will continue to work due to backward compatibility.

### Step 3: (Optional) Adopt New Patterns

If you have custom scripts or extensions, consider updating them:

#### Update Imports

**Find and replace**:
```python
# Old
from Kaiacord import config
from Kaiacord import bot_state  
from Kaiacord import rate_limiter

# New
from bot.managers.config import config
from bot.managers.state import bot_state
from bot.managers.rate_limiter import RateLimiter
```

#### Use New Exception Types

```python
# Add to imports
from bot.exceptions import (
    GPUMemoryError,
    VisionTimeoutError,
    RAGLockTimeout,
    get_user_friendly_message
)

# Update exception handling
try:
    # Your code
    pass
except GPUMemoryError as e:
    msg = get_user_friendly_message(e)
    # Handle error
```

### Step 4: (Optional) Create User Config

Create `config/kaia.yaml` to override defaults:

```yaml
# config/kaia.yaml
performance:
  rag_top_k: 10  # Override default of 8
  max_memory_messages: 50  # Override default of 30

gpu:
  image_gen_min_vram_gb: 10.0  # Be more conservative
  
logging:
  level: "DEBUG"  # More verbose logging
```

> **Note**: YAML config loading will be available in Phase 3. For now, use environment variables.

---

## Configuration Migration

### Environment Variables (Current)

**No changes required**. Existing environment variables still work:

```bash
# .env
DISCORD_TOKEN=your_token
GEMINI_API_KEY=your_key  # For news (optional)
BLACKLISTED_CHANNELS=general,announcements
```

### Future: YAML Configuration (Phase 3)

When Phase 3 is complete, you can migrate to YAML:

```yaml
# config/kaia.yaml
discord:
  token: "${DISCORD_TOKEN}"  # Still supports env vars
  blacklisted_channels: "general,announcements"
  
models:
  chat: "gemma3:12b"
  vision: "llama3.2-vision:11b"
```

---

## Breaking Changes

### None!

v2.0 is 100% backward compatible. All existing functionality works exactly as before.

---

## New Features

###stats_poller Safe Helpers (**✅ v2.0**)

**Problem Solved**: `NameError: stats_poller is not defined`

**Now Available**:
```python
from utils.stats_helpers import (
    safe_start_stats_poller,
    safe_stop_stats_poller,
    is_stats_poller_available
)

# No more crashes!
safe_stop_stats_poller()  # Returns False if not available
# ... do work ...
safe_start_stats_poller()
```

### 2. Logging Bridge (**✅ v2.0**)

**Problem Solved**: Circular dependency between logger and dashboard

**Benefits**:
- Logger works before dashboard initialized
- Can register multiple logging destinations
- No circular imports

**For Advanced Users**:
```python
from utils.logging_bridge import LoggingBridge, register_logging_bridge

class MyCustomLogger(LoggingBridge):
    def log(self, level, message, metadata):
        # Send to external service
        pass
    
    def is_available(self):
        return True

register_logging_bridge(MyCustomLogger())
```

### 3. GPU Memory Manager (**✅ v2.0**)

**Problem Solved**: Uncoordinated GPU memory usage leading to OOM

**Features**:
- Priority-based reservations
- Automatic preemption
- Memory pressure monitoring

**Example**:
```python
from utils.gpu_memory_manager import gpu_memory_manager

# Check memory pressure
pressure = gpu_memory_manager.get_memory_pressure()
if pressure == 'critical':
    print("GPU memory is critically low!")

# Get VRAM status
status = gpu_memory_manager.get_vram_status()
print(f"Free VRAM: {status['free']:.1f} GiB")
```

### 4. Exception Hierarchy (**✅ v2.0**)

**Problem Solved**: Generic exception handling

**All Exceptions**:
```python
from bot.exceptions import (
    # GPU
    GPUMemoryError,
    CUDAOutOfMemoryError,
    VRAMInsufficientError,
    
    # Vision
    VisionTimeoutError,
    ImageDownloadError,
    
    # Image Gen
    ImageGenDisabledError,
    
    # RAG
    RAGLockTimeout,
    
    # Rate Limiting
    RateLimitError,
    
    # Utilities
    get_user_friendly_message,
    should_auto_report
)
```

---

## Deprecation Timeline

### v2.0 (Current)
- ✅ New `bot/` package structure
- ✅ Backward compatibility maintained
- ✅ No deprecation warnings yet

### v2.1 (Upcoming - Phase 2.3)
- ⚠️ Deprecation warnings for old import paths
- ⚠️ Recommendation to migrate to new structure
- ✅ Old imports still work

### v3.0 (Future)
- ❌ Remove backward compatibility shims
- ❌ Old import paths no longer work
- ✅ Clean, modern architecture

**Timeline**: At least 6 months between v2.0 and v3.0.

---

## Rollback Procedure

If you encounter issues with v2.0:

### 1. Check Logs

```bash
# View recent logs
tail -f logs/kaia.log

# Check for errors
grep -i error logs/kaia.log
```

### 2. Verify Configuration

```bash
# Test configuration loading
python -c "from bot.managers.config import config; print(config)"
```

### 3. Rollback (if needed)

```bash
git log --oneline  # Find previous commit
git checkout <commit-hash>  # Rollback
pip install -r requirements.txt  # Reinstall dependencies
```

### 4. Report Issues

Create an issue with:
- Error messages
- Steps to reproduce
- System info (GPU, Python version, etc.)

---

## Performance Impact

### Startup Time

**v1.0**: ~5-10 seconds (depending on news update)  
**v2.0**: ~5-10 seconds (no change - news disabled by default)

### Memory Usage

**v1.0**: ~1.5-2 GB RAM  
**v2.0**: ~1.5-2 GB RAM (slightly better due to optimization)

### Response Time

**v1.0**: Chat ~2-5s, Vision ~30-60s, Image ~30-60s  
**v2.0**: No change (same underlying models)

### GPU Memory

**v2.0 Improvements**:
- Better VRAM tracking
- Fewer OOM errors (improved circuit breaker)
- Clearer error messages

---

## Testing Your Migration

### 1. Test Basic Functionality

```bash
# Start bot
python Kaiacord.py

# In Discord, test:
# 1. Normal chat: "@kaia hello"
# 2. Image gen: "kaia draw sunset"
# 3. Vision: Upload image + "kaia what do you see?"
# 4. Remember: "kaia remember I like dark mode"
```

### 2. Check Logs

```bash
# Should see:
# - "Stats poller registered with helper module"
# - "✅ VRAM reserved for..." (during image gen)
# - No errors about stats_poller
```

### 3. Monitor GPU

```bash
# In another terminal
watch -n 1 nvidia-smi

# Should see:
# - Stable memory usage
# - No unexpected spikes
# - Clean unloading after image gen
```

---

## FAQs

### Q: Do I need to change my code?

**A**: No! v2.0 is backward compatible. Your existing setup will work without changes.

### Q: Should I migrate to the new import paths?

**A**: Recommended but not required. It future-proofs your code for v3.0.

### Q: Will my data be affected?

**A**: No. All data files (`storage/`, `knowledge_base/`) remain compatible.

### Q: Can I use old and new imports together?

**A**: Yes! Both work simultaneously:
```python
# This is fine:
from Kaiacord import config as old_config
from bot.managers.config import config as new_config

assert old_config is new_config  # True - same object!
```

### Q: When should I create `config/kaia.yaml`?

**A**: Phase 3 (not yet released). For now, use environment variables or modify `bot/managers/config.py`.

### Q: What if I get import errors?

**A**: Ensure you're in the correct directory and the `bot/` package exists:
```bash
cd /path/to/Kaiacord
ls bot/  # Should show: __init__.py, managers/, etc.
```

---

## Getting Help

- **Documentation**: See `docs/ARCHITECTURE.md`
- **Troubleshooting**: See `TROUBLESHOOTING.md`
- **Issues**: Create a GitHub issue  
- **Logs**: Check `logs/kaia.log`

---

## Summary

✅ **No action required** -  v2.0 works out of the box  
✅ **Optional**: Update imports for future-proofing  
✅ **Optional**: Create `config/kaia.yaml` when Phase 3 releases  
✅ **Recommended**: Test image generation and vision after update  

**Migration effort**: 0-30 minutes (depending on custom scripts)  
**Risk level**: Low (backward compatible)  
**Benefit**: Improved stability, better error messages, future-ready
