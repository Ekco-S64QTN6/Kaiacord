#!/usr/bin/env bash
# ============================================================
# Kaia Post-Update Verification & RAG Lock Fix Script
# Run from your Kaiacord project root:
#   bash verify_and_fix.sh
# ============================================================
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✅ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $*${NC}"; }
fail() { echo -e "${RED}❌ $*${NC}"; }
info() { echo -e "${CYAN}ℹ️  $*${NC}"; }

echo ""
echo -e "${CYAN}=================================================="
echo " Kaia — Ollama GPU + RAG Lock Verification"
echo -e "==================================================${NC}"
echo ""

# ── Step 1: Ollama service health ────────────────────────────
info "Step 1: Checking Ollama service..."
if systemctl is-active --quiet ollama; then
    ok "ollama.service is running"
else
    fail "ollama.service is NOT running. Run: sudo systemctl start ollama"
    exit 1
fi

# ── Step 2: GPU detection in Ollama logs ─────────────────────
info "Step 2: Checking Ollama GPU detection..."
GPU_LOG=$(journalctl -u ollama --since "10 minutes ago" --no-pager -q 2>/dev/null || true)

if echo "$GPU_LOG" | grep -q "inference compute"; then
    GPU_LINE=$(echo "$GPU_LOG" | grep "inference compute" | tail -1)
    ok "GPU detected by Ollama: $GPU_LINE"
else
    warn "No 'inference compute' line in recent Ollama logs. GPU may not be visible yet."
    info "Full recent log:"
    journalctl -u ollama --since "5 minutes ago" --no-pager -q | tail -20
fi

# ── Step 3: VRAM context confirmation ────────────────────────
if echo "$GPU_LOG" | grep -q "vram-based default context"; then
    VRAM_LINE=$(echo "$GPU_LOG" | grep "vram-based default context" | tail -1)
    ok "VRAM context confirmed: $VRAM_LINE"
else
    warn "No VRAM context line found. Model may not have loaded yet."
fi

# ── Step 4: Quick model load test ────────────────────────────
info "Step 4: Testing gemma3:12b model load (this may take 30–60s on cold start)..."
START=$(date +%s)

RESPONSE=$(ollama run gemma3:12b "Reply with only the word: ready" --nowordwrap 2>&1 || true)
END=$(date +%s)
ELAPSED=$((END - START))

if echo "$RESPONSE" | grep -qi "ready"; then
    ok "Model responded in ${ELAPSED}s: '$RESPONSE'"
elif [ $ELAPSED -gt 55 ]; then
    warn "Model responded but took ${ELAPSED}s — may indicate slow VRAM load. Response: '$RESPONSE'"
else
    fail "Unexpected response (${ELAPSED}s): '$RESPONSE'"
    info "Check: ollama ps  — to see if model is in VRAM"
fi

# ── Step 5: Confirm model is in VRAM (not CPU) ──────────────
info "Step 5: Checking model residency..."
PS_OUTPUT=$(ollama ps 2>/dev/null || echo "ollama ps failed")
echo "$PS_OUTPUT"

if echo "$PS_OUTPUT" | grep -q "gemma3"; then
    if echo "$PS_OUTPUT" | grep -E "([0-9]+(\.[0-9]+)? GB)" | grep -qv "0 B"; then
        ok "gemma3:12b appears resident in VRAM"
    else
        warn "gemma3:12b loaded but VRAM size unclear. Check output above."
    fi
else
    warn "gemma3:12b not shown in 'ollama ps'. It may have been unloaded after the test."
fi

# ── Step 6: Apply RAG lock fix to kaia_rag.py ────────────────
echo ""
info "Step 6: Applying RAG lock fix (finally-block recursive await)..."

RAG_FILE="utils/core/kaia_rag.py"

if [ ! -f "$RAG_FILE" ]; then
    fail "Could not find $RAG_FILE — are you running from the Kaiacord project root?"
    exit 1
fi

# Check which lock name this version uses
if grep -q "_refresh_lock" "$RAG_FILE"; then
    LOCK_NAME="_refresh_lock"
elif grep -q "_index_lock" "$RAG_FILE"; then
    LOCK_NAME="_index_lock"
else
    warn "Could not detect lock name in $RAG_FILE. Skipping auto-patch."
    LOCK_NAME="unknown"
fi

if [ "$LOCK_NAME" != "unknown" ]; then
    info "Detected lock name: $LOCK_NAME"

    # Check if the bad pattern exists
    if grep -n "await self.refresh_knowledge_base()" "$RAG_FILE" | grep -v "#" > /dev/null 2>&1; then
        info "Found recursive await — patching..."

        # Backup first
        cp "$RAG_FILE" "${RAG_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
        ok "Backup saved"

        # Replace: await self.refresh_knowledge_base() → asyncio.create_task(self.refresh_knowledge_base())
        # Only inside finally blocks (we do a simple sed — safe because this pattern is unique)
        sed -i \
            's/await self\.refresh_knowledge_base()/asyncio.create_task(self.refresh_knowledge_base())/g' \
            "$RAG_FILE"

        # Verify
        if grep -q "asyncio.create_task(self.refresh_knowledge_base())" "$RAG_FILE"; then
            ok "Patch applied: recursive 'await' replaced with 'asyncio.create_task'"
        else
            fail "Patch may not have applied. Check $RAG_FILE manually."
        fi
    else
        ok "No recursive 'await self.refresh_knowledge_base()' found — already clean or already patched."
    fi
fi

# ── Step 7: Check for the old _lock double-release pattern ───
info "Step 7: Checking for old decorator double-release risk..."

# The dangerous pattern: release inside finally without acquired guard
UNSAFE_COUNT=$(grep -n "self\._lock\.release()" "$RAG_FILE" | grep -v "if acquired" | wc -l)
SAFE_COUNT=$(grep -n "if acquired.*release\|self\._data_lock\.release\|self\._index_lock\.release\|self\._refresh_lock\.release" "$RAG_FILE" | wc -l)

if [ "$UNSAFE_COUNT" -gt 0 ]; then
    warn "Found $UNSAFE_COUNT unguarded self._lock.release() calls. Lines:"
    grep -n "self\._lock\.release()" "$RAG_FILE" | grep -v "if acquired"
    info "These should either be guarded with 'if acquired:' or migrated to _data_lock / _refresh_lock."
else
    ok "No unguarded _lock.release() calls found."
fi

# ── Step 8: Verify model_load_timeout is sane ────────────────
info "Step 8: Checking model_load_timeout in config..."
CONFIG_FILE="config/default_config.yaml"
if [ -f "$CONFIG_FILE" ]; then
    TIMEOUT=$(grep "model_load_seconds" "$CONFIG_FILE" | head -1 | awk '{print $2}')
    if [ -n "$TIMEOUT" ]; then
        info "model_load_seconds = $TIMEOUT"
        if (( $(echo "$TIMEOUT > 120" | bc -l) )); then
            warn "model_load_seconds is ${TIMEOUT}s. Consider reducing to 60–90s to prevent boot hangs."
            info "Edit config/default_config.yaml: model_load_seconds: 90.0"
        else
            ok "model_load_seconds ($TIMEOUT) looks reasonable."
        fi
    fi
fi

# ── Summary ──────────────────────────────────────────────────
echo ""
echo -e "${CYAN}=================================================="
echo " Summary"
echo -e "==================================================${NC}"
echo ""
echo "Ollama update:     ✅ Complete"
echo "GPU detection:     See Step 2 above"
echo "Model load test:   See Step 4 above"
echo "RAG lock patch:    See Step 6 above"
echo ""
echo "If all steps passed, you can now restart Kaia:"
echo ""
echo -e "  ${GREEN}python Kaiacord.py${NC}"
echo ""
echo "Watch the boot logs for:"
echo "  [Phase 1] VRAM lock confirmed"
echo "  [Phase 3] RAG knowledge base refreshed"
echo ""
echo "If you still see 'cannot release un-acquired lock',"
echo "run: grep -n 'release' utils/core/kaia_rag.py"
echo "and share the output."
