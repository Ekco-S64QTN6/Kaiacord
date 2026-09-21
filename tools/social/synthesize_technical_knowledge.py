#!/usr/bin/env python3
"""Turn the scraped Project 1999 technical forum and wiki into troubleshooting guides.

Four stages: extract a {category, symptom, resolution} triple from each thread,
group by category, consolidate each group with deduplication, write one guide
per category into knowledge_base/troubleshooting/.

Defaults to a dry run — it writes nothing without --apply, because it writes
across the corpus (CLAUDE.md §10; `enrich_kb_metadata.py` had no argument
parsing at all, so probing it with --help rewrote frontmatter on 124 files).

    python tools/social/synthesize_technical_knowledge.py                 # dry run
    python tools/social/synthesize_technical_knowledge.py --limit 40 --apply
    python tools/social/synthesize_technical_knowledge.py --apply         # the lot

Every Ollama call goes through `gpu_memory_manager` at BACKGROUND priority, so
a live chat always wins the GPU (CLAUDE.md §4). It is still a few thousand
inferences; running it with her stopped is kinder.
"""
import argparse
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
from utils.core.frontmatter import dump_frontmatter

WORK_DIR = Path("tools/.tech_scrape_data")
EXTRACTED_FILE = WORK_DIR / "extracted_issues.jsonl"
CHECKPOINT_FILE = WORK_DIR / "synthesis_checkpoint.json"
KB_DIR = Path("knowledge_base/troubleshooting")

DRY_RUN = True          # flipped by --apply
LIMIT = None            # capped by --limit
CONSOLIDATE_ONLY = False  # --consolidate-only: re-run stages 2-4 on existing extractions


async def _guarded_chat(client, model_name, prompt, options, tag):
    """One Ollama call, behind the GPU guard.

    The original called `client.chat` through `asyncio.to_thread` directly, so
    four concurrent 12B inferences competed with live chat for a 12 GB card.
    BACKGROUND priority means this yields to anything the bot is doing.
    """
    from utils.infrastructure.gpu.gpu_manager import gpu_memory_manager, GPUTaskPriority
    return await gpu_memory_manager.run_with_gpu_guard(
        model_name=model_name,
        priority=GPUTaskPriority.BACKGROUND,
        coro=asyncio.to_thread(
            client.chat, model=model_name,
            messages=[{"role": "user", "content": prompt}], options=options),
        task_id=tag,
    )


def strip_model_preamble(text: str) -> str:
    """Drop the assistant chatter around a synthesised section.

    gemma3 opens with "Okay, here's a consolidated and deduplicated guide... I'll
    focus on clarity... Since this is based on only *one* report" and sometimes
    closes by offering to do more. In a knowledge-base document that is not
    commentary, it is retrievable text that reads as fact — and it leaks the
    model's own voice into a corpus her answers are grounded in.

    The prompt asks for `### Heading` sections, so anything before the first
    heading is preamble by construction.
    """
    if not text:
        return text
    m = re.search(r'^#{2,4}\s+\S', text, re.M)
    if m:
        text = text[m.start():]
    # trailing offers of further help
    text = re.sub(
        r'\n+(?:Let me know|Would you like|If you(?:\'d| would) like|I hope this)[^\n]*$',
        '', text.rstrip(), flags=re.I)
    return text.strip()


# The extraction prompt names eight categories; the model supplies variants
# anyway. A 1,194-issue sample produced nine flavours of "UI"
# (UI/Customization, UI/Interface, UI/Cosmetic, UI/Windows, UI/WinEQ2,
# UI/Appearance, UI/Graphics, UI/Installation, UI), three of WinEQ2, plus
# "Antivirus" and "Game Mechanics". Each distinct string becomes its own output
# file, so without folding them the run produces guides containing a single
# issue. Normalising at grouping time costs nothing and needs no re-extraction.
CANONICAL = [
    "Installation", "Login/Password", "WinEQ2", "Audio/Video",
    "Networking/Lag", "Crashing", "Mac/Linux", "UI", "Other",
]


def canonical_category(raw: str) -> str:
    c = (raw or "Other").strip()
    low = c.lower()
    for exact in CANONICAL:
        if low == exact.lower():
            return exact
    # A prefix before the slash is the real category: "UI/Cosmetic" -> UI.
    head = low.split("/", 1)[0].strip()
    aliases = {
        "ui": "UI", "wineq": "WinEQ2", "wineq2": "WinEQ2",
        "install": "Installation", "installation": "Installation",
        "login": "Login/Password", "password": "Login/Password",
        "audio": "Audio/Video", "video": "Audio/Video", "sound": "Audio/Video",
        "graphics": "Audio/Video",
        "network": "Networking/Lag", "networking": "Networking/Lag",
        "lag": "Networking/Lag", "connection": "Networking/Lag",
        "crash": "Crashing", "crashing": "Crashing",
        "mac": "Mac/Linux", "linux": "Mac/Linux",
        "antivirus": "Installation", "firewall": "Networking/Lag",
        "game mechanics": "Other", "performance": "Networking/Lag",
    }
    return aliases.get(head, aliases.get(low, "Other"))


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

    if LIMIT:
        target_files = target_files[:LIMIT]
        print(f"--limit {LIMIT}: taking the {len(target_files)} largest unprocessed files")
    
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
                response = await _guarded_chat(
                    client, model_name, prompt, options, f"techsynth_extract_{i}")

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
                cat = canonical_category(data.get("category")).replace("/", "_").replace(" ", "_")
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
                response = await _guarded_chat(
                    client, model_name, prompt, options,
                    f"techsynth_consolidate_{category}_{i}")
                all_synthesized_sections.append(response['message']['content'].strip())
            except Exception as e:
                print(f"  Error on chunk: {e}")
                
            await asyncio.sleep(1)
            
        if all_synthesized_sections:
            if DRY_RUN:
                print(f"  [dry run] would write {output_file} "
                      f"({len(all_synthesized_sections)} sections from {len(issues)} reports)")
                continue
            readable = category.replace("_", " ")
            keywords = sorted({
                "Project 1999", "EverQuest", "troubleshooting", readable,
                *[w for iss in issues[:40]
                  for w in re.findall(r"[A-Za-z][A-Za-z0-9+#.]{3,}",
                                      str(iss.get("symptom", "")))[:2]],
            })[:14]
            # The project frontmatter schema (CLAUDE.md §10). Without it these
            # land among the 1,508 corpus files carrying no document_type, and
            # tech-support grounding depends on retrieving them well.
            # Through the YAML writer: `readable` is derived from scraped
            # thread titles, so a quote or a colon in it used to break the
            # block, and a broken block is invisible downstream (§10).
            plural = "s" if len(issues) != 1 else ""
            fm = dump_frontmatter({
                "title": f"P99 Troubleshooting — {readable}",
                "category": "Troubleshooting",
                "document_type": "Troubleshooting Guide",
                "summary": (f"Deduplicated fixes for {readable} problems on Project 1999, "
                            f"consolidated from {len(issues)} community "
                            f"report{plural} and wiki pages."),
                "keywords": list(keywords),
            }) + "\n"
            tmp = output_file.with_suffix(".tmp")
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(fm)
                f.write(f"# P99 Troubleshooting: {readable}\n\n")
                f.write(f"Consolidated from {len(issues)} community "
                        f"report{'s' if len(issues) != 1 else ''}.\n\n")
                for section in all_synthesized_sections:
                    cleaned = strip_model_preamble(section)
                    if cleaned:
                        f.write(cleaned + "\n\n---\n\n")
            os.replace(tmp, output_file)      # atomic write, CLAUDE.md §4
            print(f"  Created {output_file.name}")

async def main():
    ensure_dirs()
    # `intelligence.main_model` and `ollama.host` are not keys this project
    # defines — both were silently falling back to defaults that happened to be
    # right. Use the real accessors.
    model_name = config.chat_model
    gpu_manager = OllamaGPUManager(model_name)
    options = gpu_manager.get_gpu_options(for_chat=True)
    client = Client(host=config.get('ollama_host', 'http://localhost:11434'))

    print(f"model: {model_name}   mode: {'DRY RUN (no files written)' if DRY_RUN else 'APPLY'}")

    if not CONSOLIDATE_ONLY:
        await stage1_extract(client, model_name, options)
    else:
        print("--consolidate-only: skipping extraction, using extracted_issues.jsonl")
    grouped = stage2_group()
    if grouped:
        await stage3_and_4_consolidate(client, model_name, options, grouped)

    if DRY_RUN:
        print("\nDry run — nothing written to knowledge_base/troubleshooting/.")
        print("Re-run with --apply to write the guides.")
    else:
        print("\nPipeline complete.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="actually write the guides (default: dry run)")
    ap.add_argument("--limit", type=int, default=None,
                    help="only extract from the N largest unprocessed files")
    ap.add_argument("--consolidate-only", action="store_true",
                    help="skip extraction and rebuild the guides from "
                         "extracted_issues.jsonl (extraction over the whole "
                         "corpus takes hours; this re-runs only stages 2-4)")
    args = ap.parse_args()
    DRY_RUN = not args.apply
    LIMIT = args.limit
    CONSOLIDATE_ONLY = args.consolidate_only
    asyncio.run(main())
