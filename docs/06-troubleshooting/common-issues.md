# Common Troubleshooting Issues

Quick solutions to common Kaiacord problems.

## 🔴 Bot Hangs at "[Phase 1] Claiming GPU"

**Symptom**: Boot stuck at Phase 1 for 3+ minutes then fails.

**Cause**: `model_load_seconds` timeout too short, or Ollama needs recovery time after being killed at startup.

**Solution**:
```bash
# In config/kaia.yaml add:
timeouts:
  model_load_seconds: 240.0
```

If still failing, Ollama may need a manual restart:
```bash
sudo systemctl restart ollama
# Wait 5 seconds, then start bot
python Kaiacord.py
```

---

## 🔴 CUDA Out of Memory

**Symptom**: VRAM exhausted, model fails to load at boot.

**Cause**: Another application (e.g. games, video editors) consuming VRAM alongside `gemma3:12b` + 8k KV cache (~9-10GB total).

**Solution**:
```bash
# Check what's using VRAM
nvidia-smi

# Free VRAM manually
curl http://localhost:11434/api/generate \
  -d '{"model":"gemma3:12b","keep_alive":0}'

# Reduce context window if needed
# In config/kaia.yaml:
# performance:
#   max_context_tokens: 4096
```

---

## 🔴 Missing Startup Logs / kaiacord_startup.log

**Symptom**: `logs/kaiacord_startup.log` is missing, or you're looking for startup messages.

**Cause**: Hardened Logging (v2.1+). All output is now consolidated.

**Solution**:
```bash
# All startup and runtime messages are now in:
tail -f logs/kaiacord.log

# Search specifically for startup sequence:
grep "Starting Kaia" logs/kaiacord.log
```

**Note**: External shell redirection (e.g., `> kaiacord_startup.log`) is no longer necessary as the bot programmatically captures all output.

---

## 🔴 stats_poller NameError

**Symptom**: `NameError: name 'stats_poller' is not defined`

**Cause**: Fixed in v2.0 with safe helpers

**Solution**:
```bash
# Update to latest version
git pull origin main

# Verify fix references in Kaiacord.py
```

---

## 🔴 !news Command Not Working

**Symptom**: `!news` says "temporarily disabled"

**Cause**: Fixed in v2.0+

**Solution**:
```bash
# Update to latest
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
ollama pull gemma2:2b
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

# Reduce context window in config/kaia.yaml:
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

# Verify Discord token in .env

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

## 🔴 Social Media Auth Errors

**Symptom**: X/Twitter login fails, Cloudflare blocks, or posts silently fail

**Cause**: Session expired, Cloudflare challenge, or circuit breaker tripped

**Solution**:
```bash
# Check circuit breaker state in logs
grep "circuit" logs/kaiacord.log

# Clear X cookies and force re-login
rm memory/x_cookies.json
python Kaiacord.py

# If Cloudflare blocks direct login:
# 1. Log into X in Chrome or Firefox manually
# 2. Kaia will auto-extract browser cookies on next attempt
# 3. Ensure browser_cookie3 is installed: pip install browser_cookie3
```

---

## Getting Help

1. **Check logs**: `tail -f logs/kaiacord.log`
2. **Run health check**: `python tools/maintenance/health_check.py`
3. **See docs**: [03-Architecture](../03-architecture/overview.md)
4. **GitHub Issues**: Report bugs with logs

---

<p align="center">
  <sub>Still stuck? Check <a href="../03-architecture/overview.md">Architecture</a> or <a href="../03-architecture/gpu-management.md">GPU Management Guide</a></sub>
</p>
