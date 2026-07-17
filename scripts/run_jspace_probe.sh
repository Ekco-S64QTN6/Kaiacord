#!/bin/bash
# run_jspace_probe.sh — Run Kaia J-Space Behavioral Probing
#
# Usage:
#   ./scripts/run_jspace_probe.sh [mode] [options]
#
# Modes:
#   full            Runs static battery AND real user log replays (default)
#   static-only     Runs only static probe battery
#   replay-only     Runs only real user log replays
#
# Options:
#   --model <tag>   Specify Ollama model (default: gemma3:12b)
#   --limit <num>   Limit log replay turns (default: 12)
#   --help          Show help

set -euo pipefail

# Project root setup
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROBE_SCRIPT="$PROJECT_ROOT/tools/diagnostics/jspace_probe.py"

# Default configuration
MODE="full"
MODEL="gemma3:12b"
LIMIT="12"
EXTRA_ARGS=()

show_help() {
    echo "Usage: $0 [mode] [options]"
    echo ""
    echo "Modes:"
    echo "  full            Run static battery AND real user log replays (default)"
    echo "  static-only     Run static probe battery only"
    echo "  replay-only     Run real user log replays only"
    echo ""
    echo "Options:"
    echo "  --model <tag>   Specify Ollama model tag (default: gemma3:12b)"
    echo "  --limit <num>   Limit the number of user log replays (default: 12)"
    echo "  --help          Show this help text"
    echo ""
}

# Parse mode (optional first argument)
if [[ $# -gt 0 ]] && [[ "$1" != --* ]]; then
    case "$1" in
        full|static-only|replay-only)
            MODE="$1"
            shift
            ;;
        help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown mode: $1"
            show_help
            exit 1
            ;;
    esac
fi

# Parse remaining options
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)
            MODEL="$2"
            shift 2
            ;;
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

# Assemble command args based on mode
ARGS=("--model" "$MODEL")

case "$MODE" in
    full)
        ARGS+=("--limit-user-logs" "$LIMIT")
        ;;
    static-only)
        ARGS+=("--skip-user-logs")
        ;;
    replay-only)
        ARGS+=("--only-user-logs" "--limit-user-logs" "$LIMIT")
        ;;
esac

# Append extra arguments
ARGS+=("${EXTRA_ARGS[@]}")

# Run probe
echo "=========================================================="
echo " Starting Kaia J-Space Behavioral Probe"
echo " Mode:       $MODE"
echo " Model:      $MODEL"
echo "=========================================================="
echo ""

python3 "$PROBE_SCRIPT" "${ARGS[@]}"
