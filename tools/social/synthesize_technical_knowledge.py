#!/usr/bin/env python3
import asyncio
import os
import json
from pathlib import Path
import sys

# Add project root to path
sys.path.append(os.getcwd())

from ollama import Client
from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
from utils.infrastructure.system.yaml_config import config
from utils.infrastructure.logging.kaia_logger import log_info, log_error

WORK_DIR = Path("tools/.tech_scrape_data")
CHECKPOINT_FILE = WORK_DIR / "synthesis_checkpoint.json"

def ensure_work_dir():
    WORK_DIR.mkdir(parents=True, exist_ok=True)

def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_checkpoint(data):
    ensure_work_dir()
    tmp = CHECKPOINT_FILE.with_suffix('.tmp')
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, CHECKPOINT_FILE)

async def synthesize_technical_knowledge():
    print("--- Synthesizing Technical Knowledge ---")
    
    technical_dir = Path("./knowledge_base/forum_posts/technical")
    if not technical_dir.exists():
        print("Technical knowledge directory not found.")
        return

    md_files = list(technical_dir.glob("*.md"))
    if not md_files:
        print("No technical logs found to synthesize.")
        return

    checkpoint_data = load_checkpoint()
    unprocessed_files = [f for f in md_files if f.name not in checkpoint_data]

    if not unprocessed_files:
        print("All technical logs have already been synthesized!")
        return

    model_name = config.get('intelligence.main_model', 'gemma3:12b')
    gpu_manager = OllamaGPUManager(model_name)
    options = gpu_manager.get_gpu_options(for_chat=True)
    client = Client(host=config.get('ollama.host', 'http://localhost:11434'))

    print(f"Processing {len(unprocessed_files)} new logs (out of {len(md_files)} total)...")
    print("GPU options:", options)

    final_cheat_sheet_path = Path("./knowledge_base/Project_1999_Technical_Cheat_Sheet.md")
    
    # Initialize the file if it doesn't exist
    if not final_cheat_sheet_path.exists():
        with open(final_cheat_sheet_path, 'w', encoding='utf-8') as f:
            f.write("# 🛠️ Project 1999 Technical Troubleshooting Cheat Sheet\n\n")
            f.write("This document is a synthesized guide based on community-vetted solutions from the P99 Technical Discussion forums and Wiki.\n\n")

    for i, md_file in enumerate(unprocessed_files):
        print(f"\n[{i+1}/{len(unprocessed_files)}] Analyzing: {md_file.name} (Size: {md_file.stat().st_size} bytes)")
        try:
            content = md_file.read_text(encoding='utf-8')
        except Exception as e:
            print(f"  Error reading file: {e}")
            checkpoint_data[md_file.name] = "ERROR_READING_FILE"
            save_checkpoint(checkpoint_data)
            continue
        
        # Take a good chunk (up to 4k chars) to avoid overwhelming context
        sample = content[:4000]
        
        prompt = (
            "Analyze the following Project 1999 forum thread or wiki page. "
            "Extract Technical Problems and their Solutions.\n\n"
            "FORMAT:\n"
            "### [Problem Description]\n"
            "- **Symptom**: ...\n"
            "- **Resolution**: ...\n\n"
            "If no clear problem/resolution exists, respond with 'NO_DATA'.\n\n"
            "LOGS:\n"
            f"{sample}\n\n"
            "EXTRACTION:"
        )

        try:
            response = await asyncio.to_thread(
                client.chat,
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                options=options
            )
            
            summary = response['message']['content'].strip()
            if "NO_DATA" not in summary:
                print(f"  Found knowledge.")
                
                # Append to cheat sheet immediately
                with open(final_cheat_sheet_path, 'a', encoding='utf-8') as f:
                    f.write(summary + "\n\n---\n\n")
                
                checkpoint_data[md_file.name] = "SYNTHESIZED"
            else:
                print(f"  No specific data found.")
                checkpoint_data[md_file.name] = "NO_DATA"
                
        except Exception as e:
            print(f"  Failed to analyze {md_file.name}: {e}")
            checkpoint_data[md_file.name] = f"ERROR: {e}"
        
        save_checkpoint(checkpoint_data)
        
        # Brief pause between threads
        await asyncio.sleep(1)

    print(f"\nSynthesis Complete! Cheat sheet updated at: {final_cheat_sheet_path}")

if __name__ == "__main__":
    asyncio.run(synthesize_technical_knowledge())
