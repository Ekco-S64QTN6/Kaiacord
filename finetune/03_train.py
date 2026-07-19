#!/usr/bin/env python3
"""
03_train.py — Fine-tune Gemma 3 12B with LoRA using Unsloth + TRL SFTTrainer.

Tuned for a 12 GB VRAM GPU (e.g. RTX 3060) with 30 GB system RAM.

If OOM occurs:
  1. FIRST: reduce max_seq_length from 2048 → 1024  (line ~35)
  2. Do NOT reduce LoRA rank — r=16 is already minimal for quality.
"""

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
MAX_SEQ_LENGTH = 512    # Reduced from 1024 to 512 to save ~1.5GB VRAM (longest example is ~350 tokens)
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
    texts = []
    for messages in examples["messages"]:
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
        texts.append(text)
    return {"text": texts}


def main():
    # Verify dataset files exist
    for fpath in [TRAIN_FILE, EVAL_FILE]:
        if not os.path.isfile(fpath):
            print(f"ERROR: Dataset file not found: {fpath}")
            print("Run 01_convert_logs.py first.")
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
        local_files_only=False, # Allow downloading missing weight files
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

    # Apply chat template formatting
    dataset = dataset.map(
        lambda examples: formatting_func(examples, tokenizer),
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
        warmup_steps=10,
        num_train_epochs=6,                  # Increased epochs from 4 to 6
        learning_rate=2e-4,                  # Increased learning rate from 2e-5 to 2e-4
        fp16=False,
        bf16=True,                           # RTX 3060 supports bf16
        logging_steps=10,
        eval_strategy="steps",               # Enable step-based evaluation
        eval_steps=20,                       # Evaluate every 20 steps
        save_strategy="steps",
        save_steps=50,                       # Save checkpoints every 50 steps
        output_dir=CHECKPOINT_DIR,
        optim="adamw_8bit",                  # 8-bit optimizer saves ~2 GB
        weight_decay=0.01,
        lr_scheduler_type="cosine",
        seed=42,
        dataloader_num_workers=0,            # Avoid multiprocessing issues
        dataset_text_field="text",
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset["train"],
        eval_dataset=dataset["eval"],
        args=training_args,
        max_seq_length=MAX_SEQ_LENGTH,
    )

    # Run training
    # Automatically resume from checkpoint if available
    latest_checkpoint = None
    if os.path.isdir(CHECKPOINT_DIR):
        checkpoints = [d for d in os.listdir(CHECKPOINT_DIR) if d.startswith("checkpoint-")]
        if checkpoints:
            latest_checkpoint = os.path.join(CHECKPOINT_DIR, sorted(checkpoints, key=lambda x: int(x.split("-")[1]))[-1])
            print(f"Resuming from: {latest_checkpoint}")

    train_result = trainer.train(resume_from_checkpoint=latest_checkpoint)

    # -----------------------------------------------------------------
    # 5. Save adapter — Save BEFORE evaluation to ensure work is kept
    # -----------------------------------------------------------------
    print(f"\nSaving LoRA adapter to: {OUTPUT_DIR}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
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
