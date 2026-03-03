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

    model_name = config.get('intelligence.main_model', 'qwen3.5:9b')
    gpu_manager = OllamaGPUManager(model_name)
    options = gpu_manager.get_gpu_options(for_chat=True)
    client = Client(host=config.get('ollama.host', 'http://localhost:11434'))

    summaries = []
    print(f"Processing {len(md_files)} logs...")
    print("GPU options:", options)

    # For debugging, let's just do 5 logs first
    # md_files = md_files[:5]

    for i, md_file in enumerate(md_files):
        print(f"[{i+1}/{len(md_files)}] Analyzing: {md_file.name} (Size: {md_file.stat().st_size} bytes)")
        try:
            content = md_file.read_text(encoding='utf-8')
        except Exception as e:
            print(f"  Error reading file: {e}")
            continue
        
        # Take a good chunk (up to 4k chars) to avoid overwhelming context
        sample = content[:4000]
        print(f"  Sample size: {len(sample)} chars")
        
        prompt = (
            "Analyze the following Project 1999 forum thread logs. "
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
                summaries.append(summary)
                print(f"  Found knowledge.")
            else:
                print(f"  No specific data found.")
                
        except Exception as e:
            print(f"  Failed to analyze {md_file.name}: {e}")
        
        # Brief pause between threads
        await asyncio.sleep(1)

    if not summaries:
        print("No technical knowledge could be synthesized.")
        return

    # Consolidate into final cheat sheet
    print("Consolidating final cheat sheet...")
    
    final_cheat_sheet_path = Path("./knowledge_base/Project_1999_Technical_Cheat_Sheet.md")
    
    with open(final_cheat_sheet_path, 'w', encoding='utf-8') as f:
        f.write("# 🛠️ Project 1999 Technical Troubleshooting Cheat Sheet\n\n")
        f.write(f"**Last Updated:** {Path('.').stat().st_mtime}\n")
        f.write("This document is a synthesized guide based on community-vetted solutions from the P99 Technical Discussion forums.\n\n")
        
        for summary in summaries:
            f.write(summary + "\n\n---\n\n")

    print(f"Synthesis Complete! Cheat sheet saved to: {final_cheat_sheet_path}")

if __name__ == "__main__":
    asyncio.run(synthesize_technical_knowledge())
