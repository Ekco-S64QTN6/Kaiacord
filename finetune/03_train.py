#!/usr/bin/env python3
"""
03_train.py — Fine-tune Gemma 3 12B with LoRA using Unsloth + TRL SFTTrainer.

Tuned for a 12 GB VRAM GPU (e.g. RTX 3060) with 30 GB system RAM.

    python finetune/03_train.py            # a fresh run
    python finetune/03_train.py --resume   # continue the newest checkpoint

If OOM occurs, lower MAX_SEQ_LENGTH to 768 before touching LoRA rank (and the
builder's window with it: kaia_quality.TRAIN_MAX_TOKENS).
"""

import argparse
import os
import sys

# Critical for tight VRAM (12GB) to avoid fragmentation
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True"

from unsloth import FastLanguageModel
from datasets import load_dataset
from trl import SFTTrainer, SFTConfig

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRAIN_FILE = os.path.join(SCRIPT_DIR, "dataset", "train.jsonl")
EVAL_FILE = os.path.join(SCRIPT_DIR, "dataset", "eval.jsonl")
CHECKPOINT_DIR = os.path.join(SCRIPT_DIR, "checkpoints")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output", "kaia_lora_adapter")

# ---------------------------------------------------------------------------
# Model Configuration
# ---------------------------------------------------------------------------

MODEL_NAME = "unsloth/gemma-3-12b-it-bnb-4bit"
# Kept equal to kaia_quality.TRAIN_MAX_TOKENS: the builder never writes an
# example longer than this, measured in real tokens on the rendered template,
# so nothing is truncated mid-target. 512 once truncated 23% of examples.
MAX_SEQ_LENGTH = 1024
DTYPE = None            # Auto-detect
LOAD_IN_4BIT = True

# ---------------------------------------------------------------------------
# LoRA Configuration — tuned for 12 GB VRAM
# ---------------------------------------------------------------------------

LORA_R = 32              # Increased from 16 to 32 for higher identity-learning capacity
LORA_ALPHA = 64          # Scaled accordingly (alpha = 2 * r)
LORA_DROPOUT = 0         # Optimized for Unsloth fast patching
LORA_TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]


def formatting_func(examples, tokenizer):
    """Apply chat template to format messages arrays for training."""
    # The chat template already writes <bos>, and the trainer adds its own when
    # it tokenizes the text: without removeprefix every sequence starts with two.
    texts = []
    for messages in examples["messages"]:
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
        # And the template ends on "<end_of_turn>\n" while the tokenizer's EOS is
        # <end_of_turn>, so TRL appends a second one after the newline and every
        # reply is trained to end "<end_of_turn>\n<end_of_turn>". Ending on the
        # EOS itself stops that. (Both checked on every example of the dataset.)
        texts.append(text.removeprefix(tokenizer.bos_token or "<bos>").rstrip("\n"))
    return {"text": texts}


def write_run_record(trainer, training_args):
    """What produced this adapter, next to it: the dataset (by hash, with the
    builder's report), the settings, the library versions and the eval-loss
    curve. A 05c score means little without knowing which data and which run
    it belongs to."""
    import hashlib
    import importlib.metadata as md
    import json

    def sha(path):
        return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16] if os.path.isfile(path) else None

    report = os.path.join(SCRIPT_DIR, "dataset", "build_report.json")
    record = {
        "model": MODEL_NAME,
        "dataset": {"train_sha256": sha(TRAIN_FILE), "eval_sha256": sha(EVAL_FILE),
                    "build_report": json.load(open(report)) if os.path.isfile(report) else None},
        "lora": {"r": LORA_R, "alpha": LORA_ALPHA, "dropout": LORA_DROPOUT,
                 "target_modules": LORA_TARGET_MODULES},
        "training": {k: getattr(training_args, k) for k in (
            "learning_rate", "num_train_epochs", "per_device_train_batch_size",
            "gradient_accumulation_steps", "warmup_ratio", "lr_scheduler_type", "weight_decay",
            "max_length", "seed")},
        "best_checkpoint": trainer.state.best_model_checkpoint,
        "best_eval_loss": trainer.state.best_metric,
        "steps": trainer.state.global_step,
        "eval_loss": [(h["step"], h["eval_loss"]) for h in trainer.state.log_history if "eval_loss" in h],
        "versions": {p: md.version(p) for p in ("unsloth", "trl", "transformers", "peft", "torch")},
    }
    with open(os.path.join(OUTPUT_DIR, "run.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, default=str)
    print(f"Run record: {os.path.join(OUTPUT_DIR, 'run.json')}")


def main():
    ap = argparse.ArgumentParser(description="Train the Kaia persona LoRA.")
    ap.add_argument("--resume", action="store_true",
                    help="continue from the newest checkpoint in finetune/checkpoints/")
    args = ap.parse_args()

    # Verify dataset files exist
    for fpath in [TRAIN_FILE, EVAL_FILE]:
        if not os.path.isfile(fpath):
            print(f"ERROR: Dataset file not found: {fpath}")
            print("Build it: python finetune/01_convert_logs.py --apply")
            sys.exit(1)

    # The gate run_finetune.sh applies, so running this script directly cannot
    # train on a dataset that fails it.
    import subprocess
    if subprocess.run([sys.executable, os.path.join(SCRIPT_DIR, "01f_check_dataset.py")]).returncode:
        print("ERROR: the dataset check failed; rebuild with 01_convert_logs.py --apply.")
        sys.exit(1)

    # -----------------------------------------------------------------
    # 1. Load model
    # -----------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"Loading model: {MODEL_NAME}")
    print(f"max_seq_length={MAX_SEQ_LENGTH}, load_in_4bit={LOAD_IN_4BIT}")
    print(f"{'='*60}\n")

    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=DTYPE,
        load_in_4bit=LOAD_IN_4BIT,
        device_map={"": 0}, # Force all modules to GPU 0
        local_files_only=True, # Prevent telemetry/hangs by forcing local weights
    )

    # -----------------------------------------------------------------
    # 2. Apply LoRA
    # -----------------------------------------------------------------
    print(f"\nApplying LoRA adapter (r={LORA_R}, alpha={LORA_ALPHA})")

    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_R,
        target_modules=LORA_TARGET_MODULES,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        use_gradient_checkpointing="unsloth",   # Critical for 12 GB
        random_state=42,
    )

    # -----------------------------------------------------------------
    # 3. Load & format dataset
    # -----------------------------------------------------------------
    print(f"\nLoading datasets...")

    dataset = load_dataset(
        "json",
        data_files={
            "train": TRAIN_FILE,
            "eval": EVAL_FILE,
        },
    )

    print(f"  Train: {len(dataset['train'])} examples")
    print(f"  Eval:  {len(dataset['eval'])} examples")

    # For Gemma 3 Unsloth can hand back a multimodal processor; the chat
    # template, the tokenization and TRL's text path all want the text
    # tokenizer inside it (TRL treats a processor as a vision model).
    text_tokenizer = getattr(tokenizer, "tokenizer", tokenizer)

    # Apply chat template formatting
    dataset = dataset.map(
        lambda examples: formatting_func(examples, text_tokenizer),
        batched=True,
        remove_columns=dataset["train"].column_names,
    )

    # -----------------------------------------------------------------
    # 4. Training
    # -----------------------------------------------------------------
    print(f"\nStarting training...")

    training_args = SFTConfig(
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,        # Batch size 1 prevents evaluation OOM on 12GB VRAM
        gradient_accumulation_steps=8,       # Effective batch = 8
        # A ratio, not a step count: a fixed count becomes a different share of
        # the run every time the dataset changes size.
        warmup_ratio=0.05,
        num_train_epochs=6,                  # a ceiling: early stopping and the best checkpoint decide
        learning_rate=2e-4,
        fp16=False,
        bf16=True,                           # RTX 3060 supports bf16
        logging_steps=10,
        eval_strategy="steps",               # Enable step-based evaluation
        eval_steps=20,                       # Evaluate every 20 steps
        save_strategy="steps",
        save_steps=20,                       # Must match eval_steps for best-model tracking
        # Six epochs at 2e-4 on about a thousand targets overfits well before the
        # end; the lowest-eval-loss checkpoint is restored before saving.
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        save_total_limit=3,                  # Keep the disk footprint bounded
        output_dir=CHECKPOINT_DIR,
        optim="adamw_8bit",                  # 8-bit optimizer saves ~2 GB
        weight_decay=0.01,
        lr_scheduler_type="cosine",
        seed=42,
        dataloader_num_workers=0,            # Avoid multiprocessing issues
        dataset_text_field="text",
        max_length=MAX_SEQ_LENGTH,           # TRL >= 0.20 reads the window from the config
    )

    trainer = SFTTrainer(
        model=model,
        processing_class=text_tokenizer,     # `tokenizer=` was removed from TRL
        train_dataset=dataset["train"],
        eval_dataset=dataset["eval"],
        args=training_args,
    )

    # Compute loss on Kaia's turns only.
    #
    # Without this the model is also trained to predict the *user* turns, which
    # spends capacity learning to imitate Ekco and Starkind — and on a dataset
    # this size that capacity is the scarce resource. The goal is that the model
    # *is* Kaia, so only Kaia's tokens should carry gradient.
    try:
        from unsloth.chat_templates import train_on_responses_only
        trainer = train_on_responses_only(
            trainer,
            instruction_part="<start_of_turn>user\n",
            response_part="<start_of_turn>model\n",
        )
        print("Loss masked to assistant turns only (train_on_responses_only).")
    except Exception as e:
        # Not a warning: unmasked, the run fits Ekco's and Starkind's turns as
        # well as hers, which is a different model from the one intended.
        print(f"ERROR: could not mask the user turns ({e}). Stopping.")
        sys.exit(1)

    # Stop when eval loss has not improved for three evaluations. With
    # load_best_model_at_end the best checkpoint is still what gets exported,
    # so this only saves wall-clock time and reduces overfitting risk.
    try:
        from transformers import EarlyStoppingCallback
        trainer.add_callback(EarlyStoppingCallback(early_stopping_patience=3))
    except Exception as e:
        print(f"WARNING: early stopping unavailable ({e})")

    # Resume only when asked. Checkpoints left by an earlier run belong to an
    # earlier dataset; resuming one silently continues that run's optimizer and
    # schedule on different data.
    latest_checkpoint = None
    checkpoints = ([d for d in os.listdir(CHECKPOINT_DIR) if d.startswith("checkpoint-")]
                   if os.path.isdir(CHECKPOINT_DIR) else [])
    if args.resume and checkpoints:
        latest_checkpoint = os.path.join(CHECKPOINT_DIR, sorted(checkpoints, key=lambda x: int(x.split("-")[1]))[-1])
        print(f"Resuming from: {latest_checkpoint}")
    elif checkpoints:
        print(f"ERROR: {CHECKPOINT_DIR} holds checkpoints from an earlier run. Pass --resume to "
              "continue it, or delete them to start fresh on the current dataset.")
        sys.exit(1)

    train_result = trainer.train(resume_from_checkpoint=latest_checkpoint)

    # -----------------------------------------------------------------
    # 5. Save adapter — Save BEFORE evaluation to ensure work is kept
    # -----------------------------------------------------------------
    print(f"\nSaving LoRA adapter to: {OUTPUT_DIR}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    write_run_record(trainer, training_args)
    print("Done! Adapter saved successfully.")

    # -----------------------------------------------------------------
    # 6. Evaluation (Optional, can OOM on tight VRAM)
    # -----------------------------------------------------------------
    try:
        print(f"\nRunning final evaluation...")
        eval_metrics = trainer.evaluate()
        for k, v in sorted(eval_metrics.items()):
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"\nEvaluation failed or skipped (likely OOM): {e}")
        print("This is normal on tight VRAM (12GB). Your training is still valid!")

    print(f"\nNext step: run 04_merge_export.py to merge and export to GGUF.")


if __name__ == "__main__":
    main()
