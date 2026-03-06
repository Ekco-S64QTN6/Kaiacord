#!/usr/bin/env python3
"""
04_merge_export.py — Merge LoRA adapter into base model and export to GGUF.

Loads the base model + the saved adapter from training, merges them,
and exports a GGUF file ready for Ollama.
"""

import os
import sys

from unsloth import FastLanguageModel

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ADAPTER_DIR = os.path.join(SCRIPT_DIR, "output", "kaia_lora_adapter")
GGUF_OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output", "kaia_merged")
GGUF_FILE = os.path.join(SCRIPT_DIR, "output", "kaia_merged.gguf")

# Must match training config
MAX_SEQ_LENGTH = 1024
DTYPE = None
LOAD_IN_4BIT = True


def main():
    # Verify adapter exists
    if not os.path.isdir(ADAPTER_DIR):
        print(f"ERROR: Adapter directory not found: {ADAPTER_DIR}")
        print("Run 03_train.py first.")
        sys.exit(1)

    # -----------------------------------------------------------------
    # 1. Load base model + adapter
    # -----------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"Loading base model + LoRA adapter")
    print(f"Adapter: {ADAPTER_DIR}")
    print(f"{'='*60}\n")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=ADAPTER_DIR,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=DTYPE,
        load_in_4bit=LOAD_IN_4BIT,
    )

    # -----------------------------------------------------------------
    # 2. Export to GGUF
    # -----------------------------------------------------------------
    print(f"\nMerging and exporting to GGUF (q4_k_m quantization)...")
    print(f"Output directory: {GGUF_OUTPUT_DIR}")

    os.makedirs(os.path.dirname(GGUF_OUTPUT_DIR), exist_ok=True)

    model.save_pretrained_gguf(
        GGUF_OUTPUT_DIR,
        tokenizer,
        quantization_method="q4_k_m",
    )

    # -----------------------------------------------------------------
    # 3. Report
    # -----------------------------------------------------------------
    # Find the actual GGUF file (Unsloth names it based on the model)
    gguf_dir = GGUF_OUTPUT_DIR
    gguf_files = []
    if os.path.isdir(gguf_dir):
        for f in os.listdir(gguf_dir):
            if f.endswith(".gguf"):
                gguf_files.append(os.path.join(gguf_dir, f))

    # Also check if it was saved directly
    if os.path.isfile(GGUF_FILE):
        gguf_files.append(GGUF_FILE)

    print(f"\n{'='*60}")
    print("GGUF Export Complete!")
    print(f"{'='*60}")

    if gguf_files:
        for gf in gguf_files:
            size_bytes = os.path.getsize(gf)
            size_gb = size_bytes / (1024 ** 3)
            print(f"  Output: {gf}")
            print(f"  Size:   {size_gb:.2f} GB ({size_bytes:,} bytes)")
    else:
        print(f"  Output directory: {gguf_dir}")
        print("  (GGUF file will be in the output directory)")

    print(f"\nNext step: Use this GGUF file with Ollama:")
    print(f"  ollama create kaia -f Modelfile")
    print(f"  (Point the Modelfile FROM directive to the GGUF path above)")


if __name__ == "__main__":
    main()
