#!/usr/bin/env bash
# run_finetune.sh — Run the Kaia LoRA fine-tune pipeline.
# Stops immediately if any step fails.
#
# Phase 4 changes:
#   - Dataset is pre-built (new_train/eval/augmented.jsonl) — 01_convert NOT called
#   - Validation uses 05b_test_ollama.py (live Ollama test, not the stub)
#   - 01b_augment_data.py is intentionally NOT called (would overwrite clean dataset)

# -u catches an unset variable instead of expanding it to the empty string;
# -o pipefail makes a failure anywhere in a pipeline fail the step.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)" || exit 1
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)" || exit 1
cd "$PROJECT_ROOT" || { echo "Cannot enter project root: $PROJECT_ROOT" >&2; exit 1; }

VENV="$PROJECT_ROOT/venv/bin/python3"
if [[ -f "$VENV" ]]; then
    PYTHON="$VENV"
else
    PYTHON="python3"
fi

echo ""
echo "============================================="
echo "  Kaia LoRA Fine-Tune Pipeline — Phase 4"
echo "============================================="
echo ""

# ---------------------------------------------------------------------------
# Pre-flight: scan dataset for length outliers before burning GPU time
# ---------------------------------------------------------------------------
echo ">>> Pre-flight: Dataset audit"
echo "---------------------------------------------"
$PYTHON finetune/01d_scan_length_outliers.py
echo ""
echo ">>> Dataset clean — proceeding"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Hardware & dependency check
# ---------------------------------------------------------------------------
echo ">>> Step 1/4: Hardware & dependency validation"
echo "---------------------------------------------"
$PYTHON finetune/02_check_hardware.py
echo ""
echo ">>> Hardware check PASSED — proceeding to training"
echo ""

# ---------------------------------------------------------------------------
# Step 2: Training
# ---------------------------------------------------------------------------
echo ">>> Step 2/4: LoRA fine-tuning"
echo "---------------------------------------------"
$PYTHON finetune/03_train.py
echo ""
echo ">>> Training COMPLETE — proceeding to merge & export"
echo ""

# ---------------------------------------------------------------------------
# Step 3: Merge & GGUF export
# ---------------------------------------------------------------------------
echo ">>> Step 3/4: Merging adapter & exporting GGUF"
echo "---------------------------------------------"
$PYTHON finetune/04_merge_export.py
echo ""
echo ">>> GGUF export COMPLETE"
echo ""
echo "  !! ACTION REQUIRED before Step 4 !!"
echo "  Check the FROM path printed above and update finetune/Modelfile if needed."
echo "  Then press ENTER to continue to validation, or Ctrl+C to stop here."
echo ""
read -r

# ---------------------------------------------------------------------------
# Step 4: Load into Ollama + live validation
# ---------------------------------------------------------------------------
echo ">>> Step 4/4: Loading into Ollama and running validation"
echo "---------------------------------------------"
ollama rm kaia-lora 2>/dev/null || true
ollama create kaia-lora -f finetune/Modelfile
echo ""
$PYTHON -u finetune/05b_test_ollama.py
echo ""
echo "============================================="
echo "  Pipeline complete!"
echo "============================================="
