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
echo ">>> Pre-flight 1/2: Dataset audit"
echo "---------------------------------------------"
$PYTHON finetune/01d_scan_length_outliers.py
echo ""

# ---------------------------------------------------------------------------
# Pre-flight 2: verify the targets are what the runtime would actually emit.
#
# Training on unfiltered logs teaches the model to produce exactly what its own
# filters then strip — the opposite of the goal.
#
# This is a gate, not a report. It used to print its findings and proceed
# regardless, which is how an adapter came to be trained on a corpus carrying
# 753 duplicate exchanges, 17 copies of the runtime's own "i'm drawing a blank"
# failure message, and 149 bare-name openers. Regenerating the dataset from
# logs and forgetting to clean it must not silently produce a bad model.
# ---------------------------------------------------------------------------
echo ">>> Pre-flight 2/2: Target quality vs the live filter stack"
echo "---------------------------------------------"
if ! $PYTHON finetune/01f_clean_targets.py --check --strict --with-corrections; then
    echo ""
    echo "Aborting: clean the dataset first (command above), then re-run."
    exit 1
fi
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
echo ">>> Persona evaluation — does the fine-tune need the guardrails less?"
echo "---------------------------------------------"
# The measurement that matters: how often would the live filter stack have to
# remove real content? A fine-tune that has internalised the persona scores
# lower than the base model. 05b prints samples to read; this counts.
$PYTHON -u finetune/05c_evaluate_persona.py --models kaia-lora gemma3:12b
echo ""
echo "============================================="
echo "  Pipeline complete!"
echo "============================================="
