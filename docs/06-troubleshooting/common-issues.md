# Common Troubleshooting Issues

Quick solutions to common Kaiacord problems.

## 🔴 Bot Hangs at "[Phase 1] Claiming GPU"

**Symptom**: Boot stuck at Phase 1 for 3+ minutes then fails.

**Cause**: the model load outran `timeouts.model_load_seconds` (300 s by default) — a cold disk
cache, or Ollama still recovering after being killed.

**Solution**: raise the timeout in `config/kaia.yaml` if loads are simply slow on your disk:
```yaml
timeouts:
  model_load_seconds: 420.0
```

If still failing, restart Ollama, wait a few seconds, then start the bot:
```bash
sudo systemctl restart ollama
venv/bin/python3 Kaiacord.py
```

---

## 🔴 CUDA Out of Memory

**Symptom**: VRAM exhausted, model fails to load at boot.

**Cause**: Another application (a game, a video editor, a second model) using VRAM that `gemma3:12b` needs — about 9.5 GiB at the default 16,384-token context, before the desktop's share.

**Solution**:
```bash
# Check what's using VRAM
nvidia-smi

# Free VRAM manually
curl http://localhost:11434/api/generate \
  -d '{"model":"gemma3:12b","keep_alive":0}'

# Reduce the context window if needed (the KV cache shrinks with it)
# In config/kaia.yaml:
# performance:
#   max_context_tokens: 12288
```

`OLLAMA_KV_CACHE_TYPE=q8_0` with `OLLAMA_FLASH_ATTENTION=1` in Ollama's service environment
halves the KV cache without losing context — see
[GPU management](../03-architecture/gpu-management.md).

---

## 🔴 Missing Startup Logs / kaiacord_startup.log

**Symptom**: `logs/kaiacord_startup.log` is missing, or you're looking for startup messages.

**Cause**: all output is consolidated into one log.

**Solution**:
```bash
# All startup and runtime messages are in:
tail -f logs/kaiacord.log

# Each boot begins with this line (test runs go to logs/kaiacord.test.log instead):
grep -n "Unified logging system initialized" logs/kaiacord.log
```

**Note**: External shell redirection (e.g., `> kaiacord_startup.log`) is no longer necessary as the bot programmatically captures all output.

---

## 🔴 Dashboard Crashes

**Symptom**: Dashboard crashes or shows garbled text

**Cause**: Terminal incompatibility with curses

**Solution**:
```bash
# Use the simple dashboard, or none
KAIA_DASHBOARD=simple venv/bin/python3 Kaiacord.py
venv/bin/python3 Kaiacord.py --no-gui

# Or update TERM:
export TERM=xterm-256color
venv/bin/python3 Kaiacord.py
```

---

## 🔴 Model Not Loading

**Symptom**: `Model not found` or `Failed to load model`

**Cause**: Model not pulled or Ollama not running

**Solution**:
```bash
# Check Ollama status
ollama list

# If empty, pull models. These two are the whole set:
ollama pull gemma3:12b
ollama pull nomic-embed-text-cpu    # note the -cpu suffix; the bare name is a
                                    # different tag and will not be found

# If Ollama not running:
sudo systemctl start ollama
```

---

## 🔴 Import Errors

**Symptom**: `ModuleNotFoundError` — `utils`, or a package such as `bs4` or `google.genai` failing
deep inside one subsystem

**Cause**: the wrong interpreter. `Kaiacord.py` re-launches itself in the venv, but a tool run
with the system `python3` does not, and a package installed with the system `pip` lands outside
the venv.

**Solution**:
```bash
cd /path/to/Kaiacord
venv/bin/pip install -r requirements.txt
venv/bin/python3 tools/maintenance/health_check.py   # says if it is not running in the venv
```

---

## 🔴 Hallucinated Responses

**Symptom**: Kaia mentions fictional anecdotes, hallucinated tools, or phantom files.

**Cause**: Contaminated knowledge base or historical user logs.

**Solution**:
```bash
# 1. Find contaminated phrasing in the transcripts (report only)
venv/bin/python3 tools/maintenance/clean_hallucinations.py

# 2. Remove Kaia's own matching lines (user lines are never touched)
venv/bin/python3 tools/maintenance/clean_hallucinations.py --apply

# 3. Check the rest of the corpus
venv/bin/python3 tools/maintenance/audit_knowledge_base.py

# 4. Trigger a RAG re-index
venv/bin/python3 tools/maintenance/reindex_rag.py --trigger
```

---

## 🟡 Slow Response Times

**Symptom**: replies take much longer than usual. A normal turn is 10–20 s, nearly all of it
inference; the log warns `Slow response` past 30 s.

**Causes and checks**:
- **Queued behind other model work.** Model calls go one at a time, first come first served: a
  dream, a forum draft or a batch tool running beside her makes a chat turn wait. The dashboard
  and `!sysmon` show the queue.
- **The model was reloaded.** A call with different runner options makes Ollama reload it:
  `journalctl -u ollama | grep "n_ctx  "` lists every load.
- **Not on the GPU, or VRAM pressure.** `nvidia-smi` should show the GPU busy during a reply and
  only `llama-server` holding memory for her.

---

## 🟡 RAG Not Finding Information

**Symptom**: Kaia says "I don't know" for knowledge in files

**Cause**: Files not indexed or RAG disabled

**Solution**:
```bash
# Check knowledge base
ls knowledge_base/

# Check indexing health
venv/bin/python3 tools/diagnostics/check_indexing_health.py

# Force re-index
venv/bin/python3 tools/maintenance/reindex_rag.py --trigger

# Ask the index the question yourself, the way a chat turn would
venv/bin/python3 tools/diagnostics/ask_index.py "your question here"
```

If the right document is in the index but not in the answer, the question's wording routed it
elsewhere; `!explain` after her reply shows what she was given.

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
# Enable: Send Messages, Read Message History, and the Message Content intent
```

If she answers every message **twice**, two bots are running on one token. Stop and restart
through `bash scripts/kaia-tools.sh`, which waits for the old process to exit.

---

## Full Knowledge Base Rebuild

If index caches or embeddings need a complete reset:
```bash
# Full clean rebuild of the vector database
venv/bin/python3 tools/maintenance/reindex_rag.py --clear
```

---

## 🔴 Social Media Auth Errors

**Symptom**: X/Twitter login fails, Cloudflare blocks, or posts silently fail

**Cause**: Session expired, Cloudflare challenge, or circuit breaker tripped

**Solution**:
```bash
# Check circuit breaker state in logs
grep "circuit" logs/kaiacord.log

# Clear X cookies and force re-login, then restart the bot
rm memory/x_cookies.json
bash scripts/kaia-tools.sh    # → restart

# If Cloudflare blocks direct login:
# 1. Log into X in Chrome or Firefox manually
# 2. Kaia will auto-extract browser cookies on next attempt
# 3. Ensure browser_cookie3 is installed: pip install browser_cookie3
```

---

## 🟡 Scanner: "is the RTL-SDR busy or unplugged?"

**Cause**: something else holds the dongle — usually a hand-run survey or `rtl_fm`. The bot cannot
see a lock held outside its own process, so its watch fails and backs off for 15 minutes.

**Solution**: stop the other process before `radio.local.hours` or a configured net begins;
`lsusb` confirms the dongle is still attached.

---

## Getting Help

1. **Check logs**: `tail -f logs/kaiacord.log`
2. **Run health check**: `venv/bin/python3 tools/maintenance/health_check.py`
3. **See docs**: [03-Architecture](../03-architecture/overview.md)
4. **GitHub Issues**: Report bugs with logs

---

<p align="center">
  <sub>Still stuck? Check <a href="../03-architecture/overview.md">Architecture</a> or <a href="../03-architecture/gpu-management.md">GPU Management Guide</a></sub>
</p>
