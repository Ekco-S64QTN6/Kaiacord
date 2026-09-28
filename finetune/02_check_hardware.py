#!/usr/bin/env python3
"""
02_check_hardware.py — Validate hardware and dependencies for Kaia LoRA fine-tuning.

Checks CUDA/GPU availability, VRAM, unsloth importability, and dataset readiness.
Prints a go/no-go summary.
"""

import os
import sys

DATASET_DIR = os.path.join(os.path.dirname(__file__), "dataset")
TRAIN_FILE = os.path.join(DATASET_DIR, "train.jsonl")
EVAL_FILE = os.path.join(DATASET_DIR, "eval.jsonl")

MIN_VRAM_GB = 10.0
WARN_VRAM_GB = 11.5      # a 12 GB card reports ~11.7 GiB; the warning is for smaller ones
# Free, not total: with gemma3:12b resident in Ollama (the bot running) a 12 GB
# card has ~1.5 GB left, and training loaded the model and then ran out of memory.
MIN_FREE_GB = 9.5


def check_cuda():
    """Check CUDA availability and GPU info."""
    print("=" * 60)
    print("1. CUDA / GPU Check")
    print("=" * 60)

    try:
        import torch
    except ImportError:
        print("  ERROR: PyTorch is not installed.")
        print("  Install with: pip install torch")
        return False, 0.0

    if not torch.cuda.is_available():
        print("  ERROR: CUDA is not available.")
        print("  Ensure you have an NVIDIA GPU with CUDA drivers installed.")
        return False, 0.0

    gpu_name = torch.cuda.get_device_name(0)
    vram_bytes = torch.cuda.get_device_properties(0).total_memory
    vram_gb = vram_bytes / (1024 ** 3)

    free_gb = torch.cuda.mem_get_info(0)[0] / (1024 ** 3)
    print(f"  GPU:  {gpu_name}")
    print(f"  VRAM: {vram_gb:.1f} GB ({free_gb:.1f} GB free)")

    if free_gb < MIN_FREE_GB:
        print(f"  ERROR: only {free_gb:.1f} GB free; training needs about {MIN_FREE_GB} GB.")
        print("  Something holds the card — usually Ollama with the bot's model loaded.")
        print("  Stop the bot and unload it (ollama stop gemma3:12b), then re-run.")
        return False, vram_gb

    if vram_gb < MIN_VRAM_GB:
        print(f"  ERROR: VRAM ({vram_gb:.1f} GB) is below minimum {MIN_VRAM_GB} GB.")
        print("  A 12B model at 4-bit requires at least 10 GB VRAM.")
        return False, vram_gb
    elif vram_gb < WARN_VRAM_GB:
        print(f"  WARNING: VRAM ({vram_gb:.1f} GB) is under {WARN_VRAM_GB} GB.")
        print("  Training may be tight. If OOM occurs, lower MAX_SEQ_LENGTH in 03_train.py")
        print("  to 768 (and kaia_quality.TRAIN_MAX_TOKENS with it) before reducing LoRA rank.")
        return True, vram_gb
    else:
        print(f"  OK: {vram_gb:.1f} GB VRAM is sufficient.")
        return True, vram_gb


def check_unsloth():
    """Check that unsloth is importable."""
    print()
    print("=" * 60)
    print("2. Unsloth Dependency Check")
    print("=" * 60)

    try:
        import unsloth  # noqa: F401
        print(f"  OK: unsloth is installed (version: {getattr(unsloth, '__version__', 'unknown')})")
        return True
    except ImportError:
        print("  ERROR: unsloth is not installed.")
        print()
        print("  Install with these commands:")
        print('    pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"')
        print("    pip install --no-deps trl peft accelerate bitsandbytes")
        return False


def check_other_deps():
    """Check other required dependencies."""
    print()
    print("=" * 60)
    print("3. Other Dependencies")
    print("=" * 60)

    all_ok = True
    for pkg_name, import_name in [
        ("datasets", "datasets"),
        ("trl", "trl"),
        ("peft", "peft"),
        ("accelerate", "accelerate"),
        ("bitsandbytes", "bitsandbytes"),
        ("transformers", "transformers"),
    ]:
        try:
            __import__(import_name)
            print(f"  OK: {pkg_name}")
        except ImportError:
            print(f"  MISSING: {pkg_name}")
            all_ok = False

    if not all_ok:
        print("  Some dependencies are missing. Install them before training.")

    return all_ok


def check_dataset():
    """Count lines in dataset files."""
    print()
    print("=" * 60)
    print("4. Dataset Check")
    print("=" * 60)

    all_ok = True

    for label, fpath in [("train", TRAIN_FILE), ("eval", EVAL_FILE)]:
        fpath = os.path.abspath(fpath)
        if not os.path.isfile(fpath):
            print(f"  ERROR: {label} file not found: {fpath}")
            print("  Build it: python finetune/01_convert_logs.py --apply")
            all_ok = False
            continue

        with open(fpath, "r", encoding="utf-8") as f:
            count = sum(1 for _ in f)

        print(f"  {label}: {count} examples  ({fpath})")

        if count == 0:
            print(f"  WARNING: {label} file is empty!")
            all_ok = False

    return all_ok


def main():
    print()
    print("Kaia LoRA Fine-Tune — Hardware & Dependency Validation")
    print()

    cuda_ok, vram_gb = check_cuda()
    unsloth_ok = check_unsloth()
    deps_ok = check_other_deps()
    dataset_ok = check_dataset()

    # Summary
    print()
    print("=" * 60)
    print("GO / NO-GO SUMMARY")
    print("=" * 60)

    checks = [
        ("CUDA / GPU", cuda_ok),
        ("Unsloth", unsloth_ok),
        ("Other deps", deps_ok),
        ("Dataset", dataset_ok),
    ]

    all_go = True
    for name, passed in checks:
        status = "GO" if passed else "NO-GO"
        marker = "✓" if passed else "✗"
        print(f"  {marker} {name}: {status}")
        if not passed:
            all_go = False

    print()
    if all_go:
        print("  >>> ALL CHECKS PASSED — READY TO TRAIN <<<")
        if vram_gb < WARN_VRAM_GB:
            print(f"  Note: VRAM is {vram_gb:.1f} GB (tight). Monitor for OOM.")
            print("  First knob to turn: MAX_SEQ_LENGTH 1024 -> 768 in 03_train.py.")
    else:
        print("  >>> ONE OR MORE CHECKS FAILED — DO NOT PROCEED <<<")
        print("  Fix the issues above before running 03_train.py.")

    print()
    sys.exit(0 if all_go else 1)


if __name__ == "__main__":
    main()
