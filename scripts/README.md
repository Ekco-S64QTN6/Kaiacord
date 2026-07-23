# Scripts Directory

This directory is restricted to Bash automation, wrappers, and interactive TUI scripts. 
All Python-based maintenance, diagnostic, and recovery utilities have been moved to the `tools/` directory.

## Active Scripts

| Script | Purpose | Usage |
|:-------|:--------|:------|
| `kaia-tools.sh` | Interactive Whiptail TUI for managing Kaia | `bash scripts/kaia-tools.sh` |
| `run_finetune.sh` | LoRA fine-tune pipeline automation | `./scripts/run_finetune.sh` |
| `run_jspace_probe.sh` | Behavioral & J-Space probe battery runner | `./scripts/run_jspace_probe.sh full` |
| `fix_kaia_style.py` | Persona style sanitization and em-dash cleanup | `python3 scripts/fix_kaia_style.py` |

## Dependencies
- **whiptail**: Required for the interactive TUI (`sudo apt install whiptail`).

For Python tools, see [`tools/README.md`](../tools/README.md).
