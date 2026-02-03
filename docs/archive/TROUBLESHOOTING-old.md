# Kaia Troubleshooting Guide

## Common Issues and Solutions

---

## GPU / CUDA Issues

### 1. `stats_poller is not defined`

**Symptom**:
```
NameError: name 'stats_poller' is not defined
```

**Cause**: Old code trying to access `stats_poller` before initialization

**Solution (v2.0)**:
✅ **Fixed automatically** - v2.0 uses safe helpers

**Verification**:
```python
# Should see this in startup logs:
# "Stats poller registered with helper module."
```

---

### 2. `CUDA Out of Memory`

**Symptom**:
```
torch.cuda.OutOfMemoryError: CUDA out of memory
🚨 IMAGE GENERATION DISABLED until restart
```

**Causes**:
- Chat model using VRAM
- Previous image model not fully unloaded
- Insufficient total VRAM

**Solutions**:

#### Immediate Fix:
```bash
# Restart the bot
# This clears all GPU memory
pkill -f Kaiacord.py
python Kaiacord.py
```

#### Check VRAM:
```bash
# Monitor GPU memory
watch -n 1 nvidia-smi

# You need:
# - Total VRAM: 12GB+ recommended (16GB+ ideal)
# - Free before image gen: 8GB+
```

#### Preventive Measures:

1. **Ensure 8GB free** before generating images:
   ```
   # Bot checks this automatically and fails fast
   # Look for: "❌ VRAM check failed: X.X GiB free, need 8.0+ GiB"
   ```

2. **Don't generate multiple images simultaneously**:
   - Wait for first image to complete
   - Bot uses semaphore to prevent this

3. **Restart bot if memory fragmented**:
   - Long-running bots can have fragmented VRAM
   - Restart clears fragmentation

---

### 3. Insufficient VRAM for Image Generation

**Symptom**:
```
Insufficient VRAM (6.2 GiB free, need 8.0+ GiB).
Image generation aborted to protect chat model.
💡 Chat model is using VRAM. Wait or restart to free memory.
```

**Cause**: Chat model loaded and using ~6GB, leaving insufficient room for FLUX

**Solutions**:

#### Option 1: Wait for Chat Model to Unload (Not Recommended)
Chat model stays loaded for stability, so this won't help in v2.0.

#### Option 2: Restart Bot
```bash
pkill -f Kaiacord.py
python Kaiacord.py

# Then immediately (before chat model loads):
# User: "kaia draw sunset"
```

#### Option 3: Upgrade GPU
- Minimum: 12GB VRAM
- Recommended: 16GB VRAM
- Ideal: 24GB VRAM

#### Option 4: Use Smaller Models
Edit `bot/managers/config.py`:
```python
chat_model: str = "gemma2:9b"  # Smaller model
```

---

### 4. GPU Not Available

**Symptom**:
```
⚠️ GPU Manager import failed
⚠️ Using CPU fallback mode
```

**Causes**:
- NVIDIA drivers not installed
- CUDA not installed
- PyTorch not compiled with CUDA support

**Solutions**:

#### Check GPU:
```bash
nvidia-smi
# Should show your GPU
# If "command not found", drivers not installed
```

#### Check CUDA:
```bash
nvcc --version
# Should show CUDA version
```

#### Check PyTorch CUDA:
```python
python -c "import torch; print(torch.cuda.is_available())"
# Should print: True
```

#### Reinstall PyTorch with CUDA:
```bash
pip uninstall torch torchvision
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

---

## Vision System Issues

### 5. Vision Analysis Timeout

**Symptom**:
```
vision analysis took too long. the image might be too complex or the server's busy.
```

**Causes**:
- Image too large (>10MB)
- Complex image (many details)
- GPU busy with other tasks
- Slow model inference

**Solutions**:

#### Use Smaller Images:
- Resize before uploading
- Compress JPEGs
- Avoid high-resolution screenshots

#### Check GPU:
```bash
nvidia-smi
# Look for high GPU utilization
```

#### Increase Timeout (Advanced):
Edit `utils/kaia_vision.py`:
```python
# Find kaia_sees_image function
timeout_seconds = 90  # Increase from 60
```

---

### 6. Image Download Failed

**Symptom**:
```
couldn't download that image. make sure it's a valid image file.
```

**Causes**:
- URL expired
- File not an image
- Network issue
- Discord CDN slow

**Solutions**:

#### Retry:
- Upload image again
- Sometimes Discord CDN has temporary issues

#### Check Image Format:
- Supported: JPG, PNG, GIF, WEBP
- Not supported: HEIC, TIFF (convert first)

#### Check Network:
```bash
ping discord.com
# Should have low latency (<100ms)
```

---

## RAG / Knowledge Base Issues

### 7. RAG Lock Timeout

**Symptom**:
```
knowledge base is busy. try again in a moment.
```

**Cause**: Another operation holding RAG lock (indexing, refresh)

**Solutions**:

#### Wait and Retry:
- Usually resolves in 5-10 seconds
- RAG operations release lock when done

#### Check for Indexing:
```bash
# Look in logs for:
# "Refreshing knowledge base..."
# "Indexing complete"
```

#### Restart if Stuck:
```bash
# If lock held for >60 seconds
pkill -f Kaiacord.py
python Kaiacord.py
```

---

### 8. No Context Retrieved

**Symptom**:
Kaia responds without relevant context from knowledge base

**Causes**:
- Knowledge base not indexed
- Query doesn't match indexed content
- Embeddings not working

**Solutions**:

#### Check Indices:
```bash
ls memory/
# Should see:
# - chroma_persona/
# - chroma_user_logs/
# - chroma_lore/
```

#### Force Reindex:
```bash
# Delete indices
rm -rf memory/chroma_*

# Restart bot (will reindex)
python Kaiacord.py
```

#### Check Ollama:
```bash
ollama list
# Should show:
# - nomic-embed-text (embedding model)
```

---

## Configuration Issues

### 9. Discord Token Invalid

**Symptom**:
```
discord.errors.LoginFailure: Improper token has been passed.
```

**Solutions**:

#### Check .env File:
```bash
cat .env
# Should have:
# DISCORD_TOKEN=your_token_here
```

#### Regenerate Token:
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your application
3. Bot → Reset Token
4. Copy new token to `.env`

#### Check .env Loading:
```python
python -c "from utils.infrastructure.system.yaml_config import config; print(config.discord_token[:10])"
# Should print first 10 chars of token
```

---

### 10. Blacklisted Channels Not Working

**Symptom**:
Bot responds in channels it shouldn't

**Solutions**:

#### Check Config:
```python
from utils.infrastructure.system.yaml_config import config
print(config.blacklisted_channels)
# Should show: ['general', 'announcements', ...]
```

#### Update .env:
```bash
# .env
BLACKLISTED_CHANNELS=general,announcements,rules,off-topic
```

#### Restart Bot:
```bash
pkill -f Kaiacord.py
python Kaiacord.py
```

---

## Rate Limiting Issues

### 11. Rate Limit Exceeded

**Symptom**:
```
slow down. you're sending messages too fast.
```

**Cause**: User exceeded 30 requests  per minute

**Solutions**:

#### For Users:
- Wait 60 seconds
- Slow down message rate

#### For Admins (Increase Limit):
Edit `bot/managers/config.py`:
```python
requests_per_minute: int = 60  # Increase from 30
```

Restart bot.

---

## Dashboard Issues

### 12. Dashboard Not Displaying

**Symptom**:
Terminal shows ANSI escape codes instead of dashboard

**Causes**:
- Curses not supported in this terminal
- Terminal too small
- Redirected output (e.g., `python Kaiacord.py > log.txt`)

**Solutions**:

#### Check Terminal Size:
```bash
echo $COLUMNS x $LINES
# Need at least 80x24
```

#### Force ANSI Dashboard:
```bash
KAIA_DASHBOARD=ansi python Kaiacord.py
```

#### Disable Dashboard:
```bash
KAIA_DASHBOARD=none python Kaiacord.py
```

---

### 13. Circular Import Error (Logging/Dashboard)

**Symptom (v1.0)**:
```
ImportError: cannot import name 'dashboard' from partially initialized module
```

**Solution**:
✅ **Fixed in v2.0** - Logging bridge breaks circular dependency

**If still seeing this**:
```bash
# Ensure you have v2.0
git pull origin main
pip install -r requirements.txt
```

---

## Performance Issues

### 14. Slow Responses

**Symptom**:
Kaia takes >10 seconds to respond

**Causes**:
- Large context being processed
- RAG retrieval slow
- GPU under high load

**Solutions**:

#### Check GPU Load:
```bash
nvidia-smi
# Look for:
# - GPU Utilization: Should be <90%
# - Memory Usage: Should have headroom
```

#### Reduce Context Size:
Edit `bot/managers/config.py`:
```python
max_memory_messages: int = 20  # Reduce from 30
rag_top_k: int = 5  # Reduce from 8
```

#### Clear Semantic Cache:
```bash
rm memory/semantic_cache.json
```

---

### 15. High Memory Usage

**Symptom**:
Bot using >4GB RAM

**Causes**:
- Large knowledge base
- Many cached messages
- Memory leak

**Solutions**:

#### Check Memory:
```bash
ps aux | grep Kaiacord.py
# Look at RSS column
```

#### Restart Bot:
```bash
# Simplest solution
pkill -f Kaiacord.py
python Kaiacord.py
```

#### Reduce Knowledge Base:
```bash
# Archive old logs
mv knowledge_base/user_logs/old_* archive/
```

---

## Startup Issues

### 16. Bot Crashes on Startup

**Symptom**:
Bot starts then immediately crashes

**Debugging**:

#### Check Logs:
```bash
tail -50 logs/kaia.log
# Look for last error before crash
```

#### Run with Verbose Output:
```bash
python Kaiacord.py 2>&1 | tee startup.log
```

#### Check Dependencies:
```bash
pip install -r requirements.txt --upgrade
```

#### Check File Permissions:
```bash
ls -la memory/
# Should be writable
chmod -R u+w memory/
```

---

### 17. Orphan Process Cleanup Fails

**Symptom**:
```
Error checking process: [Errno 3] No such process
```

**Cause**: Attempting to terminate already-dead process

**Solution**:
✅ **Harmless** - Error caught and logged, startup continues

**If Problematic**:
```bash
# Manually kill all Kaiacord processes
pkill -9 -f Kaiacord.py

# Then start fresh
python Kaiacord.py
```

---

## News System Issues

### 18. No News Found

**Symptom**:
```
No news found for category: technology
```

**Causes**:
- News not generated yet
- News files missing
- News system disabled

**Solutions**:

#### Generate News:
```bash
python tools/update_kaia_news.py
```

#### Check News Files:
```bash
ls knowledge_base/news/daily/
# Should see: YYYYMMDD_category.md files
```

#### Enable News (if needed):
Edit `bot/managers/config.py`:
```python
startup_news_update: bool = True
```

---

## Debugging Tools

### Checkealth Check Script

Create `tools/health_check.py`:
```python
#!/usr/bin/env python3
"""Quick health check for Kaia"""

import sys
import os

checks = []

# Check GPU
try:
    import torch
    cuda_available = torch.cuda.is_available()
    checks.append(("CUDA Available", cuda_available))
    if cuda_available:
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        checks.append(("Total VRAM  ", f"{vram:.1f} GB"))
except ImportError:
    checks.append(("PyTorch", False))

# Check Ollama
import subprocess
try:
    result = subprocess.run(["ollama", "list"], capture_output=True)
    ollama_ok = result.returncode == 0
    checks.append(("Ollama", ollama_ok))
except FileNotFoundError:
    checks.append(("Ollama", False))

# Check Config
try:
    from utils.infrastructure.system.yaml_config import config
    token_ok = bool(config.discord_token)
    checks.append(("Discord Token", token_ok))
except Exception as e:
    checks.append(("Config", False))

# Print results
print("\n===  Kaia Health Check ===\n")
for name, result in checks:
    status = "✅" if result else "❌"
    print(f"{status} {name}: {result}")

all_ok = all(r for _, r in checks if isinstance(r, bool))
sys.exit(0 if all_ok else 1)
```

Run:
```bash
python tools/health_check.py
```

---

## Getting More Help

### 1. Check Logs
```bash
# Recent errors
grep ERROR logs/kaia.log | tail -20

# CUDA errors
grep -i cuda logs/kaia.log

# Vision errors
grep -i vision logs/kaia.log
```

### 2. Enable Debug Logging

Edit `utils/unified_logging.py`:
```python
# Change log level
logger.setLevel(logging.DEBUG)
```

### 3. Create Issue

Include:
- Error message (full traceback)
- Steps to reproduce
- System info:
  ```bash
  python --version
  nvidia-smi
  ollama list
  uname -a
  ```
- Relevant logs

### 4. Rollback (Last Resort)

```bash
git log --oneline
git checkout <previous-commit>
pip install -r requirements.txt
```

---

## Prevention Tips

1. **Monitor GPU Memory**:
   ```bash watch -n 5 nvidia-smi
   ```

2. **Restart Regularly**:
   - Daily restart prevents memory leaks
   - Clears GPU fragmentation

3. **Keep Knowledge Base Clean**:
   - Archive old user logs
   - Remove outdated documents

4. **Update Dependencies**:
   ```bash
   pip install -r requirements.txt --upgrade
   ```

5. **Backup Before Changes**:
   ```bash
   tar -czf backup.tar.gz memory/ knowledge_base/
   ```

---

## Quick Reference

| Issue | Quick Fix |
|:------|:----------|
| CUDA OOM | Restart bot |
| Vision timeout | Use smaller image |
| RAG lock | Wait 10s, retry |
| No context | Reindex knowledge base |
| Slow response | Reduce context size |
| High memory | Restart bot |
| Dashboard broken | Use ANSI mode |
| Rate limited | Wait 60s |

---

## Emergency Commands

```bash
# Kill all Kaiacord processes
pkill -9 -f Kaiacord.py

# Clear GPU memory
python -c "import torch; torch.cuda.empty_cache()"

# Reindex everything
rm -rf memory/chroma_*

# Fresh start
rm memory/bot_state.json memory/semantic_cache.json
```

---

See also:
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - Technical details
- [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) - Upgrading guide
- [README.md](README.md) - General documentation
