#!/usr/bin/env python3
"""
04_merge_export.py — Merge LoRA adapter into base model and export to GGUF.

Loads the base model + the saved adapter from training, merges them,
and exports a q4_k_m GGUF file ready for Ollama.

Phase 4 fix: MAX_SEQ_LENGTH corrected to 1024 to match 03_train.py.
"""

import os
import sys

# Disable HF Hub network activity/telemetry checking
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

from unsloth import FastLanguageModel

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
ADAPTER_DIR   = os.path.join(SCRIPT_DIR, "output", "kaia_lora_adapter")
GGUF_OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output", "kaia_merged")

# ---------------------------------------------------------------------------
# Model config — MUST match 03_train.py exactly
# ---------------------------------------------------------------------------

MAX_SEQ_LENGTH = 512   # ← Fixed: was 1024, must match training value
DTYPE          = None
LOAD_IN_4BIT   = True


def find_gguf_file(directory: str) -> str | None:
    """Find the exported GGUF file in the output directory."""
    if not os.path.isdir(directory):
        return None
    for fname in os.listdir(directory):
        if fname.endswith(".gguf"):
            return os.path.join(directory, fname)
    return None


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
    print(f"Adapter:        {ADAPTER_DIR}")
    print(f"MAX_SEQ_LENGTH: {MAX_SEQ_LENGTH}")
    print(f"{'='*60}\n")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=ADAPTER_DIR,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=DTYPE,
        load_in_4bit=LOAD_IN_4BIT,
        local_files_only=True, # Prevent telemetry checking/hanging
    )

    # -----------------------------------------------------------------
    # 2. Export to GGUF (q4_k_m — fits in 12GB VRAM with room to spare)
    # -----------------------------------------------------------------
    print(f"\nMerging and exporting to GGUF (q4_k_m)...")
    print(f"Output directory: {GGUF_OUTPUT_DIR}\n")

    os.makedirs(GGUF_OUTPUT_DIR, exist_ok=True)

    model.save_pretrained_gguf(
        GGUF_OUTPUT_DIR,
        tokenizer,
        quantization_method="q4_k_m",
    )

    # -----------------------------------------------------------------
    # 3. Report + Modelfile instructions
    # -----------------------------------------------------------------
    gguf_file = find_gguf_file(GGUF_OUTPUT_DIR)

    print(f"\n{'='*60}")
    print("GGUF Export Complete!")
    print(f"{'='*60}")

    if gguf_file:
        size_gb = os.path.getsize(gguf_file) / (1024 ** 3)
        print(f"  File: {gguf_file}")
        print(f"  Size: {size_gb:.2f} GB")

        gguf_basename = os.path.basename(gguf_file)
        relative_path = os.path.join("./output", "kaia_merged", gguf_basename)

        print(f"\n{'='*60}")
        print("NEXT STEP — update finetune/Modelfile FROM line:")
        print(f"{'='*60}")
        print(f"\n  FROM {relative_path}\n")
        print("Then load into Ollama:")
        print("  cd /home/ekco/github/Kaiacord")
        print("  ollama rm kaia-lora || true")
        print("  ollama create kaia-lora -f finetune/Modelfile")
        print("  python3 -u finetune/05b_test_ollama.py")
    else:
        print(f"\n  Output directory: {GGUF_OUTPUT_DIR}")
        print("  WARNING: Could not find .gguf file in output dir.")
        print("  Check the directory manually:")
        print(f"    ls -lh {GGUF_OUTPUT_DIR}")
        print("\n  Then update the FROM line in finetune/Modelfile to match.")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
