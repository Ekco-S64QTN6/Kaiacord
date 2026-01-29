# Common Troubleshooting Issues

Quick solutions to common Kaiacord problems.

## 🔴 Vision Timeout (5+ Minutes)

**Symptom**: Vision analysis hangs for 5+ minutes, used to complete in <3 min

**Cause**: Model load timeout or VRAM overflow

**Solution**:
```bash
# Check if chat model unloaded
grep "Unloading chat model" logs/kaiacord.log

# If NOT found, VRAM overflow - chat model didn't unload
# This is fixed in v2.0 - update to latest

# If found but still times out, increase timeout:
# Edit utils/gpu_manager.py line 118:
timeout=90.0  # Increase from 60s to 90s for slow HDDs
```

**Prevention**: Use SSD for faster model loading

---

## 🔴 CUDA Out of Memory

**Symptom**: `RuntimeError: CUDA out of memory`

**Cause**: Chat model didn't unload before vision/image task

**Solution**:
```bash
# Check VRAM usage
nvidia-smi

# Should see 8GB → 0GB → 7.5GB pattern during vision
# If stuck at 8GB, chat model isn't unloading

# Fix: Update to v2.0 (unload re-enabled)
# Verify: grep "Unload" logs/kaiacord.log
```

**Manual workaround**:
```bash
# Restart bot to clear VRAM
# Ctrl+C, then: python Kaiacord.py
```

---

## 🔴 stats_poller NameError

**Symptom**: `NameError: name 'stats_poller' is not defined`

**Cause**: Fixed in v2.0 with safe helpers

**Solution**:
```bash
# Update to v2.0
git pull origin main

# Verify fix exists:
grep "stats_helpers" Kaiacord.py
# Should see: from utils import stats_helpers
```

---

## 🔴 !news Command Not Working

**Symptom**: `!news` says "temporarily disabled"

**Cause**: Fixed in v2.0

**Solution**:
```bash
# Update to v2.0
git pull origin main

# Verify news exists:
python tools/maintenance/update_kaia_news.py

# Test in Discord:
!news technology
```

---

## 🔴 Dashboard Crashes

**Symptom**: Dashboard crashes or shows garbled text

**Cause**: Terminal incompatibility with curses

**Solution**:
```bash
# Use simple dashboard fallback
KAIA_DASHBOARD=simple python Kaiacord.py

# Or update TERM:
export TERM=xterm-256color
python Kaiacord.py
```

---

## 🔴 Model Not Loading

**Symptom**: `Model not found` or `Failed to load model`

**Cause**: Model not pulled or Ollama not running

**Solution**:
```bash
# Check Ollama status
ollama list

# If empty, pull models:
ollama pull gemma3:12b
ollama pull llama3.2-vision:11b
ollama pull nomic-embed-text

# If Ollama not running:
sudo systemctl start ollama
```

---

## 🔴 Import Errors

**Symptom**: `ModuleNotFoundError: No module named 'utils'`

**Cause**: Virtual environment not activated or dependencies missing

**Solution**:
```bash
# Activate venv
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Run from project root
cd /path/to/Kaiacord
python Kaiacord.py
```

---

## 🔴 Hallucinated Responses

**Symptom**: Kaia mentions "Juanita", "Deane", or fictional anecdotes

**Cause**: Contaminated knowledge base or cache

**Solution**:
```bash
# 1. Find contamination
python tools/recovery/find_contamination.py

# 2. Surgical fix
python tools/recovery/proper_fix.py --dry-run  # Preview
python tools/recovery/proper_fix.py             # Execute

# 3. If persistent, nuclear option:
python tools/recovery/nuclear_reset.py --dry-run  # Preview
python tools/recovery/nuclear_reset.py             # Execute
```

---

## 🟡 Slow Response Times

**Symptom**: Kaia takes 10+ seconds to respond

**Cause**: Model not GPU-accelerated or VRAM pressure

**Solution**:
```bash
# Check GPU usage
nvidia-smi

# Should see GPU at 90%+ during chat
# If CPU-only, check Ollama GPU settings

# Reduce context window:
# Edit config/kaia.yaml:
performance:
  max_memory_messages: 20  # Down from 30
```

---

## 🟡 RAG Not Finding Information

**Symptom**: Kaia says "I don't know" for knowledge in files

**Cause**: Files not indexed or RAG disabled

**Solution**:
```bash
# Check knowledge base
ls knowledge_base/

# Force re-index
python tools/diagnostics/trigger_rag_refresh.py

# Check RAG logs
grep "RAG" logs/kaiacord.log
```

---

## 🟡 Bot Not Responding

**Symptom**: Kaia doesn't respond to @mentions

**Cause**: Discord token invalid or bot offline

**Solution**:
```bash
# Check bot status
grep "online" logs/kaiacord.log

# Verify Discord token
# .env should have: DISCORD_TOKEN=MTxxxxx...

# Check bot permissions
# Discord Developer Portal → Bot → Permissions
# Enable: Send Messages, Read Message History
```

---

## Emergency Reset

If all else fails:
```bash
# Complete reset (DESTRUCTIVE!)
python tools/recovery/nuclear_reset.py

# This will:
# - Clear all caches
# - Delete user profiles
# - Remove logs
# - Reset to defaults
```

---

## Getting Help

1. **Check logs**: `tail -f logs/kaiacord.log`
2. **Run health check**: `python tools/maintenance/health_check.py`
3. **See docs**: [VRAM Issues](vram-issues.md), [Hallucination Fixes](hallucination-fixes.md)
4. **GitHub Issues**: Report bugs with logs

---

<p align="center">
  <sub>Still stuck? Check <a href="../03-architecture/overview.md">Architecture</a> or <a href="vram-issues.md">VRAM Guide</a></sub>
</p>
