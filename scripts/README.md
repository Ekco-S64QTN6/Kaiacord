# Kaiacord Shell Scripts & Automation Wrappers

Executive shell automation, interactive TUI, and pipeline execution wrappers for Kaiacord.

---

## 📁 Active Scripts Overview

| Script | Type | Purpose | Execution |
|:-------|:-----|:--------|:----------|
| [kaia-tools.sh](file:///home/ekco/github/Kaiacord/scripts/kaia-tools.sh) | Interactive TUI | Terminal interface for system monitoring, Ollama server control, RAG reindexing, and knowledge base maintenance | `bash scripts/kaia-tools.sh` |
| [run_finetune.sh](file:///home/ekco/github/Kaiacord/scripts/run_finetune.sh) | Pipeline | 4-step LoRA fine-tuning automation (hardware audit, training, adapter merge, Ollama GGUF export & validation) | `./scripts/run_finetune.sh` |
| [run_jspace_probe.sh](file:///home/ekco/github/Kaiacord/scripts/run_jspace_probe.sh) | Diagnostic Wrapper | Executes offline J-Space behavioral probe batteries and user log replays | `./scripts/run_jspace_probe.sh full` |

---

## 🛠️ Detailed Script Descriptions

### 1. `kaia-tools.sh` — Interactive Whiptail TUI
The primary operational control menu for Kaiacord administrators. Provides menu-driven access to:
- **System & Bot Control:** Process state check, log tailing, channel memory clearing (`memory/bot_state.json`), startup troubleshooting.
- **Ollama Management:** Unload model VRAM, systemctl restart/stop/start, and journalctl log inspection.
- **RAG Operations:** Incremental reindexing (`.trigger_reindex`), single-file reindexing, and full storage rebuilds (`reindex_rag.py --clear`).
- **Knowledge Base Utilities:** OCR artifact cleaning, log sanitization, user profile generation, and Project 1999 forum support synthesis.

**Prerequisites:**
```bash
sudo apt install whiptail
```

### 2. `run_finetune.sh` — LoRA Fine-Tuning Automation
Orchestrates the 4-phase LLM fine-tuning pipeline:
1. **Pre-flight & Hardware Audit:** Scans dataset for token length outliers (`01d_scan_length_outliers.py`) and validates GPU VRAM (`02_check_hardware.py`).
2. **LoRA Training:** Executes adapter training via Unsloth/PyTorch (`03_train.py`).
3. **Merge & Export:** Merges LoRA weights and exports GGUF quantization (`04_merge_export.py`).
4. **Ollama Deployment & Validation:** Creates `kaia-lora` model in Ollama (`Modelfile`) and executes validation benchmarks (`05b_test_ollama.py`).

### 3. `run_jspace_probe.sh` — Behavioral & J-Space Probe Wrapper
Executes offline behavioral probe batteries to measure persona adherence and linguistic distribution:
```bash
# Run full static battery and real user log replays
./scripts/run_jspace_probe.sh full

# Run static probe battery only
./scripts/run_jspace_probe.sh static-only --model gemma3:12b

# Replay specific user interaction logs
./scripts/run_jspace_probe.sh replay-only --limit 20
```

---

## 📌 Related References
- Python maintenance, diagnostic, and recovery tools: [`tools/README.md`](../tools/README.md)
