#!/usr/bin/env bash
# kaia-tools.sh — Kaiacord maintenance TUI
# Run from the Kaiacord project root: bash kaia-tools.sh
# Requires: whiptail (standard on Ubuntu/Debian)

set -euo pipefail

# ── Locate project root ──────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

VENV="$SCRIPT_DIR/../venv/bin/python"
PYTHON="${VENV:-python3}"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✔ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠  $*${NC}"; }
fail() { echo -e "${RED}✘  $*${NC}"; }
info() { echo -e "${CYAN}→  $*${NC}"; }

pause() { echo; read -rp "  Press ENTER to return to menu..." _; }

# ── Helpers ───────────────────────────────────────────────────────────────────
bot_running() {
    pgrep -f "Kaiacord.py" > /dev/null 2>&1
}

confirm() {
    # confirm "Are you sure?" → returns 0 for yes, 1 for no
    whiptail --title "Confirm" --yesno "$1" 8 60
}

run_script() {
    # run_script <label> <python args...>
    local label="$1"; shift
    echo
    info "Running: $label"
    echo "────────────────────────────────────────"
    $PYTHON "$@" || true
    echo "────────────────────────────────────────"
    pause
}

# ═══════════════════════════════════════════════════════════════════════════════
# MENUS
# ═══════════════════════════════════════════════════════════════════════════════

menu_rag() {
    while true; do
        CHOICE=$(whiptail --title "Kaiacord Tools — RAG Management" --menu \
            "Bot status: $(bot_running && echo '🟢 RUNNING' || echo '🔴 STOPPED')\n\nChoose an operation:" \
            20 80 8 \
            "1" "Incremental refresh  (pick up new/edited files, bot can be running)" \
            "2" "Remove specific file  (delete nodes for one file, then re-index it)" \
            "3" "Full rebuild — CPU  (clear manifest, reindex all, bot can be running)" \
            "4" "Full rebuild — GPU  (faster, BOT MUST BE STOPPED)" \
            "5" "Diagnose index  (show node counts per index type)" \
            "6" "Diagnose embeddings  (verify embedding pipeline is working)" \
            "7" "Full RAG debug  (hybrid retriever deep-dive)" \
            "b" "← Back" \
            3>&1 1>&2 2>&3) || return

        case "$CHOICE" in
        1)
            info "Triggering incremental RAG refresh..."
            echo
            $PYTHON tools/maintenance/force_reindex.py
            pause
            ;;
        2)
            FILE=$(whiptail --title "Remove File from RAG" \
                --inputbox "Enter path relative to project root:\n(e.g. knowledge_base/user_logs/Ekco_177011971818782721/interactions_20260209.txt)" \
                10 70 3>&1 1>&2 2>&3) || continue
            if [[ -z "$FILE" ]]; then warn "No file entered."; pause; continue; fi
            if [[ ! -f "$FILE" ]]; then
                warn "File not found: $FILE"
                pause; continue
            fi
            info "Removing $FILE from RAG index and re-indexing..."
            echo
            $PYTHON tools/maintenance/force_reindex.py "$FILE"
            pause
            ;;
        3)
            if confirm "Clear entire RAG manifest and rebuild from scratch?\n\nThis will re-index ALL files. Bot can keep running but will be slow."; then
                info "Clearing manifest and triggering full rebuild..."
                echo
                # force_reindex with no args clears manifest; refresh does the rest
                $PYTHON - <<'EOF'
import asyncio, sys, os
sys.path.append(os.getcwd())
from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.logging.kaia_logger import log_info, log_success

async def main():
    rag = KaiaRAG()
    await asyncio.to_thread(rag._load_indexed_files)
    await asyncio.to_thread(rag._initialize_indices)
    count = len(rag.indexed_files)
    rag.indexed_files.clear()
    log_info(f"Cleared {count} manifest entries. Running full refresh...")
    await rag.refresh_knowledge_base()
    log_success("Full rebuild complete.")

asyncio.run(main())
EOF
                pause
            fi
            ;;
        4)
            if bot_running; then
                fail "Bot is currently RUNNING. Stop it first before GPU rebuild."
                fail "  pkill -f Kaiacord.py"
                pause; continue
            fi
            if confirm "GPU-accelerated full rebuild.\n\nBot MUST be stopped. This will wipe and rebuild all RAG storage.\nContinue?"; then
                info "Starting GPU rebuild..."
                echo
                $PYTHON tools/rebuild_rag_gpu.py --clear
                pause
            fi
            ;;
        5)
            run_script "RAG Index Diagnostics" tools/diag_rag_index.py
            ;;
        6)
            run_script "Embedding Pipeline Diagnostics" tools/diagnose_embeddings.py
            ;;
        7)
            run_script "Full RAG Debug (Hybrid Retriever)" tools/diagnose_rag.py
            ;;
        b|B) return ;;
        esac
    done
}

menu_knowledge_base() {
    while true; do
        CHOICE=$(whiptail --title "Kaiacord Tools — Knowledge Base" --menu \
            "Choose an operation:" 18 80 7 \
            "1" "Scan KB for issues  (corrupted files, bad nodes)" \
            "2" "Clean OCR artifacts  (fix encoding issues in books/docs)" \
            "3" "Sanitize user logs  (strip internal runtime tags from logs)" \
            "4" "LLM-powered log clean  (denoise + rebuild metadata, uses Ollama)" \
            "5" "Sync sanitized logs to RAG  (after manual log edits)" \
            "6" "Rebuild all user profiles  (regenerate from interaction logs)" \
            "7" "Find contamination  (scan for hallucinated content)" \
            "b" "← Back" \
            3>&1 1>&2 2>&3) || return

        case "$CHOICE" in
        1)
            run_script "Scan Knowledge Base" tools/diagnostics/scan_knowledge_base.py
            ;;
        2)
            DIR=$(whiptail --title "Clean OCR Artifacts" \
                --inputbox "Directory to clean (default: knowledge_base):" \
                8 60 "knowledge_base" 3>&1 1>&2 2>&3) || continue
            info "Cleaning OCR artifacts in: $DIR"
            echo
            $PYTHON tools/cleanup_kb.py "$DIR"
            pause
            ;;
        3)
            info "Stripping internal runtime tags from user logs..."
            echo
            $PYTHON tools/sanitize_logs.py
            pause
            ;;
        4)
            warn "This uses Ollama (gemma3:12b) to clean each log file. Can take a while."
            if confirm "Run LLM-powered log cleaning on all user logs?\n\nFiles are edited in-place. Make sure git is clean first."; then
                info "Running LLM log cleaner..."
                echo
                $PYTHON tools/kb_cleanse_user_logs.py
                pause
            fi
            ;;
        5)
            info "Syncing sanitized logs to RAG..."
            echo
            $PYTHON tools/sync_sanitized_logs.py
            pause
            ;;
        6)
            info "Rebuilding user profiles from interaction logs..."
            echo
            $PYTHON tools/development/generate_user_profiles.py
            pause
            ;;
        7)
            run_script "Find Contamination" tools/recovery/find_contamination.py
            ;;
        b|B) return ;;
        esac
    done
}

menu_news() {
    while true; do
        CHOICE=$(whiptail --title "Kaiacord Tools — News" --menu \
            "Choose an operation:" 14 80 4 \
            "1" "Update today's news  (requires GEMINI_API_KEY)" \
            "2" "Update with backfill  (fill missing days, uses more API quota)" \
            "3" "Ingest manual news brief  (for paste-in or file-based news)" \
            "b" "← Back" \
            3>&1 1>&2 2>&3) || return

        case "$CHOICE" in
        1)
            info "Fetching today's news..."
            echo
            $PYTHON tools/maintenance/update_kaia_news.py
            pause
            ;;
        2)
            info "Fetching news with backfill..."
            echo
            $PYTHON tools/maintenance/update_kaia_news.py --backfill
            pause
            ;;
        3)
            info "Running manual news ingestion..."
            echo
            $PYTHON tools/maintenance/ingest_manual_news.py
            pause
            ;;
        b|B) return ;;
        esac
    done
}

menu_recovery() {
    while true; do
        CHOICE=$(whiptail --title "Kaiacord Tools — Recovery ⚠️" --menu \
            "WARNING: These tools modify or delete data.\n\nChoose an operation:" 16 80 4 \
            "1" "Find contamination  (scan only, no changes)" \
            "2" "Surgical fix  (targeted hallucination removal, dry-run first)" \
            "3" "Surgical fix  (APPLY changes)" \
            "4" "☢  NUCLEAR RESET  (wipe profiles, cache, logs — last resort)" \
            "b" "← Back" \
            3>&1 1>&2 2>&3) || return

        case "$CHOICE" in
        1)
            run_script "Find Contamination (scan only)" tools/recovery/find_contamination.py
            ;;
        2)
            info "Running proper_fix.py in dry-run mode..."
            echo
            $PYTHON tools/recovery/proper_fix.py --dry-run
            pause
            ;;
        3)
            if confirm "Apply surgical hallucination fix?\n\nThis will modify files. Make sure you've run the dry-run first."; then
                info "Running proper_fix.py..."
                echo
                $PYTHON tools/recovery/proper_fix.py
                pause
            fi
            ;;
        4)
            if confirm "⚠️  NUCLEAR RESET\n\nThis will purge ALL user profiles, semantic cache, and reset hallucination data.\n\nThis CANNOT be undone. Are you absolutely sure?" ; then
                if confirm "Last chance. Really run nuclear reset?"; then
                    info "Running nuclear_reset.py..."
                    echo
                    $PYTHON tools/recovery/nuclear_reset.py
                    pause
                fi
            fi
            ;;
        b|B) return ;;
        esac
    done
}

menu_system() {
    while true; do
        CHOICE=$(whiptail --title "Kaiacord Tools — System" --menu \
            "Bot status: $(bot_running && echo '🟢 RUNNING' || echo '🔴 STOPPED')\n\nChoose an operation:" \
            16 80 5 \
            "1" "Full health check  (Ollama, models, GPU, KB, config)" \
            "2" "View recent logs  (tail kaiacord.log)" \
            "3" "View recent errors only  (grep ERROR from log)" \
            "4" "Start bot  (python Kaiacord.py)" \
            "5" "Stop bot  (pkill Kaiacord.py)" \
            "b" "← Back" \
            3>&1 1>&2 2>&3) || return

        case "$CHOICE" in
        1)
            echo
            info "Running health check..."
            echo "────────────────────────────────────────"
            $PYTHON tools/maintenance/health_check.py || true
            echo "────────────────────────────────────────"
            pause
            ;;
        2)
            echo
            info "Tailing logs/kaiacord.log (Ctrl+C to stop)..."
            echo
            tail -f logs/kaiacord.log 2>/dev/null || {
                warn "Log file not found at logs/kaiacord.log"
                ls logs/ 2>/dev/null || warn "No logs directory found"
            }
            pause
            ;;
        3)
            echo
            info "Recent errors from logs/kaiacord.log:"
            echo "────────────────────────────────────────"
            grep -i "error\|critical\|traceback" logs/kaiacord.log 2>/dev/null | tail -50 || \
                warn "No errors found or log file missing."
            echo "────────────────────────────────────────"
            pause
            ;;
        4)
            if bot_running; then
                warn "Bot is already running."
                pause; continue
            fi
            info "Starting Kaiacord.py in background..."
            nohup $PYTHON Kaiacord.py > logs/kaiacord_startup.log 2>&1 &
            ok "Started (PID $!). Check logs/kaiacord_startup.log"
            pause
            ;;
        5)
            if ! bot_running; then
                warn "Bot is not running."
                pause; continue
            fi
            if confirm "Stop Kaiacord.py?"; then
                pkill -f "Kaiacord.py" && ok "Stopped." || fail "Could not stop process."
                pause
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
            --menu "Bot: $(bot_running && echo '🟢 RUNNING' || echo '🔴 STOPPED')   |   $(date '+%Y-%m-%d %H:%M')\n\nWhat do you need?" \
            18 80 6 \
            "1" "RAG Management" \
            "2" "Knowledge Base" \
            "3" "News" \
            "4" "Recovery ⚠️" \
            "5" "System / Health" \
            "q" "Quit" \
            3>&1 1>&2 2>&3) || break

        case "$CHOICE" in
        1) menu_rag ;;
        2) menu_knowledge_base ;;
        3) menu_news ;;
        4) menu_recovery ;;
        5) menu_system ;;
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

if [[ ! -f "$VENV" ]]; then
    warn "venv not found at $VENV — falling back to system python3"
    PYTHON="python3"
fi

main_menu
clear
echo "bye."
