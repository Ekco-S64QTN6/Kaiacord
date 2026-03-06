#!/usr/bin/env bash
# run_finetune.sh — Run the Kaia LoRA fine-tune pipeline in order.
# Stops immediately if any step fails.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "============================================="
echo "  Kaia LoRA Fine-Tune Pipeline"
echo "============================================="
echo ""

# Step 1: Hardware & dependency check
echo ">>> Step 1/4: Hardware & dependency validation"
echo "---------------------------------------------"
python finetune/02_check_hardware.py
echo ""
echo ">>> Hardware check PASSED — proceeding to training"
echo ""

# Step 2: Training
echo ">>> Step 2/4: LoRA fine-tuning"
echo "---------------------------------------------"
python finetune/03_train.py
echo ""
echo ">>> Training COMPLETE — proceeding to merge & export"
echo ""

# Step 3: Merge & GGUF export
echo ">>> Step 3/4: Merging adapter & exporting GGUF"
echo "---------------------------------------------"
python finetune/04_merge_export.py
echo ""
echo ">>> GGUF export COMPLETE — proceeding to validation"
echo ""

# Step 4: Validation
echo ">>> Step 4/4: Running validation prompts"
echo "---------------------------------------------"
python finetune/05_validate.py
echo ""
echo "============================================="
echo "  Pipeline complete!"
echo "============================================="
