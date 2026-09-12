#!/usr/bin/env bash
# kaia-tools.sh — Kaiacord maintenance TUI
# Runs from anywhere; it locates the project root from its own path.
# Renders with fzf when present, whiptail otherwise. Force one with
#   KAIA_TOOLS_UI=fzf|whiptail  kaia-tools
# Requires: fzf  (preferred)  or  whiptail (Debian/Ubuntu: whiptail · Arch: libnewt)

set -uo pipefail

# ── Locate project root ──────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)" || exit 1
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)" || exit 1
# Every tool path below is relative to the root, so a failed cd would run them
# against the wrong tree. -e is not set, so check it explicitly.
cd "$PROJECT_ROOT" || { echo "Cannot enter project root: $PROJECT_ROOT" >&2; exit 1; }

VENV="$PROJECT_ROOT/venv/bin/python"
# `${VENV:-python3}` was a no-op here — VENV is a constructed path string and so
# is never empty. The existence check is what actually picks the interpreter.
if [[ -x "$VENV" ]]; then
    PYTHON="$VENV"
else
    # Falling back to the system interpreter is not a neutral default. A system
    # update moved python3 from 3.12 to 3.14, and with a stray set of packages
    # in ~/.local the bot started anyway and then failed inside two subsystems
    # (bs4 for forum scraping, google-genai for news) hours later. Say so here.
    PYTHON="python3"
    echo "WARNING: $VENV not found — falling back to system $(python3 -V 2>&1)." >&2
    echo "         Project deps live in the venv; recreate it with:" >&2
    echo "         python3.12 -m venv venv && ./venv/bin/pip install -r requirements.txt" >&2
fi

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✔ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠  $*${NC}"; }
fail() { echo -e "${RED}✘  $*${NC}"; }
info() { echo -e "${CYAN}→  $*${NC}"; }

pause() { echo; read -rp "  Press ENTER to return to menu..." _; }

# ── Layout ────────────────────────────────────────────────────────────────────
# whiptail sizes its frame with wcwidth(), which disagrees with what a terminal
# actually draws for some characters. U+26A0 U+FE0F ("warning sign" + variation
# selector) measures 1 column but renders as 2, so every occurrence pushed the
# right border one column past the frame and broke the box. Menu strings are now
# limited to characters whose wcwidth matches their rendered width: ASCII plus a
# few single-width BMP glyphs (em dash, arrows, middle dot) and the full-width
# status circles, all of which newt measures correctly.
#
# Box dimensions are derived from the terminal instead of being hardcoded to 80,
# so long entries are not clipped on a narrow window.
term_cols() { tput cols 2>/dev/null || echo 80; }
term_rows() { tput lines 2>/dev/null || echo 24; }

# menu_width <length-of-longest-entry-text>
menu_width() {
    local content=$1 cols want max
    cols=$(term_cols)
    want=$(( content + 14 ))        # tag column + frame + padding
    max=$(( cols - 4 ))
    (( want > max )) && want=$max
    (( want < 60 )) && want=60
    echo "$want"
}

# menu_height <number-of-entries>
menu_height() {
    local entries=$1 rows want max
    rows=$(term_rows)
    want=$(( entries + 9 ))         # title, prompt, padding, frame
    max=$(( rows - 2 ))
    (( want > max )) && want=$max
    (( want < 12 )) && want=12
    echo "$want"
}

# ── Helpers ───────────────────────────────────────────────────────────────────
bot_running() {
    pgrep -f "Kaiacord.py" > /dev/null 2>&1
}

ollama_running() {
    pgrep -x "ollama" > /dev/null 2>&1 || systemctl is-active --quiet ollama 2>/dev/null
}

# Shown on the main menu so staged documents do not sit unnoticed.
ingress_hint() {
    local n
    n=$(find knowledge_base/_ingress -maxdepth 1 -name "*.md" ! -name "README.md" 2>/dev/null | wc -l)
    (( n > 0 )) && printf '  |  %s doc(s) awaiting ingest' "$n"
}

status_line() {
    local bot ollama
    bot=$(bot_running && echo "🟢 RUNNING" || echo "🔴 STOPPED")
    ollama=$(ollama_running && echo "🟢 UP" || echo "🔴 DOWN")
    echo "Bot: $bot  |  Ollama: $ollama  |  $(date '+%H:%M:%S')"
}

# ── Presentation layer ────────────────────────────────────────────────────────
# `ui_dialog` takes the same arguments whiptail does, so the call sites below
# are unchanged and there is exactly one place that knows how anything is
# drawn. It renders with fzf when available — truecolor, rounded borders, type
# to filter — and falls back to whiptail, which is what the tool looked like
# before: a grey newt box that a user fairly described as an MS-DOS installer.
#
# The whiptail calling convention is preserved: the UI is drawn on the
# terminal and the *result* goes to stderr, because every call site uses the
# `3>&1 1>&2 2>&3` swap to capture it. fzf draws on /dev/tty of its own accord,
# so its stdout is only the selection.

if [[ -z "${KAIA_TOOLS_UI:-}" ]]; then
    if command -v fzf >/dev/null 2>&1; then KAIA_TOOLS_UI=fzf
    else KAIA_TOOLS_UI=whiptail; fi
fi

# Muted violet/cyan on the terminal's own background, so it sits in the user's
# theme rather than painting a grey slab over it.
FZF_THEME='fg:#c8c8d4,bg:-1,hl:#a78bfa,fg+:#ffffff,bg+:#2a2a3a,hl+:#c4b5fd'
FZF_THEME+=',info:#6b7280,border:#6d5b9e,prompt:#7dd3fc,pointer:#a78bfa'
FZF_THEME+=',marker:#7dd3fc,header:#6b7280,gutter:-1'

ui_banner() {
    local cols w rule left right pad
    cols=$(term_cols)
    w=$(( cols - 4 )); (( w > 72 )) && w=72; (( w < 34 )) && w=34

    # Built by parameter expansion, not `tr`: tr substitutes bytes, and every
    # character in this frame is multibyte, so it produced mojibake.
    printf -v rule '%*s' "$w" ''; rule=${rule// /─}

    left="KAIACORD  maintenance console"
    right="$(bot_running && echo 'bot up' || echo 'bot down') · $(ollama_running && echo 'ollama up' || echo 'ollama down')"
    pad=$(( w - ${#left} - ${#right} - 4 )); (( pad < 1 )) && pad=1

    printf '\033[38;5;98m  ╭%s╮\n' "$rule"
    printf '  │\033[0m  \033[1mKAIACORD\033[0m\033[2m  maintenance console\033[0m%*s\033[2m%s\033[0m  \033[38;5;98m│\n' \
        "$pad" '' "$right"
    printf '  ╰%s╯\033[0m\n' "$rule"
}

# Split "Label  (hint)" into a bright label and a dim hint column.
_ui_split_hint() {
    local text=$1
    if [[ "$text" =~ ^(.*[^\ ])\ \ +\((.*)\)$ ]]; then
        printf '\033[0m%s\t\033[2m%s\033[0m' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    else
        printf '\033[0m%s\t' "$text"
    fi
}

_ui_menu_fzf() {
    local title=$1 prompt=$2; shift 2
    local -a rows=()
    while (( $# >= 2 )); do
        rows+=("$(printf '%s\t%s' "$1" "$(_ui_split_hint "$2")")")
        shift 2
    done

    # The prompt carries the live status line and any pending-ingress note.
    local header
    header=$(printf '%b' "$prompt" | sed '/^$/d')

    local sel
    sel=$(printf '%s\n' "${rows[@]}" | fzf \
        --ansi --no-sort --no-multi --layout=reverse --info=hidden \
        --height=~70% --min-height=12 --border=rounded --border-label=" $title " \
        --border-label-pos=3 --padding=1 --delimiter=$'\t' \
        --with-nth=2,3 --nth=2 --tabstop=1 \
        --header="$header" --header-first \
        --prompt='  ' --pointer='▸' --color="$FZF_THEME" \
        --bind='esc:abort,ctrl-c:abort') || return 1
    printf '%s' "${sel%%$'\t'*}" >&2
}

_ui_input_fzf() {
    local title=$1 prompt=$2 default=${3:-} reply
    {
        printf '\n\033[38;5;98m  ╭─ \033[0m\033[1m%s\033[0m\n' "$title"
        printf '%b\n' "  \033[38;5;98m│\033[0m  ${prompt//\\n/$'\n'  \\033[38;5;98m│\\033[0m  }"
        printf '\033[38;5;98m  ╰─\033[0m '
    } >/dev/tty
    IFS= read -r -e -i "$default" reply </dev/tty >/dev/tty 2>&1 || return 1
    printf '%s' "$reply" >&2
}

_ui_confirm_fzf() {
    # `default_no` mirrors whiptail's --defaultno: the row listed first is the
    # one preselected, so a destructive confirm cannot be accepted by a stray
    # Enter. confirm_offline_rebuild relies on this to guard a RAG wipe against
    # a running bot.
    local title=$1 prompt=$2 default_no=${3:-} sel
    local -a rows=($'yes\t\033[0mYes, continue' $'no\t\033[0mNo, cancel')
    [[ -n "$default_no" ]] && rows=($'no\t\033[0mNo, cancel' $'yes\t\033[0mYes, continue')
    sel=$(printf '%s\n' "${rows[@]}" | fzf \
        --ansi --no-sort --no-multi --layout=reverse --info=hidden \
        --height=~70% --min-height=8 --border=rounded --border-label=" $title " \
        --border-label-pos=3 --padding=1 --delimiter=$'\t' --with-nth=2 \
        --header="$(printf '%b' "$prompt")" --header-first \
        --prompt='  ' --pointer='▸' --color="$FZF_THEME" \
        --bind='esc:abort,ctrl-c:abort') || return 1
    [[ "${sel%%$'\t'*}" == yes ]]
}

# Accepts whiptail's argument grammar so nothing below has to change.
ui_dialog() {
    local title="" mode="" prompt="" default=""
    local -a rest=() original=("$@")
    while (( $# )); do
        case "$1" in
            --title)     title=$2; shift 2 ;;
            --menu)      mode=menu;  prompt=$2; shift 2
                         shift 3 2>/dev/null || true ;;   # height width count
            --inputbox)  mode=input; prompt=$2; shift 2
                         shift 2 2>/dev/null || true      # height width
                         if (( $# )) && [[ "$1" != --* ]]; then default=$1; shift; fi ;;
            --yesno)     mode=yesno; prompt=$2; shift 2
                         shift 2 2>/dev/null || true ;;
            --defaultno) default=defaultno; shift ;;
            --*)         shift ;;
            *)           rest+=("$1"); shift ;;
        esac
    done

    if [[ "$KAIA_TOOLS_UI" == fzf ]]; then
        case "$mode" in
            menu)  _ui_menu_fzf "$title" "$prompt" "${rest[@]}"; return $? ;;
            input) _ui_input_fzf "$title" "$prompt" "$default"; return $? ;;
            yesno) _ui_confirm_fzf "$title" "$prompt" "$default"; return $? ;;
        esac
    fi
    # Fallback: the original arguments, verbatim, to the real thing.
    command whiptail "${original[@]}"
}

confirm() {
    ui_dialog --title "Confirm" --yesno "$1" 10 65
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
    local rc=0
    "$PYTHON" "$tool_path" "$@" || rc=$?
    echo "────────────────────────────────────────"
    # `|| true` used to swallow the status here, so a failed reindex, a missing
    # dependency and a clean run were indistinguishable to the operator.
    if (( rc == 0 )); then
        ok "$label completed."
    else
        fail "$label exited with status $rc. See the output above."
    fi
    pause
    return $rc
}

# Destructive index operations must not run against a live bot: it holds the
# index open, so wiping memory/rag_storage underneath it corrupts both the
# on-disk store and the in-process copy.
confirm_offline_rebuild() {
    if bot_running; then
        ui_dialog --title "Bot is running" --yesno \
            "Kaia is currently RUNNING.\n\nRebuilding the index while she holds it open can corrupt memory/rag_storage.\n\nStop the bot first (System & Bot Control).\n\nProceed anyway?" \
            14 70 --defaultno || return 1
    fi
    confirm "$1"
}

# ═══════════════════════════════════════════════════════════════════════════════
# OLLAMA / SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

menu_ollama() {
    while true; do
        CHOICE=$(ui_dialog --title "Kaiacord Tools — Ollama Server" --menu \
            "$(status_line)\n\nOllama management:" \
            "$(menu_height 7)" "$(menu_width 66)" 7 \
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
        CHOICE=$(ui_dialog --title "Kaiacord Tools — System & Bot Control" --menu \
            "$(status_line)\n\nChoose an operation:" \
            "$(menu_height 10)" "$(menu_width 66)" 10 \
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
            MODE=$(ui_dialog --title "Start Bot" --menu "Choose mode:" 10 50 2 \
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
                MODE=$(ui_dialog --title "Restart Bot" --menu "Choose mode:" 10 50 2 \
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
        CHOICE=$(ui_dialog --title "Kaiacord Tools — RAG Management" --menu \
            "$(status_line)\n\nChoose an operation:" \
            "$(menu_height 7)" "$(menu_width 66)" 7 \
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
            FILE=$(ui_dialog --title "Re-index Specific File" \
                --inputbox "Enter path relative to project root:\n(e.g. knowledge_base/user_logs/Ekco_177.../interactions_20260209.md)" \
                10 72 3>&1 1>&2 2>&3) || continue
            [[ -z "$FILE" ]] && { warn "No file entered."; pause; continue; }
            [[ ! -f "$FILE" ]] && { warn "File not found: $FILE"; pause; continue; }
            if confirm "Re-index '$FILE' now?"; then
                run_tool "Re-index File" tools/maintenance/reindex_rag.py "$FILE"
            fi
            ;;
        3)
            # Embeddings run on CPU by default so a live bot keeps the 12b
            # chat model in VRAM. With the bot stopped nothing is holding that
            # VRAM, and the GPU embeds ~9x faster on real chunk sizes, so
            # reindex_rag.py switches automatically. --cpu-embed forces CPU.
            if confirm_offline_rebuild "Full RAG Rebuild.\n\nThis clears memory/rag_storage and reindexes all documents.\nWith the bot STOPPED this embeds on GPU: ~14 min.\nWith it running, CPU: ~2 hours.\nContinue?"; then
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
        CHOICE=$(ui_dialog --title "Kaiacord Tools — Knowledge Base" --menu \
            "Choose an operation:" "$(menu_height 11)" "$(menu_width 66)" 11 \
            "1" "Scan KB for issues  (corrupted files, bad nodes)" \
            "2" "Clean OCR artifacts  (fix encoding issues in books/docs)" \
            "3" "Sanitize user logs  (strip internal runtime tags from logs)" \
            "4" "Compact user logs  (link dumps + scrape debris, no LLM)" \
            "5" "Roll up + index user folders  (monthly archives, READMEs)" \
            "6" "Rebuild all user profiles  (regenerate from interaction logs)" \
            "7" "Find contamination  (scan for hallucinated content)" \
            "8" "Delete logs for specific date  (targeted contamination removal)" \
            "9" "Scrape P99 Wiki  (crawls verified wiki articles to KB)" \
            "10" "Run Support Synthesis  (compile all tech support forum threads)" \
            "11" "Backfill P99 Off-Topic  (lets Kaia start posting there sooner)" \
            "b" "← Back" \
            3>&1 1>&2 2>&3) || return

        case "$CHOICE" in
        1)
            run_tool "Scan Knowledge Base" tools/diagnostics/scan_knowledge_base.py
            ;;
        2)
            DIR=$(ui_dialog --title "Clean OCR Artifacts" \
                --inputbox "Directory to clean (default: knowledge_base):" \
                8 60 "knowledge_base" 3>&1 1>&2 2>&3) || continue
            [[ -z "$DIR" ]] && DIR="knowledge_base"
            run_tool "Clean KB Artifacts" tools/maintenance/cleanup_kb.py "$DIR"
            ;;
        3)
            run_tool "Sanitize User Logs" tools/maintenance/sanitize_logs.py
            ;;
        4)
            # Replaces the LLM log cleaner, which asked a model to reformat the
            # transcripts and got exactly that: it rewrote the
            # "[timestamp] Ekco:" turn markers into "User:" across 774 files,
            # taking the timestamps and speaker names the retrieval layer runs
            # on. This pass is deterministic, idempotent, and cannot remove a
            # turn marker — it refuses the file if a rewrite would.
            info "Deterministic — no model involved. Shows a dry run first."
            run_tool "Compact User Logs (dry run)" tools/maintenance/compact_user_logs.py
            if confirm "Apply these changes?\n\nOriginals are copied to memory/log_compaction_backup first."; then
                run_tool "Compact User Logs (apply)" tools/maintenance/compact_user_logs.py --apply
            fi
            ;;
        5)
            # A day is the wrong unit for chunking: 533 of 1,112 daily files
            # held fewer than the splitter's 6 turns, so half the corpus was
            # chunked below the intended granularity. Closed months roll into
            # one archive each; the last week stays daily so only today's file
            # is ever re-embedded. Merging is lossless — every turn carries its
            # own timestamp.
            info "Rolls closed months into monthly archives, then rebuilds each folder's README."
            run_tool "Roll Up User Logs (dry run)" tools/maintenance/rollup_user_logs.py
            if confirm "Roll up closed months?\n\nOriginals are copied to memory/log_rollup_backup first."; then
                run_tool "Roll Up User Logs" tools/maintenance/rollup_user_logs.py --apply
            fi
            run_tool "Rebuild Folder Indexes" tools/maintenance/build_user_folder_index.py --apply
            ;;
        6)
            run_tool "Rebuild User Profiles" tools/maintenance/generate_user_profiles.py
            ;;
        7)
            run_tool "Find Contamination (scan only)" tools/maintenance/clean_hallucinations.py --dry-run
            ;;
        8)
            DATE=$(ui_dialog --title "Delete Logs by Date" \
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
        11)
            # Kaia will not post to a forum she has not been reading. The
            # periodic scrape fills that corpus at five threads per half hour,
            # so from empty it is about a day; this clears it in one run.
            PAGES=$(ui_dialog --title "Backfill P99 Off-Topic" \
                --inputbox "Listing pages to walk (more = longer, gentler on their server if you keep it low):" \
                9 66 "4" 3>&1 1>&2 2>&3) || continue
            [[ -z "$PAGES" ]] && PAGES="4"
            run_tool "Backfill Off-Topic Corpus" tools/maintenance/backfill_forum_corpus.py \
                --pages "$PAGES"
            ;;
        b|B) return ;;
        esac
    done
}

# ═══════════════════════════════════════════════════════════════════════════════
# NEWS
# ═══════════════════════════════════════════════════════════════════════════════

menu_documents() {
    while true; do
        local staged
        staged=$(find knowledge_base/_ingress -maxdepth 1 -name "*.md" ! -name "README.md" 2>/dev/null | wc -l)
        local errors
        errors=$(find knowledge_base/_ingress -maxdepth 1 -name "*.error" 2>/dev/null | wc -l)

        CHOICE=$(ui_dialog --title "Kaiacord Tools — Documents & Ingestion" --menu \
            "Staged from !download: ${staged}   Failed: ${errors}\n\nChoose an operation:" \
            "$(menu_height 9)" "$(menu_width 62)" 9 \
            "1" "Process ingress now  (clean + file staged !download docs)" \
            "2" "Preview ingress  (dry run, nothing written)" \
            "3" "Convert ebook/PDF to KB markdown  (epub, pdf, txt, html)" \
            "4" "Repair book structure  (chapters, page numbers)" \
            "5" "Enrich metadata  (frontmatter for logs & forum posts)" \
            "6" "List staged documents" \
            "7" "Clear failed ingress markers" \
            "8" "Fetch a YouTube transcript  (paste a video url)" \
            "b" "← Back" \
            3>&1 1>&2 2>&3) || return

        case "$CHOICE" in
        1)
            run_tool "Process Ingress" tools/maintenance/process_ingress.py
            ;;
        2)
            run_tool "Preview Ingress" tools/maintenance/process_ingress.py --dry-run
            ;;
        3)
            SRC=$(ui_dialog --title "Convert to KB Markdown" \
                --inputbox "Path to an .epub / .pdf / .txt / .html file, or a directory:\n\n(tab completion is not available here — paste a full path)" \
                12 72 "$HOME/" 3>&1 1>&2 2>&3) || continue
            [[ -z "$SRC" ]] && { warn "Nothing entered."; pause; continue; }
            if [[ ! -e "$SRC" ]]; then warn "Not found: $SRC"; pause; continue; fi
            DEST=$(ui_dialog --title "Convert to KB Markdown" \
                --inputbox "Destination folder under knowledge_base/:" \
                9 60 "books" 3>&1 1>&2 2>&3) || continue
            [[ -z "$DEST" ]] && DEST="books"
            mkdir -p "knowledge_base/$DEST"
            if [[ -d "$SRC" ]]; then
                mapfile -t FILES < <(find "$SRC" -maxdepth 1 -type f \
                    \( -iname "*.epub" -o -iname "*.pdf" -o -iname "*.txt" -o -iname "*.html" \) )
                if (( ${#FILES[@]} == 0 )); then warn "No convertible files in $SRC"; pause; continue; fi
                info "Converting ${#FILES[@]} file(s)..."
                run_tool "Convert to KB Markdown" tools/maintenance/ebook_to_kb_md.py \
                    --outdir "knowledge_base/$DEST" "${FILES[@]}"
            else
                run_tool "Convert to KB Markdown" tools/maintenance/ebook_to_kb_md.py \
                    --outdir "knowledge_base/$DEST" "$SRC"
            fi
            info "Run RAG → Incremental refresh to index the new documents."
            pause
            ;;
        4)
            if confirm "Repair chapter structure and strip page numbers in knowledge_base/books?\n\nA dry run is shown first."; then
                run_tool "Repair Book Structure (preview)" tools/maintenance/repair_kb_book_structure.py
                if confirm "Apply those repairs?"; then
                    run_tool "Repair Book Structure (apply)" tools/maintenance/repair_kb_book_structure.py --apply
                fi
            fi
            ;;
        5)
            run_tool "Enrich Metadata (preview)" tools/maintenance/enrich_kb_metadata.py
            if confirm "Apply the frontmatter changes listed above?"; then
                run_tool "Enrich Metadata (apply)" tools/maintenance/enrich_kb_metadata.py --apply
            fi
            ;;
        6)
            echo
            if (( staged == 0 && errors == 0 )); then
                info "Ingress is empty. Documents arrive here via !download in Discord."
            else
                info "knowledge_base/_ingress/"
                ls -lh knowledge_base/_ingress/ | grep -v "^total\|README.md"
            fi
            pause
            ;;
        8)
            URL=$(ui_dialog --title "YouTube Transcript" \
                --inputbox "Paste a YouTube video URL.\n\nThe transcript is converted to knowledge-base markdown and staged in _ingress." \
                12 72 "" 3>&1 1>&2 2>&3) || continue
            [[ -z "$URL" ]] && { warn "Nothing entered."; pause; continue; }
            run_tool "YouTube Transcript" tools/maintenance/youtube_to_kb_md.py "$URL" \
                --outdir knowledge_base/_ingress
            info "Run 'Process ingress now' to file it, or wait for the hourly pass."
            pause
            ;;
        7)
            if (( errors == 0 )); then
                info "No failed markers to clear."
                pause
            elif confirm "Delete ${errors} .error marker(s)?\n\nThe documents themselves stay staged and will be retried."; then
                find knowledge_base/_ingress -maxdepth 1 -name "*.error" -delete
                ok "Cleared."
                pause
            fi
            ;;
        b|B) return ;;
        esac
    done
}

menu_news() {
    while true; do
        CHOICE=$(ui_dialog --title "Kaiacord Tools — News" --menu \
            "Choose an operation:" "$(menu_height 4)" "$(menu_width 66)" 4 \
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
        CHOICE=$(ui_dialog --title "Kaiacord Tools — Recovery  (!)" --menu \
            "WARNING: These tools modify or delete data.\n\nChoose an operation:" \
            "$(menu_height 5)" "$(menu_width 66)" 5 \
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
            if confirm "Apply surgical hallucination fix?\n\nRemoves matching lines from Kaia's own log entries only.\nUser-authored lines are never touched. A .bak is written first.\nRun the dry-run first to preview."; then
                run_tool "Surgical Fix (APPLY)" tools/maintenance/clean_hallucinations.py --apply
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
            if confirm_offline_rebuild "(!)  RAG STORAGE REBUILD\n\nWipes memory/rag_storage and rebuilds vector & BM25 indices.\nContinue?"; then
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
        CHOICE=$(ui_dialog --title "Kaiacord Maintenance Tools" \
            --menu "$(status_line)$(ingress_hint)\n\nWhat do you need?" \
            "$(menu_height 8)" "$(menu_width 58)" 8 \
            "1" "System & Bot Control  (start/stop/restart, logs, memory)" \
            "2" "Ollama Server  (restart, flush VRAM, model status)" \
            "3" "RAG Management  (reindex, rebuild, diagnose)" \
            "4" "Knowledge Base  (clean, sanitize, profiles)" \
            "5" "Documents & Ingestion  (convert books, file !download)" \
            "6" "News" \
            "7" "Recovery (!)  (contamination, surgical fix, RAG reset)" \
            "q" "Quit" \
            3>&1 1>&2 2>&3) || break

        case "$CHOICE" in
        1) menu_system ;;
        2) menu_ollama ;;
        3) menu_rag ;;
        4) menu_knowledge_base ;;
        5) menu_documents ;;
        6) menu_news ;;
        7) menu_recovery ;;
        q|Q) break ;;
        esac
    done
}

# ── Dependency check ──────────────────────────────────────────────────────────
# Either renderer will do. fzf is preferred and whiptail is the fallback, so the
# tool only fails when neither is present — it used to hard-require whiptail
# even on a machine that had something better.
if ! command -v fzf &>/dev/null && ! command -v whiptail &>/dev/null; then
    fail "This needs either fzf (preferred) or whiptail."
    # The package name differs per distro, and the previous message only ever
    # gave the Debian one.
    if   command -v pacman  &>/dev/null; then info "Install it with:  sudo pacman -S fzf     (or libnewt)"
    elif command -v apt-get &>/dev/null; then info "Install it with:  sudo apt install fzf   (or whiptail)"
    elif command -v dnf     &>/dev/null; then info "Install it with:  sudo dnf install fzf   (or newt)"
    elif command -v zypper  &>/dev/null; then info "Install it with:  sudo zypper install fzf (or newt)"
    else info "Install fzf, or the 'newt' / 'whiptail' package for your distribution."
    fi
    exit 1
fi

clear
ui_banner
main_menu
clear
echo "bye."