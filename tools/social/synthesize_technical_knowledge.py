#!/usr/bin/env python3
import asyncio
import os
import json
import re
from pathlib import Path
import sys

# Add project root to path
sys.path.append(os.getcwd())

from ollama import Client
from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
from utils.infrastructure.system.yaml_config import config

WORK_DIR = Path("tools/.tech_scrape_data")
EXTRACTED_FILE = WORK_DIR / "extracted_issues.jsonl"
CHECKPOINT_FILE = WORK_DIR / "synthesis_checkpoint.json"
KB_DIR = Path("knowledge_base/troubleshooting")

def ensure_dirs():
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    KB_DIR.mkdir(parents=True, exist_ok=True)

def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_checkpoint(data):
    ensure_dirs()
    tmp = CHECKPOINT_FILE.with_suffix('.tmp')
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, CHECKPOINT_FILE)

def parse_json_from_llm(content: str) -> dict:
    content = content.strip()
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
        
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None

async def stage1_extract(client, model_name, options):
    print("\n--- STAGE 1: Extraction & Categorization (Parallel & Comprehensive) ---")
    technical_dir = Path("./knowledge_base/forum_posts/technical")
    if not technical_dir.exists():
        print("Technical knowledge directory not found.")
        return

    md_files = list(technical_dir.glob("*.md"))
    if not md_files:
        print("No technical logs found to synthesize.")
        return

    # Include wiki files
    wiki_dir = Path("./knowledge_base/wiki")
    if wiki_dir.exists():
        md_files.extend(list(wiki_dir.glob("*.md")))

    checkpoint_data = load_checkpoint()
    
    # Process ALL unprocessed files without any post-count or keyword filters!
    # A single post is still an extremely valuable technical question to learn from.
    target_files = [f for f in md_files if f.name not in checkpoint_data]

    if not target_files:
        print("Stage 1 complete! All files extracted.")
        return

    # Sort files by size so larger, more detailed files are processed first
    target_files.sort(key=lambda x: x.stat().st_size, reverse=True)
    
    print(f"Processing {len(target_files)} remaining files for synthesis...")

    # We use a semaphore of 4 to process in parallel
    semaphore = asyncio.Semaphore(4)
    lock = asyncio.Lock()

    async def process_file(i, md_file):
        async with semaphore:
            print(f"[{i+1}/{len(target_files)}] Analyzing: {md_file.name}")
            try:
                content = md_file.read_text(encoding='utf-8')
            except Exception as e:
                print(f"  Error reading file: {e}")
                async with lock:
                    checkpoint_data[md_file.name] = "ERROR_READING_FILE"
                    save_checkpoint(checkpoint_data)
                return

            sample = content[:4000]
            
            prompt = (
                "Analyze the following Project 1999 forum thread or wiki page. "
                "Extract the primary technical problem and its solution.\n\n"
                "OUTPUT FORMAT:\n"
                "Respond ONLY with a valid JSON object. No other text.\n"
                "{\n"
                '  "category": "One of: Installation, Login/Password, WinEQ2, Audio/Video, Networking/Lag, Crashing, Mac/Linux, Other",\n'
                '  "symptom": "Brief description of the problem",\n'
                '  "resolution": "Step-by-step fix or final conclusion"\n'
                "}\n\n"
                "If no clear problem/resolution exists, respond with:\n"
                '{"category": "NO_DATA"}\n\n'
                "LOGS:\n"
                f"{sample}\n"
            )

            try:
                response = await asyncio.to_thread(
                    client.chat,
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    options=options
                )
                
                summary = response['message']['content'].strip()
                data = parse_json_from_llm(summary)
                
                async with lock:
                    if data and data.get("category") and data.get("category") != "NO_DATA":
                        data["source"] = md_file.name
                        with open(EXTRACTED_FILE, 'a', encoding='utf-8') as f:
                            f.write(json.dumps(data) + "\n")
                        print(f"  ✓ Extracted: {data.get('category')} -> {md_file.name}")
                        checkpoint_data[md_file.name] = "SYNTHESIZED"
                    else:
                        print(f"  ✗ No clear data in: {md_file.name}")
                        checkpoint_data[md_file.name] = "NO_DATA"
            except Exception as e:
                print(f"  Failed to analyze {md_file.name}: {e}")
                async with lock:
                    checkpoint_data[md_file.name] = f"ERROR: {e}"
            
            async with lock:
                save_checkpoint(checkpoint_data)

    tasks = [process_file(i, f) for i, f in enumerate(target_files)]
    await asyncio.gather(*tasks)

def stage2_group():
    print("\n--- STAGE 2: Grouping Issues ---")
    if not EXTRACTED_FILE.exists():
        print("No extracted issues found.")
        return {}
        
    grouped = {}
    count = 0
    with open(EXTRACTED_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                data = json.loads(line)
                cat = data.get("category", "Other").replace("/", "_").replace(" ", "_")
                if cat not in grouped:
                    grouped[cat] = []
                grouped[cat].append(data)
                count += 1
            except Exception:
                pass
                
    print(f"Grouped {count} issues into {len(grouped)} categories: {list(grouped.keys())}")
    return grouped

async def stage3_and_4_consolidate(client, model_name, options, grouped_issues):
    print("\n--- STAGE 3 & 4: Deduplication & Generation ---")
    
    for category, issues in grouped_issues.items():
        output_file = KB_DIR / f"Troubleshooting_{category}.md"
        
        chunk_size = 20
        all_synthesized_sections = []
        
        print(f"Consolidating {len(issues)} issues for category: {category}")
        
        for i in range(0, len(issues), chunk_size):
            chunk = issues[i:i+chunk_size]
            
            prompt_data = ""
            for idx, issue in enumerate(chunk):
                prompt_data += f"Issue {idx+1}:\nSymptom: {issue.get('symptom')}\nResolution: {issue.get('resolution')}\n\n"
            
            prompt = (
                f"You are a technical editor for Project 1999 troubleshooting.\n"
                f"Here are {len(chunk)} raw reports about {category}. Many are duplicates.\n"
                "Consolidate them into a definitive, deduplicated guide. "
                "Merge overlapping solutions, list step-by-step fixes, and remove noise.\n"
                "Format using markdown headings (### [Specific Issue Name]) and bullet points.\n\n"
                "REPORTS:\n"
                f"{prompt_data}\n"
            )
            
            print(f"  Processing chunk {i//chunk_size + 1}/{(len(issues)-1)//chunk_size + 1}...")
            try:
                response = await asyncio.to_thread(
                    client.chat,
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    options=options
                )
                all_synthesized_sections.append(response['message']['content'].strip())
            except Exception as e:
                print(f"  Error on chunk: {e}")
                
            await asyncio.sleep(1)
            
        if all_synthesized_sections:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"# 🛠️ P99 Troubleshooting: {category}\n\n")
                f.write(f"Source: Extracted and deduplicated from {len(issues)} community reports.\n\n")
                for section in all_synthesized_sections:
                    f.write(section + "\n\n---\n\n")
            print(f"  Created {output_file.name}")

async def main():
    ensure_dirs()
    model_name = config.get('intelligence.main_model', 'gemma3:12b')
    gpu_manager = OllamaGPUManager(model_name)
    options = gpu_manager.get_gpu_options(for_chat=True)
    client = Client(host=config.get('ollama.host', 'http://localhost:11434'))

    await stage1_extract(client, model_name, options)
    grouped = stage2_group()
    if grouped:
        await stage3_and_4_consolidate(client, model_name, options, grouped)
        
    print("\n✅ Pipeline Complete!")

if __name__ == "__main__":
    asyncio.run(main())
