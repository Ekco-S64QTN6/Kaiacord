# Scripts Directory

This directory is restricted to Bash automation, wrappers, and interactive TUI scripts. 
All Python-based maintenance, diagnostic, and recovery utilities have been moved to the `tools/` directory.

## Active Scripts

| Script | Purpose | Usage |
|:-------|:--------|:------|
| `kaia-tools.sh` | Interactive Whiptail TUI for managing Kaia | `bash scripts/kaia-tools.sh` |
| `run_finetune.sh` | LoRA fine-tune pipeline automation (requires GPU + Unsloth/PEFT) | `./scripts/run_finetune.sh` |

## Dependencies
- **whiptail**: Required for the interactive TUI (`sudo apt install whiptail`).

For Python tools, see [`tools/README.md`](../tools/README.md).
