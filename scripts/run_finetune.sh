#!/usr/bin/env bash
# run_finetune.sh — Run the Kaia LoRA fine-tune pipeline.
# Stops immediately if any step fails.
#
# The dataset is built separately, because building it is a decision worth
# looking at before a GPU hour is spent:
#     python finetune/01_convert_logs.py            # what a rebuild would keep, and why
#     python finetune/01_convert_logs.py --apply
#     python finetune/01g_review.py                 # optional: review targets by hand

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
echo "  Kaia LoRA Fine-Tune Pipeline"
echo "============================================="
echo ""

# ---------------------------------------------------------------------------
# Pre-flight: the dataset against today's rules. A gate, not a report: an
# adapter was once trained on a corpus carrying 753 duplicate exchanges and
# the runtime's own failure messages because this step printed and carried on.
# ---------------------------------------------------------------------------
echo ">>> Pre-flight: dataset check"
echo "---------------------------------------------"
if ! $PYTHON finetune/01f_check_dataset.py; then
    echo ""
    echo "Aborting: rebuild the dataset (python finetune/01_convert_logs.py --apply), then re-run."
    exit 1
fi
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
if [[ ! -f finetune/output/kaia_merged/kaia_merged.Q4_K_M.gguf ]]; then
    echo "Aborting: finetune/output/kaia_merged/kaia_merged.Q4_K_M.gguf was not written." >&2
    exit 1
fi

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
