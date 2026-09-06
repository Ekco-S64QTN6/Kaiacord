#!/usr/bin/env bash
# kaia-tools.sh — Kaiacord maintenance TUI
# Run from the Kaiacord project root: bash scripts/kaia-tools.sh
# Requires: whiptail (standard on Ubuntu/Debian)

set -uo pipefail

# ── Locate project root ──────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

VENV="$SCRIPT_DIR/../venv/bin/python"
PYTHON="${VENV:-python3}"
if [[ ! -f "$VENV" ]]; then
    PYTHON="python3"
fi

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✔ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠  $*${NC}"; }
fail() { echo -e "${RED}✘  $*${NC}"; }
info() { echo -e "${CYAN}→  $*${NC}"; }

pause() { echo; read -rp "  Press ENTER to return to menu..." _; }

# ── Helpers ───────────────────────────────────────────────────────────────────
bot_running() {
    pgrep -f "Kaiacord.py" > /dev/null 2>&1
}

ollama_running() {
    pgrep -x "ollama" > /dev/null 2>&1 || systemctl is-active --quiet ollama 2>/dev/null
}

status_line() {
    local bot ollama
    bot=$(bot_running && echo "🟢 RUNNING" || echo "🔴 STOPPED")
    ollama=$(ollama_running && echo "🟢 UP" || echo "🔴 DOWN")
    echo "Bot: $bot  |  Ollama: $ollama  |  $(date '+%H:%M:%S')"
}

confirm() {
    whiptail --title "Confirm" --yesno "$1" 10 65
}

# Validate a tool path exists before running it, warn if missing
run_tool() {
    local label="$1"; shift
    local tool_path="$1"; shift
    echo
    if [[ ! -f "$tool_path" ]]; then
        fail "Tool not found: $tool_path"
        warn "Check tools/ directory structure."
        pause
        return 1
    fi
    info "Running: $label"
    echo "────────────────────────────────────────"
    $PYTHON "$tool_path" "$@" || true
    echo "────────────────────────────────────────"
    pause
}

# ═══════════════════════════════════════════════════════════════════════════════
# OLLAMA / SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

menu_ollama() {
    while true; do
        CHOICE=$(whiptail --title "Kaiacord Tools — Ollama Server" --menu \
            "$(status_line)\n\nOllama management:" \
            18 80 7 \
            "1" "Show loaded models  (ollama ps)" \
            "2" "Flush all models from VRAM  (unload everything)" \
            "3" "Restart Ollama service  (systemctl restart ollama)" \
            "4" "Stop Ollama service" \
            "5" "Start Ollama service" \
            "6" "Ollama server logs  (journalctl -u ollama)" \
            "b" "← Back" \
            3>&1 1>&2 2>&3) || return

        case "$CHOICE" in
        1)
            echo
            info "Currently loaded models:"
            echo "────────────────────────────────────────"
            ollama ps 2>/dev/null || warn "Ollama not running or 'ollama' not in PATH"
            echo "────────────────────────────────────────"
            pause
            ;;
        2)
            if bot_running; then
                warn "Bot is running — flushing will interrupt active inference."
                confirm "Flush VRAM anyway?" || { pause; continue; }
            fi
            echo
            info "Flushing all models from VRAM..."
            MODELS=$(ollama ps 2>/dev/null | tail -n +2 | awk '{print $1}' | grep -v "^$") || true
            if [[ -z "$MODELS" ]]; then
                ok "No models currently loaded."
            else
                while IFS= read -r model; do
                    [[ -z "$model" ]] && continue
                    info "Unloading: $model"
                    curl -s -X POST http://localhost:11434/api/generate \
                        -d "{\"model\": \"$model\", \"keep_alive\": 0}" \
                        --max-time 10 > /dev/null 2>&1 && ok "Unloaded $model" || warn "Failed to unload $model"
                done <<< "$MODELS"
            fi
            pause
            ;;
        3)
            if bot_running; then
                warn "Bot is running. Restarting Ollama will break active connections."
                confirm "Restart Ollama anyway?" || { pause; continue; }
            fi
            echo
            info "Restarting Ollama service..."
            if systemctl restart ollama 2>/dev/null; then
                ok "Ollama restarted. Waiting for it to come up..."
                sleep 3
                ollama_running && ok "Ollama is up." || warn "Ollama may still be starting."
            else
                warn "systemctl failed. Trying manual restart..."
                pkill -f "ollama serve" 2>/dev/null || true
                sleep 2
                nohup ollama serve > /tmp/ollama_restart.log 2>&1 &
                sleep 3
                ok "Ollama started (PID $!). Log: /tmp/ollama_restart.log"
            fi
            pause
            ;;
        4)
            confirm "Stop Ollama service?" || { pause; continue; }
            systemctl stop ollama 2>/dev/null || pkill -f "ollama serve" 2>/dev/null || true
            ok "Ollama stopped."
            pause
            ;;
        5)
            if ollama_running; then
                warn "Ollama is already running."
                pause; continue
            fi
            if ! systemctl start ollama 2>/dev/null; then
                nohup ollama serve > /tmp/ollama.log 2>&1 &
                sleep 2
            fi
            ok "Ollama started."
            pause
            ;;
        6)
            echo
            info "Ollama service logs (last 50 lines, Ctrl+C to stop):"
            echo "────────────────────────────────────────"
            journalctl -u ollama -n 50 --no-pager 2>/dev/null || \
                tail -50 /tmp/ollama.log 2>/dev/null || \
                warn "No Ollama logs found (try journalctl -u ollama manually)"
            echo "────────────────────────────────────────"
            pause
            ;;
        b|B) return ;;
        esac
    done
}

# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM / BOT CONTROL
# ═══════════════════════════════════════════════════════════════════════════════

menu_system() {
    while true; do
        CHOICE=$(whiptail --title "Kaiacord Tools — System & Bot Control" --menu \
            "$(status_line)\n\nChoose an operation:" \
            22 80 10 \
            "1"  "Full health check  (Ollama, models, GPU, KB, config)" \
            "2"  "View live logs  (tail kaiacord.log)" \
            "3"  "View startup log  (last bot start output)" \
            "4"  "View recent errors only  (grep ERROR from log)" \
            "5"  "Start bot" \
            "6"  "Stop bot" \
            "7"  "Restart bot  (stop + start)" \
            "8"  "Ollama server management →" \
            "9"  "Clear channel memory  (wipe bot_state.json - fixes style lock)" \
            "10" "Delete today's poisoned logs  (fixes contaminated RAG after bad session)" \
            "b"  "← Back" \
            3>&1 1>&2 2>&3) || return

        case "$CHOICE" in
        1)
            run_tool "Health Check" tools/maintenance/health_check.py
            ;;
        2)
            echo
            info "Tailing logs/kaiacord.log (Ctrl+C to stop)..."
            echo
            tail -f logs/kaiacord.log 2>/dev/null || {
                warn "Log file not found at logs/kaiacord.log"
                ls logs/ 2>/dev/null || warn "No logs/ directory"
            }
            pause
            ;;
        3)
            echo
            info "Startup log (logs/kaiacord_startup.log):"
            echo "────────────────────────────────────────"
            tail -100 logs/kaiacord_startup.log 2>/dev/null || warn "No startup log found."
            echo "────────────────────────────────────────"
            pause
            ;;
        4)
            echo
            info "Recent errors from logs/kaiacord.log:"
            echo "────────────────────────────────────────"
            grep -i "error\|critical\|traceback" logs/kaiacord.log 2>/dev/null | tail -60 || \
                warn "No errors found or log file missing."
            echo "────────────────────────────────────────"
            pause
            ;;
        5)
            if bot_running; then
                warn "Bot is already running (PID: $(pgrep -f Kaiacord.py))."
                pause; continue
            fi
            MODE=$(whiptail --title "Start Bot" --menu "Choose mode:" 10 50 2 \
                "1" "Curses dashboard (default)" \
                "2" "No GUI (simple mode)" \
                3>&1 1>&2 2>&3) || continue
            echo
            info "Starting Kaiacord.py..."
            mkdir -p logs
            if [[ "$MODE" == "2" ]]; then
                nohup $PYTHON Kaiacord.py --no-gui > logs/kaiacord_startup.log 2>&1 &
                ok "Started (PID $!). Tailing logs/kaiacord_startup.log for 10s..."
                sleep 10
                tail -20 logs/kaiacord_startup.log 2>/dev/null || true
                pause
            else
                info "Launching curses dashboard (this menu will close)..."
                sleep 1
                exec $PYTHON Kaiacord.py
            fi
            ;;
        6)
            if ! bot_running; then
                warn "Bot is not running."
                pause; continue
            fi
            if confirm "Stop Kaiacord.py?"; then
                pkill -f "Kaiacord.py" && ok "Bot stopped." || fail "Could not stop process."
                pause
            fi
            ;;
        7)
            if confirm "Restart bot? (stop existing, then start fresh)"; then
                if bot_running; then
                    info "Stopping bot..."
                    pkill -f "Kaiacord.py" && ok "Stopped." || warn "Could not stop cleanly."
                    sleep 3
                fi
                MODE=$(whiptail --title "Restart Bot" --menu "Choose mode:" 10 50 2 \
                    "1" "Curses dashboard (default)" \
                    "2" "No GUI (simple mode)" \
                    3>&1 1>&2 2>&3) || continue
                info "Starting bot..."
                mkdir -p logs
                if [[ "$MODE" == "2" ]]; then
                    nohup $PYTHON Kaiacord.py --no-gui > logs/kaiacord_startup.log 2>&1 &
                    ok "Started (PID $!). Check logs/kaiacord_startup.log"
                    pause
                else
                    info "Launching curses dashboard (this menu will close)..."
                    sleep 1
                    exec $PYTHON Kaiacord.py
                fi
            fi
            ;;
        8)
            menu_ollama
            ;;
        9)
            echo
            warn "This wipes in-memory channel history (channel_memory) persisted to disk."
            warn "Kaia will lose conversation context from this session, but relationships are preserved."
            if confirm "Clear channel memory?\n\nFixes style lock-in / ellipsis contamination.\nPreserves user relationships, familiarity, and system stats.\nBot must be stopped or will reload state on next persist."; then
                if bot_running; then
                    warn "Bot is running — state may be re-written on next persist cycle."
                fi
                if [[ -f memory/bot_state.json ]]; then
                    cp memory/bot_state.json memory/bot_state.json.bak
                    # Gate the success message on the rewrite actually succeeding. Corrupt
                    # JSON is the exact condition people open this menu to fix, and json.load
                    # raising there left the file untouched while reporting success.
                    if python3 -c "import json, os; p='memory/bot_state.json'; d=json.load(open(p)) if os.path.exists(p) else {}; d['channel_memory']={}; open(p+'.tmp','w').write(json.dumps(d, indent=2)); os.replace(p+'.tmp', p)"; then
                        ok "channel_memory cleared in bot_state.json (relationships preserved; backup: memory/bot_state.json.bak)"
                    else
                        warn "Failed to rewrite bot_state.json (corrupt JSON?). File left unchanged; backup at memory/bot_state.json.bak"
                    fi
                else
                    warn "memory/bot_state.json not found."
                fi
                pause
            fi
            ;;
        10)
            echo
            TODAY=$(date '+%Y%m%d')
            warn "This deletes all interaction logs written today ($TODAY)."
            warn "Use after a bad session caused by Ollama errors or style contamination."
            if confirm "Delete today's interaction logs (interactions_${TODAY}.md)?\n\nThis will scan all user_log directories."; then
                FOUND=0
                while IFS= read -r -d '' f; do
                    info "Deleting: $f"
                    rm -f "$f"
                    FOUND=$((FOUND + 1))
                done < <(find knowledge_base/user_logs -name "interactions_${TODAY}.md" -print0 2>/dev/null)
                if [[ $FOUND -eq 0 ]]; then
                    warn "No logs found for today ($TODAY)."
                else
                    ok "Deleted $FOUND log file(s). Trigger a RAG reindex to clean up."
                fi
                pause
            fi
            ;;
        b|B) return ;;
        esac
    done
}

# ═══════════════════════════════════════════════════════════════════════════════
# RAG MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

menu_rag() {
    while true; do
        CHOICE=$(whiptail --title "Kaiacord Tools — RAG Management" --menu \
            "$(status_line)\n\nChoose an operation:" \
            22 80 7 \
            "1" "Incremental refresh  (signal live bot via .trigger_reindex)" \
            "2" "Re-index specific file  (targeted file update)" \
            "3" "Full RAG rebuild  (clear storage & reindex all files)" \
            "4" "Index & manifest health  (document counts & file integrity)" \
            "5" "Embedding pipeline diagnostics" \
            "6" "Full RAG deep-dive debug" \
            "b" "← Back" \
            3>&1 1>&2 2>&3) || return

        case "$CHOICE" in
        1)
            echo
            info "Triggering incremental RAG refresh..."
            echo "────────────────────────────────────────"
            $PYTHON tools/maintenance/reindex_rag.py --trigger || warn "reindex_rag.py failed."
            echo "────────────────────────────────────────"
            pause
            ;;
        2)
            FILE=$(whiptail --title "Re-index Specific File" \
                --inputbox "Enter path relative to project root:\n(e.g. knowledge_base/user_logs/Ekco_177.../interactions_20260209.md)" \
                10 72 3>&1 1>&2 2>&3) || continue
            [[ -z "$FILE" ]] && { warn "No file entered."; pause; continue; }
            [[ ! -f "$FILE" ]] && { warn "File not found: $FILE"; pause; continue; }
            if confirm "Re-index '$FILE' now?"; then
                run_tool "Re-index File" tools/maintenance/reindex_rag.py "$FILE"
            fi
            ;;
        3)
            if confirm "Full RAG Rebuild.\n\nThis clears memory/rag_storage and reindexes all documents.\nContinue?"; then
                run_tool "Full RAG Rebuild" tools/maintenance/reindex_rag.py --clear
            fi
            ;;
        4)
            run_tool "Indexing Health Check" tools/diagnostics/check_indexing_health.py
            ;;
        5)
            run_tool "Embedding Diagnostics" tools/diagnostics/diagnose_embeddings.py
            ;;
        6)
            run_tool "Full RAG Debug" tools/diagnostics/diagnose_rag.py
            ;;
        b|B) return ;;
        esac
    done
}

# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE
# ═══════════════════════════════════════════════════════════════════════════════

menu_knowledge_base() {
    while true; do
        CHOICE=$(whiptail --title "Kaiacord Tools — Knowledge Base" --menu \
            "Choose an operation:" 24 80 10 \
            "1" "Scan KB for issues  (corrupted files, bad nodes)" \
            "2" "Clean OCR artifacts  (fix encoding issues in books/docs)" \
            "3" "Sanitize user logs  (strip internal runtime tags from logs)" \
            "4" "LLM-powered log clean  (denoise + rebuild metadata, uses Ollama)" \
            "5" "Sync sanitized logs to RAG  (after manual log edits)" \
            "6" "Rebuild all user profiles  (regenerate from interaction logs)" \
            "7" "Find contamination  (scan for hallucinated content)" \
            "8" "Delete logs for specific date  (targeted contamination removal)" \
            "9" "Scrape P99 Wiki  (crawls verified wiki articles to KB)" \
            "10" "Run Support Synthesis  (compile all tech support forum threads)" \
            "b" "← Back" \
            3>&1 1>&2 2>&3) || return

        case "$CHOICE" in
        1)
            run_tool "Scan Knowledge Base" tools/diagnostics/scan_knowledge_base.py
            ;;
        2)
            DIR=$(whiptail --title "Clean OCR Artifacts" \
                --inputbox "Directory to clean (default: knowledge_base):" \
                8 60 "knowledge_base" 3>&1 1>&2 2>&3) || continue
            [[ -z "$DIR" ]] && DIR="knowledge_base"
            run_tool "Clean KB Artifacts" tools/maintenance/cleanup_kb.py "$DIR"
            ;;
        3)
            run_tool "Sanitize User Logs" tools/maintenance/sanitize_logs.py
            ;;
        4)
            warn "This uses Ollama (gemma3:12b) to clean each log file. Takes a while."
            if bot_running; then
                warn "Bot is running — this will compete with active inference."
            fi
            if confirm "Run LLM-powered log cleaning on all user logs?\n\nFiles edited in-place. Make sure git is clean first."; then
                run_tool "LLM Log Cleaner" tools/maintenance/kb_cleanse_user_logs.py
            fi
            ;;
        5)
            run_tool "Sync Sanitized Logs" tools/maintenance/sync_sanitized_logs.py
            ;;
        6)
            run_tool "Rebuild User Profiles" tools/maintenance/generate_user_profiles.py
            ;;
        7)
            run_tool "Find Contamination (scan only)" tools/maintenance/clean_hallucinations.py --dry-run
            ;;
        8)
            DATE=$(whiptail --title "Delete Logs by Date" \
                --inputbox "Enter date to purge (YYYYMMDD format):\n(e.g. $(date '+%Y%m%d') for today)" \
                9 55 "$(date '+%Y%m%d')" 3>&1 1>&2 2>&3) || continue
            [[ -z "$DATE" ]] && { warn "No date entered."; pause; continue; }
            echo
            info "Scanning for interactions_${DATE}.md..."
            FOUND=$(find knowledge_base/user_logs -name "interactions_${DATE}.md" 2>/dev/null | wc -l)
            if [[ "$FOUND" -eq 0 ]]; then
                warn "No logs found for date: $DATE"
                pause; continue
            fi
            if confirm "Delete $FOUND log file(s) for $DATE?\n\nThis removes contaminated logs from that session."; then
                find knowledge_base/user_logs -name "interactions_${DATE}.md" -delete
                ok "Deleted $FOUND file(s)."
                info "Run RAG → Incremental refresh to clean up the index."
                pause
            fi
            ;;
        9)
            run_tool "Scrape P99 Wiki" tools/social/scrape_p99_wiki.py
            ;;
        10)
            run_tool "Forum Technical Support Synthesis" tools/social/synthesize_technical_knowledge.py
            ;;
        b|B) return ;;
        esac
    done
}

# ═══════════════════════════════════════════════════════════════════════════════
# NEWS
# ═══════════════════════════════════════════════════════════════════════════════

menu_news() {
    while true; do
        CHOICE=$(whiptail --title "Kaiacord Tools — News" --menu \
            "Choose an operation:" 14 80 4 \
            "1" "Update today's news  (requires GEMINI_API_KEY)" \
            "2" "Update with backfill  (fill missing days, uses more API quota)" \
            "3" "Ingest manual news brief  (paste-in or file-based)" \
            "b" "← Back" \
            3>&1 1>&2 2>&3) || return

        case "$CHOICE" in
        1) run_tool "Update Today's News" tools/maintenance/update_kaia_news.py ;;
        2) run_tool "Update News with Backfill" tools/maintenance/update_kaia_news.py --backfill ;;
        3) run_tool "Ingest Manual News Brief" tools/maintenance/ingest_manual_news.py ;;
        b|B) return ;;
        esac
    done
}

# ═══════════════════════════════════════════════════════════════════════════════
# RECOVERY
# ═══════════════════════════════════════════════════════════════════════════════

menu_recovery() {
    while true; do
        CHOICE=$(whiptail --title "Kaiacord Tools — Recovery ⚠️" --menu \
            "WARNING: These tools modify or delete data.\n\nChoose an operation:" \
            18 80 5 \
            "1" "Find contamination  (scan only, no changes)" \
            "2" "Surgical fix — dry run  (preview hallucination removal)" \
            "3" "Surgical fix — APPLY  (targeted hallucination removal)" \
            "4" "Flush poisoned session  (delete today's logs + clear channel memory)" \
            "5" "Clear RAG storage & rebuild  (re-index all knowledge base documents)" \
            "b" "← Back" \
            3>&1 1>&2 2>&3) || return

        case "$CHOICE" in
        1)
            run_tool "Find Contamination (scan only)" tools/maintenance/clean_hallucinations.py --dry-run
            ;;
        2)
            run_tool "Surgical Fix (dry-run)" tools/maintenance/clean_hallucinations.py --dry-run
            ;;
        3)
            if confirm "Apply surgical hallucination fix?\n\nFiles are modified in-place. Run dry-run first to preview."; then
                run_tool "Surgical Fix (APPLY)" tools/maintenance/clean_hallucinations.py
            fi
            ;;
        4)
            echo
            warn "This combines two fixes for a bad/contaminated session:"
            warn "  1. Delete today's interaction logs"
            warn "  2. Clear channel memory (bot_state.json)"
            if confirm "Flush poisoned session?\n\nDeletes today's logs + clears channel memory.\nBot should be stopped first for cleanest result."; then
                TODAY=$(date '+%Y%m%d')
                FOUND=0
                while IFS= read -r -d '' f; do
                    info "Deleting: $f"
                    rm -f "$f"
                    FOUND=$((FOUND + 1))
                done < <(find knowledge_base/user_logs -name "interactions_${TODAY}.md" -print0 2>/dev/null)
                ok "Deleted $FOUND log file(s) for today."

                if [[ -f memory/bot_state.json ]]; then
                    cp memory/bot_state.json memory/bot_state.json.bak
                    if python3 -c "import json, os; p='memory/bot_state.json'; d=json.load(open(p)) if os.path.exists(p) else {}; d['channel_memory']={}; open(p+'.tmp','w').write(json.dumps(d, indent=2)); os.replace(p+'.tmp', p)"; then
                        ok "Channel memory cleared (relationships preserved; backup: memory/bot_state.json.bak)"
                    else
                        warn "Failed to rewrite bot_state.json (corrupt JSON?). File left unchanged; backup at memory/bot_state.json.bak"
                    fi
                fi
                info "Run RAG → Incremental refresh after restarting the bot."
                pause
            fi
            ;;
        5)
            if confirm "⚠️  RAG STORAGE REBUILD\n\nWipes memory/rag_storage and rebuilds vector & BM25 indices.\nContinue?"; then
                run_tool "Full RAG Rebuild" tools/maintenance/reindex_rag.py --clear
            fi
            ;;
        b|B) return ;;
        esac
    done
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN MENU
# ═══════════════════════════════════════════════════════════════════════════════

main_menu() {
    while true; do
        CHOICE=$(whiptail --title "Kaiacord Maintenance Tools" \
            --menu "$(status_line)\n\nWhat do you need?" \
            20 80 7 \
            "1" "System & Bot Control  (start/stop/restart, logs, memory)" \
            "2" "Ollama Server  (restart, flush VRAM, model status)" \
            "3" "RAG Management  (reindex, rebuild, diagnose)" \
            "4" "Knowledge Base  (clean, sanitize, profiles)" \
            "5" "News" \
            "6" "Recovery ⚠️  (contamination, surgical fix, RAG reset)" \
            "q" "Quit" \
            3>&1 1>&2 2>&3) || break

        case "$CHOICE" in
        1) menu_system ;;
        2) menu_ollama ;;
        3) menu_rag ;;
        4) menu_knowledge_base ;;
        5) menu_news ;;
        6) menu_recovery ;;
        q|Q) break ;;
        esac
    done
}

# ── Dependency check ──────────────────────────────────────────────────────────
if ! command -v whiptail &>/dev/null; then
    fail "whiptail is required but not installed."
    info "Install it with:  sudo apt install whiptail"
    exit 1
fi

main_menu
clear
echo "bye."